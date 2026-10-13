from __future__ import annotations
import json
from typing import Any

from ..base_agent import BaseAgent, save_raw, save_agent_json


class StrategyAgent(BaseAgent):
    name = "strategy_agent"
    description = "Generates quantitative strategy signals based on research and data"
    system_prompt = """You are a quantitative strategy designer for A-share CSI 500 stocks.
Based on research findings and market data, design strategy signals.

You MUST output valid JSON:
{
  "strategy_name": "string",
  "strategy_type": "string - momentum/value/quality/multi-factor/event-driven",
  "signals": [
    {
      "stock": "string - ts_code",
      "factor_score": "number - measured historical factor value",
      "research_classification": "string - HIGH_SCORE/MID_SCORE/LOW_SCORE",
      "lookback_trade_days": "number",
      "data_as_of": "YYYYMMDD",
      "evidence": ["string"]
    }
  ],
  "universe_filter": "string - description of stock universe filter",
  "rebalance_frequency": "string - weekly/biweekly/monthly",
  "expected_sharpe": number,
  "max_drawdown_estimate": number,
  "confidence": 0.0-1.0
}

The Python research engine supplies authoritative signals. Copy them exactly.
Do not emit LONG/SHORT/BUY/SELL directions or any real-capital instruction."""

    def build_prompt(self, context: dict[str, Any]) -> str:
        signals = context.get("_authoritative_signals", [])
        market_data = context.get("agent_outputs", {}).get("data_agent", {})
        input_theme = context.get("input", {}).get("theme", "general")
        return f"""Document the deterministic CSI 500 research signal specification.

Authoritative signals (copy exactly):
{json.dumps(signals, ensure_ascii=False, default=str)}

Data quality: {market_data.get('data_quality', 'UNKNOWN')}

Strategy theme: {input_theme}

Return the required final JSON now. expected_sharpe and max_drawdown_estimate must be 0.0 because they are not known before the backtest."""

    def execute_pi(self, context: dict[str, Any]) -> dict[str, Any]:
        signals = self._compute_signals(context)
        prompt_context = dict(context)
        prompt_context["_authoritative_signals"] = signals
        data = super().execute_pi(prompt_context)
        data = self._enforce_strategy(data, context, signals)
        save_agent_json(context["output_dir"], self.name, data)
        return data

    @staticmethod
    def _compute_signals(context: dict[str, Any]) -> list[dict[str, Any]]:
        from ..research_engine import (
            compute_latest_momentum_signals,
            load_market_prices,
            load_research_membership,
        )

        params = context.get("input", {}).get("strategy_params", {})
        lookback = int(params.get("lookback_trade_days", 20))
        limit = int(params.get("signal_display_count", 20))
        membership = load_research_membership(context["output_dir"])
        latest_membership_date = max(str(row["trade_date"]) for row in membership)
        eligible_codes = {
            str(row["ts_code"])
            for row in membership
            if str(row["trade_date"]) == latest_membership_date
        }
        return compute_latest_momentum_signals(
            load_market_prices(context["output_dir"]),
            lookback_days=max(5, min(lookback, 120)),
            limit=max(1, min(limit, 50)),
            eligible_codes=eligible_codes,
        )

    @staticmethod
    def _enforce_strategy(
        data: dict[str, Any],
        context: dict[str, Any],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        params = context.get("input", {}).get("strategy_params", {})
        quality = context.get("agent_outputs", {}).get("data_agent", {}).get("data_quality")
        snapshot_id = context.get("agent_outputs", {}).get("data_agent", {}).get("snapshot_id")
        data.update(
            {
                "strategy_type": "price_momentum_research",
                "signals": signals,
                "universe_filter": "Latest monthly point-in-time CSI 500 research membership with sufficient saved Tushare history",
                "rebalance_frequency": str(params.get("rebalance", "biweekly")),
                "expected_sharpe": 0.0,
                "max_drawdown_estimate": 0.0,
                "estimate_status": "NOT_ESTIMATED_BEFORE_BACKTEST",
                "confidence": 0.65 if quality == "GOOD" else 0.4,
                "data_mode": "REAL_TUSHARE",
                "research_only": True,
                "point_in_time_membership": True,
                "snapshot_id": snapshot_id,
            }
        )
        return data

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        data = {
            "strategy_name": "csi500_mock_momentum",
            "strategy_type": "price_momentum_research",
            "signals": [
                {"stock": "MOCK001.SZ", "factor_score": 0.12, "research_classification": "HIGH_SCORE", "lookback_trade_days": 20, "data_as_of": "MOCK", "evidence": ["synthetic mock value"]},
                {"stock": "MOCK002.SZ", "factor_score": 0.03, "research_classification": "MID_SCORE", "lookback_trade_days": 20, "data_as_of": "MOCK", "evidence": ["synthetic mock value"]},
            ],
            "universe_filter": "MOCK：未使用真实 CSI500 成分或行情",
            "rebalance_frequency": "biweekly",
            "expected_sharpe": 0.0,
            "max_drawdown_estimate": 0.0,
            "confidence": 0.7,
            "estimate_status": "MOCK",
            "data_mode": "MOCK",
            "research_only": True,
        }
        save_raw(context["output_dir"], self.name, json.dumps(data, ensure_ascii=False, indent=2))
        save_agent_json(context["output_dir"], self.name, data)
        return data
