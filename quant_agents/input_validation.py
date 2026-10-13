from __future__ import annotations

from datetime import datetime
from typing import Any

from .governance import validate_governance_input
from .market_rules import build_policy_snapshot, validate_cost_model


SUPPORTED_FACTORS = {"momentum"}


def validate_research_input(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    validate_governance_input(payload)
    if str(payload.get("scope", "CSI500")).upper() != "CSI500":
        raise ValueError("this pipeline currently supports scope=CSI500 only")

    date_range = payload.get("date_range")
    if not isinstance(date_range, dict):
        raise ValueError("date_range is required")
    since = _parse_date(date_range.get("since"), "date_range.since")
    until = _parse_date(date_range.get("until"), "date_range.until")
    if since >= until:
        raise ValueError("date_range.since must be before date_range.until")
    if (until - since).days < 60:
        raise ValueError("date range must span at least 60 calendar days")

    params = payload.get("strategy_params", {})
    if not isinstance(params, dict):
        raise ValueError("strategy_params must be a JSON object")
    factors = {str(value).lower() for value in params.get("factors", ["momentum"])}
    unsupported = sorted(factors.difference(SUPPORTED_FACTORS))
    if unsupported:
        raise ValueError(
            "unsupported factors for deterministic backtest: "
            f"{', '.join(unsupported)}; currently supported: momentum"
        )
    max_positions = int(params.get("max_positions", 20))
    if not 1 <= max_positions <= 50:
        raise ValueError("strategy_params.max_positions must be between 1 and 50")
    research_universe_size = int(
        params.get("research_universe_size", max(30, max_positions * 2))
    )
    if research_universe_size < max_positions or research_universe_size > 60:
        raise ValueError(
            "strategy_params.research_universe_size must be between max_positions and 60"
        )
    if "transaction_cost_rate" in params:
        raise ValueError(
            "strategy_params.transaction_cost_rate is a prohibited legacy flat-cost field; "
            "use execution_controls.cost_model"
        )
    lookback_trade_days = int(params.get("lookback_trade_days", 20))
    if not 5 <= lookback_trade_days <= 120:
        raise ValueError(
            "strategy_params.lookback_trade_days must be between 5 and 120"
        )
    if str(params.get("rebalance", "biweekly")).lower() not in {
        "weekly",
        "biweekly",
        "monthly",
    }:
        raise ValueError(
            "strategy_params.rebalance must be weekly, biweekly, or monthly"
        )

    data_controls = payload.get("data_controls", {})
    if not isinstance(data_controls, dict):
        raise ValueError("data_controls must be a JSON object")
    minimum_quality = str(data_controls.get("minimum_data_quality", "GOOD")).upper()
    if minimum_quality not in {"GOOD", "PARTIAL"}:
        raise ValueError("data_controls.minimum_data_quality must be GOOD or PARTIAL")
    max_staleness = int(data_controls.get("max_staleness_trade_days", 0))
    if not 0 <= max_staleness <= 5:
        raise ValueError("data_controls.max_staleness_trade_days must be between 0 and 5")

    execution_controls = payload.get("execution_controls", {})
    if not isinstance(execution_controls, dict):
        raise ValueError("execution_controls must be a JSON object")
    if execution_controls.get("require_tradeability_data", True) is not True:
        raise ValueError("execution_controls.require_tradeability_data must be true")
    minimum_amount = float(
        execution_controls.get("minimum_daily_amount_cny", 50_000_000)
    )
    if not 0 <= minimum_amount <= 10_000_000_000:
        raise ValueError("execution_controls.minimum_daily_amount_cny is out of range")
    notional = float(execution_controls.get("simulation_notional_cny", 10_000_000))
    if not 0 < notional <= 10_000_000_000:
        raise ValueError("execution_controls.simulation_notional_cny is out of range")
    participation = float(execution_controls.get("max_participation_rate", 0.05))
    if not 0 < participation <= 0.2:
        raise ValueError("execution_controls.max_participation_rate must be in (0, 0.2]")
    if execution_controls.get("execution_price_policy") != "prior_close_after_signal_lag":
        raise ValueError(
            "execution_controls.execution_price_policy must be prior_close_after_signal_lag"
        )
    if execution_controls.get("price_limit_fill_policy") != "directional_close_conservative":
        raise ValueError(
            "execution_controls.price_limit_fill_policy must be directional_close_conservative"
        )
    if execution_controls.get("order_time_in_force") != "DAY":
        raise ValueError("execution_controls.order_time_in_force must be DAY")
    if (
        execution_controls.get("unfilled_order_policy")
        != "cancel_at_session_end_recompute_next_rebalance"
    ):
        raise ValueError(
            "execution_controls.unfilled_order_policy must be "
            "cancel_at_session_end_recompute_next_rebalance"
        )
    if execution_controls.get("round_lot_enforced") is not True:
        raise ValueError("execution_controls.round_lot_enforced must be true")
    if execution_controls.get("t_plus_one_enforced") is not True:
        raise ValueError("execution_controls.t_plus_one_enforced must be true")
    cost_model = validate_cost_model(execution_controls.get("cost_model"))
    build_policy_snapshot(
        since.strftime("%Y%m%d"),
        until.strftime("%Y%m%d"),
        cost_model,
    )

    validation_controls = payload.get("validation_controls")
    if not isinstance(validation_controls, dict):
        raise ValueError("validation_controls is required and must be a JSON object")
    hypothesis_id = str(validation_controls.get("hypothesis_id", "")).strip()
    if not hypothesis_id or len(hypothesis_id) > 100:
        raise ValueError("validation_controls.hypothesis_id is invalid")
    if (
        validation_controls.get("parameter_selection_policy")
        != "pre_registered_no_search"
    ):
        raise ValueError(
            "validation_controls.parameter_selection_policy must be pre_registered_no_search"
        )
    if validation_controls.get("parameter_search_count") != 0:
        raise ValueError("validation_controls.parameter_search_count must be 0")
    holdout_fraction = float(validation_controls.get("holdout_fraction", 0.0))
    if not 0.2 <= holdout_fraction <= 0.5:
        raise ValueError("validation_controls.holdout_fraction must be between 0.2 and 0.5")
    minimum_holdout_days = int(
        validation_controls.get("minimum_holdout_trade_days", 0)
    )
    if not 15 <= minimum_holdout_days <= 120:
        raise ValueError(
            "validation_controls.minimum_holdout_trade_days must be between 15 and 120"
        )
    cost_multipliers = validation_controls.get("cost_stress_multipliers")
    if (
        not isinstance(cost_multipliers, list)
        or not cost_multipliers
        or len(cost_multipliers) > 4
    ):
        raise ValueError("validation_controls.cost_stress_multipliers is invalid")
    normalized_cost_multipliers = sorted({float(value) for value in cost_multipliers})
    if (
        normalized_cost_multipliers != [float(value) for value in cost_multipliers]
        or any(value <= 1.0 or value > 5.0 for value in normalized_cost_multipliers)
        or 2.0 not in normalized_cost_multipliers
    ):
        raise ValueError(
            "validation_controls.cost_stress_multipliers must be sorted unique values in "
            "(1, 5] and include 2.0"
        )
    delay_days = validation_controls.get("signal_delay_stress_trade_days")
    if not isinstance(delay_days, list) or not delay_days or len(delay_days) > 3:
        raise ValueError(
            "validation_controls.signal_delay_stress_trade_days is invalid"
        )
    normalized_delays = sorted({int(value) for value in delay_days})
    if (
        normalized_delays != [int(value) for value in delay_days]
        or any(value < 2 or value > 5 for value in normalized_delays)
    ):
        raise ValueError(
            "validation_controls.signal_delay_stress_trade_days must be sorted unique "
            "values between 2 and 5"
        )
    thresholds = validation_controls.get("acceptance_thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("validation_controls.acceptance_thresholds is required")
    required_thresholds = {
        "minimum_holdout_trade_count",
        "minimum_holdout_sharpe",
        "maximum_holdout_drawdown",
        "minimum_double_cost_total_return",
    }
    missing_thresholds = sorted(required_thresholds.difference(thresholds))
    if missing_thresholds:
        raise ValueError(
            "validation_controls.acceptance_thresholds missing fields: "
            + ", ".join(missing_thresholds)
        )
    minimum_trades = int(thresholds["minimum_holdout_trade_count"])
    minimum_sharpe = float(thresholds["minimum_holdout_sharpe"])
    maximum_drawdown = float(thresholds["maximum_holdout_drawdown"])
    minimum_double_cost_return = float(thresholds["minimum_double_cost_total_return"])
    if not 1 <= minimum_trades <= 100:
        raise ValueError("minimum_holdout_trade_count must be between 1 and 100")
    if not -5.0 <= minimum_sharpe <= 5.0:
        raise ValueError("minimum_holdout_sharpe must be between -5 and 5")
    if not -1.0 <= maximum_drawdown <= 0.0:
        raise ValueError("maximum_holdout_drawdown must be between -1 and 0")
    if not -1.0 <= minimum_double_cost_return <= 1.0:
        raise ValueError("minimum_double_cost_total_return must be between -1 and 1")

    walk_forward = validation_controls.get("walk_forward")
    if not isinstance(walk_forward, dict):
        raise ValueError("validation_controls.walk_forward is required")
    fold_count = int(walk_forward.get("fold_count", 0))
    fold_trade_days = int(walk_forward.get("fold_trade_days", 0))
    minimum_development_trade_days = int(
        walk_forward.get("minimum_development_trade_days", 0)
    )
    minimum_passing_folds = int(walk_forward.get("minimum_passing_folds", 0))
    if not 2 <= fold_count <= 6:
        raise ValueError("walk_forward.fold_count must be between 2 and 6")
    if not minimum_holdout_days <= fold_trade_days <= 120:
        raise ValueError(
            "walk_forward.fold_trade_days must be between minimum_holdout_trade_days and 120"
        )
    if not lookback_trade_days <= minimum_development_trade_days <= 252:
        raise ValueError(
            "walk_forward.minimum_development_trade_days must be between "
            "lookback_trade_days and 252"
        )
    required_passing_folds = (fold_count * 2 + 2) // 3
    if not required_passing_folds <= minimum_passing_folds <= fold_count:
        raise ValueError(
            "walk_forward.minimum_passing_folds must be at least two-thirds of folds"
        )
    required_performance_trade_days = (
        minimum_development_trade_days + fold_count * fold_trade_days
    )
    minimum_calendar_days = (required_performance_trade_days * 3 + 1) // 2
    if (until - since).days < minimum_calendar_days:
        raise ValueError(
            "date range is too short for the declared walk-forward contract: "
            f"need at least {minimum_calendar_days} calendar days"
        )


def _parse_date(value: Any, field: str) -> datetime:
    text = str(value or "").replace("-", "")
    try:
        return datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYYMMDD or YYYY-MM-DD") from exc
