from time import sleep
from okx_engine import OKXEngine


def run(engine: OKXEngine):
    """
    脚本策略的主函数说明：
    1. 唯一入参是脚本引擎ScriptEngine对象，通用它来完成查询和请求操作
    2. 该函数会通过一个独立的线程来启动运行，区别于其他策略模块的事件驱动
    3. while循环的维护，请通过engine.strategy_active状态来判断，实现可控退出

    脚本策略的应用举例：
    1. 自定义篮子委托执行执行算法
    2. 股指期货和一篮子股票之间的对冲策略
    3. 国内外商品、数字货币跨交易所的套利
    4. 自定义组合指数行情监控以及消息通知
    5. 股票市场扫描选股类交易策略（龙一、龙二）
    6. 等等~~~
    """
    vt_symbols = ["BTC-USDT-SWAP.OKEX", "ETH-USDT-SWAP.OKEX"]
    sleep(1)
    engine.subscribe(vt_symbols)
    engine.offset = 0.1

    # 订阅行情

    for vt_symbol in vt_symbols:
        engine.sltp_cfg[vt_symbol] = {'stoploss': -0.5, 'takeprofit': 4.5}

    # 获取合约信息
    for vt_symbol in vt_symbols:
        contract = engine.get_contract(vt_symbol)
        msg = f"合约信息，{contract}"
        engine.write_log(msg)
    # 持续运行，使用strategy_active来判断是否要退出程序
    while engine.strategy_active:
        # 轮询获取行情
        for vt_symbol in vt_symbols:
            tick = engine.get_tick(vt_symbol)
            if tick is not None:
                msg = f"\n{tick.vt_symbol} ask:{tick.ask_price_1} {tick.ask_volume_1} \
                bid: {tick.bid_price_1} {tick.bid_volume_1}"
                #engine.write_log(msg)
        accounts = engine.get_all_accounts(use_df=True)
        positions  = engine.get_all_positions(use_df=True)
        orders = engine.get_all_active_orders(use_df=True)
        #engine.write_log(accounts)
        #if positions is not None:
        #    engine.write_log(positions)
        #engine.write_log(orders)
        # 等待3秒进入下一轮
        sleep(0.1)
