
import importlib
import sys
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
from vnpy_evo.trader.constant import (
    Direction,
    OrderType,
    Interval,
    Exchange,
    Offset,
    Status
)

from vnpy_evo.trader.utility import load_json, save_json, extract_vt_symbol, round_to
from .utils import get_data
from concurrent.futures import ThreadPoolExecutor

from copy import copy
from tzlocal import get_localzone

import inspect 

def get_debug_info():
    stack_t = inspect.stack()
    #stack_info = stack_t[1]
    t = stack_t[2]
    return f"{t.filename} {t.lineno} {t.function}"
LOCAL_TZ = get_localzone()

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
        self.DEBUG = True

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

    def write_log(self, msg: str) -> None:
        """"""
        log = LogData(msg=msg, gateway_name=APP_NAME)
        #print(f"{log.time}\t{log.msg}\t{get_debug_info()}")
        print(f"{log.time}\t{log.msg}\t")

        event = Event(EVENT_CRYPTO_LOG, log)
        self.event_engine.put(event)

    def send_email(self, msg: str) -> None:
        """"""
        subject = "脚本策略引擎通知"
        self.main_engine.send_email(subject, msg)

    def cleanup(self):
        self.write_log("cleanup threads...")
        self.write_log("bye!")
