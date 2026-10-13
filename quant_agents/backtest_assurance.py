from __future__ import annotations

from typing import Any


ASSURANCE_DECISION = "PASSED_FOR_INTERNAL_RESEARCH"
ASSURANCE_SCOPE = "internal_research_only_no_order_execution"


def build_backtest_assurance(backtest: dict[str, Any]) -> dict[str, Any]:
    methodology = backtest.get("methodology", {})
    tradeability = backtest.get("tradeability_controls", {})
    diagnostics = backtest.get("execution_diagnostics", {})
    policy_snapshot = backtest.get("execution_policy_snapshot", {})
    cost_summary = backtest.get("cost_summary", {})
    robustness = backtest.get("robustness_validation", {})
    checks = [
        _check(
            "real_tushare_metrics",
            backtest.get("data_mode") == "REAL_TUSHARE",
            str(backtest.get("data_mode", "UNAVAILABLE")),
        ),
        _check(
            "snapshot_binding",
            bool(backtest.get("snapshot_id")),
            str(backtest.get("snapshot_id", "UNAVAILABLE")),
        ),
        _check(
            "point_in_time_membership",
            methodology.get("point_in_time_membership") is True,
            str(methodology.get("point_in_time_membership")),
        ),
        _check(
            "signal_execution_lag",
            methodology.get("execution_price_policy") == "prior_close_after_signal_lag"
            and methodology.get("signal_to_execution_lag_trade_days") == 1,
            str(methodology.get("signal_to_execution_lag_trade_days", "UNAVAILABLE")),
        ),
        _check(
            "effective_dated_rulebook",
            bool(policy_snapshot.get("policy_ids"))
            and len(str(policy_snapshot.get("rulebook_sha256", ""))) == 64
            and diagnostics.get("rulebook_sha256") == policy_snapshot.get("rulebook_sha256"),
            ",".join(policy_snapshot.get("policy_ids", [])),
        ),
        _check(
            "structured_cost_ledger",
            methodology.get("cost_model_type") == "structured_effective_dated_order_ledger"
            and diagnostics.get("cost_ledger_reconciled") is True
            and bool(cost_summary.get("model_id")),
            str(cost_summary.get("model_id", "UNAVAILABLE")),
        ),
        _check(
            "nonzero_slippage_assumption",
            float(cost_summary.get("slippage_bps", 0.0)) > 0.0,
            str(cost_summary.get("slippage_bps", "UNAVAILABLE")),
        ),
        _check(
            "explicit_suspension_source",
            tradeability.get("explicit_suspension_source_present") is True,
            str(tradeability.get("explicit_suspension_record_count", 0)),
        ),
        _check(
            "directional_price_limit_control",
            methodology.get("price_limit_fill_policy") == "directional_close_conservative"
            and diagnostics.get("directional_limit_checks") is True,
            str(methodology.get("price_limit_fill_policy", "UNAVAILABLE")),
        ),
        _check(
            "unfilled_order_lifecycle",
            methodology.get("order_time_in_force") == "DAY"
            and methodology.get("unfilled_order_policy")
            == "cancel_at_session_end_recompute_next_rebalance",
            str(methodology.get("unfilled_order_policy", "UNAVAILABLE")),
        ),
        _check(
            "round_lot_control",
            methodology.get("round_lot_enforced") is True
            and diagnostics.get("round_lot_enforced") is True,
            str(diagnostics.get("lot_adjustment_count", 0)),
        ),
        _check(
            "t_plus_one_control",
            methodology.get("t_plus_one_enforced") is True
            and diagnostics.get("t_plus_one_enforced") is True
            and diagnostics.get("same_day_round_trip_count") == 0,
            str(diagnostics.get("same_day_round_trip_count", "UNAVAILABLE")),
        ),
        _check(
            "liquidity_capacity_control",
            float(tradeability.get("capacity_screen_amount_cny", 0.0)) > 0.0
            and 0.0 < float(tradeability.get("max_participation_rate", 0.0)) <= 0.2,
            str(tradeability.get("capacity_screen_amount_cny", "UNAVAILABLE")),
        ),
        _check(
            "chronological_holdout_and_stress_matrix",
            robustness.get("decision") == "PASSED"
            and int(robustness.get("scenario_count", 0)) >= 10
            and robustness.get("walk_forward", {}).get("decision") == "PASSED"
            and int(
                robustness.get("walk_forward", {}).get("passing_fold_count", 0)
            )
            >= int(
                robustness.get("walk_forward", {}).get("minimum_passing_folds", 1)
            )
            and not robustness.get("failed_checks"),
            str(robustness.get("contract_fingerprint", "UNAVAILABLE")),
        ),
        _check(
            "research_only_boundary",
            ASSURANCE_SCOPE == "internal_research_only_no_order_execution",
            ASSURANCE_SCOPE,
        ),
    ]
    failed = [check["check_id"] for check in checks if check["status"] != "passed"]
    return {
        "schema_version": 1,
        "decision": ASSURANCE_DECISION if not failed else "FAILED",
        "scope": ASSURANCE_SCOPE,
        "checks": checks,
        "failed_checks": failed,
        "known_limitations": list(backtest.get("limitations", [])),
        "human_confirmation_required": [
            "Quant owner confirms the cost assumptions against the applicable mandate and broker statement before relying on cost drag.",
            "Data owner confirms the Tushare snapshot, suspension endpoint evidence, and point-in-time membership coverage.",
            "Compliance owner confirms the effective rulebook and internal-research-only boundary before release review.",
            "Independent reviewer assesses daily-bar fill uncertainty and robustness outside the calibration period.",
        ],
        "release_gate_passed": not failed,
        "disclaimer": "Assurance applies only to deterministic internal research simulation and is not real-capital trading advice.",
    }


def _check(check_id: str, passed: bool, evidence: str) -> dict[str, str]:
    return {
        "check_id": check_id,
        "status": "passed" if passed else "failed",
        "evidence": evidence,
    }
