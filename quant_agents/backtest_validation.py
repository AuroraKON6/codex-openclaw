from __future__ import annotations

import copy
import math
from typing import Any

from .audit import canonical_json_sha256
from .research_engine import run_momentum_backtest


ROBUSTNESS_DECISION = "PASSED"


def run_robustness_validation(
    baseline: dict[str, Any],
    validation_controls: dict[str, Any],
    engine_kwargs: dict[str, Any],
) -> dict[str, Any]:
    equity_curve = baseline.get("equity_curve", [])
    performance_dates = [
        str(row.get("trade_date"))
        for row in equity_curve
        if isinstance(row, dict) and row.get("trade_date")
    ]
    minimum_holdout_days = int(validation_controls["minimum_holdout_trade_days"])
    requested_holdout = math.ceil(
        len(performance_dates) * float(validation_controls["holdout_fraction"])
    )
    holdout_days = max(minimum_holdout_days, requested_holdout)
    if len(performance_dates) < minimum_holdout_days * 2 or holdout_days >= len(
        performance_dates
    ):
        raise ValueError(
            "insufficient performance history for an independent chronological holdout: "
            f"available={len(performance_dates)}, minimum_holdout={minimum_holdout_days}"
        )
    holdout_start = performance_dates[-holdout_days]
    holdout_end = performance_dates[-1]
    development_end = performance_dates[-holdout_days - 1]
    base_cost_model = copy.deepcopy(engine_kwargs["cost_model"])
    thresholds = validation_controls["acceptance_thresholds"]
    scenario_base = dict(engine_kwargs)
    scenario_base["start_date"] = holdout_start
    scenario_base["end_date"] = holdout_end

    scenarios: list[dict[str, Any]] = []
    scenarios.append(
        _run_scenario(
            "holdout_baseline",
            "chronological_holdout",
            scenario_base,
            {
                "cost_multiplier": 1.0,
                "signal_to_execution_lag_trade_days": 1,
            },
        )
    )
    for multiplier in validation_controls["cost_stress_multipliers"]:
        stressed_kwargs = dict(scenario_base)
        stressed_kwargs["cost_model"] = _stressed_cost_model(
            base_cost_model,
            float(multiplier),
        )
        scenarios.append(
            _run_scenario(
                f"holdout_cost_{float(multiplier):g}x",
                "cost_stress",
                stressed_kwargs,
                {
                    "cost_multiplier": float(multiplier),
                    "signal_to_execution_lag_trade_days": 1,
                },
            )
        )
    for delay_days in validation_controls["signal_delay_stress_trade_days"]:
        delayed_kwargs = dict(scenario_base)
        delayed_kwargs["signal_to_execution_lag_trade_days"] = int(delay_days)
        scenarios.append(
            _run_scenario(
                f"holdout_signal_delay_{int(delay_days)}d",
                "signal_delay_stress",
                delayed_kwargs,
                {
                    "cost_multiplier": 1.0,
                    "signal_to_execution_lag_trade_days": int(delay_days),
                },
            )
        )

    scenario_map = {row["scenario_id"]: row for row in scenarios}
    holdout = scenario_map["holdout_baseline"]
    double_cost = next(
        (
            row
            for row in scenarios
            if row["scenario_type"] == "cost_stress"
            and row["assumptions"]["cost_multiplier"] == 2.0
        ),
        None,
    )
    walk_forward = _run_walk_forward_validation(
        performance_dates=performance_dates,
        controls=validation_controls["walk_forward"],
        thresholds=thresholds,
        engine_kwargs=engine_kwargs,
        base_cost_model=base_cost_model,
        signal_delay_days=max(validation_controls["signal_delay_stress_trade_days"]),
    )
    checks = [
        _check(
            "pre_registered_fixed_parameters",
            validation_controls.get("parameter_selection_policy")
            == "pre_registered_no_search"
            and validation_controls.get("parameter_search_count") == 0,
            str(validation_controls.get("hypothesis_id", "UNAVAILABLE")),
        ),
        _check(
            "chronological_holdout_size",
            holdout.get("status") == "completed"
            and int(holdout.get("performance_trade_days", 0)) >= minimum_holdout_days,
            str(holdout.get("performance_trade_days", 0)),
        ),
        _check(
            "holdout_trade_count",
            holdout.get("status") == "completed"
            and int(holdout.get("metrics", {}).get("trade_count", 0))
            >= int(thresholds["minimum_holdout_trade_count"]),
            str(holdout.get("metrics", {}).get("trade_count", "UNAVAILABLE")),
        ),
        _check(
            "holdout_sharpe_threshold",
            holdout.get("status") == "completed"
            and float(holdout.get("metrics", {}).get("sharpe_ratio", -999.0))
            >= float(thresholds["minimum_holdout_sharpe"]),
            str(holdout.get("metrics", {}).get("sharpe_ratio", "UNAVAILABLE")),
        ),
        _check(
            "holdout_drawdown_threshold",
            holdout.get("status") == "completed"
            and float(holdout.get("metrics", {}).get("max_drawdown", -999.0))
            >= float(thresholds["maximum_holdout_drawdown"]),
            str(holdout.get("metrics", {}).get("max_drawdown", "UNAVAILABLE")),
        ),
        _check(
            "double_cost_survival",
            isinstance(double_cost, dict)
            and double_cost.get("status") == "completed"
            and float(double_cost.get("metrics", {}).get("total_return", -999.0))
            >= float(thresholds["minimum_double_cost_total_return"]),
            str(
                double_cost.get("metrics", {}).get("total_return", "UNAVAILABLE")
                if isinstance(double_cost, dict)
                else "UNAVAILABLE"
            ),
        ),
        _check(
            "all_stress_scenarios_completed",
            all(row.get("status") == "completed" for row in scenarios),
            f"{sum(row.get('status') == 'completed' for row in scenarios)}/{len(scenarios)}",
        ),
        _check(
            "walk_forward_all_scenarios_completed",
            walk_forward["all_scenarios_completed"] is True,
            f"{walk_forward['completed_scenario_count']}/{walk_forward['scenario_count']}",
        ),
        _check(
            "walk_forward_minimum_passing_folds",
            walk_forward["decision"] == "PASSED",
            f"{walk_forward['passing_fold_count']}/{walk_forward['fold_count']}",
        ),
    ]
    failed = [row["check_id"] for row in checks if row["status"] != "passed"]
    contract = {
        "hypothesis_id": validation_controls["hypothesis_id"],
        "parameter_selection_policy": validation_controls["parameter_selection_policy"],
        "parameter_search_count": validation_controls["parameter_search_count"],
        "holdout_fraction": validation_controls["holdout_fraction"],
        "minimum_holdout_trade_days": minimum_holdout_days,
        "cost_stress_multipliers": validation_controls["cost_stress_multipliers"],
        "signal_delay_stress_trade_days": validation_controls[
            "signal_delay_stress_trade_days"
        ],
        "walk_forward": validation_controls["walk_forward"],
        "acceptance_thresholds": thresholds,
    }
    return {
        "schema_version": 1,
        "decision": ROBUSTNESS_DECISION if not failed else "FAILED",
        "contract_fingerprint": canonical_json_sha256(contract),
        "contract": contract,
        "chronological_split": {
            "development_start": performance_dates[0],
            "development_end": development_end,
            "holdout_start": holdout_start,
            "holdout_end": holdout_end,
            "development_trade_days": len(performance_dates) - holdout_days,
            "holdout_trade_days": holdout_days,
        },
        "scenario_count": len(scenarios) + walk_forward["scenario_count"],
        "scenarios": scenarios,
        "walk_forward": walk_forward,
        "checks": checks,
        "failed_checks": failed,
        "limitations": [
            "This deterministic backtest artifact alone cannot authenticate preregistration; the run-level research-protocol gate separately binds the exact input and frozen model contract to external evidence.",
            "Walk-forward folds use anchored expanding development windows and non-overlapping evaluation windows, but each evaluation fold resets the simulated portfolio to cash.",
            "Cost and signal-delay stresses are deterministic sensitivity tests, not forecasts of live fills.",
            "Passing thresholds only permits internal research review and does not establish future performance.",
        ],
        "disclaimer": "Robustness evidence is for internal research validation only and is not real-capital trading advice.",
    }


def _run_walk_forward_validation(
    performance_dates: list[str],
    controls: dict[str, Any],
    thresholds: dict[str, Any],
    engine_kwargs: dict[str, Any],
    base_cost_model: dict[str, Any],
    signal_delay_days: int,
) -> dict[str, Any]:
    fold_count = int(controls["fold_count"])
    fold_trade_days = int(controls["fold_trade_days"])
    minimum_development_trade_days = int(
        controls["minimum_development_trade_days"]
    )
    minimum_passing_folds = int(controls["minimum_passing_folds"])
    evaluation_trade_days = fold_count * fold_trade_days
    first_evaluation_index = len(performance_dates) - evaluation_trade_days
    if first_evaluation_index < minimum_development_trade_days:
        raise ValueError(
            "insufficient performance history for walk-forward validation: "
            f"available={len(performance_dates)}, development_required="
            f"{minimum_development_trade_days}, evaluation_required={evaluation_trade_days}"
        )

    folds: list[dict[str, Any]] = []
    for fold_index in range(fold_count):
        evaluation_start_index = first_evaluation_index + fold_index * fold_trade_days
        evaluation_end_index = evaluation_start_index + fold_trade_days - 1
        fold_id = f"walk_forward_{fold_index + 1:02d}"
        fold_kwargs = dict(engine_kwargs)
        fold_kwargs["start_date"] = performance_dates[evaluation_start_index]
        fold_kwargs["end_date"] = performance_dates[evaluation_end_index]

        baseline = _run_scenario(
            f"{fold_id}_baseline",
            "walk_forward_baseline",
            fold_kwargs,
            {
                "fold_id": fold_id,
                "cost_multiplier": 1.0,
                "signal_to_execution_lag_trade_days": 1,
            },
        )
        double_cost_kwargs = dict(fold_kwargs)
        double_cost_kwargs["cost_model"] = _stressed_cost_model(
            base_cost_model,
            2.0,
        )
        double_cost = _run_scenario(
            f"{fold_id}_cost_2x",
            "walk_forward_cost_stress",
            double_cost_kwargs,
            {
                "fold_id": fold_id,
                "cost_multiplier": 2.0,
                "signal_to_execution_lag_trade_days": 1,
            },
        )
        delay_kwargs = dict(fold_kwargs)
        delay_kwargs["signal_to_execution_lag_trade_days"] = signal_delay_days
        delayed = _run_scenario(
            f"{fold_id}_signal_delay_{signal_delay_days}d",
            "walk_forward_signal_delay_stress",
            delay_kwargs,
            {
                "fold_id": fold_id,
                "cost_multiplier": 1.0,
                "signal_to_execution_lag_trade_days": signal_delay_days,
            },
        )
        scenarios = [baseline, double_cost, delayed]
        fold_checks = [
            _check(
                "evaluation_window_size",
                baseline.get("status") == "completed"
                and int(baseline.get("performance_trade_days", 0)) == fold_trade_days,
                str(baseline.get("performance_trade_days", 0)),
            ),
            _check(
                "baseline_trade_count",
                baseline.get("status") == "completed"
                and int(baseline.get("metrics", {}).get("trade_count", 0))
                >= int(thresholds["minimum_holdout_trade_count"]),
                str(baseline.get("metrics", {}).get("trade_count", "UNAVAILABLE")),
            ),
            _check(
                "baseline_sharpe_threshold",
                baseline.get("status") == "completed"
                and float(baseline.get("metrics", {}).get("sharpe_ratio", -999.0))
                >= float(thresholds["minimum_holdout_sharpe"]),
                str(baseline.get("metrics", {}).get("sharpe_ratio", "UNAVAILABLE")),
            ),
            _check(
                "baseline_drawdown_threshold",
                baseline.get("status") == "completed"
                and float(baseline.get("metrics", {}).get("max_drawdown", -999.0))
                >= float(thresholds["maximum_holdout_drawdown"]),
                str(baseline.get("metrics", {}).get("max_drawdown", "UNAVAILABLE")),
            ),
            _check(
                "double_cost_survival",
                double_cost.get("status") == "completed"
                and float(double_cost.get("metrics", {}).get("total_return", -999.0))
                >= float(thresholds["minimum_double_cost_total_return"]),
                str(double_cost.get("metrics", {}).get("total_return", "UNAVAILABLE")),
            ),
            _check(
                "fold_scenarios_completed",
                all(row.get("status") == "completed" for row in scenarios),
                f"{sum(row.get('status') == 'completed' for row in scenarios)}/{len(scenarios)}",
            ),
        ]
        failed_checks = [
            row["check_id"] for row in fold_checks if row["status"] != "passed"
        ]
        folds.append(
            {
                "fold_id": fold_id,
                "decision": "PASSED" if not failed_checks else "FAILED",
                "development_start": performance_dates[0],
                "development_end": performance_dates[evaluation_start_index - 1],
                "development_trade_days": evaluation_start_index,
                "evaluation_start": performance_dates[evaluation_start_index],
                "evaluation_end": performance_dates[evaluation_end_index],
                "evaluation_trade_days": fold_trade_days,
                "scenarios": scenarios,
                "checks": fold_checks,
                "failed_checks": failed_checks,
            }
        )

    scenario_count = sum(len(fold["scenarios"]) for fold in folds)
    completed_scenario_count = sum(
        row.get("status") == "completed"
        for fold in folds
        for row in fold["scenarios"]
    )
    passing_fold_count = sum(fold["decision"] == "PASSED" for fold in folds)
    all_scenarios_completed = completed_scenario_count == scenario_count
    decision = (
        "PASSED"
        if all_scenarios_completed and passing_fold_count >= minimum_passing_folds
        else "FAILED"
    )
    return {
        "schema_version": 1,
        "method": "anchored_expanding_non_overlapping_out_of_time",
        "decision": decision,
        "fold_count": fold_count,
        "fold_trade_days": fold_trade_days,
        "minimum_development_trade_days": minimum_development_trade_days,
        "minimum_passing_folds": minimum_passing_folds,
        "passing_fold_count": passing_fold_count,
        "scenario_count": scenario_count,
        "completed_scenario_count": completed_scenario_count,
        "all_scenarios_completed": all_scenarios_completed,
        "folds": folds,
    }


def _run_scenario(
    scenario_id: str,
    scenario_type: str,
    kwargs: dict[str, Any],
    assumptions: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = run_momentum_backtest(**kwargs)
    except (RuntimeError, ValueError) as exc:
        return {
            "scenario_id": scenario_id,
            "scenario_type": scenario_type,
            "status": "failed",
            "assumptions": assumptions,
            "error": str(exc),
            "metrics": {},
            "performance_trade_days": 0,
        }
    return {
        "scenario_id": scenario_id,
        "scenario_type": scenario_type,
        "status": "completed",
        "assumptions": assumptions,
        "performance_trade_days": len(result.get("equity_curve", [])),
        "metrics": {
            "backtest_period": result.get("backtest_period"),
            "total_return": result.get("total_return"),
            "annualized_return": result.get("annualized_return"),
            "sharpe_ratio": result.get("sharpe_ratio"),
            "max_drawdown": result.get("max_drawdown"),
            "trade_count": result.get("trade_count"),
            "rebalance_count": result.get("rebalance_count"),
            "turnover": result.get("turnover"),
            "total_cost_cny": result.get("cost_summary", {}).get("total_cost_cny"),
            "modeled_performance_drag": result.get("cost_summary", {}).get(
                "modeled_performance_drag"
            ),
        },
    }


def _stressed_cost_model(
    cost_model: dict[str, Any],
    multiplier: float,
) -> dict[str, Any]:
    stressed = copy.deepcopy(cost_model)
    stressed["model_id"] = f"{cost_model['model_id']}-stress-{multiplier:g}x"
    for field in (
        "broker_commission_rate",
        "minimum_commission_cny",
        "slippage_bps",
        "market_impact_bps",
    ):
        stressed[field] = float(stressed[field]) * multiplier
    stressed["cost_assumption_source"] = (
        str(stressed["cost_assumption_source"])
        + f"; deterministic {multiplier:g}x stress"
    )
    return stressed


def _check(check_id: str, passed: bool, evidence: str) -> dict[str, str]:
    return {
        "check_id": check_id,
        "status": "passed" if passed else "failed",
        "evidence": evidence,
    }
