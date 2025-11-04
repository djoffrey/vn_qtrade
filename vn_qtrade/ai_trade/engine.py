"""
AI Agent Engine

The "Brain" of the AI trading system.
"""

import asyncio
from vnpy_evo.trader.engine import BaseEngine, MainEngine, EventEngine
from vnpy_evo.trader.event import EVENT_TICK
from vnpy_evo.trader.object import TickData

from .base import EVENT_AI_SIGNAL, SignalData
from .gi_llm_integration import TradingThinkingAgent
from vnpy_evo.trader.constant import Direction


class AIAgentEngine(BaseEngine):
    """
    The AIAgentEngine is responsible for:
    1.  Listening to market data events (e.g., ticks, bars).
    2.  Maintaining a "world model" of the market.
    3.  Running AI agents (LLM, ML, RL, etc.) to analyze the data.
    4.  Generating trading signals (SignalData).
    5.  Emitting these signals as EVENT_AI_SIGNAL to the event bus.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """
        Constructor
        """
        super().__init__(main_engine, event_engine, "AIAgent")

        # Initialize LLM-driven trading thinking agent
        self.thinking_agent = TradingThinkingAgent()

        # Configuration
        self.analysis_enabled = True
        self.thinking_interval = 5  # Analyze every 5 ticks
        self.tick_counter = {}

        self.register_event()

        self.write_log("AIAgentEngine initialized with LLM thinking capabilities")

    def write_log(self, msg: str) -> None:
        """
        Write a log message.
        """
        print(f"[AIAgentEngine] {msg}")

    def log_info(self, msg: str) -> None:
        """Log info message."""
        self.write_log(msg)

    def log_error(self, msg: str) -> None:
        """Log error message."""
        print(f"[AIAgentEngine ERROR] {msg}")

    def log_debug(self, msg: str) -> None:
        """Log debug message."""
        print(f"[AIAgentEngine DEBUG] {msg}")

    def register_event(self) -> None:
        """
        Register event listeners.
        The AI engine needs to listen to market data to make decisions.
        """
        #self.event_engine.register(EVENT_TICK, self.process_tick_event)
        pass

    def process_tick_event(self, event) -> None:
        """
        Process incoming tick data.
        This is where the AI's core logic begins.
        """
        tick: TickData = event.data

        # Update tick counter for this symbol
        vt_symbol = tick.vt_symbol
        self.tick_counter[vt_symbol] = self.tick_counter.get(vt_symbol, 0) + 1

        # Use LLM to analyze market and make decisions
        if self.analysis_enabled:
            try:
                # Get current context (positions, orders, etc.)
                context = self._get_market_context(vt_symbol)

                # Analyze market with LLM
                analysis = asyncio.run(
                    self.thinking_agent.analyze_market_situation(tick, context)
                )

                # Log analysis result
                self.write_log(
                    f"LLM Analysis for {vt_symbol}: {analysis.get('decision', {}).get('rationale', 'No action')}"
                )

                # Generate trading signal if decision warrants action
                signal = self.thinking_agent.get_trading_signal(analysis, tick)
                if signal:
                    self.generate_llm_signal(signal)

            except Exception as e:
                self.write_log(f"Error in LLM analysis: {e}")
                # Fallback to simple threshold logic
                self._fallback_tick_processing(tick)

    def _get_market_context(self, vt_symbol: str) -> dict:
        """Get current market context for analysis."""
        try:
            positions = self.main_engine.get_all_positions()
            orders = self.main_engine.get_all_active_orders()
            accounts = self.main_engine.get_all_accounts()

            return {
                "positions": [
                    {
                        "vt_symbol": p.vt_symbol,
                        "direction": p.direction.value,
                        "volume": p.volume,
                        "pnl": p.pnl
                    }
                    for p in positions if p.vt_symbol == vt_symbol
                ],
                "active_orders": len([
                    o for o in orders if o.vt_symbol == vt_symbol
                ]),
                "account_balance": accounts[0].balance if accounts else 0,
                "analysis_time": self.tick_counter.get(vt_symbol, 0)
            }
        except Exception as e:
            self.write_log(f"Error getting market context: {e}")
            return {}

    def _fallback_tick_processing(self, tick: TickData) -> None:
        """Fallback simple logic when LLM analysis fails."""
        # Simple threshold-based trading
        if tick.last_price < 60000 and "BTC" in tick.vt_symbol:
            self.generate_signal(
                vt_symbol=tick.vt_symbol,
                direction=Direction.LONG,
                price=tick.last_price,
                volume=0.001,
                agent_id="SimpleThresholdAgent",
                rationale=f"Price {tick.last_price} is below the 60000 threshold."
            )

    def generate_llm_signal(self, signal_data: dict) -> None:
        """Generate signal from LLM analysis."""
        self.generate_signal(
            vt_symbol=signal_data["vt_symbol"],
            direction=signal_data["direction"],
            price=signal_data["price"],
            volume=signal_data["volume"],
            agent_id="LLMThinkingAgent",
            rationale=signal_data["rationale"]
        )

    def generate_signal(
        self,
        vt_symbol: str,
        direction: Direction,
        price: float,
        volume: float,
        agent_id: str,
        rationale: str
    ) -> None:
        """
        Creates and emits an AI signal event.
        """
        signal = SignalData(
            vt_symbol=vt_symbol,
            direction=direction,
            price=price,
            volume=volume,
            agent_id=agent_id,
            rationale=rationale
        )

        self.event_engine.put(EVENT_AI_SIGNAL, signal)
        self.write_log(f"AI Agent [{agent_id}] generated signal: {direction.value} {volume} {vt_symbol} @ {price}")

    def close(self) -> None:
        """
        Stop the engine.
        """
        # Unregister event listeners if needed
        pass
