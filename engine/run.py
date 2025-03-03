#!/usr/bin/env python
import importlib
import okex_engine
importlib.reload(okex_engine)

import logging
import time
from IPython.core.debugger import set_trace
from IPython.terminal.embed import embed

from vnpy.trader.constant import (
    Direction,
    Exchange,
    Interval,
    Offset,
    OrderType,
    Product,
    Status,
    OptionType
)


from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.event import EVENT_LOG, EVENT_ACCOUNT
from vnpy.trader.setting import SETTINGS

#from vnpy_ctastrategy import CtaEngine, CtaStrategyApp

from okex_engine import EVENT_CRYPTO_LOG, OKEXEngine
from vnpy_okx import OkxGateway

try:
    from local_setting import (okex_setting)
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

    engine = OKEXEngine(main_engine, event_engine, terminal=False)

    engine.connect_gateway(okex_setting, "OKX")
    engine.init_ccxt()
    return engine

def main():
    #engine.connect_gateway(binance_setting, "BINANCE")
    #engine.connect_gateway(huobi_setting, "HUOBIS")
    #engine.connect_gateway(huobi_setting, "HUOBI")
    engine = init_engine()
    #log_engine = engine.main_engine.get_engine('log')
    #engine.event_engine.register(EVENT_CRYPTO_LOG, log_engine.process_log_event)
    # engine.event_engine.register(EVENT_ACCOUNT, log_engine.process_log_event)
    # cta_engine = engine.main_engine.add_app(CtaStrategyApp)
    # time.sleep(3)
    # cta_engine.init_engine()
    # engine.write_log("CTA引擎初始化完成")
    # time.sleep(5)
    # cta_engine.init_all_strategies()
    # 
    # while True:
    #     inited = [(k,v) for k,v in cta_engine.strategies.items() if v.inited==True]
    #     all_strategies = [(k,v) for k,v in cta_engine.strategies.items()]
    #     engine.write_log(f"已加载: {len(inited)}/{len(all_strategies)}")
    #     if len(inited) == len(all_strategies):
    #         engine.write_log("CTA策略加载完成")
    #         break
    #     else:
    #         time.sleep(3)
    # 
    # cta_engine.start_all_strategies()
    # engine.write_log("CTA启动完成")

    #recorder_engine = engine.main_engine.get_engine(DataRecorderApp.app_name)
    #recorder_engine.add_bar_recording('btcusdt.BINANCE')
    #recorder_engine.add_tick_recording('btcusdt.BINANCE')

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
