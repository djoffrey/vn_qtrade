#!/usr/bin/env python
import importlib
from vn_qtrade import okx_engine
importlib.reload(okx_engine)

import logging
import time
from IPython.core.debugger import set_trace
from IPython.terminal.embed import embed

from vnpy_evo.trader.constant import (
    Direction,
    Exchange,
    Interval,
    Offset,
    OrderType,
    Product,
    Status,
    OptionType
)


from vnpy_evo.event import EventEngine
from vnpy_evo.trader.engine import MainEngine
from vnpy_evo.trader.event import EVENT_LOG, EVENT_ACCOUNT
from vnpy_evo.trader.setting import SETTINGS

from vn_qtrade.okx_engine import EVENT_CRYPTO_LOG, OKXEngine
from vnpy_okx import OkxGateway

try:
    from local_setting import (okx_setting)
except ImportError:
    raise

import asyncio
import nest_asyncio
nest_asyncio.apply()

SETTINGS["log.level"] = logging.INFO

def init_engine():
    gateways = [OkxGateway]

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)
    for gateway in gateways:
        main_engine.add_gateway(gateway)

    engine = OKXEngine(main_engine, event_engine, terminal=False)

    engine.connect_gateway(okx_setting, "OKX")
    engine.init_ccxt()
    return engine

def main():

    engine = init_engine()


    time.sleep(1)
    engine.start_strategy('demo.py')
    #engine.start_strategy('grid1.py')

    while True:
        if engine.monitor_thread.is_set():
            embed(colors="Linux")
            engine.monitor_thread.unset()
        time.sleep(5)


if __name__ == '__main__':
    #asyncio.get_event_loop().run_until_complete(main())
    main()
