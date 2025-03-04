from time import sleep
from vn_qtrade.okx_engine import OKXEngine


def run(engine: OKXEngine):
    """
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
