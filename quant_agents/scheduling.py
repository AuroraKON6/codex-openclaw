from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any

from .audit import canonical_json_sha256, write_json_atomic
from .config import Config
from .data_client import DataClient
from .governance import evaluate_data_license
from .input_validation import validate_research_input
from .research_protocol import (
    build_model_contract_fingerprint,
    evaluate_research_protocol,
)
from .forward_observation import load_campaign_metadata


def build_scheduled_input(
    template_path: str,
    output_path: str,
    as_of: str | None = None,
    data_client: DataClient | None = None,
    now: datetime | None = None,
    campaign_path: str | None = None,
) -> dict[str, Any]:
    with open(template_path, "r", encoding="utf-8") as file:
        payload = json.load(file)
    validate_research_input(payload)
    license_gate = evaluate_data_license(payload)
    intended_use = str(
        payload.get("governance", {}).get("intended_use", "")
    ).lower()
    protocol_gate = None
    if intended_use == "licensed_internal_research" or campaign_path:
        protocol_gate = evaluate_research_protocol(payload)
    campaign = load_campaign_metadata(campaign_path) if campaign_path else None
    if intended_use == "licensed_internal_research" and not campaign:
        raise RuntimeError(
            "licensed scheduled research requires an approved forward-observation campaign"
        )
    if campaign:
        if canonical_json_sha256(payload) != campaign.get("baseline_input_sha256"):
            raise RuntimeError(
                "scheduled template does not match the approved campaign baseline input"
            )
        if build_model_contract_fingerprint(payload) != campaign.get(
            "model_contract_sha256"
        ):
            raise RuntimeError("scheduled template model contract differs from campaign")
        if not protocol_gate or protocol_gate.get("protocol_id") != campaign.get(
            "protocol_id"
        ):
            raise RuntimeError("scheduled template protocol differs from campaign")
    errors = Config.validate(require_deepseek=False, require_tushare=True)
    if errors:
        raise RuntimeError("scheduled input preflight failed: " + "; ".join(errors))

    current = now or datetime.now()
    as_of_date = _parse_date(as_of) if as_of else current.date()
    schedule_controls = payload.get("schedule_controls", {})
    not_before = str(schedule_controls.get("not_before_local_time", "18:30"))
    if as_of_date == current.date() and current.strftime("%H:%M") < not_before:
        raise RuntimeError(
            f"scheduled input for today's close cannot be generated before {not_before} local time"
        )

    client = data_client or DataClient()
    window_start = (as_of_date - timedelta(days=31)).strftime("%Y%m%d")
    trade_dates = client.get_trade_dates(window_start, as_of_date.strftime("%Y%m%d"))
    if not trade_dates:
        raise RuntimeError("no Tushare trading date found for scheduled input")
    resolved_trade_date = trade_dates[-1]
    if campaign:
        start_date = str(
            campaign.get("forward_observation_controls", {}).get(
                "warmup_since", ""
            )
        )
        baseline_cutoff = str(campaign.get("baseline_cutoff", ""))
        if resolved_trade_date <= baseline_cutoff:
            raise RuntimeError(
                "resolved trade date must be after the campaign baseline cutoff"
            )
    else:
        lookback_days = int(schedule_controls.get("lookback_calendar_days", 365))
        if not 90 <= lookback_days <= 1825:
            raise RuntimeError("schedule_controls.lookback_calendar_days must be between 90 and 1825")
        start_date = (
            datetime.strptime(resolved_trade_date, "%Y%m%d").date()
            - timedelta(days=lookback_days)
        ).strftime("%Y%m%d")
    payload["date_range"] = {"since": start_date, "until": resolved_trade_date}
    request_identity = {
        "scope": payload.get("scope"),
        "governance": payload.get("governance"),
        "date_range": payload.get("date_range"),
        "strategy_params": payload.get("strategy_params"),
        "data_controls": payload.get("data_controls"),
        "execution_controls": payload.get("execution_controls"),
        "resolved_trade_date": resolved_trade_date,
        "campaign_id": campaign.get("campaign_id") if campaign else None,
    }
    request_fingerprint = canonical_json_sha256(request_identity)
    request_id = f"CSI500-{resolved_trade_date}-{request_fingerprint[:12]}"
    payload["schedule_context"] = {
        "generated_at": current.isoformat(),
        "requested_as_of": as_of_date.strftime("%Y%m%d"),
        "resolved_trade_date": resolved_trade_date,
        "data_license_status": license_gate["status"],
        "request_fingerprint": request_fingerprint,
        "request_id": request_id,
    }
    if campaign and protocol_gate:
        payload["schedule_context"].update(
            {
                "run_class": "forward_observation_refresh",
                "campaign_id": campaign["campaign_id"],
                "research_protocol_id": protocol_gate["protocol_id"],
                "research_protocol_version": protocol_gate["protocol_version"],
                "model_contract_sha256": protocol_gate[
                    "model_contract_sha256"
                ],
                "baseline_cutoff": campaign["baseline_cutoff"],
            }
        )
    validate_research_input(payload)
    if campaign:
        evaluate_research_protocol(payload)
    write_json_atomic(output_path, payload)
    return {
        "output_path": os.path.abspath(output_path),
        "request_id": request_id,
        "resolved_trade_date": resolved_trade_date,
        "request_fingerprint": request_fingerprint,
        "input_fingerprint": canonical_json_sha256(payload),
        "campaign_id": campaign.get("campaign_id") if campaign else None,
    }


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.replace("-", ""), "%Y%m%d").date()
    except ValueError as exc:
        raise RuntimeError("as_of must use YYYYMMDD or YYYY-MM-DD") from exc
