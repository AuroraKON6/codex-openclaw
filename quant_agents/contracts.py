from __future__ import annotations

import re
from typing import Any


REQUIRED_FIELDS = {
    "research_lead": {
        "macro_summary",
        "sector_trends",
        "risk_factors",
        "research_priorities",
        "trigger_level",
        "confidence",
    },
    "data_agent": {"universe_size", "sample_stocks", "market_stats", "data_quality", "notes"},
    "strategy_agent": {
        "strategy_name",
        "strategy_type",
        "signals",
        "universe_filter",
        "rebalance_frequency",
        "expected_sharpe",
        "max_drawdown_estimate",
        "confidence",
    },
    "backtest_agent": {
        "backtest_period",
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "summary",
    },
    "risk_agent": {"overall_risk_level", "risk_score", "risk_factors", "warnings"},
    "visualization_agent": {"charts", "layout", "summary_visual"},
    "review_agent": {
        "conclusion",
        "trigger_level",
        "key_risks",
        "human_confirmation_needed",
        "next_actions",
        "overall_confidence",
        "disclaimer",
    },
}

_PLACEHOLDER = re.compile(
    r"\b(?:ready|awaiting(?:[_ ]task)?|standing by|pong)\b|(?:等待|待命|已准备好|请提供任务)",
    re.IGNORECASE,
)
_TRADING_ACTION = re.compile(
    r"(?:买入|卖出|加仓|减仓|建仓|清仓|止损|止盈|实盘下单|执行交易|对冲比例)"
    r"|\b(?:buy|sell|go long|go short|reduce exposure|increase exposure|stop[- ]loss|take[- ]profit)\b",
    re.IGNORECASE,
)


class OutputContractError(ValueError):
    pass


def validate_agent_output(agent_name: str, data: Any) -> None:
    if not isinstance(data, dict):
        raise OutputContractError("agent output is not a JSON object")
    required = REQUIRED_FIELDS.get(agent_name, set())
    missing = sorted(required.difference(data))
    if missing:
        raise OutputContractError(f"missing required fields: {', '.join(missing)}")

    searchable = _flatten_strings(data, skip_keys={"disclaimer"})
    if _PLACEHOLDER.search(" ".join(searchable)):
        raise OutputContractError("agent returned a readiness placeholder instead of completing the task")
    if _TRADING_ACTION.search(" ".join(searchable)):
        raise OutputContractError("agent output contains a real-capital trading action")

    if agent_name == "strategy_agent":
        for signal in data.get("signals", []):
            if isinstance(signal, dict) and {"direction", "action", "recommendation"}.intersection(signal):
                raise OutputContractError("strategy signals must be research classifications, not trade directions")

    if agent_name == "risk_agent":
        forbidden_keys = {
            "max_position_size_recommendation",
            "stop_loss_recommendation",
            "hedging_suggestions",
        }
        if forbidden_keys.intersection(data):
            raise OutputContractError("risk output contains real-capital action fields")

    if agent_name == "review_agent":
        review_text = " ".join(
            _flatten_strings(
                {
                    "conclusion": data.get("conclusion", ""),
                    "next_actions": data.get("next_actions", []),
                }
            )
        )
        if _TRADING_ACTION.search(review_text):
            raise OutputContractError("review contains a trading action recommendation")
        disclaimer = str(data.get("disclaimer", ""))
        if "不构成" not in disclaimer and "not" not in disclaimer.lower():
            raise OutputContractError("review disclaimer does not reject real trading advice")


def _flatten_strings(value: Any, skip_keys: set[str] | None = None) -> list[str]:
    skip_keys = skip_keys or set()
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_strings(item, skip_keys))
        return result
    if isinstance(value, dict):
        result = []
        for key, item in value.items():
            if key not in skip_keys:
                result.extend(_flatten_strings(item, skip_keys))
        return result
    return []
