from __future__ import annotations

import json
import math
import os
import statistics
from collections import defaultdict
from typing import Any

from .market_rules import (
    board_rule,
    build_policy_snapshot,
    calculate_trade_cost,
    load_market_rulebook,
    policy_for_date,
    quantize_order_shares,
    round_price_to_tick,
    validate_cost_model,
)


def load_market_prices(output_dir: str) -> list[dict[str, Any]]:
    return _load_records(output_dir, "prices.json")


def load_research_membership(output_dir: str) -> list[dict[str, Any]]:
    return _load_records(output_dir, "research_membership.json")


def load_trade_limits(output_dir: str) -> list[dict[str, Any]]:
    return _load_records(output_dir, "limits.json")


def load_suspensions(output_dir: str) -> list[dict[str, Any]]:
    return _load_records(output_dir, "suspensions.json")


def load_snapshot_manifest(output_dir: str) -> dict[str, Any]:
    path = os.path.join(output_dir, "market_data", "snapshot_manifest.json")
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict) or not payload.get("snapshot_id"):
        raise ValueError("market_data/snapshot_manifest.json is invalid")
    return payload


def compute_latest_momentum_signals(
    records: list[dict[str, Any]],
    lookback_days: int = 20,
    limit: int = 20,
    eligible_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    returns_by_code, dates = _prepare_returns(records)
    if len(dates) <= lookback_days:
        raise ValueError(f"need more than {lookback_days} trade dates for momentum signals")
    window = dates[-lookback_days:]
    scores = []
    for code, return_map in returns_by_code.items():
        if eligible_codes is not None and code not in eligible_codes:
            continue
        values = [return_map[date] for date in window if date in return_map]
        if len(values) < math.ceil(lookback_days * 0.7):
            continue
        momentum = _compound(values) - 1.0
        scores.append((code, momentum, len(values)))
    scores.sort(key=lambda item: item[1], reverse=True)
    if not scores:
        raise ValueError("no eligible securities have sufficient momentum history")

    result = []
    denominator = max(len(scores) - 1, 1)
    for rank, (code, momentum, observations) in enumerate(scores[:limit]):
        percentile = 1.0 - rank / denominator
        if percentile >= 0.7:
            classification = "HIGH_SCORE"
        elif percentile <= 0.3:
            classification = "LOW_SCORE"
        else:
            classification = "MID_SCORE"
        result.append(
            {
                "stock": code,
                "factor_score": round(momentum, 6),
                "research_classification": classification,
                "lookback_trade_days": observations,
                "data_as_of": dates[-1],
                "evidence": [
                    "20-trade-day compounded Tushare pct_chg",
                    "latest point-in-time CSI 500 research membership snapshot",
                ],
            }
        )
    return result


def run_momentum_backtest(
    records: list[dict[str, Any]],
    start_date: str,
    end_date: str,
    max_positions: int = 20,
    lookback_days: int = 20,
    rebalance_days: int = 10,
    cost_model: dict[str, Any] | None = None,
    membership_records: list[dict[str, Any]] | None = None,
    limit_records: list[dict[str, Any]] | None = None,
    suspension_records: list[dict[str, Any]] | None = None,
    suspension_source_present: bool = False,
    minimum_daily_amount_cny: float = 50_000_000.0,
    simulation_notional_cny: float = 10_000_000.0,
    max_participation_rate: float = 0.05,
    require_tradeability_data: bool = True,
    execution_price_policy: str = "prior_close_after_signal_lag",
    price_limit_fill_policy: str = "directional_close_conservative",
    order_time_in_force: str = "DAY",
    unfilled_order_policy: str = "cancel_at_session_end_recompute_next_rebalance",
    round_lot_enforced: bool = True,
    t_plus_one_enforced: bool = True,
    signal_to_execution_lag_trade_days: int = 1,
) -> dict[str, Any]:
    if execution_price_policy != "prior_close_after_signal_lag":
        raise ValueError("unsupported execution-price policy")
    if price_limit_fill_policy != "directional_close_conservative":
        raise ValueError("unsupported price-limit fill policy")
    if order_time_in_force != "DAY":
        raise ValueError("unsupported order time-in-force")
    if unfilled_order_policy != "cancel_at_session_end_recompute_next_rebalance":
        raise ValueError("unsupported unfilled-order policy")
    if round_lot_enforced is not True or t_plus_one_enforced is not True:
        raise ValueError("A-share round-lot and T+1 controls must be enabled")
    if not 1 <= int(signal_to_execution_lag_trade_days) <= 5:
        raise ValueError("signal-to-execution lag must be between 1 and 5 trade days")
    normalized_cost_model = validate_cost_model(cost_model)
    rulebook, rulebook_sha256 = load_market_rulebook()
    policy_snapshot = build_policy_snapshot(start_date, end_date, normalized_cost_model)

    returns_by_code, dates = _prepare_returns(records)
    price_map = _price_map(records)
    membership_by_date = _membership_by_date(membership_records or [])
    limits = _limit_map(limit_records or [])
    suspensions = _suspension_map(suspension_records or [])
    if require_tradeability_data and not membership_by_date:
        raise ValueError("point-in-time membership data is required")
    if require_tradeability_data and not limits:
        raise ValueError("daily limit-price data is required")
    if require_tradeability_data and not suspension_source_present:
        raise ValueError("explicit suspension-data source evidence is required")

    dates = [date for date in dates if date <= end_date]
    requested_start_index = next(
        (index for index, date in enumerate(dates) if date >= start_date),
        None,
    )
    if requested_start_index is None:
        raise ValueError("no market dates fall inside the requested backtest period")
    first_performance_index = max(
        requested_start_index,
        lookback_days + int(signal_to_execution_lag_trade_days),
    )
    if len(dates) - first_performance_index < rebalance_days + 1:
        raise ValueError(
            f"insufficient history after warmup: {len(dates) - first_performance_index} "
            f"performance dates; need at least {rebalance_days + 1}"
        )

    capacity_threshold = max(
        minimum_daily_amount_cny,
        simulation_notional_cny / max(max_positions, 1) / max(max_participation_rate, 1e-9),
    )
    current_weights: dict[str, float] = {}
    strategy_returns: list[float] = []
    benchmark_returns: list[float] = []
    turnovers: list[float] = []
    invested_ratios: list[float] = []
    rebalance_count = 0
    executed_order_count = 0
    equity_curve = []
    rebalance_log = []
    cost_ledger = []
    strategy_index = 1.0
    gross_strategy_index = 1.0
    benchmark_index = 1.0
    policy_ids_used: set[str] = set()
    lot_adjustment_count = 0
    lot_zero_fill_count = 0
    total_cost_components: dict[str, float] = defaultdict(float)

    performance_dates = dates[first_performance_index:]
    for day_index in range(first_performance_index, len(dates)):
        trade_date = dates[day_index]
        turnover = 0.0
        transaction_cost_ratio = 0.0
        if (day_index - first_performance_index) % rebalance_days == 0:
            execution_date = dates[day_index - 1]
            lookback_end = day_index - int(signal_to_execution_lag_trade_days)
            lookback = dates[lookback_end - lookback_days : lookback_end]
            policy = policy_for_date(rulebook, execution_date)
            policy_ids_used.add(policy["policy_id"])
            members, membership_as_of = _members_as_of(
                membership_by_date,
                execution_date,
                fallback_codes=set(returns_by_code) if not require_tradeability_data else None,
            )
            blocked_existing = {}
            for code in current_weights:
                reason = _execution_block_reason(
                    code,
                    execution_date,
                    price_map,
                    limits,
                    suspensions,
                    side="S",
                    minimum_amount_cny=0.0,
                    require_limit_data=require_tradeability_data,
                    policy=policy,
                )
                if reason:
                    blocked_existing[code] = reason

            ranked = []
            candidate_blocks: dict[str, str] = {}
            existing_buy_constraints: dict[str, str] = {}
            for code in sorted(members):
                return_map = returns_by_code.get(code, {})
                values = [return_map[date] for date in lookback if date in return_map]
                if len(values) < math.ceil(lookback_days * 0.7):
                    candidate_blocks[code] = "insufficient_lookback_history"
                    continue
                reason = _execution_block_reason(
                    code,
                    execution_date,
                    price_map,
                    limits,
                    suspensions,
                    side="B",
                    minimum_amount_cny=capacity_threshold,
                    require_limit_data=require_tradeability_data,
                    policy=policy,
                )
                if reason and code not in current_weights:
                    candidate_blocks[code] = reason
                    continue
                if reason:
                    existing_buy_constraints[code] = reason
                ranked.append((code, _compound(values) - 1.0))
            ranked.sort(key=lambda item: item[1], reverse=True)

            locked_weight = sum(current_weights.get(code, 0.0) for code in blocked_existing)
            available_slots = max(max_positions - len(blocked_existing), 0)
            selected = [
                code
                for code, _ in ranked
                if code not in blocked_existing
            ][:available_slots]
            residual_weight = max(0.0, 1.0 - locked_weight)
            new_weights = {
                code: current_weights[code]
                for code in blocked_existing
            }
            if selected:
                target_weight = residual_weight / len(selected)
                new_weights.update({code: target_weight for code in selected})
            buy_adjustment_blocks = {}
            for code in selected:
                if (
                    code in existing_buy_constraints
                    and new_weights.get(code, 0.0) > current_weights.get(code, 0.0)
                ):
                    new_weights[code] = current_weights.get(code, 0.0)
                    buy_adjustment_blocks[code] = existing_buy_constraints[code]

            equity_before_cost_cny = simulation_notional_cny * strategy_index
            execution = _execute_weight_rebalance(
                current_weights=current_weights,
                target_weights=new_weights,
                execution_date=execution_date,
                equity_before_cost_cny=equity_before_cost_cny,
                price_map=price_map,
                policy=policy,
                cost_model=normalized_cost_model,
            )
            new_weights = execution["weights"]
            transaction_cost_ratio = execution["total_cost_cny"] / max(
                equity_before_cost_cny,
                1e-12,
            )
            executed_order_count += execution["executed_order_count"]
            lot_adjustment_count += execution["lot_adjustment_count"]
            lot_zero_fill_count += execution["lot_zero_fill_count"]
            for key, value in execution["cost_totals"].items():
                total_cost_components[key] += value

            all_codes = set(current_weights).union(new_weights)
            stock_weight_change = sum(
                abs(new_weights.get(code, 0.0) - current_weights.get(code, 0.0))
                for code in all_codes
            )
            old_cash = max(0.0, 1.0 - sum(current_weights.values()))
            new_cash = max(0.0, 1.0 - sum(new_weights.values()))
            turnover = 0.5 * (stock_weight_change + abs(new_cash - old_cash))
            current_weights = new_weights
            turnovers.append(turnover)
            rebalance_count += 1
            rebalance_log.append(
                {
                    "signal_window_end": lookback[-1],
                    "execution_date": execution_date,
                    "effective_date": trade_date,
                    "membership_as_of": membership_as_of,
                    "selected_codes": selected,
                    "blocked_existing": blocked_existing,
                    "buy_adjustment_blocks": buy_adjustment_blocks,
                    "candidate_block_counts": _count_values(candidate_blocks),
                    "position_count": len(current_weights),
                    "invested_ratio": round(sum(current_weights.values()), 6),
                    "turnover": round(turnover, 6),
                    "execution_policy_id": policy["policy_id"],
                    "executed_order_count": execution["executed_order_count"],
                    "transaction_cost_cny": round(execution["total_cost_cny"], 6),
                    "transaction_cost_ratio": round(transaction_cost_ratio, 10),
                    "cash_after_execution_cny": round(execution["cash_after_cny"], 6),
                }
            )
            cost_ledger.append(
                {
                    "signal_window_end": lookback[-1],
                    "execution_date": execution_date,
                    "effective_date": trade_date,
                    "policy_id": policy["policy_id"],
                    "equity_before_cost_cny": round(equity_before_cost_cny, 6),
                    "orders": execution["orders"],
                    "lot_adjustments": execution["lot_adjustments"],
                    "cost_totals": {
                        key: round(value, 6)
                        for key, value in execution["cost_totals"].items()
                    },
                    "total_cost_cny": round(execution["total_cost_cny"], 6),
                    "cost_ratio": round(transaction_cost_ratio, 10),
                }
            )

        gross_return = sum(
            weight * returns_by_code.get(code, {}).get(trade_date, 0.0)
            for code, weight in current_weights.items()
        )
        strategy_return = gross_return - transaction_cost_ratio
        benchmark_members, _ = _members_as_of(
            membership_by_date,
            trade_date,
            fallback_codes=set(returns_by_code) if not require_tradeability_data else None,
        )
        available_benchmark_returns = [
            returns_by_code[code][trade_date]
            for code in benchmark_members
            if code in returns_by_code and trade_date in returns_by_code[code]
        ]
        benchmark_return = (
            statistics.fmean(available_benchmark_returns)
            if available_benchmark_returns
            else 0.0
        )
        strategy_returns.append(strategy_return)
        benchmark_returns.append(benchmark_return)
        invested_ratios.append(sum(current_weights.values()))
        strategy_index *= 1.0 + strategy_return
        gross_strategy_index *= 1.0 + gross_return
        benchmark_index *= 1.0 + benchmark_return
        if current_weights and 1.0 + strategy_return > 0:
            current_weights = {
                code: weight
                * (1.0 + returns_by_code.get(code, {}).get(trade_date, 0.0))
                / (1.0 + strategy_return)
                for code, weight in current_weights.items()
            }
        equity_curve.append(
            {
                "trade_date": trade_date,
                "strategy_index": round(strategy_index, 8),
                "gross_strategy_index": round(gross_strategy_index, 8),
                "benchmark_index": round(benchmark_index, 8),
                "invested_ratio": round(invested_ratios[-1], 6),
                "transaction_cost_ratio": round(transaction_cost_ratio, 10),
            }
        )

    total_return = strategy_index - 1.0
    benchmark_total = benchmark_index - 1.0
    annualized_return = strategy_index ** (252.0 / len(strategy_returns)) - 1.0
    sharpe_ratio = _sharpe(strategy_returns)
    max_drawdown, drawdown_duration = _max_drawdown(strategy_returns)
    positive = [value for value in strategy_returns if value > 0]
    negative = [value for value in strategy_returns if value < 0]
    win_rate = len(positive) / max(len(positive) + len(negative), 1)
    profit_loss_ratio = (
        statistics.fmean(positive) / abs(statistics.fmean(negative))
        if positive and negative
        else 0.0
    )
    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0.0

    return {
        "backtest_period": {"start": performance_dates[0], "end": performance_dates[-1]},
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized_return, 6),
        "sharpe_ratio": round(sharpe_ratio, 6),
        "max_drawdown": round(max_drawdown, 6),
        "max_drawdown_duration_days": drawdown_duration,
        "win_rate": round(win_rate, 6),
        "profit_loss_ratio": round(profit_loss_ratio, 6),
        "trade_count": executed_order_count,
        "rebalance_count": rebalance_count,
        "turnover": round(sum(turnovers), 6),
        "benchmark_excess_return": round(total_return - benchmark_total, 6),
        "calmar_ratio": round(calmar_ratio, 6),
        "monthly_returns": _monthly_returns(performance_dates, strategy_returns),
        "summary": "Deterministic point-in-time research backtest computed from the saved Tushare snapshot with effective-dated A-share execution rules.",
        "data_mode": "REAL_TUSHARE",
        "methodology": {
            "name": "point_in_time_cross_sectional_momentum",
            "lookback_trade_days": lookback_days,
            "rebalance_trade_days": rebalance_days,
            "max_positions": max_positions,
            "weighting": "equal_weight_with_untradeable_positions_locked",
            "cost_model_id": normalized_cost_model["model_id"],
            "cost_model_type": "structured_effective_dated_order_ledger",
            "signal_lag": (
                f"signals end {int(signal_to_execution_lag_trade_days)} trade day(s) "
                "before execution; returns begin the next trade day"
            ),
            "signal_to_execution_lag_trade_days": int(
                signal_to_execution_lag_trade_days
            ),
            "point_in_time_membership": bool(membership_by_date),
            "benchmark": "daily equal-weight return of point-in-time research membership",
            "execution_price_policy": execution_price_policy,
            "price_limit_fill_policy": price_limit_fill_policy,
            "order_time_in_force": order_time_in_force,
            "unfilled_order_policy": unfilled_order_policy,
            "round_lot_enforced": round_lot_enforced,
            "t_plus_one_enforced": t_plus_one_enforced,
        },
        "tradeability_controls": {
            "daily_limit_prices_required": require_tradeability_data,
            "explicit_suspension_source_present": suspension_source_present,
            "explicit_suspension_record_count": len(suspensions),
            "missing_bar_suspension_fallback": True,
            "price_limit_fill_policy": price_limit_fill_policy,
            "minimum_daily_amount_cny": minimum_daily_amount_cny,
            "capacity_screen_amount_cny": round(capacity_threshold, 2),
            "simulation_notional_cny": simulation_notional_cny,
            "max_participation_rate": max_participation_rate,
            "average_invested_ratio": round(statistics.fmean(invested_ratios), 6),
        },
        "execution_policy_snapshot": policy_snapshot,
        "execution_diagnostics": {
            "rulebook_sha256": rulebook_sha256,
            "policy_ids_used": sorted(policy_ids_used),
            "round_lot_enforced": True,
            "lot_adjustment_count": lot_adjustment_count,
            "lot_zero_fill_count": lot_zero_fill_count,
            "t_plus_one_enforced": True,
            "same_day_round_trip_count": 0,
            "directional_limit_checks": True,
            "cost_ledger_reconciled": _cost_ledger_reconciles(
                cost_ledger,
                total_cost_components,
            ),
        },
        "cost_summary": _build_cost_summary(
            total_cost_components,
            normalized_cost_model,
            strategy_index,
            gross_strategy_index,
            simulation_notional_cny,
        ),
        "limitations": [
            "Index membership is monthly because Tushare index_weight is monthly data.",
            f"Execution is modeled at the prior close with a {int(signal_to_execution_lag_trade_days)}-trade-day signal lag.",
            "Held securities with a missing daily bar are carried at zero return for that date and flagged through the suspension fallback.",
            "Daily bars cannot prove closing-auction queue priority, partial fills, or intraday order-book depth; close-limit fills are blocked conservatively by direction.",
            "Round-lot sizing uses a weight ledger and raw closing prices; full odd-lot exits and corporate-action share counts remain an approximation.",
            "Slippage and market-impact basis points are explicit research assumptions and require mandate-specific calibration before operational reliance.",
            "Results are research diagnostics and are not real-capital trading advice.",
        ],
        "rebalance_log": rebalance_log,
        "cost_ledger": cost_ledger,
        "equity_curve": equity_curve,
    }


def _load_records(output_dir: str, filename: str) -> list[dict[str, Any]]:
    path = os.path.join(output_dir, "market_data", filename)
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"market_data/{filename} does not contain a record list")
    return records


def _prepare_returns(
    records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, float]], list[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        code = str(row.get("ts_code", ""))
        trade_date = str(row.get("trade_date", ""))
        if code and trade_date:
            grouped[code].append(row)

    returns_by_code: dict[str, dict[str, float]] = {}
    all_dates = set()
    for code, rows in grouped.items():
        rows.sort(key=lambda item: str(item.get("trade_date")))
        return_map: dict[str, float] = {}
        previous_close = None
        for row in rows:
            trade_date = str(row["trade_date"])
            pct_chg = _float_or_none(row.get("pct_chg"))
            close = _float_or_none(row.get("qfq_close")) or _float_or_none(row.get("close"))
            if pct_chg is not None:
                daily_return = pct_chg / 100.0
            elif previous_close and close is not None:
                daily_return = close / previous_close - 1.0
            else:
                daily_return = None
            if daily_return is not None and daily_return > -1.0:
                return_map[trade_date] = daily_return
                all_dates.add(trade_date)
            if close is not None:
                previous_close = close
        if return_map:
            returns_by_code[code] = return_map
    return returns_by_code, sorted(all_dates)


def _price_map(records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row.get("ts_code")), str(row.get("trade_date"))): row
        for row in records
        if row.get("ts_code") and row.get("trade_date")
    }


def _membership_by_date(
    records: list[dict[str, Any]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in records:
        trade_date = str(row.get("trade_date", ""))
        code = str(row.get("ts_code", ""))
        if trade_date and code:
            result[trade_date].add(code)
    return dict(result)


def _members_as_of(
    membership_by_date: dict[str, set[str]],
    date: str,
    fallback_codes: set[str] | None,
) -> tuple[set[str], str]:
    eligible_dates = [snapshot for snapshot in membership_by_date if snapshot <= date]
    if eligible_dates:
        snapshot = max(eligible_dates)
        return membership_by_date[snapshot], snapshot
    if fallback_codes is not None:
        return fallback_codes, "ALL_AVAILABLE"
    return set(), "UNAVAILABLE"


def _limit_map(records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float | None]]:
    return {
        (str(row.get("ts_code")), str(row.get("trade_date"))): {
            "up_limit": _float_or_none(row.get("up_limit")),
            "down_limit": _float_or_none(row.get("down_limit")),
        }
        for row in records
        if row.get("ts_code") and row.get("trade_date")
    }


def _suspension_map(records: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("ts_code")), str(row.get("trade_date")))
        for row in records
        if row.get("ts_code") and row.get("trade_date")
    }


def _execute_weight_rebalance(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    execution_date: str,
    equity_before_cost_cny: float,
    price_map: dict[tuple[str, str], dict[str, Any]],
    policy: dict[str, Any],
    cost_model: dict[str, Any],
) -> dict[str, Any]:
    if equity_before_cost_cny <= 0:
        raise ValueError("simulation equity must remain positive")
    weights = dict(current_weights)
    cash_weight = max(0.0, 1.0 - sum(weights.values()))
    orders: list[dict[str, Any]] = []
    lot_adjustments: list[dict[str, Any]] = []
    cost_totals: dict[str, float] = defaultdict(float)
    lot_adjustment_count = 0
    lot_zero_fill_count = 0

    sell_codes = sorted(
        code
        for code in set(current_weights).union(target_weights)
        if current_weights.get(code, 0.0) - target_weights.get(code, 0.0) > 1e-12
    )
    for code in sell_codes:
        old_weight = weights.get(code, 0.0)
        target_weight = target_weights.get(code, 0.0)
        desired_weight = max(old_weight - target_weight, 0.0)
        price, price_rounded = _execution_price(code, execution_date, price_map, policy)
        rule = board_rule(policy, code)
        desired_notional = desired_weight * equity_before_cost_cny
        desired_shares = desired_notional / price
        full_exit = target_weight <= 1e-12
        quantized = quantize_order_shares(desired_shares, rule, full_exit=full_exit)
        if full_exit:
            executed_weight = desired_weight
            executed_notional = desired_notional
            executed_shares: float | int = round(desired_shares, 6)
            order_count = max(
                1,
                math.ceil(desired_shares / int(rule["maximum_limit_order_shares"])),
            )
            share_model = "weight_ledger_full_exit_approximation"
        else:
            executed_shares = quantized["executed_shares"]
            executed_notional = min(float(executed_shares) * price, desired_notional)
            executed_weight = executed_notional / equity_before_cost_cny
            order_count = quantized["order_count"]
            share_model = "round_lot_quantized"
        adjustment = _lot_adjustment_record(
            code,
            "S",
            rule,
            desired_notional,
            executed_notional,
            desired_shares,
            executed_shares,
            full_exit,
        )
        lot_adjustments.append(adjustment)
        if adjustment["unexecuted_notional_cny"] > 1e-6:
            lot_adjustment_count += 1
        if executed_notional <= 0:
            lot_zero_fill_count += 1
            continue
        cost = calculate_trade_cost(
            executed_notional,
            "S",
            order_count,
            policy,
            cost_model,
        )
        weights[code] = max(old_weight - executed_weight, 0.0)
        if weights[code] <= 1e-12:
            weights.pop(code, None)
        cash_weight += executed_weight - cost["total_cost_cny"] / equity_before_cost_cny
        order = {
            "ts_code": code,
            "board": rule["board"],
            "execution_price_cny": price,
            "price_rounded_to_tick": price_rounded,
            "estimated_executed_shares": executed_shares,
            "share_model": share_model,
            **cost,
        }
        orders.append(order)
        _accumulate_costs(cost_totals, cost)

    buy_codes = sorted(
        code
        for code in set(current_weights).union(target_weights)
        if target_weights.get(code, 0.0) - weights.get(code, 0.0) > 1e-12
    )
    for code in buy_codes:
        current_weight = weights.get(code, 0.0)
        target_weight = target_weights.get(code, 0.0)
        desired_weight = max(target_weight - current_weight, 0.0)
        price, price_rounded = _execution_price(code, execution_date, price_map, policy)
        rule = board_rule(policy, code)
        desired_notional = desired_weight * equity_before_cost_cny
        desired_shares = desired_notional / price
        available_cash_cny = max(cash_weight * equity_before_cost_cny, 0.0)
        fitted = _fit_buy_to_cash(
            desired_shares=desired_shares,
            price=price,
            available_cash_cny=available_cash_cny,
            rule=rule,
            policy=policy,
            cost_model=cost_model,
        )
        executed_shares = fitted["executed_shares"]
        executed_notional = float(executed_shares) * price
        adjustment = _lot_adjustment_record(
            code,
            "B",
            rule,
            desired_notional,
            executed_notional,
            desired_shares,
            executed_shares,
            False,
        )
        lot_adjustments.append(adjustment)
        if adjustment["unexecuted_notional_cny"] > 1e-6:
            lot_adjustment_count += 1
        if executed_notional <= 0:
            lot_zero_fill_count += 1
            continue
        cost = fitted["cost"]
        required_cash = executed_notional + cost["total_cost_cny"]
        if required_cash > available_cash_cny + 1e-6:
            raise ValueError("buy affordability calculation exceeded available cash")
        executed_weight = executed_notional / equity_before_cost_cny
        weights[code] = current_weight + executed_weight
        cash_weight -= required_cash / equity_before_cost_cny
        order = {
            "ts_code": code,
            "board": rule["board"],
            "execution_price_cny": price,
            "price_rounded_to_tick": price_rounded,
            "estimated_executed_shares": executed_shares,
            "share_model": "round_lot_quantized",
            **cost,
        }
        orders.append(order)
        _accumulate_costs(cost_totals, cost)

    total_cost = cost_totals.get("total_cost_cny", 0.0)
    return {
        "weights": {code: weight for code, weight in weights.items() if weight > 1e-12},
        "cash_after_cny": max(cash_weight, 0.0) * equity_before_cost_cny,
        "orders": orders,
        "lot_adjustments": lot_adjustments,
        "executed_order_count": sum(int(order["order_count"]) for order in orders),
        "lot_adjustment_count": lot_adjustment_count,
        "lot_zero_fill_count": lot_zero_fill_count,
        "cost_totals": dict(cost_totals),
        "total_cost_cny": total_cost,
    }


def _fit_buy_to_cash(
    desired_shares: float,
    price: float,
    available_cash_cny: float,
    rule: dict[str, Any],
    policy: dict[str, Any],
    cost_model: dict[str, Any],
) -> dict[str, Any]:
    quantized = quantize_order_shares(desired_shares, rule)
    maximum_shares = int(quantized["executed_shares"])
    minimum = int(rule["minimum_order_shares"])
    increment = int(rule["order_increment_shares"])
    maximum_per_order = int(rule["maximum_limit_order_shares"])

    def candidate(step_count: int) -> tuple[int, dict[str, Any]]:
        shares = 0 if step_count <= 0 else minimum + (step_count - 1) * increment
        order_count = math.ceil(shares / maximum_per_order) if shares else 0
        cost = calculate_trade_cost(
            shares * price,
            "B",
            order_count,
            policy,
            cost_model,
        )
        return shares, cost

    if maximum_shares <= 0:
        _, zero_cost = candidate(0)
        return {"executed_shares": 0, "order_count": 0, "cost": zero_cost}
    maximum_steps = (maximum_shares - minimum) // increment + 1
    low = 0
    high = maximum_steps
    while low < high:
        middle = (low + high + 1) // 2
        shares, cost = candidate(middle)
        if shares * price + cost["total_cost_cny"] <= available_cash_cny + 1e-9:
            low = middle
        else:
            high = middle - 1
    shares, cost = candidate(low)
    return {
        "executed_shares": shares,
        "order_count": cost["order_count"],
        "cost": cost,
    }


def _execution_price(
    code: str,
    date: str,
    price_map: dict[tuple[str, str], dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[float, bool]:
    row = price_map.get((code, date))
    close = _float_or_none(row.get("close")) if row else None
    if close is None or close <= 0:
        raise ValueError(f"valid raw closing price is required for {code} on {date}")
    rounded = round_price_to_tick(close, policy)
    return rounded, abs(rounded - close) > 1e-9


def _lot_adjustment_record(
    code: str,
    side: str,
    rule: dict[str, Any],
    desired_notional: float,
    executed_notional: float,
    desired_shares: float,
    executed_shares: float | int,
    full_exit: bool,
) -> dict[str, Any]:
    return {
        "ts_code": code,
        "side": side,
        "board": rule["board"],
        "desired_notional_cny": round(desired_notional, 6),
        "executed_notional_cny": round(executed_notional, 6),
        "unexecuted_notional_cny": round(
            max(desired_notional - executed_notional, 0.0),
            6,
        ),
        "desired_shares": round(desired_shares, 6),
        "executed_shares": executed_shares,
        "minimum_order_shares": rule["minimum_order_shares"],
        "order_increment_shares": rule["order_increment_shares"],
        "full_exit": full_exit,
    }


def _accumulate_costs(totals: dict[str, float], cost: dict[str, Any]) -> None:
    notional_key = "buy_notional_cny" if cost["side"] == "B" else "sell_notional_cny"
    totals[notional_key] += float(cost["trade_notional_cny"])
    for key in (
        "broker_net_commission_cny",
        "exchange_handling_fee_cny",
        "regulatory_fee_cny",
        "commission_minimum_topup_cny",
        "transfer_fee_cny",
        "stamp_duty_cny",
        "slippage_cny",
        "market_impact_cny",
        "total_cost_cny",
    ):
        totals[key] += float(cost[key])


def _cost_ledger_reconciles(
    cost_ledger: list[dict[str, Any]],
    totals: dict[str, float],
) -> bool:
    ledger_total = sum(float(row.get("total_cost_cny", 0.0)) for row in cost_ledger)
    if abs(ledger_total - float(totals.get("total_cost_cny", 0.0))) > 0.01:
        return False
    for row in cost_ledger:
        for order in row.get("orders", []):
            components = sum(
                float(order.get(key, 0.0))
                for key in (
                    "broker_net_commission_cny",
                    "exchange_handling_fee_cny",
                    "regulatory_fee_cny",
                    "transfer_fee_cny",
                    "stamp_duty_cny",
                    "slippage_cny",
                    "market_impact_cny",
                )
            )
            if abs(components - float(order.get("total_cost_cny", 0.0))) > 0.01:
                return False
    return True


def _build_cost_summary(
    totals: dict[str, float],
    cost_model: dict[str, Any],
    net_index: float,
    gross_index: float,
    initial_notional_cny: float,
) -> dict[str, Any]:
    result = {
        "model_id": cost_model["model_id"],
        "broker_commission_quote_mode": cost_model["broker_commission_quote_mode"],
        "broker_commission_rate": cost_model["broker_commission_rate"],
        "minimum_commission_cny": cost_model["minimum_commission_cny"],
        "slippage_bps": cost_model["slippage_bps"],
        "market_impact_bps": cost_model["market_impact_bps"],
        "cost_assumption_source": cost_model["cost_assumption_source"],
    }
    result.update({key: round(float(value), 6) for key, value in totals.items()})
    result["total_cost_as_initial_notional"] = round(
        float(totals.get("total_cost_cny", 0.0)) / max(initial_notional_cny, 1e-12),
        8,
    )
    result["modeled_performance_drag"] = round(gross_index - net_index, 8)
    return result


def _execution_block_reason(
    code: str,
    date: str,
    price_map: dict[tuple[str, str], dict[str, Any]],
    limits: dict[tuple[str, str], dict[str, float | None]],
    suspensions: set[tuple[str, str]],
    side: str,
    minimum_amount_cny: float,
    require_limit_data: bool,
    policy: dict[str, Any],
) -> str | None:
    if (code, date) in suspensions:
        return "explicitly_suspended"
    price = price_map.get((code, date))
    if not price:
        return "suspended_or_missing_daily_bar"
    amount_cny = (_float_or_none(price.get("amount")) or 0.0) * 1000.0
    if amount_cny < minimum_amount_cny:
        return "insufficient_daily_amount"
    limit = limits.get((code, date))
    if require_limit_data and not limit:
        return "missing_limit_price"
    if limit:
        close = _float_or_none(price.get("close"))
        if close is None:
            return "missing_execution_price"
        up_limit = limit.get("up_limit")
        down_limit = limit.get("down_limit")
        tolerance = float(policy["trading"]["price_tick_cny"]) / 2.0
        if side == "B" and up_limit is not None and close >= up_limit - tolerance:
            return "closed_at_up_limit"
        if side == "S" and down_limit is not None and close <= down_limit + tolerance:
            return "closed_at_down_limit"
    return None


def _count_values(values: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values.values():
        counts[value] = counts.get(value, 0) + 1
    return counts


def _compound(values: list[float]) -> float:
    result = 1.0
    for value in values:
        result *= 1.0 + value
    return result


def _sharpe(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    deviation = statistics.stdev(values)
    return statistics.fmean(values) / deviation * math.sqrt(252.0) if deviation else 0.0


def _max_drawdown(values: list[float]) -> tuple[float, int]:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    current_duration = 0
    max_duration = 0
    for value in values:
        equity *= 1.0 + value
        if equity >= peak:
            peak = equity
            current_duration = 0
        else:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
            max_drawdown = min(max_drawdown, equity / peak - 1.0)
    return max_drawdown, max_duration


def _monthly_returns(dates: list[str], values: list[float]) -> list[float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for trade_date, value in zip(dates, values):
        grouped[trade_date[:6]].append(value)
    return [round(_compound(grouped[month]) - 1.0, 6) for month in sorted(grouped)]


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    except (TypeError, ValueError):
        return None
