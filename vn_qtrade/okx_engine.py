
""""""

import importlib
import sys
import traceback
from typing import Sequence, Any
from pathlib import Path
from datetime import datetime, timezone
import time
import threading
import signal
from threading import Thread
from functools import partial
import atexit
from dataclasses import dataclass, field

import pandas as pd
from pandas import DataFrame

from vnpy_evo.event import Event, EventEngine
from vnpy_evo.trader.engine import BaseEngine, MainEngine
from vnpy_evo.trader.constant import Direction, Offset, OrderType, Interval
from vnpy_evo.trader.object import (
    OrderRequest,
    HistoryRequest,
    SubscribeRequest,
    TickData,
    OrderData,
    TradeData,
    PositionData,
    AccountData,
    ContractData,
    LogData,
    BarData
)
from vnpy_evo.trader.event import (
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION
)
from vn_qtrade.ai_trade.base import EVENT_AI_SIGNAL
from vnpy_evo.trader.constant import (
    Direction,
    OrderType,
    Interval,
    Exchange,
    Offset,
    Status
)

from vnpy_evo.trader.utility import load_json, save_json, extract_vt_symbol, round_to
from concurrent.futures import ThreadPoolExecutor
from .base import CryptoEngineBase

from copy import copy
from tzlocal import get_localzone

import inspect 


import ccxt

APP_NAME = "CryptoTrader"

EVENT_CRYPTO_LOG = "eCryptoLog"


@dataclass
class TTOrder:
    vt_symbol: str
    direction: Direction
    offset: Offset
    price: float
    volume: float
    datetime: datetime
    lock: bool = False
    net: bool = False
    vt_orderids: list = field(default_factory=list)


class OKXEngine(CryptoEngineBase):
    def __init__(self, main_engine: MainEngine, event_engine: EventEngine, terminal:bool=True):
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)
        self.ccxt = None
        self.init_ccxt()

        self.sltp_cfg = {}  # should be {vt-symbol: config}
        self.default_sl = -0.35
        self.default_tp = 1.55
        self.trigger_trigger_orders = {} # tto
        self.tp_with_trigger = True # take profit using trigger orders
        self.max_tp = 1

        self.tp_trigger_orders = {}
        self.last_position = {}
        self.offset = 0.1
        self.cancel_tp = True

        self.register_event()

        self.last_tick = {}
        self._pause = False

    def init_ccxt(self):
        okx_gw = self.main_engine.gateways.get('OKX')
        if okx_gw:
            self.ccxt = ccxt.okx(
                {
                    'enableRateLimit': True,
                    'apiKey': okx_gw.key,
                    'secret': okx_gw.secret,
                    'password': okx_gw.passphrase,
                    # 'verbose': True,  # for debug output
            }
            )
            if okx_gw.proxy_host:
                self.ccxt.proxies = {
                    'http': f'http://{okx_gw.proxy_host}:{okx_gw.proxy_port}',
                    'https': f'http://{okx_gw.proxy_host}:{okx_gw.proxy_port}'
                }

    def register_event(self):
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)
        self.event_engine.register(EVENT_POSITION, self.process_position_event)
        # Register AI signal event listener
        self.event_engine.register(EVENT_AI_SIGNAL, self.process_ai_signal_event)

    def process_tick_event(self, event: Event):
        """"""
        tick = event.data
        self.last_tick[tick.vt_symbol] = tick
        self.check_latency(tick)
        try:
            self.check_trigger_trigger_order(tick)
        except Exception as e:
            self.write_log(f'tick error {e}')

    def check_latency(self, tick: TickData):
        """
        Checks the latency between the tick timestamp and the current time.
        """
        now = datetime.now(timezone.utc)

        # OKX sends UTC time, but the datetime object is naive. Attach timezone info.
        aware_tick_datetime = tick.datetime.replace(tzinfo=timezone.utc)

        latency = now - aware_tick_datetime
        latency_ms = latency.total_seconds() * 1000
        self.write_log(f"Market data latency for {tick.vt_symbol}: {latency_ms:.2f} ms")

    def pause(self):
        if self._pause is False:
            self._pause = True

    def resume(self):
        if self._pause is True:
            self._pause = False

    def process_order_event(self, event: Event):
        """"""
        order = event.data
        self.write_log(f'received order event: {order}')

    def process_trade_event(self, event: Event):
        """"""
        trade = event.data
        self.write_log(f'received trade event: {trade}')

    def process_position_event(self, event: Event):
        """"""
        position = event.data
        try:
            if self._pause is False:
                self.check_sl_tp(position)
        except Exception as e:
            self.write_log(f'position error {e}')
        self.last_position[position.vt_symbol] = position

    def process_ai_signal_event(self, event: Event):
        """
        Process AI-generated trading signals.

        This method is triggered when AIAgentEngine emits an EVENT_AI_SIGNAL.
        It executes the trading action recommended by the LLM.
        """
        signal = event.data

        try:
            self.write_log(f"Received AI Signal: {signal.vt_symbol} {signal.direction.value} {signal.volume} @ {signal.price}")
            self.write_log(f"AI Rationale: {signal.rationale}")

            # Execute the trade based on signal
            if signal.direction == Direction.LONG:
                # Buy to open long position or close short position
                order_id = self.buy(signal.vt_symbol, signal.price, signal.volume)
            else:
                # Sell to open short position or close long position
                order_id = self.sell(signal.vt_symbol, signal.price, signal.volume)

            if order_id:
                self.write_log(f"AI trade executed successfully: {order_id}")
            else:
                self.write_log(f"AI trade failed to execute")

        except Exception as e:
            self.write_log(f"Error processing AI signal: {e}")
            self.write_log(f"Signal details: {signal}")

    def set_lever(self, vt_symbol, lever):
        symbol, exchange_name = extract_vt_symbol(vt_symbol)
        params = {
            'instId': symbol,
            'mgnMode': 'cross',
            'lever': lever
        }
        try:
            data = self.ccxt.private_post_account_set_leverage(params=params)
            return data
        except Exception as e:
            self.write_log(f'set level error {e}')


    def set_sl(self, vt_symbol, sl):
        self.sltp_cfg[vt_symbol]['stoploss'] = sl
        self.set_trigger_cover_positions(vt_symbol=vt_symbol)

    def set_all_sl(self, sl):
        for (k, v) in self.sltp_cfg.items():
            self.sltp_cfg[k]['stoploss'] = sl
        self.set_trigger_cover_positions()

    def set_tp(self, vt_symbol, tp):
        self.sltp_cfg[vt_symbol]['takeprofit'] = tp
        self.set_trigger_cover_positions(vt_symbol=vt_symbol)

    def set_all_tp(self, tp):
        for (k, v) in self.sltp_cfg.items():
            self.sltp_cfg[k]['takeprofit'] = tp
        self.set_trigger_cover_positions()

    def trigger_sl(self, vt_symbol: str, side:str, price: float, volume: float) -> str:
        symbol, exchange_name = extract_vt_symbol(vt_symbol)
        assert side in ['buy', 'sell']
        params = {
            'instId': symbol,
            'tdMode': 'cross',
            'side': side,
            'ordType': 'conditional',
            'slTriggerPx': price,
            'sz': volume,
            'slOrdPx': -1
        }
        try:
            data = self.ccxt.private_post_trade_order_algo(params=params)
            return data
        except Exception as e:
            self.write_log(f'trigger sl error {e}')

    def trigger_tp(self, vt_symbol: str, side:str, price: float, volume: float) -> str:
        symbol, exchange_name = extract_vt_symbol(vt_symbol)
        assert side in ['buy', 'sell']
        params = {
            'instId': symbol,
            'tdMode': 'cross',
            'side': side,
            'ordType': 'conditional',
            'tpTriggerPx': price,
            'sz': volume,
            'tpOrdPx': -1
        }
        try:
            data = self.ccxt.private_post_trade_order_algo(params=params)
            return data
        except Exception as e:
            self.write_log(f'trigger tp error {e}')

    def cover_position(self, position: PositionData, trigger:bool=False):
        symbol, exchange_name = extract_vt_symbol(position.vt_symbol)
        side = 'sell' if position.direction == Direction.LONG else 'buy'
        sz = str(round(position.volume))

        params = {
            'instId': symbol,
            'tdMode': 'cross',
            'side': side,
            'posSide': 'short' if side=='buy' else 'long',
            'ordType': 'market',
            'sz': sz
        }
        try:
            data = self.ccxt.private_post_trade_order(params=params)
            #data= self.ccxt.create_order(symbol, 'market', side, sz)
            if data['code'] == "0":
                return data
        except Exception as e:
            self.write_log(f'cover position error {e}')

    def set_trigger_cover_current_positions(self, offset=0.05, vt_symbol:str=None):
        return self.set_trigger_cover_positions(cancel_all=False, offset=offset, use_tick_price=True, vt_symbol=vt_symbol)

    def set_trigger_cover_positions(self, cancel_all=True, offset=0.0, use_tick_price=False, use_max_tp=False, vt_symbol=None):
        positions = self.get_all_positions(use_df=False)
        for position in positions:
            if vt_symbol is not None and position.vt_symbol!=vt_symbol: continue
            if cancel_all:
                side = 'short' if position.direction == Direction.SHORT else 'long'
                self.cancel_all_trigger_orders(position.vt_symbol, side=side)
            if position.volume == 0: continue
            symbol, exchange_name = extract_vt_symbol(position.vt_symbol)
            side = 'sell' if position.direction == Direction.LONG else 'buy'
            sz = str(round(position.volume))
            if self.sltp_cfg.get(position.vt_symbol) is None:
                sl = self.default_sl
                tp = self.default_tp
                # add subscribe for new symbol
                self.subscribe([position.vt_symbol])
                self.sltp_cfg[position.vt_symbol] = {}
                self.sltp_cfg[position.vt_symbol]['stoploss'] = sl
                self.sltp_cfg[position.vt_symbol]['takeprofit'] = tp
            else:
                sl = self.sltp_cfg.get(position.vt_symbol).get('stoploss')
                tp = self.sltp_cfg.get(position.vt_symbol).get('takeprofit')

            assert not (use_tick_price and use_max_tp), "use_tick_price and use_max_tp should not both set"

            liqPrice = position.liqPrice
            # stop loss
            if sl is not None:
                if position.direction == Direction.SHORT:
                    if use_tick_price:
                        trigger_price = self.last_tick[position.vt_symbol].last_price * (1 + offset / position.lever)
                        if trigger_price >= liqPrice:
                            trigger_price = liqPrice * (1 - self.offset / position.lever)
                    else:
                        trigger_price = position.price * (1 - (sl - offset) / position.lever)
                        if trigger_price >= liqPrice:
                            trigger_price = liqPrice * (1 - self.offset / position.lever)
                        if use_max_tp:
                            if position.pnlRatio > self.max_tp:
                                trigger_price = position.price * (1 + (self.max_tp - self.offset) / position.lever)
                else:
                    if use_tick_price:
                        trigger_price = self.last_tick[position.vt_symbol].last_price * (1 - offset / position.lever)
                        if trigger_price <= liqPrice:
                            trigger_price = liqPrice * (1 + self.offset / position.lever)
                    else:
                        trigger_price = position.price * (1 + (sl + offset) / position.lever)
                        if trigger_price <= liqPrice:
                            trigger_price = liqPrice * (1 + self.offset / position.lever)
                        if use_max_tp:
                            if position.pnlRatio > self.max_tp:
                                trigger_price = position.price * (1 - (self.max_tp + self.offset) / position.lever)

                symbol, exchange = extract_vt_symbol(position.vt_symbol)
                params = {
                    'instId': symbol,
                    'tdMode': 'cross',
                    'side': side,
                    'posSide': 'short' if side=='buy' else 'long',
                    'ordType': 'trigger',
                    'triggerPx': trigger_price,
                    'sz': sz,
                    'orderPx': -1
                }
                data = self.send_trigger_order(position.vt_symbol,
                                               side,
                                               'short' if side=='buy' else 'long',
                                               trigger_price,
                                               sz
                )
                if data['code'] == "0":
                    self.write_log(f'place sl trigger order {params}')
                else:
                    self.write_log(f'place sl trigger order error {data}')
            # take profit
            if tp is not None and not self.tp_with_trigger:
                if position.direction == Direction.SHORT:
                    trigger_price = position.price * (1 - (tp - offset) / position.lever)
                else:
                    trigger_price = position.price * (1 + (tp + offset) / position.lever)
                if position.volume>0:
                    params = {
                        'instId': symbol,
                        'tdMode': 'cross',
                        'side': side,
                        'posSide': 'short' if side=='buy' else 'long',
                        'ordType': 'trigger',
                        'triggerPx': trigger_price,
                        'sz': sz,
                        'orderPx': -1
                    }
                data = self.send_trigger_order(position.vt_symbol,
                                               side,
                                               'short' if side=='buy' else 'long',
                                               trigger_price,
                                               sz
                )
                if data['code'] == "0":
                    self.write_log(f'place tp trigger order {params}')
                else:
                    self.write_log(f'error place tp trigger order {params}')

    def send_trigger_order(self, vt_symbol: str, side:str, posSide:str, price: float, volume: float) -> str:
        symbol, exchange_name = extract_vt_symbol(vt_symbol)
        assert side in ['buy', 'sell']
        if side == 'buy':
            params = {
                'instId': symbol,
                'tdMode': 'cross',
                'side': side,
                'posSide': posSide,
                'ordType': 'trigger',
                'triggerPx': price,
                'sz': volume,
                'orderPx': -1
            }
        else:
            params = {
                'instId': symbol,
                'tdMode': 'cross',
                'side': side,
                'posSide': posSide,
                'ordType': 'trigger',
                'triggerPx': price,
                'sz': volume,
                'orderPx': -1
            }
        try:
            data = self.ccxt.private_post_trade_order_algo(params=params)
            if data['code'] == "0":
                return data
            else:
                return data
        except Exception as e:
            self.write_log(f'send trigger order error {e}')

    def get_trigger_orders(self, vt_symbol:str=None, instType:str='SWAP', ordType:str='trigger'):
        """
        请求示例

        GET /api/v5/trade/orders-algo-pending?ordType=conditional

        请求参数
        参数名	类型	是否必须	描述
        algoId	String	可选	策略委托单ID
        instType	String	否	产品类型
        SPOT：币币
        SWAP：永续合约
        FUTURES：交割合约
        MARGIN：杠杆
        instId	String	否	产品ID，BTC-USD-190927
        ordType	String	是	订单类型
        conditional：单向止盈止损
        oco：双向止盈止损
        trigger：计划委托
        iceberg：冰山委托
        twap：时间加权委托
        after	String	否	请求此ID之前（更旧的数据）的分页内容，传的值为对应接口的algoId
        before	String	否	请求此ID之后（更新的数据）的分页内容，传的值为对应接口的algoId
        limit	String	否	返回结果的数量，默认100条
        """
        if vt_symbol is None:
            params = {
                'ordType': ordType
            }
        else:
            symbol, exchange_name = extract_vt_symbol(vt_symbol)
            params = {
                'instId': symbol,
                'ordType': ordType
            }
        try:
            data = self.ccxt.private_get_trade_orders_algo_pending(params=params)
            return data
        except Exception as e:
            self.write_log(f'get trigger orders error {e}')

    def cancel_trigger_orders(self, ordIds:list):
        param = ordIds
        try:
            data = self.ccxt.private_post_trade_cancel_algos(params=param)
            return data
        except Exception as e:
            self.write_log(f'cancel trigger order error {e}')

    def cancel_all_trigger_orders(self, symbol:str=None, side:str='all'):
        tg_orders = self.get_trigger_orders(symbol)
        orders = []
        if tg_orders is None or len(tg_orders['data'])==0:
            return
        for od in tg_orders['data']:
            if side == 'all':
                orders.append({'algoId': od['algoId'], 'instId': od['instId']})
            elif side == 'long':
                if od['posSide'] == 'long':
                    orders.append({'algoId': od['algoId'], 'instId': od['instId']})
            elif side == 'short':
                if od['posSide'] == 'short':
                    orders.append({'algoId': od['algoId'], 'instId': od['instId']})

        for i in range(0, len(orders), 10):
            od_list = orders[i:i+10]
            data = self.cancel_trigger_orders(od_list)
            time.sleep(0.1)
            self.write_log(f'cancel trigger orders {data}')

    def check_stop_order(self, tick: TickData):
        """"""
        for stop_order in list(self.stop_orders.values()):
            if stop_order.vt_symbol != tick.vt_symbol:
                continue

            long_triggered = (
                stop_order.direction == Direction.LONG and tick.last_price >= stop_order.price
            )
            short_triggered = (
                stop_order.direction == Direction.SHORT and tick.last_price <= stop_order.price
            )

            if long_triggered or short_triggered:
                strategy = self.strategies[stop_order.strategy_name]

                # To get excuted immediately after stop order is
                # triggered, use limit price if available, otherwise
                # use ask_price_5 or bid_price_5
                if stop_order.direction == Direction.LONG:
                    if tick.limit_up:
                        price = tick.limit_up
                    else:
                        price = tick.ask_price_5
                else:
                    if tick.limit_down:
                        price = tick.limit_down
                    else:
                        price = tick.bid_price_5

                contract = self.main_engine.get_contract(stop_order.vt_symbol)

                vt_orderids = self.send_limit_order(
                    strategy,
                    contract,
                    stop_order.direction,
                    stop_order.offset,
                    price,
                    stop_order.volume,
                    stop_order.lock,
                    stop_order.net
                )

                # Update stop order status if placed successfully
                if vt_orderids:
                    # Remove from relation map.
                    self.stop_orders.pop(stop_order.stop_orderid)

                    strategy_vt_orderids = self.strategy_orderid_map[strategy.strategy_name]
                    if stop_order.stop_orderid in strategy_vt_orderids:
                        strategy_vt_orderids.remove(stop_order.stop_orderid)

                    # Change stop order status to cancelled and update to strategy.
                    #stop_order.status = StopOrderStatus.TRIGGERED
                    stop_order.vt_orderids = vt_orderids

                    self.call_strategy_func(
                        strategy, strategy.on_stop_order, stop_order
                    )
                    self.put_stop_order_event(stop_order)

    def set_trigger_trigger_order(self, vt_symbol: str, side:str,
                                  trigPx1: float, trigPx2: float, volume: float, orderPx: float=-1,
                                  clean_others:bool=False):
        """
        Trigger a trigger order when price could rapidly reverse
        """
        tto_data = {
            "vt_symbol": vt_symbol,
            "side": side,
            "trigPx1": trigPx1,
            "trigPx2": trigPx2,
            "volume": volume,
            "orderPx": orderPx
        }
        if side == 'buy'    and trigPx1 > self.last_tick[vt_symbol].last_price:
            self.write_log(f'trigPx1 {trigPx1} should < {self.last_tick[vt_symbol].last_price}')
            return
        elif side == 'sell' and trigPx1 < self.last_tick[vt_symbol].last_price:
            self.write_log(f'trigPx1 {trigPx1} should > {self.last_tick[vt_symbol].last_price}')
            return
        if self.trigger_trigger_orders.get(vt_symbol) is None or clean_others:
            self.trigger_trigger_orders[vt_symbol] = []
        self.trigger_trigger_orders[vt_symbol].append(tto_data)

    def tto(self, vt_symbol: str, side:str,
                                  trigPx1: float, trigPx2: float, volume: float, orderPx: float=-1,
                                  clean_others:bool=False):
        return self.set_trigger_trigger_order(vt_symbol, side, trigPx1, trigPx2,
                                              volume, orderPx=orderPx,
                                              clean_others=clean_others)

    def set_trigger_tto_around_price(self, trigger_price, offset):
        pass

    def lock_pos(self, offset: float=None, vt_symbol:str=None):
        if offset is not None:
            self.set_trigger_cover_current_positions(offset, vt_symbol=vt_symbol)
        else:
            self.set_trigger_cover_current_positions(self.offset, vt_symbol=vt_symbol)

    def check_trigger_trigger_order(self, tick: TickData):
        """
        Check if current tick is cross the preset price
        """
        # self.write_log(f'check tick {tick}')
        for (vt_symbol, ttos) in self.trigger_trigger_orders.items():
            if tick.vt_symbol != vt_symbol:
                continue
            for i in range(0, len(ttos)):
                tto = ttos[i]
                if tto['side'] == 'buy':
                    if tick.last_price < tto['trigPx1']:
                        self.write_log(f'triggered {tto}')
                        data = self.send_trigger_order(
                            vt_symbol,
                            tto['side'],
                            'long',
                            tto['trigPx2'],
                            tto['volume']
                        )
                        if data['code'] == '0':
                            ttos.pop(i)
                            self.write_log(f'{tto} trigger order sent')
                        else:
                            self.write_log(f'tto error {data}')
                elif tto['side'] == 'sell':
                    if tick.last_price > tto['trigPx1']:
                        self.write_log(f'triggered {tto}')
                        data = self.send_trigger_order(
                            vt_symbol,
                            tto['side'],
                            'short',
                            tto['trigPx2'],
                            tto['volume']
                        )
                        if data['code'] == '0':
                            ttos.pop(i)
                            self.write_log(f'{tto} trigger order sent')
                        else:
                            self.write_log(f'tto error {data}')
                else:
                    self.write_log('not valid')

    def cleanup_ttos(self):
        self.trigger_trigger_orders = {}

    def adjust_tp(self, vt_symbol: str=None, mul: float = 1.5):
        """
        set takeprofit to stoploss * multiplier, default 1.5
        """
        assert mul > 0, "mul should not be negetive"
        # change it for single symbol
        if vt_symbol:
            if self.sltp_cfg.get(vt_symbol) is None: return
            self.sltp_cfg[vt_symbol]['takeprofit'] = abs(self.sltp_cfg[vt_symbol]['stoploss']) * mul
        # change for all symbols
        else:
            for (vt_symbol, config) in self.sltp_cfg.items():
                config['takeprofit'] = config['stoploss'] * mul
        # done

    def check_sl_tp(self, position: PositionData):
        #self.write_log("sltp")
        # create sl tp trigger orders first
        last_position = self.last_position.get(position.vt_symbol)
        if last_position is None:
            self.set_trigger_cover_positions(vt_symbol=position.vt_symbol)
        elif position.volume != last_position.volume:
            self.set_trigger_cover_positions(vt_symbol=position.vt_symbol)
        # check if volume valid
        if not position.volume > 0: return False
        for (vt_symbol, sltp_cfg) in self.sltp_cfg.items():
            if vt_symbol != position.vt_symbol:
                continue
            elif position.volume == 0:
                continue
            sl = sltp_cfg.get('stoploss')
            tp = sltp_cfg.get('takeprofit')
            if sl and position.pnlRatio < sl:
                self.write_log('trigger stoploss')
                self.cover_position(position)
            if tp and position.pnlRatio > tp:
                if self.tp_with_trigger is True:
                    # self.set_trigger_cover_positions(cancel_all=True, use_max_tp=True, vt_symbol=position.vt_symbol)
                    if position.direction == Direction.LONG:
                        trigger_price = self.last_tick[vt_symbol].last_price * (1 - self.offset / position.lever)
                        if position.pnlRatio > self.max_tp:
                            trigger_price = position.price * (1 + (self.max_tp - self.offset) / position.lever)
                    else:
                        trigger_price = self.last_tick[vt_symbol].last_price * (1 + self.offset / position.lever)
                        if position.pnlRatio > self.max_tp:
                            trigger_price = position.price * (1 - (self.max_tp + self.offset) / position.lever)

                    symbol, exchange_name = extract_vt_symbol(position.vt_symbol)
                    side = 'sell' if position.direction == Direction.LONG else 'buy'
                    sz = str(round(position.volume))
                    params = {
                        'instId': symbol,
                        'tdMode': 'cross',
                        'side': side,
                        'posSide': 'short' if side=='buy' else 'long',
                        'ordType': 'trigger',
                        'triggerPx': trigger_price,
                        'sz': sz,
                        'orderPx': -1
                    }
                    #if self.last_tick[vt_symbol].last_price - position.price
                    if self.cancel_tp:
                        self.cancel_all_trigger_orders(position.vt_symbol,
                                                       side='short' if side=='buy' else 'long')
                    data = self.send_trigger_order(position.vt_symbol,
                                                   side,
                                                   'short' if side=='buy' else 'long',
                                                   trigger_price,
                                                   sz
                    )
                    if data['code'] == "0":
                        self.write_log(f'place tp trigger order {params}')
                else:
                    self.write_log('trigger takeprofit')
                    self.cover_position(position)

    def get_kline(self, vt_symbol, frequency:str="1h", as_df:bool=True):
        symbol, exchange = extract_vt_symbol(vt_symbol)
        kline = self.ccxt.fetch_ohlcv(symbol, frequency)
        df = pd.DataFrame(kline, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['ts'], unit='ms')
        df.index = df['datetime']
        del df['datetime']
        return df
"""
    def set_trigger_zone(self, vt_symbol, price, volume, offset:float=None):
        # set a trigger zone if price enters this zone, and left out with tto triggered
        if offset is None: offset = self.offset
        last_price = self.last_tick[vt_symbol].last_price
        trend_dir = 'up' if price > last_price else 'down'
        if trend_dir == 'down':
            self.engine.tto(vt_symbol,
                       'sell',
                       trend_val,
                       trend_val * (1 - offset),
                       size,
                       clean_others=True)
            data = self.engine.send_trigger_order(
                vt_symbol,
                'buy',
                'long',
                trend_val * (1 + offset * 1.5),
                size
            )
            if data['code'] == '0':
                engine.write_log(f'{vt_symbol} {freq} {trend_dir} trigger order sent')
            else:
                engine.write_log(f'error {data}')
        elif trend_dir == 'up':
            engine.tto(vt_symbol,
                       'buy',
                       trend_val,
                       trend_val * (1 + offset),
                       size,
                       clean_others=True)
            data = engine.send_trigger_order(
                vt_symbol,
                'sell',
                'short',
                trend_val * (1 - offset * 1.5),
                size
            )
            if data['code'] == '0':
                engine.write_log(f'{vt_symbol} {freq} {trend_dir} trigger order sent')
            else:
                engine.write_log(f'error {data}')   
"""

def to_df(data_list: Sequence):
    """"""
    if not data_list:
        return None

    dict_list = [data.__dict__ for data in data_list if data is not None]
    df = DataFrame(dict_list)
    if 'datetime' in df.columns:
        df.index = df.datetime
    return df


def get_data(func: callable, arg: Any = None, use_df: bool = True):
    """"""
    if not arg:
        data = func()
    else:
        data = func(arg)

    if not use_df:
        return data
    elif data is None:
        return data
    else:
        if not isinstance(data, list):
            data = [data]
        return to_df(data)
