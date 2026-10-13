from __future__ import annotations
import json
import os
from typing import Any

from ..audit import write_json_atomic
from ..backtest_assurance import build_backtest_assurance
from ..backtest_validation import run_robustness_validation
from ..base_agent import BaseAgent, save_raw, save_agent_json


class BacktestAgent(BaseAgent):
    name = "backtest_agent"
    description = "Reviews deterministic research backtest metrics"
    system_prompt = """You are a backtesting analyst for A-share quantitative strategies.
The Python research engine has already computed the backtest. Review the supplied metrics without changing them.

You MUST output valid JSON:
{
  "backtest_period": {"start": "string", "end": "string"},
  "total_return": number,
  "annualized_return": number,
  "sharpe_ratio": number,
  "max_drawdown": number,
  "max_drawdown_duration_days": number,
  "win_rate": number,
  "profit_loss_ratio": number,
  "trade_count": number,
  "turnover": number,
  "benchmark_excess_return": number,
  "calmar_ratio": number,
  "monthly_returns": [number],
  "summary": "string - brief interpretation"
}

Do not invent, estimate, or recalculate any metric. Do not provide real-capital instructions."""

    def build_prompt(self, context: dict[str, Any]) -> str:
        computed = context.get("_computed_backtest", {})
        excluded = {
            "equity_curve",
            "cost_ledger",
            "rebalance_log",
            "execution_policy_snapshot",
        }
        compact = {key: value for key, value in computed.items() if key not in excluded}
        return f"""Review this deterministic CSI 500 research backtest.

Authoritative computed metrics (copy all values exactly):
{json.dumps(compact, ensure_ascii=False, default=str)}

Return the required final JSON object now. The summary may interpret limitations only."""

    def execute_pi(self, context: dict[str, Any]) -> dict[str, Any]:
        computed = self._compute_backtest(context)
        prompt_context = dict(context)
        prompt_context["_computed_backtest"] = computed
        data = super().execute_pi(prompt_context)
        data = self._enforce_computed(data, computed)
        self._save_backtest(context["output_dir"], data)
        save_agent_json(context["output_dir"], self.name, data)
        return data

    @staticmethod
    def _compute_backtest(context: dict[str, Any]) -> dict[str, Any]:
        from ..research_engine import (
            load_market_prices,
            load_research_membership,
            load_suspensions,
            load_snapshot_manifest,
            load_trade_limits,
            run_momentum_backtest,
        )

        params = context.get("input", {}).get("strategy_params", {})
        controls = context.get("input", {}).get("execution_controls", {})
        rebalance = str(params.get("rebalance", "biweekly")).lower()
        rebalance_days = {"weekly": 5, "biweekly": 10, "monthly": 20}.get(rebalance, 10)
        date_range = context.get("date_range", {})
        prices = load_market_prices(context["output_dir"])
        membership = load_research_membership(context["output_dir"])
        limits = load_trade_limits(context["output_dir"])
        suspensions = load_suspensions(context["output_dir"])
        engine_kwargs = {
            "records": prices,
            "start_date": str(date_range.get("since", "")).replace("-", ""),
            "end_date": str(date_range.get("until", "")).replace("-", ""),
            "max_positions": max(1, min(int(params.get("max_positions", 20)), 50)),
            "lookback_days": max(
                5,
                min(int(params.get("lookback_trade_days", 20)), 120),
            ),
            "rebalance_days": rebalance_days,
            "cost_model": controls.get("cost_model"),
            "membership_records": membership,
            "limit_records": limits,
            "suspension_records": suspensions,
            "suspension_source_present": os.path.isfile(
                os.path.join(context["output_dir"], "market_data", "suspensions.json")
            ),
            "minimum_daily_amount_cny": float(
                controls.get("minimum_daily_amount_cny", 50_000_000)
            ),
            "simulation_notional_cny": float(
                controls.get("simulation_notional_cny", 10_000_000)
            ),
            "max_participation_rate": float(
                controls.get("max_participation_rate", 0.05)
            ),
            "require_tradeability_data": bool(
                controls.get("require_tradeability_data", True)
            ),
            "execution_price_policy": str(
                controls.get("execution_price_policy", "")
            ),
            "price_limit_fill_policy": str(
                controls.get("price_limit_fill_policy", "")
            ),
            "order_time_in_force": str(controls.get("order_time_in_force", "")),
            "unfilled_order_policy": str(
                controls.get("unfilled_order_policy", "")
            ),
            "round_lot_enforced": controls.get("round_lot_enforced") is True,
            "t_plus_one_enforced": controls.get("t_plus_one_enforced") is True,
            "signal_to_execution_lag_trade_days": 1,
        }
        result = run_momentum_backtest(**engine_kwargs)
        result["snapshot_id"] = load_snapshot_manifest(context["output_dir"])["snapshot_id"]
        result["robustness_validation"] = run_robustness_validation(
            baseline=result,
            validation_controls=context.get("input", {}).get("validation_controls", {}),
            engine_kwargs=engine_kwargs,
        )
        result["backtest_assurance"] = build_backtest_assurance(result)
        return result

    @staticmethod
    def _enforce_computed(data: dict[str, Any], computed: dict[str, Any]) -> dict[str, Any]:
        llm_summary = data.get("summary")
        data.update(computed)
        if isinstance(llm_summary, str) and llm_summary.strip():
            data["llm_review"] = llm_summary.strip()
        return data

    def _save_backtest(self, output_dir: str, data: dict):
        bt_dir = os.path.join(output_dir, "backtest")
        os.makedirs(bt_dir, exist_ok=True)
        write_json_atomic(os.path.join(bt_dir, f"{self.name}.json"), data)
        write_json_atomic(
            os.path.join(bt_dir, "cost_ledger.json"),
            {
                "schema_version": 1,
                "data_mode": data.get("data_mode"),
                "snapshot_id": data.get("snapshot_id"),
                "cost_summary": data.get("cost_summary", {}),
                "records": data.get("cost_ledger", []),
            },
        )
        write_json_atomic(
            os.path.join(bt_dir, "execution_policy.json"),
            data.get("execution_policy_snapshot", {}),
        )
        write_json_atomic(
            os.path.join(bt_dir, "backtest_assurance.json"),
            data.get("backtest_assurance", {}),
        )
        write_json_atomic(
            os.path.join(bt_dir, "robustness_validation.json"),
            data.get("robustness_validation", {}),
        )

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        data = {
            "backtest_period": {"start": "2025-01-01", "end": "2025-05-30"},
            "total_return": 0.087, "annualized_return": 0.21, "sharpe_ratio": 1.35,
            "max_drawdown": -0.082, "max_drawdown_duration_days": 18, "win_rate": 0.62,
            "profit_loss_ratio": 1.8, "trade_count": 45, "turnover": 2.3,
            "benchmark_excess_return": 0.052, "calmar_ratio": 2.56,
            "monthly_returns": [0.021, 0.015, -0.008, 0.032, 0.027],
            "summary": "MOCK：指标为合成验收数据，不代表任何真实市场表现。",
            "data_mode": "MOCK",
            "methodology": {"name": "synthetic_mock"},
            "tradeability_controls": {"mode": "MOCK"},
            "cost_summary": {"mode": "MOCK"},
            "execution_policy_snapshot": {"mode": "MOCK"},
            "backtest_assurance": {
                "schema_version": 1,
                "decision": "NOT_APPLICABLE_MOCK",
                "scope": "software_regression_only",
                "checks": [],
                "failed_checks": ["real_tushare_metrics"],
                "release_gate_passed": False,
                "disclaimer": "MOCK assurance is not market research or real-capital trading advice.",
            },
            "robustness_validation": {
                "schema_version": 1,
                "decision": "NOT_APPLICABLE_MOCK",
                "scenario_count": 0,
                "scenarios": [],
                "walk_forward": {
                    "decision": "NOT_APPLICABLE_MOCK",
                    "fold_count": 0,
                    "passing_fold_count": 0,
                },
                "failed_checks": ["real_tushare_metrics"],
                "disclaimer": "MOCK robustness output is not market evidence.",
            },
            "limitations": ["MOCK: no market data was used."],
            "rebalance_log": [],
            "cost_ledger": [],
            "equity_curve": [],
        }
        self._save_backtest(context["output_dir"], data)
        save_raw(context["output_dir"], self.name, json.dumps(data, ensure_ascii=False, indent=2))
        save_agent_json(context["output_dir"], self.name, data)
        return data
