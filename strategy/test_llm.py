"""
Test LLM Integration

This script demonstrates how to test the LLM integration in isolation.
Run this in REPL to test AI thinking without live trading.

Usage:
    # From project root:
    python vn_qtrade/strategy/test_llm.py

    # From vn_qtrade directory:
    cd vn_qtrade
    python strategy/test_llm.py
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "vn_qtrade"))

from ai_trade.gi_llm_integration import TradingThinkingAgent
from vnpy_evo.trader.object import TickData
from vnpy_evo.trader.constant import Exchange, Direction
from datetime import datetime
import asyncio


async def test_llm_thinking():
    """Test LLM thinking agent independently."""
    print("="*60)
    print("Testing LLM Trading Thinking Agent")
    print("="*60)

    # Initialize thinking agent
    thinking_agent = TradingThinkingAgent()
    print("\n✓ Thinking agent initialized")

    # Create mock tick data
    tick = TickData(
        gateway_name="OKX",
        symbol="BTC-USDT-SWAP",
        exchange=Exchange.OKX,
        datetime=datetime.now(),
        last_price=67500.0,
        bid_price_1=67499.0,
        ask_price_1=67501.0,
        bid_volume_1=0.5,
        ask_volume_1=0.5,
        volume=1250.5
    )

    # Create market context
    context = {
        "positions": [
            {
                "vt_symbol": "BTC-USDT-SWAP.OKEX",
                "direction": "long",
                "volume": 0.01,
                "pnl": 50.0
            }
        ],
        "active_orders": 1,
        "account_balance": 10000.0,
        "analysis_time": 1
    }

    print(f"\nAnalyzing market for {tick.vt_symbol}")
    print(f"Price: ${tick.last_price}")
    print(f"Context: {context}")

    # Analyze market with LLM
    print("\n" + "-"*60)
    print("LLM Analysis in progress...")
    print("-"*60)

    analysis = await thinking_agent.analyze_market_situation(tick, context)

    print("\n✓ Analysis complete!")
    print("\n" + "="*60)
    print("Analysis Result:")
    print("="*60)
    print(f"Reasoning Type: {analysis.get('reasoning_type')}")
    print(f"Market Regime: {analysis.get('understanding', {}).get('market_regime')}")
    print(f"Confidence: {analysis.get('understanding', {}).get('confidence')}")
    print(f"Decision: {analysis.get('decision', {}).get('action')}")
    print(f"Rationale: {analysis.get('decision', {}).get('rationale')}")
    print(f"TQR Score: {analysis.get('tqr_score')}")
    print("="*60)

    # Generate trading signal
    signal = thinking_agent.get_trading_signal(analysis, tick)

    if signal:
        print("\n✓ Trading signal generated:")
        print(f"  Direction: {signal['direction'].value}")
        print(f"  Price: ${signal['price']}")
        print(f"  Volume: {signal['volume']}")
        print(f"  Confidence: {signal['confidence']}")
        print(f"  TQR Score: {signal['tqr_score']}")
    else:
        print("\n✓ No trading action recommended")

    # Show thought history
    history = thinking_agent.get_thought_history()
    print(f"\n✓ Thought history: {len(history)} entries")

    print("\n" + "="*60)
    print("Test completed successfully!")
    print("="*60)


def run_test():
    """Run the async test."""
    asyncio.run(test_llm_thinking())


if __name__ == "__main__":
    run_test()
