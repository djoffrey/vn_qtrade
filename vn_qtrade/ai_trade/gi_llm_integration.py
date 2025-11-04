"""
Native LLM Integration Module

A lightweight, dependency-free LLM integration for vn_qtrade trading decisions.
This module provides direct LLM API integration without external frameworks.
"""

import os
import sys
import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv

from vnpy_evo.trader.constant import Direction
from vnpy_evo.trader.object import TickData

# Load environment variables from .env file
load_dotenv()


class TradingThinkingAgent:
    """
    Native LLM-driven trading agent.

    A lightweight, dependency-free agent that directly integrates with LLM APIs
    to analyze market data and generate trading decisions.
    """

    def __init__(
        self,
        model_id: str = None,
        api_base: str = None,
        api_key: str = None,
    ):
        """
        Initialize the TradingThinkingAgent with native LLM capabilities.

        Args:
            model_id: LLM model identifier (loaded from .env if not provided)
            api_base: API base URL for OpenAI-compatible LLM (loaded from .env if not provided)
            api_key: API key for the LLM service (loaded from .env if not provided)
        """
        # Load configuration from environment variables
        self.model_id = model_id or os.getenv("LLM_MODEL_ID", "deepseek-chat")
        self.api_base = api_base or os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2000"))
        self.timeout = int(os.getenv("API_TIMEOUT_MS", "60000")) / 1000  # Convert to seconds

        # Print configuration
        print(f"\n{'='*60}")
        print("Native LLM Trading Agent - Configuration")
        print(f"{'='*60}")
        print(f"Model ID: {self.model_id}")
        print(f"API Base: {self.api_base}")
        print(f"API Key: {'*' * (len(self.api_key) - 4) + self.api_key[-4:] if len(self.api_key) > 4 else 'Not set'}")
        print(f"Temperature: {self.temperature}")
        print(f"Max Tokens: {self.max_tokens}")
        print(f"Timeout: {self.timeout}s")
        print(f"{'='*60}\n")

        # Initialize client if possible
        self.client = None
        self.has_api_key = bool(self.api_key and self.api_key != "")

        if self.has_api_key:
            try:
                from openai import AsyncOpenAI
                self.client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.api_base
                )
                print("[TradingThinkingAgent] ✓ LLM client initialized")
            except Exception as e:
                print(f"[TradingThinkingAgent] ⚠ Failed to initialize LLM client: {e}")
                self.has_api_key = False
        else:
            print("[TradingThinkingAgent] ℹ No API key found - using rule-based mode")

        # Market data cache
        self.market_data_cache = {}
        self.thought_history = []

    async def analyze_market_situation(
        self,
        tick: TickData,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Analyze market situation using native LLM integration.

        Args:
            tick: Current market tick data
            context: Additional market context (positions, orders, etc.)

        Returns:
            Analysis result with reasoning and decision
        """
        # Update market data cache
        self.market_data_cache[tick.vt_symbol] = {
            "price": tick.last_price,
            "bid": tick.bid_price_1,
            "ask": tick.ask_price_1,
            "volume": tick.volume,
            "timestamp": tick.datetime
        }

        # Build analysis prompt
        analysis_prompt = self._build_analysis_prompt(tick, context or {})

        try:
            # Use native LLM for analysis
            if self.has_api_key and self.client:
                result = await self._call_llm_analysis(analysis_prompt, context or {})
            else:
                result = await self._fallback_reasoning(analysis_prompt)

            # Store thought in history
            self.thought_history.append({
                "timestamp": datetime.now(),
                "vt_symbol": tick.vt_symbol,
                "analysis": result,
                "price": tick.last_price
            })

            # Limit history size
            max_history = int(os.getenv("COGNITIVE_MAX_THOUGHT_HISTORY", "100"))
            if len(self.thought_history) > max_history:
                self.thought_history = self.thought_history[-max_history:]

            return result

        except Exception as e:
            print(f"[TradingThinkingAgent] Error in analysis: {e}")
            import traceback
            traceback.print_exc()
            return self._get_default_analysis(tick)

    async def _call_llm_analysis(
        self,
        prompt: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call native LLM for market analysis."""
        try:
            # Prepare messages for LLM
            messages = [
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            # Make async LLM call
            response = await self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )

            # Parse LLM response
            llm_response = response.choices[0].message.content

            # Extract JSON from markdown code blocks if present
            import re
            json_match = re.search(r'```(?:json)?\s*\n?({.*?})\n?```', llm_response, re.DOTALL)
            if json_match:
                llm_response = json_match.group(1)

            # Try to parse as JSON
            try:
                import json
                result = json.loads(llm_response)

                # Validate and normalize the result
                if "decision" not in result:
                    result["decision"] = {
                        "action": "hold",
                        "rationale": "No clear signal from LLM",
                        "risk_level": "moderate"
                    }

                result["reasoning_type"] = "native_llm"
                return result

            except json.JSONDecodeError:
                # If not JSON, create structured response
                return {
                    "reasoning_type": "native_llm",
                    "raw_response": llm_response,
                    "decision": {
                        "action": "monitor",
                        "rationale": f"LLM Analysis: {llm_response[:200]}",
                        "risk_level": "moderate"
                    },
                    "confidence": 0.6
                }

        except Exception as e:
            print(f"[TradingThinkingAgent] LLM call failed: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM trading agent."""
        return """你是一个专业的加密货币交易分析专家。

你的任务是基于实时市场数据做出交易决策。请始终以JSON格式返回分析结果，包含以下字段：

{
  "understanding": {
    "market_regime": "趋势类型（trend_up/trend_down/sideways）",
    "confidence": "置信度（0.0-1.0）",
    "key_factors": ["关键因素1", "关键因素2"]
  },
  "decision": {
    "action": "交易动作（buy/sell/hold/monitor）",
    "rationale": "详细理由说明",
    "risk_level": "风险级别（low/moderate/high）",
    "expected_move": "预期走势"
  },
  "confidence": "整体置信度（0.0-1.0）"
}

重要原则：
1. 只在有明确信号时建议买入或卖出
2. 在市场不确定时保持观望
3. 始终考虑风险管理
4. 保持冷静理性，不受情绪影响
5. 回答简洁明了，理由充分
"""

    async def _fallback_reasoning(self, prompt: str) -> Dict[str, Any]:
        """Fallback reasoning when LLM is not available."""
        # Simple rule-based fallback without external dependencies
        return {
            "reasoning_type": "rule_based_fallback",
            "decision": {
                "action": "monitor",
                "rationale": "No API key configured - using rule-based mode",
                "risk_level": "low"
            },
            "confidence": 0.5,
            "understanding": {
                "market_regime": "unknown",
                "confidence": 0.5,
                "key_factors": ["no_data"]
            }
        }

    def _build_analysis_prompt(self, tick: TickData, context: Dict[str, Any]) -> str:
        """Build comprehensive analysis prompt from market data."""
        prompt = f"""
        分析以下加密货币市场数据并做出交易决策：

        当前数据：
        - 交易对: {tick.vt_symbol}
        - 最新价格: {tick.last_price}
        - 买一价: {tick.bid_price_1}
        - 卖一价: {tick.ask_price_1}
        - 成交量: {tick.volume}
        - 时间: {tick.datetime}

        市场上下文：
        {json.dumps(context, ensure_ascii=False, indent=2)}

        请基于以下框架进行分析：
        1. 市场态势理解（趋势、震荡、突破等）
        2. 技术分析（价格行为、成交量、波动率）
        3. 风险评估（潜在损失、最大回撤）
        4. 交易决策（买入、卖出、持有）
        5. 理由说明

        请以JSON格式返回分析结果。
        """
        return prompt

    def _get_default_analysis(self, tick: TickData) -> Dict[str, Any]:
        """Get default analysis when error occurs."""
        return {
            "reasoning_type": "default",
            "decision": {
                "action": "hold",
                "rationale": "分析系统暂时不可用，维持当前状态",
                "risk_level": "moderate"
            }
        }

    def should_trade(self, analysis: Dict[str, Any]) -> bool:
        """Determine if trading action should be taken."""
        decision = analysis.get("decision", {})
        action = decision.get("action", "hold").lower()

        # Only trade on strong signals
        strong_actions = ["buy", "sell", "long", "short"]

        # Check if action is in strong actions
        if action not in strong_actions:
            return False

        # Check confidence threshold
        confidence = analysis.get("confidence", 0.0)
        min_confidence = float(os.getenv("AI_MIN_CONFIDENCE", "0.6"))

        if confidence < min_confidence:
            return False

        # Check risk level
        risk_level = decision.get("risk_level", "").lower()
        if risk_level == "high":
            return False

        return True

    def get_trading_signal(self, analysis: Dict[str, Any], tick: TickData) -> Optional[Dict[str, Any]]:
        """
        Extract trading signal from analysis.

        Returns:
            Trading signal dict or None
        """
        if not self.should_trade(analysis):
            return None

        decision = analysis.get("decision", {})
        action = decision.get("action", "").lower()

        # Map action to direction
        direction_map = {
            "buy": Direction.LONG,
            "long": Direction.LONG,
            "sell": Direction.SHORT,
            "short": Direction.SHORT,
        }

        direction = direction_map.get(action)
        if not direction:
            return None

        # Extract or calculate trade parameters
        price = tick.last_price
        volume = 0.001  # Default volume, should be configurable

        return {
            "vt_symbol": tick.vt_symbol,
            "direction": direction,
            "price": price,
            "volume": volume,
            "rationale": decision.get("rationale", ""),
            "confidence": analysis.get("understanding", {}).get("confidence", 0.5),
            "tqr_score": analysis.get("tqr_score", 0.0),
            "analysis": analysis
        }

    def get_thought_history(self) -> List[Dict[str, Any]]:
        """Get the complete thought history."""
        return self.thought_history

    def clear_history(self):
        """Clear thought history."""
        self.thought_history = []
