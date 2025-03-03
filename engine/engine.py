
""""""

import sys
import importlib
import traceback
from typing import Sequence, Any
from pathlib import Path
from datetime import datetime
import time
import threading
import signal
from threading import Thread
from functools import partial
import atexit
from dataclasses import dataclass, field

from pandas import DataFrame

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.constant import Direction, Offset, OrderType, Interval
from vnpy.trader.object import (
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
from vnpy.trader.event import (
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION
)
from vnpy.trader.constant import (
    Direction,
    OrderType,
    Interval,
    Exchange,
    Offset,
    Status
)

from vnpy.trader.utility import load_json, save_json, extract_vt_symbol, round_to
from concurrent.futures import ThreadPoolExecutor

from copy import copy
from tzlocal import get_localzone

LOCAL_TZ = get_localzone()

import ccxt

APP_NAME = "CryptoTrader"

EVENT_CRYPTO_LOG = "eCryptoLog"



@dataclass
class SLTPOrder:
    vt_symbol: str
    direction: Direction
    offset: Offset
    price: float
    volume: float
    sl: float
    tp: float
    sltp_orderid: str
    datetime: datetime
    lock: bool = False
    net: bool = False
    vt_orderids: list = field(default_factory=list)


class WorkingThread(threading.Thread):
    def __init__(self, *kargs, **kwargs):
        threading.Thread.__init__(self, *kargs, **kwargs)

        # event for manual debug
        self.dbg_event = threading.Event()

    def set(self):
        return self.dbg_event.set()

    def unset(self):
        return self.dbg_event.clear()

    def is_set(self):
        return self.dbg_event.is_set()


class CryptoEngineBase(BaseEngine):
    """"""
    setting_filename = "crypto_trader_setting.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine, terminal:bool=True):
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)

        self.strategy_active = False
        self.strategy_thread = None

        self.contracts = None

        if terminal:
            self.monitor_thread =  WorkingThread(
                target=self.monitor)
            self.monitor_thread.start()
            signal.signal(signal.SIGINT, self.debug_handler)

        atexit.register(self.cleanup)

    def debug_handler(self, signum, frame):
        try:
            self.write_log('signal triggered (press Ctrl+c again will force exit)')
            if self.monitor_thread.is_set():
                exit(-1)
            else:
                self.monitor_thread.set()
        except Exception as e:
            self.write_log(f'error: {e}')
            exit(-1)

    def monitor(self):
        while True:
            time.sleep(5)

    def init(self):
        """
        Start script engine.
        """
        #result = rqdata_client.init()
        #if result:
        #    self.write_log("RQData数据接口初始化成功")
        pass

    def start_strategy(self, script_path: str):
        """
        Start running strategy function in strategy_thread.
        """
        if self.strategy_active:
            return
        self.strategy_active = True

        self.strategy_thread = WorkingThread(
            target=self.run_strategy, args=(script_path,))
        self.strategy_thread.start()

        self.write_log("策略交易脚本启动")

    def run_strategy(self, script_path: str):
        """
        Load strategy script and call the run function.
        """
        path = Path(script_path)
        sys.path.append(str(path.parent))

        script_name = path.parts[-1]
        module_name = script_name.replace(".py", "")

        try:
            module = importlib.import_module(module_name)
            importlib.reload(module)
            module.run(self)
        except:     # noqa
            msg = f"触发异常已停止\n{traceback.format_exc()}"
            self.write_log(msg)

    def stop_strategy(self):
        """
        Stop the running strategy.
        """
        if not self.strategy_active:
            return
        self.strategy_active = False

        if self.strategy_thread:
            self.strategy_thread.join()
        self.strategy_thread = None

        self.write_log("策略交易脚本停止")

    def connect_gateway(self, setting: dict, gateway_name: str):
        """"""
        self.main_engine.connect(setting, gateway_name)

    def send_order(
        self,
        vt_symbol: str,
        price: float,
        volume: float,
        direction: Direction,
        offset: Offset,
        order_type: OrderType
    ) -> str:
        """"""
        contract = self.get_contract(vt_symbol)
        if not contract:
            return ""

        req = OrderRequest(
            symbol=contract.symbol,
            exchange=contract.exchange,
            direction=direction,
            type=order_type,
            volume=volume,
            price=price,
            offset=offset
        )

        vt_orderid = self.main_engine.send_order(req, contract.gateway_name)
        return vt_orderid

    def subscribe(self, vt_symbols):
        """"""
        for vt_symbol in vt_symbols:
            contract = self.main_engine.get_contract(vt_symbol)
            if contract:
                req = SubscribeRequest(
                    symbol=contract.symbol,
                    exchange=contract.exchange
                )
                self.main_engine.subscribe(req, contract.gateway_name)

    def buy(self, vt_symbol: str, price: float, volume: float, order_type: OrderType = OrderType.LIMIT) -> str:
        """"""
        return self.send_order(vt_symbol, price, volume, Direction.LONG, Offset.OPEN, order_type)

    def sell(self, vt_symbol: str, price: float, volume: float, order_type: OrderType = OrderType.LIMIT) -> str:
        """"""
        return self.send_order(vt_symbol, price, volume, Direction.SHORT, Offset.CLOSE, order_type)

    def short(self, vt_symbol: str, price: float, volume: float, order_type: OrderType = OrderType.LIMIT) -> str:
        """"""
        return self.send_order(vt_symbol, price, volume, Direction.SHORT, Offset.OPEN, order_type)

    def cover(self, vt_symbol: str, price: float, volume: float, order_type: OrderType = OrderType.LIMIT) -> str:
        """"""
        return self.send_order(vt_symbol, price, volume, Direction.LONG, Offset.CLOSE, order_type)

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
        data = self.ccxt.private_post_trade_order_algo(params=params)
        return data

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
        data = self.ccxt.private_post_trade_order_algo(params=params)
        return data


    def get_trigger_orders(self, vt_symbol:str, instType:str='SWAP', ordType:str='conditional'):
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
        symbol, exchange_name = extract_vt_symbol(vt_symbol)
        params = {
            'instId': symbol,
            'ordType': ordType
        }
        if symbol is None:
            del params['instId']

        data = self.ccxt.private_get_trade_orders_algo_pending(params=params)
        return data

    def cancel_trigger_orders(self, ordIds:list):
        param = ordIds

        return self.ccxt.private_post_trade_cancel_algos(params=param)

    def cancel_all_trigger_orders(self, symbol:str=None):
        tg_orders = self.get_trigger_orders(symbol)
        orders = []
        for od in tg_orders['data']:
            orders.append({'algoId': od['algoId'], 'instId': od['instId']})

        if len(orders)>0:
            return self.cancel_trigger_orders(orders)
        else:
            return None


    def cancel_order(self, vt_orderid: str) -> None:
        """"""
        order = self.get_order(vt_orderid)
        if not order:
            return

        req = order.create_cancel_request()
        self.main_engine.cancel_order(req, order.gateway_name)

    def get_tick(self, vt_symbol: str, use_df: bool = False) -> TickData:
        """"""
        return get_data(self.main_engine.get_tick, arg=vt_symbol, use_df=use_df)

    def get_ticks(self, vt_symbols: Sequence[str], use_df: bool = False) -> Sequence[TickData]:
        """"""
        ticks = []
        for vt_symbol in vt_symbols:
            tick = self.main_engine.get_tick(vt_symbol)
            ticks.append(tick)

        if not use_df:
            return ticks
        else:
            return to_df(ticks)

    def get_order(self, vt_orderid: str, use_df: bool = False) -> OrderData:
        """"""
        return get_data(self.main_engine.get_order, arg=vt_orderid, use_df=use_df)

    def get_orders(self, vt_orderids: Sequence[str], use_df: bool = False) -> Sequence[OrderData]:
        """"""
        orders = []
        for vt_orderid in vt_orderids:
            order = self.main_engine.get_order(vt_orderid)
            orders.append(order)

        if not use_df:
            return orders
        else:
            return to_df(orders)

    def get_trades(self, vt_orderid: str, use_df: bool = False) -> Sequence[TradeData]:
        """"""
        trades = []
        all_trades = self.main_engine.get_all_trades()

        for trade in all_trades:
            if trade.vt_orderid == vt_orderid:
                trades.append(trade)

        if not use_df:
            return trades
        else:
            return to_df(trades)

    def get_all_active_orders(self, use_df: bool = True) -> Sequence[OrderData]:
        """"""
        return get_data(self.main_engine.get_all_active_orders, use_df=use_df)

    def get_contract(self, vt_symbol, use_df: bool = False) -> ContractData:
        """"""
        return get_data(self.main_engine.get_contract, arg=vt_symbol, use_df=use_df)

    def get_all_contracts(self, use_df: bool = True) -> Sequence[ContractData]:
        """"""
        return get_data(self.main_engine.get_all_contracts, use_df=use_df)

    def get_account(self, vt_accountid: str, use_df: bool = False) -> AccountData:
        """"""
        return get_data(self.main_engine.get_account, arg=vt_accountid, use_df=use_df)

    def get_all_accounts(self, use_df: bool = True) -> Sequence[AccountData]:
        """"""
        return get_data(self.main_engine.get_all_accounts, use_df=use_df)

    def get_position(self, vt_positionid: str, use_df: bool = False) -> PositionData:
        """"""
        return get_data(self.main_engine.get_position, arg=vt_positionid, use_df=use_df)

    def get_all_positions(self, use_df: bool = True) -> Sequence[PositionData]:
        """"""
        return get_data(self.main_engine.get_all_positions, use_df=use_df)

    def get_bars(self, vt_symbol: str, start_date: str, interval: Interval, use_df: bool = True) -> Sequence[BarData]:
        """"""
        contract = self.main_engine.get_contract(vt_symbol)
        if not contract:
            return []

        start = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.now()

        req = HistoryRequest(
            symbol=contract.symbol,
            exchange=contract.exchange,
            start=start,
            end=end,
            interval=interval
        )

        gateway = self.main_engine.gateways.get(contract.gateway_name)
        if gateway is not None:
            return get_data(gateway.query_history, arg=req, use_df=use_df)
        #else:
        #    return get_data(rqdata_client.query_history, arg=req, use_df=use_df)

    def write_log(self, msg: str) -> None:
        """"""
        log = LogData(msg=msg, gateway_name=APP_NAME)
        print(f"{log.time}\t{log.msg}")

        event = Event(EVENT_CRYPTO_LOG, log)
        self.event_engine.put(event)

    def send_email(self, msg: str) -> None:
        """"""
        subject = "脚本策略引擎通知"
        self.main_engine.send_email(subject, msg)

    def cleanup(self):
        self.write_log("cleanup threads...")
        self.write_log("bye!")

class CryptoEngine(CryptoEngineBase):
    def __init__(self, main_engine: MainEngine, event_engine: EventEngine, terminal:bool=True):
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)


class OKEXEngine(CryptoEngine):
    def __init__(self, main_engine: MainEngine, event_engine: EventEngine, terminal:bool=True):
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)
        self.ccxt = None
        self.init_ccxt()

        self.sltp_cfg = {}  # should be {vt-symbol: config}

    def init_ccxt(self):
        okex_gw = self.main_engine.gateways.get('OKEX')
        if okex_gw:
            self.ccxt = ccxt.okex(
                {
                    'enableRateLimit': True,
                    'apiKey': okex_gw.key,
                    'secret': okex_gw.secret,
                    'password': okex_gw.passphrase,
                    # 'verbose': True,  # for debug output
            }
            )
            if okex_gw.proxy_host:
                self.ccxt.proxies = {
                    'http': f'http://{okex_gw.proxy_host}:{okex_gw.proxy_port}',
                    'https': f'http://{okex_gw.proxy_host}:{okex_gw.proxy_port}'
                }

    def register_event(self):
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)
        self.event_engine.register(EVENT_POSITION, self.process_position_event)

    def process_tick_event(self, event: Event):
        """"""
        tick = event.data

    def process_order_event(self, event: Event):
        """"""
        order = event.data

    def process_trade_event(self, event: Event):
        """"""
        trade = event.data

    def process_position_event(self, event: Event):
        """"""
        position = event.data

        self.check_sl_tp(position)

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
                    stop_order.status = StopOrderStatus.TRIGGERED
                    stop_order.vt_orderids = vt_orderids

                    self.call_strategy_func(
                        strategy, strategy.on_stop_order, stop_order
                    )
                    self.put_stop_order_event(stop_order)


    def set_trigger_trigger_order(self, vt_symbol: str, side:str,
                                  trigPx1: float, trigPx2: float, volume: float):
        """
        Trigger a trigger order when price could rapidly reverse
        """
        pass

    def check_sl_tp(self, position: PositionData):
        for (vt_symbol, sltp_cfg) in self.sltp_cfg.items():
            if vt_symbol != position.vt_symbol:
                continue
            elif position.volume == 0:
                continue
            sl = sltp_cfg['stoploss']
            tp = sltp_cfg['takeprofit']
            if position.pnlRatio < sl:
                self.write_log('trigger stoploss')
            if position.pnlRatio > tp:
                self.write_log('trigger takeprofit')


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
