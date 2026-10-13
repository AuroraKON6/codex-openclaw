from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


RULEBOOK_PATH = Path(__file__).resolve().parents[1] / "governance" / "a_share_market_rules.json"
SUPPORTED_COMMISSION_QUOTE_MODES = {"all_in_regulatory", "net_plus_regulatory"}


def load_market_rulebook(path: str | Path | None = None) -> tuple[dict[str, Any], str]:
    rulebook_path = Path(path) if path is not None else RULEBOOK_PATH
    raw = rulebook_path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    _validate_rulebook(payload)
    return payload, hashlib.sha256(raw).hexdigest()


def validate_cost_model(cost_model: Any) -> dict[str, Any]:
    if not isinstance(cost_model, dict):
        raise ValueError("execution_controls.cost_model is required and must be a JSON object")
    required = {
        "model_id",
        "broker_commission_quote_mode",
        "broker_commission_rate",
        "minimum_commission_cny",
        "slippage_bps",
        "market_impact_bps",
        "cost_assumption_source",
    }
    missing = sorted(required.difference(cost_model))
    if missing:
        raise ValueError(
            "execution_controls.cost_model missing fields: " + ", ".join(missing)
        )
    model_id = str(cost_model["model_id"]).strip()
    assumption_source = str(cost_model["cost_assumption_source"]).strip()
    quote_mode = str(cost_model["broker_commission_quote_mode"]).strip()
    if not model_id or len(model_id) > 80:
        raise ValueError("execution_controls.cost_model.model_id is invalid")
    if not assumption_source or len(assumption_source) > 200:
        raise ValueError("execution_controls.cost_model.cost_assumption_source is invalid")
    if quote_mode not in SUPPORTED_COMMISSION_QUOTE_MODES:
        raise ValueError(
            "execution_controls.cost_model.broker_commission_quote_mode must be "
            "all_in_regulatory or net_plus_regulatory"
        )

    commission_rate = _bounded_number(
        cost_model["broker_commission_rate"],
        "execution_controls.cost_model.broker_commission_rate",
        0.0,
        0.003,
    )
    minimum_commission = _bounded_number(
        cost_model["minimum_commission_cny"],
        "execution_controls.cost_model.minimum_commission_cny",
        0.0,
        100.0,
    )
    slippage_bps = _bounded_number(
        cost_model["slippage_bps"],
        "execution_controls.cost_model.slippage_bps",
        0.01,
        100.0,
    )
    market_impact_bps = _bounded_number(
        cost_model["market_impact_bps"],
        "execution_controls.cost_model.market_impact_bps",
        0.0,
        100.0,
    )
    return {
        "model_id": model_id,
        "broker_commission_quote_mode": quote_mode,
        "broker_commission_rate": commission_rate,
        "minimum_commission_cny": minimum_commission,
        "slippage_bps": slippage_bps,
        "market_impact_bps": market_impact_bps,
        "cost_assumption_source": assumption_source,
    }


def build_policy_snapshot(
    start_date: str,
    end_date: str,
    cost_model: dict[str, Any],
    path: str | Path | None = None,
) -> dict[str, Any]:
    normalized_cost_model = validate_cost_model(cost_model)
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if start > end:
        raise ValueError("market-rule period start must not exceed end")
    rulebook, rulebook_sha256 = load_market_rulebook(path)
    policies = _policies_covering_period(rulebook, start, end)
    for policy in policies:
        fees = policy["fees"]
        embedded_rate = float(fees["exchange_handling_fee_rate"]) + float(
            fees["regulatory_fee_rate"]
        )
        if (
            normalized_cost_model["broker_commission_quote_mode"] == "all_in_regulatory"
            and normalized_cost_model["broker_commission_rate"] + 1e-12 < embedded_rate
        ):
            raise ValueError(
                "all-in broker commission rate is below the effective exchange and "
                f"regulatory fee floor for policy {policy['policy_id']}"
            )
    source_ids = sorted(
        {source_id for policy in policies for source_id in policy.get("source_ids", [])}
    )
    return {
        "schema_version": 1,
        "rulebook_id": rulebook["rulebook_id"],
        "rulebook_sha256": rulebook_sha256,
        "rulebook_path": "governance/a_share_market_rules.json",
        "verified_as_of": rulebook["verified_as_of"],
        "period": {
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
        },
        "policy_ids": [policy["policy_id"] for policy in policies],
        "source_ids": source_ids,
        "sources": {source_id: rulebook["sources"][source_id] for source_id in source_ids},
        "cost_model": normalized_cost_model,
        "scope": rulebook["scope"],
    }


def policy_for_date(rulebook: dict[str, Any], trade_date: str) -> dict[str, Any]:
    target = _parse_date(trade_date, "trade_date")
    matches = []
    for policy in rulebook["policies"]:
        start = _parse_date(policy["effective_from"], "effective_from")
        end = (
            _parse_date(policy["effective_until"], "effective_until")
            if policy.get("effective_until")
            else datetime.max
        )
        if start <= target <= end:
            matches.append(policy)
    if len(matches) != 1:
        raise ValueError(
            f"market rulebook has {len(matches)} effective policies for {trade_date}; expected one"
        )
    return matches[0]


def classify_board(ts_code: str) -> str:
    code = str(ts_code).upper()
    security_code, separator, exchange = code.partition(".")
    if not separator:
        raise ValueError(f"security code lacks exchange suffix: {ts_code}")
    if exchange == "SH":
        return "SSE_STAR" if security_code.startswith(("688", "689")) else "SSE_MAIN"
    if exchange == "SZ":
        return (
            "SZSE_CHINEXT"
            if security_code.startswith(("300", "301"))
            else "SZSE_MAIN"
        )
    raise ValueError(f"unsupported exchange for CSI 500 A-share execution: {ts_code}")


def board_rule(policy: dict[str, Any], ts_code: str) -> dict[str, Any]:
    board = classify_board(ts_code)
    rule = policy["trading"]["boards"].get(board)
    if not isinstance(rule, dict):
        raise ValueError(f"market policy {policy['policy_id']} lacks board rule {board}")
    return {"board": board, **rule}


def round_price_to_tick(price: float, policy: dict[str, Any]) -> float:
    tick = Decimal(str(policy["trading"]["price_tick_cny"]))
    value = Decimal(str(price))
    units = (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float((units * tick).quantize(tick))


def quantize_order_shares(
    desired_shares: float,
    rule: dict[str, Any],
    full_exit: bool = False,
) -> dict[str, Any]:
    desired = max(float(desired_shares), 0.0)
    minimum = int(rule["minimum_order_shares"])
    increment = int(rule["order_increment_shares"])
    maximum = int(rule["maximum_limit_order_shares"])
    if desired <= 0:
        executed = 0
    elif full_exit:
        executed = max(int(math.floor(desired + 1e-9)), 1)
    elif desired + 1e-9 < minimum:
        executed = 0
    else:
        executed = minimum + int(math.floor((desired - minimum + 1e-9) / increment)) * increment
    return {
        "desired_shares": round(desired, 6),
        "executed_shares": executed,
        "unexecuted_shares": round(max(desired - executed, 0.0), 6),
        "order_count": math.ceil(executed / maximum) if executed else 0,
        "minimum_order_shares": minimum,
        "order_increment_shares": increment,
        "maximum_limit_order_shares": maximum,
        "full_exit": full_exit,
    }


def calculate_trade_cost(
    trade_notional_cny: float,
    side: str,
    order_count: int,
    policy: dict[str, Any],
    cost_model: dict[str, Any],
) -> dict[str, Any]:
    notional = max(float(trade_notional_cny), 0.0)
    normalized = validate_cost_model(cost_model)
    side_code = str(side).upper()
    if side_code not in {"B", "S"}:
        raise ValueError("trade-cost side must be B or S")
    fees = policy["fees"]
    handling_rate = float(fees["exchange_handling_fee_rate"])
    regulatory_rate = float(fees["regulatory_fee_rate"])
    embedded_rate = handling_rate + regulatory_rate
    if normalized["broker_commission_quote_mode"] == "all_in_regulatory":
        all_in_commission_rate = normalized["broker_commission_rate"]
    else:
        all_in_commission_rate = normalized["broker_commission_rate"] + embedded_rate
    minimum_total = normalized["minimum_commission_cny"] * max(int(order_count), 1)
    commission_total = max(notional * all_in_commission_rate, minimum_total) if notional else 0.0
    exchange_handling_fee = notional * handling_rate
    regulatory_fee = notional * regulatory_rate
    broker_net_commission = max(
        commission_total - exchange_handling_fee - regulatory_fee,
        0.0,
    )
    transfer_fee = notional * float(fees["transfer_fee_rate"])
    stamp_duty = (
        notional * float(fees["stamp_duty_sell_rate"])
        if side_code == "S"
        else 0.0
    )
    slippage = notional * normalized["slippage_bps"] / 10_000.0
    market_impact = notional * normalized["market_impact_bps"] / 10_000.0
    total = commission_total + transfer_fee + stamp_duty + slippage + market_impact
    return {
        "trade_notional_cny": round(notional, 6),
        "side": side_code,
        "order_count": max(int(order_count), 1) if notional else 0,
        "broker_net_commission_cny": round(broker_net_commission, 6),
        "exchange_handling_fee_cny": round(exchange_handling_fee, 6),
        "regulatory_fee_cny": round(regulatory_fee, 6),
        "commission_minimum_topup_cny": round(
            max(commission_total - notional * all_in_commission_rate, 0.0),
            6,
        ),
        "transfer_fee_cny": round(transfer_fee, 6),
        "stamp_duty_cny": round(stamp_duty, 6),
        "slippage_cny": round(slippage, 6),
        "market_impact_cny": round(market_impact, 6),
        "total_cost_cny": round(total, 6),
    }


def _validate_rulebook(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("A-share market rulebook schema is invalid")
    if not payload.get("rulebook_id") or not payload.get("verified_as_of"):
        raise ValueError("A-share market rulebook identity is incomplete")
    _parse_date(payload["verified_as_of"], "verified_as_of")
    sources = payload.get("sources")
    policies = payload.get("policies")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("A-share market rulebook sources are missing")
    if not isinstance(policies, list) or not policies:
        raise ValueError("A-share market rulebook policies are missing")
    previous_end: datetime | None = None
    for policy in sorted(policies, key=lambda item: item.get("effective_from", "")):
        start = _parse_date(policy.get("effective_from"), "effective_from")
        end = (
            _parse_date(policy.get("effective_until"), "effective_until")
            if policy.get("effective_until")
            else None
        )
        if end is not None and end < start:
            raise ValueError(f"market policy {policy.get('policy_id')} has an invalid period")
        if previous_end is not None and start <= previous_end:
            raise ValueError("A-share market rulebook policy periods overlap")
        previous_end = end or datetime.max
        for source_id in policy.get("source_ids", []):
            source = sources.get(source_id)
            if not isinstance(source, dict) or not str(source.get("url", "")).startswith("https://"):
                raise ValueError(f"market policy source is invalid: {source_id}")
        fees = policy.get("fees", {})
        for field in (
            "stamp_duty_sell_rate",
            "transfer_fee_rate",
            "exchange_handling_fee_rate",
            "regulatory_fee_rate",
        ):
            _bounded_number(fees.get(field), f"fees.{field}", 0.0, 0.01)
        trading = policy.get("trading", {})
        if trading.get("t_plus_one") is not True:
            raise ValueError("A-share market rulebook must enforce T+1")
        _bounded_number(trading.get("price_tick_cny"), "price_tick_cny", 0.001, 1.0)
        boards = trading.get("boards", {})
        for board in ("SSE_MAIN", "SSE_STAR", "SZSE_MAIN", "SZSE_CHINEXT"):
            rule = boards.get(board)
            if not isinstance(rule, dict):
                raise ValueError(f"A-share market rulebook lacks board {board}")
            for field in (
                "minimum_order_shares",
                "order_increment_shares",
                "maximum_limit_order_shares",
            ):
                if int(rule.get(field, 0)) <= 0:
                    raise ValueError(f"market board rule {board}.{field} is invalid")


def _policies_covering_period(
    rulebook: dict[str, Any],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    selected = []
    for policy in sorted(rulebook["policies"], key=lambda item: item["effective_from"]):
        policy_start = _parse_date(policy["effective_from"], "effective_from")
        policy_end = (
            _parse_date(policy["effective_until"], "effective_until")
            if policy.get("effective_until")
            else datetime.max
        )
        if policy_start <= end and policy_end >= start:
            selected.append(policy)
    cursor = start
    for policy in selected:
        policy_start = _parse_date(policy["effective_from"], "effective_from")
        policy_end = (
            _parse_date(policy["effective_until"], "effective_until")
            if policy.get("effective_until")
            else datetime.max
        )
        if policy_start > cursor:
            raise ValueError(
                "A-share market rulebook does not cover " + cursor.strftime("%Y%m%d")
            )
        cursor = max(cursor, policy_end + timedelta(days=1)) if policy_end < datetime.max else datetime.max
        if cursor > end:
            break
    if not selected or cursor <= end:
        raise ValueError(
            "A-share market rulebook does not cover the complete requested period"
        )
    return selected


def _parse_date(value: Any, field: str) -> datetime:
    text = str(value or "").replace("-", "")
    try:
        return datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYYMMDD or YYYY-MM-DD") from exc


def _bounded_number(value: Any, field: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return number
