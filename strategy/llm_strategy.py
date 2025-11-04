"""
LLM-Driven Trading Strategy

This strategy demonstrates how to use LLM-based market analysis for trading decisions.
The AI agent will analyze market data and generate trading signals autonomously.
"""

from time import sleep
from vn_qtrade.okx_engine import OKXEngine


def run(engine: OKXEngine):
    """
    LLM-powered trading strategy runner.

    The strategy will:
    1. Subscribe to market data for configured symbols
    2. Let the AIAgentEngine analyze market conditions using LLM
    3. Automatically execute trades based on AI recommendations
    """
    # Configuration
    vt_symbols = ["BTC-USDT-SWAP.OKEX", "ETH-USDT-SWAP.OKEX"]

    # Subscribe to market data
    sleep(1)  # Wait for connection to stabilize
    engine.subscribe(vt_symbols)
    engine.offset = 0.1

    # Configure SL/TP for risk management
    engine.write_log("Configuring risk management...")
    for vt_symbol in vt_symbols:
        engine.sltp_cfg[vt_symbol] = {'stoploss': -0.05, 'takeprofit': 0.10}

    # Get contract information
    engine.write_log("=== Contract Information ===")
    for vt_symbol in vt_symbols:
        contract = engine.get_contract(vt_symbol)
        if contract:
            engine.write_log(f"{vt_symbol}: {contract.name}, Min: {contract.min_volume}, Max: {contract.max_volume}")

    # Display strategy info
    engine.write_log("\n" + "="*60)
    engine.write_log("LLM-Driven Trading Strategy Started")
    engine.write_log("="*60)
    engine.write_log(f"Symbols: {', '.join(vt_symbols)}")
    engine.write_log(f"Stop Loss: 5%")
    engine.write_log(f"Take Profit: 10%")
    engine.write_log("\nThe AI agent will:")
    engine.write_log("1. Analyze market data using LLM")
    engine.write_log("2. Generate trading signals based on analysis")
    engine.write_log("3. Execute trades automatically")
    engine.write_log("\nPress Ctrl+C to enter REPL for debugging")
    engine.write_log("="*60 + "\n")

    # Main trading loop
    # The AIAgentEngine runs in the background and will:
    # - Listen to tick events
    # - Analyze market with LLM
    # - Generate AI signals
    # - Execute trades automatically

    check_interval = 10  # Check status every 10 seconds
    check_counter = 0

    while engine.strategy_active:
        check_counter += 1

        # Periodic status check
        if check_counter >= check_interval:
            check_counter = 0

            # Get positions
            positions = engine.get_all_positions(use_df=True)
            if positions is not None and len(positions) > 0:
                engine.write_log("\n--- Active Positions ---")
                for _, pos in positions.iterrows():
                    pnl_pct = (pos.get('pnl', 0) / pos.get('volume', 1)) * 100
                    engine.write_log(
                        f"{pos['vt_symbol']}: {pos['direction'].value} "
                        f"Volume: {pos['volume']:.4f}, PnL: {pnl_pct:.2f}%"
                    )
                engine.write_log("-------------------------\n")

        sleep(1)

    engine.write_log("LLM Trading Strategy stopped")
