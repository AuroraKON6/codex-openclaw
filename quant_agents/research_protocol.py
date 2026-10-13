from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime, timezone
from typing import Any

from .audit import canonical_json_sha256, sha256_file
from .config import Config, PROJECT_ROOT


PROTOCOL_SCHEMA_VERSION = 1
PROTOCOL_REVIEW_MAX_AGE_DAYS = 90
SUPPORTED_RECORD_TYPES = {
    "organization_research_registry_export",
    "signed_research_protocol_and_change_ticket",
}
REQUIRED_APPROVAL_ROLES = {
    "quant_owner",
    "independent_model_validator",
    "compliance_owner",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ResearchProtocolGateError(RuntimeError):
    pass


def build_model_contract(input_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "theme": input_data.get("theme"),
        "scope": str(input_data.get("scope", "")).upper(),
        "governance": input_data.get("governance", {}),
        "focus_sectors": input_data.get("focus_sectors", []),
        "strategy_params": input_data.get("strategy_params", {}),
        "data_controls": input_data.get("data_controls", {}),
        "execution_controls": input_data.get("execution_controls", {}),
        "validation_controls": input_data.get("validation_controls", {}),
        "schedule_controls": input_data.get("schedule_controls", {}),
    }


def build_model_contract_fingerprint(input_data: dict[str, Any]) -> str:
    return canonical_json_sha256(build_model_contract(input_data))


def evaluate_research_protocol(
    input_data: dict[str, Any],
    evidence_path: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = os.path.abspath(
        evidence_path or Config.RESEARCH_PROTOCOL_EVIDENCE_PATH or ""
    )
    if not evidence_path and not Config.RESEARCH_PROTOCOL_EVIDENCE_PATH:
        raise ResearchProtocolGateError(
            "real research requires RESEARCH_PROTOCOL_EVIDENCE_PATH; "
            "parameter_selection_policy is a self-declaration, not external registration"
        )
    if not os.path.isfile(path):
        raise ResearchProtocolGateError(
            f"research-protocol evidence file does not exist: {path}"
        )
    if _is_within_project(path):
        raise ResearchProtocolGateError(
            "research-protocol evidence must be stored outside the project repository"
        )
    try:
        with open(path, "r", encoding="utf-8") as file:
            evidence = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchProtocolGateError(
            f"cannot read research-protocol evidence: {exc}"
        ) from exc
    if not isinstance(evidence, dict):
        raise ResearchProtocolGateError(
            "research-protocol evidence must be a JSON object"
        )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = current.date()
    expected_input_sha256 = canonical_json_sha256(input_data)
    expected_model_contract_sha256 = build_model_contract_fingerprint(input_data)
    schedule_context = input_data.get("schedule_context")
    run_class = "development_backtest"
    binding_mode = "exact_registered_input"
    if isinstance(schedule_context, dict):
        run_class = str(schedule_context.get("run_class", ""))
        binding_mode = "forward_schedule_model_contract"

    errors: list[str] = []
    if evidence.get("schema_version") != PROTOCOL_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PROTOCOL_SCHEMA_VERSION}")
    if str(evidence.get("status", "")).upper() != "APPROVED_FOR_BACKTEST":
        errors.append("status must be APPROVED_FOR_BACKTEST")
    protocol_id = str(evidence.get("protocol_id", "")).strip()
    if not protocol_id or len(protocol_id) > 120 or protocol_id.upper().startswith("REPLACE_"):
        errors.append("protocol_id is required and must be at most 120 characters")
    protocol_version = _integer_or_zero(evidence.get("protocol_version"))
    if not 1 <= protocol_version <= 999:
        errors.append("protocol_version must be between 1 and 999")
    if str(evidence.get("scope", "")).upper() != str(input_data.get("scope", "")).upper():
        errors.append("scope does not match the run input")
    hypothesis_id = str(
        input_data.get("validation_controls", {}).get("hypothesis_id", "")
    )
    if str(evidence.get("hypothesis_id", "")) != hypothesis_id:
        errors.append("hypothesis_id does not match the run input")
    if evidence.get("parameter_selection_policy") != "pre_registered_no_search":
        errors.append("parameter_selection_policy must be pre_registered_no_search")
    if evidence.get("parameter_search_count") != 0:
        errors.append("parameter_search_count must be 0")
    if evidence.get("live_execution_authorized") is not False:
        errors.append("live_execution_authorized must be false")
    if evidence.get("external_distribution_authorized") is not False:
        errors.append("external_distribution_authorized must be false")

    registered_input_sha256 = str(
        evidence.get("registered_input_sha256", "")
    ).lower()
    model_contract_sha256 = str(
        evidence.get("model_contract_sha256", "")
    ).lower()
    if not _SHA256.fullmatch(registered_input_sha256):
        errors.append("registered_input_sha256 must be a lowercase SHA-256 value")
    if not _SHA256.fullmatch(model_contract_sha256):
        errors.append("model_contract_sha256 must be a lowercase SHA-256 value")
    if model_contract_sha256 != expected_model_contract_sha256:
        errors.append("model_contract_sha256 does not match the frozen run contract")
    if run_class == "development_backtest":
        if registered_input_sha256 != expected_input_sha256:
            errors.append("registered_input_sha256 does not match the exact development input")
    elif run_class == "forward_observation_refresh":
        if not isinstance(schedule_context, dict):
            errors.append("forward observation requires schedule_context")
        else:
            if schedule_context.get("research_protocol_id") != protocol_id:
                errors.append("schedule_context research_protocol_id mismatch")
            if _integer_or_zero(schedule_context.get("research_protocol_version")) != protocol_version:
                errors.append("schedule_context research_protocol_version mismatch")
            if schedule_context.get("model_contract_sha256") != model_contract_sha256:
                errors.append("schedule_context model_contract_sha256 mismatch")
    else:
        errors.append(
            "schedule_context.run_class must be forward_observation_refresh"
        )

    registered_date_range = evidence.get("registered_date_range")
    if not isinstance(registered_date_range, dict):
        errors.append("registered_date_range is required")
        registered_date_range = {}
    registered_since = _parse_compact_date(
        registered_date_range.get("since"), "registered_date_range.since", errors
    )
    registered_until = _parse_compact_date(
        registered_date_range.get("until"), "registered_date_range.until", errors
    )
    if registered_since and registered_until and registered_since >= registered_until:
        errors.append("registered_date_range.since must be before until")
    if run_class == "development_backtest":
        observed_range = input_data.get("date_range", {})
        if _compact_date_text(observed_range.get("since")) != _compact_date_text(
            registered_date_range.get("since")
        ) or _compact_date_text(observed_range.get("until")) != _compact_date_text(
            registered_date_range.get("until")
        ):
            errors.append("registered_date_range does not match the development input")
    elif run_class == "forward_observation_refresh":
        observed_range = input_data.get("date_range", {})
        observed_since = _parse_compact_date(
            observed_range.get("since"), "date_range.since", errors
        )
        observed_until = _parse_compact_date(
            observed_range.get("until"), "date_range.until", errors
        )
        if registered_since and observed_since and registered_since != observed_since:
            errors.append("forward observation must preserve the registered warm-up origin")
        if registered_until and observed_until and observed_until <= registered_until:
            errors.append("forward observation cutoff must be after the registered period")

    change_type = str(evidence.get("change_type", ""))
    if change_type not in {"initial_registration", "approved_amendment"}:
        errors.append("change_type must be initial_registration or approved_amendment")
    supersedes = str(evidence.get("supersedes_protocol_id", "")).strip()
    change_reason = str(evidence.get("change_reason", "")).strip()
    if change_type == "initial_registration" and (supersedes or change_reason):
        errors.append("initial_registration must not claim a superseded protocol or change reason")
    if change_type == "approved_amendment" and (not supersedes or not change_reason):
        errors.append("approved_amendment requires supersedes_protocol_id and change_reason")

    registered_at = _parse_timestamp(
        evidence.get("registered_at"), "registered_at", errors
    )
    reviewed_at = _parse_iso_date(evidence.get("reviewed_at"), "reviewed_at", errors)
    valid_from = _parse_iso_date(evidence.get("valid_from"), "valid_from", errors)
    valid_until = _parse_iso_date(evidence.get("valid_until"), "valid_until", errors)
    if registered_at and registered_at > current:
        errors.append("registered_at must not be in the future")
    if reviewed_at and reviewed_at > today:
        errors.append("reviewed_at must not be in the future")
    if reviewed_at and (today - reviewed_at).days > PROTOCOL_REVIEW_MAX_AGE_DAYS:
        errors.append(
            f"research protocol review is older than {PROTOCOL_REVIEW_MAX_AGE_DAYS} days"
        )
    if valid_from and today < valid_from:
        errors.append("research protocol is not yet effective")
    if valid_until and today > valid_until:
        errors.append("research protocol has expired")
    if valid_from and valid_until and valid_from > valid_until:
        errors.append("valid_from must not be after valid_until")

    system_of_record = evidence.get("system_of_record")
    if not isinstance(system_of_record, dict):
        errors.append("system_of_record is required")
        system_of_record = {}
    record_type = str(system_of_record.get("type", ""))
    if record_type not in SUPPORTED_RECORD_TYPES:
        errors.append("system_of_record.type is not supported")
    for field in ("record_id", "record_reference"):
        value = str(system_of_record.get(field, "")).strip()
        if not value or value.upper().startswith("REPLACE_"):
            errors.append(f"system_of_record.{field} is required")

    approvals = evidence.get("approvals")
    if not isinstance(approvals, list):
        approvals = []
        errors.append("approvals must be a list")
    by_role = {
        str(row.get("role")): row
        for row in approvals
        if isinstance(row, dict) and row.get("role")
    }
    missing_roles = sorted(REQUIRED_APPROVAL_ROLES.difference(by_role))
    if missing_roles:
        errors.append("missing approval roles: " + ", ".join(missing_roles))
    approvers: list[str] = []
    approval_evidence: list[str] = []
    for role in REQUIRED_APPROVAL_ROLES:
        approval = by_role.get(role, {})
        if str(approval.get("decision", "")).upper() != "APPROVED":
            errors.append(f"{role} decision must be APPROVED")
        approver = str(approval.get("approver", "")).strip()
        if not approver or approver.upper().startswith("REPLACE_"):
            errors.append(f"{role} approver is required")
        else:
            approvers.append(approver.casefold())
        reference = str(approval.get("evidence_reference", "")).strip()
        if not reference or reference.upper().startswith("REPLACE_"):
            errors.append(f"{role} evidence_reference is required")
        else:
            approval_evidence.append(reference)
        approved_at = _parse_timestamp(
            approval.get("approved_at"), f"{role}.approved_at", errors
        )
        if approved_at and approved_at > current:
            errors.append(f"{role} approved_at must not be in the future")
        if approved_at and registered_at and approved_at < registered_at:
            errors.append(f"{role} approved_at predates registration")
    if len(set(approvers)) != len(approvers):
        errors.append("protocol approval roles require three distinct people")

    if evidence.get("registered_before_execution_attested") is not True:
        errors.append("registered_before_execution_attested must be true")
    forward_controls = _validate_forward_controls(
        evidence.get("forward_observation_controls"),
        registered_since,
        registered_until,
        errors,
    )

    document_type = str(evidence.get("supporting_document_type", ""))
    if document_type not in SUPPORTED_RECORD_TYPES:
        errors.append("supporting_document_type is not supported")
    document_path = str(evidence.get("supporting_document_path", "")).strip()
    if document_path and not os.path.isabs(document_path):
        document_path = os.path.abspath(os.path.join(os.path.dirname(path), document_path))
    if not document_path or document_path.upper().startswith("REPLACE_"):
        errors.append("supporting_document_path is required")
    elif _is_within_project(document_path):
        errors.append("supporting protocol document must be stored outside the project repository")
    document_sha256 = str(evidence.get("supporting_document_sha256", "")).lower()
    if not _SHA256.fullmatch(document_sha256):
        errors.append("supporting_document_sha256 must be a lowercase SHA-256 value")
    if document_path and not os.path.isfile(document_path):
        errors.append(f"supporting protocol document does not exist: {document_path}")
    elif document_path and document_sha256 and sha256_file(document_path) != document_sha256:
        errors.append("supporting protocol document SHA-256 does not match evidence")

    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not any(
        str(item).strip() for item in limitations
    ):
        errors.append("limitations must contain at least one material limitation")
    if errors:
        raise ResearchProtocolGateError(
            "research-protocol gate failed: " + "; ".join(errors)
        )

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "status": "approved_for_backtest",
        "protocol_id": protocol_id,
        "protocol_version": protocol_version,
        "change_type": change_type,
        "hypothesis_id": hypothesis_id,
        "scope": str(input_data.get("scope", "")).upper(),
        "run_class": run_class,
        "binding_mode": binding_mode,
        "registered_input_sha256": registered_input_sha256,
        "evaluated_input_sha256": expected_input_sha256,
        "model_contract_sha256": model_contract_sha256,
        "registered_date_range": {
            "since": _compact_date_text(registered_date_range.get("since")),
            "until": _compact_date_text(registered_date_range.get("until")),
        },
        "registered_at": registered_at.isoformat() if registered_at else None,
        "reviewed_at": evidence["reviewed_at"],
        "valid_from": evidence["valid_from"],
        "valid_until": evidence["valid_until"],
        "approval_roles": sorted(REQUIRED_APPROVAL_ROLES),
        "approval_evidence_references": sorted(approval_evidence),
        "forward_observation_controls": forward_controls,
        "live_execution_authorized": False,
        "external_distribution_authorized": False,
        "supporting_document_type": document_type,
        "supporting_document_sha256": document_sha256,
        "evidence_file_sha256": sha256_file(path),
        "identity_and_timestamp_assurance": (
            "external_record_claim_bound_by_hash_not_cryptographically_authenticated"
        ),
        "limitations": [str(item).strip() for item in limitations if str(item).strip()],
    }


def is_release_eligible_research_protocol(
    protocol_gate: dict[str, Any],
    input_fingerprint: str | None = None,
    model_contract_fingerprint: str | None = None,
    today: date | None = None,
) -> bool:
    try:
        valid_from = datetime.strptime(
            str(protocol_gate.get("valid_from", "")), "%Y-%m-%d"
        ).date()
        valid_until = datetime.strptime(
            str(protocol_gate.get("valid_until", "")), "%Y-%m-%d"
        ).date()
        reviewed_at = datetime.strptime(
            str(protocol_gate.get("reviewed_at", "")), "%Y-%m-%d"
        ).date()
        registered_at = datetime.fromisoformat(
            str(protocol_gate.get("registered_at", "")).replace("Z", "+00:00")
        )
        if registered_at.tzinfo is None:
            return False
    except ValueError:
        return False
    evaluation_date = today or date.today()
    controls = protocol_gate.get("forward_observation_controls", {})
    return (
        protocol_gate.get("schema_version") == PROTOCOL_SCHEMA_VERSION
        and protocol_gate.get("status") == "approved_for_backtest"
        and protocol_gate.get("run_class")
        in {"development_backtest", "forward_observation_refresh"}
        and protocol_gate.get("binding_mode")
        in {"exact_registered_input", "forward_schedule_model_contract"}
        and bool(str(protocol_gate.get("protocol_id", "")).strip())
        and protocol_gate.get("change_type")
        in {"initial_registration", "approved_amendment"}
        and protocol_gate.get("scope") == "CSI500"
        and bool(str(protocol_gate.get("hypothesis_id", "")).strip())
        and 1 <= _integer_or_zero(protocol_gate.get("protocol_version")) <= 999
        and bool(_SHA256.fullmatch(str(protocol_gate.get("registered_input_sha256", ""))))
        and bool(_SHA256.fullmatch(str(protocol_gate.get("evaluated_input_sha256", ""))))
        and bool(_SHA256.fullmatch(str(protocol_gate.get("model_contract_sha256", ""))))
        and (
            input_fingerprint is None
            or protocol_gate.get("evaluated_input_sha256") == input_fingerprint
        )
        and (
            (
                protocol_gate.get("run_class") == "development_backtest"
                and protocol_gate.get("binding_mode") == "exact_registered_input"
                and protocol_gate.get("registered_input_sha256")
                == protocol_gate.get("evaluated_input_sha256")
            )
            or (
                protocol_gate.get("run_class") == "forward_observation_refresh"
                and protocol_gate.get("binding_mode")
                == "forward_schedule_model_contract"
            )
        )
        and (
            model_contract_fingerprint is None
            or protocol_gate.get("model_contract_sha256")
            == model_contract_fingerprint
        )
        and set(protocol_gate.get("approval_roles", [])) == REQUIRED_APPROVAL_ROLES
        and len(protocol_gate.get("approval_evidence_references", [])) == 3
        and protocol_gate.get("live_execution_authorized") is False
        and protocol_gate.get("external_distribution_authorized") is False
        and protocol_gate.get("identity_and_timestamp_assurance")
        == "external_record_claim_bound_by_hash_not_cryptographically_authenticated"
        and bool(_SHA256.fullmatch(str(protocol_gate.get("evidence_file_sha256", ""))))
        and bool(
            _SHA256.fullmatch(
                str(protocol_gate.get("supporting_document_sha256", ""))
            )
        )
        and protocol_gate.get("supporting_document_type")
        in SUPPORTED_RECORD_TYPES
        and _release_eligible_forward_controls(controls)
        and isinstance(protocol_gate.get("limitations"), list)
        and any(str(item).strip() for item in protocol_gate.get("limitations", []))
        and valid_from <= evaluation_date <= valid_until
        and reviewed_at <= evaluation_date
        and registered_at.astimezone(timezone.utc).date() <= evaluation_date
        and (evaluation_date - reviewed_at).days <= PROTOCOL_REVIEW_MAX_AGE_DAYS
    )


def _release_eligible_forward_controls(controls: dict[str, Any]) -> bool:
    try:
        minimum_days = int(controls.get("minimum_observation_trade_days"))
        minimum_rebalances = int(controls.get("minimum_rebalance_count"))
        review_frequency = int(controls.get("review_frequency_trade_days"))
        promotion = controls.get("promotion_thresholds", {})
        pause = controls.get("pause_thresholds", {})
        minimum_excess = float(promotion.get("minimum_excess_return"))
        maximum_drawdown = float(promotion.get("maximum_drawdown"))
        maximum_cost = float(promotion.get("maximum_cumulative_cost_ratio"))
        pause_drawdown = float(pause.get("drawdown_at_or_below"))
        pause_excess = float(pause.get("excess_return_at_or_below"))
    except (TypeError, ValueError):
        return False
    return (
        controls.get("authorized") is True
        and controls.get("observation_mode") == "fixed_origin_forward"
        and bool(_parse_date_without_errors(controls.get("warmup_since")))
        and bool(_parse_date_without_errors(controls.get("baseline_cutoff")))
        and 60 <= minimum_days <= 252
        and 3 <= minimum_rebalances <= 52
        and 5 <= review_frequency <= 20
        and all(
            math.isfinite(value)
            for value in (
                minimum_excess,
                maximum_drawdown,
                maximum_cost,
                pause_drawdown,
                pause_excess,
            )
        )
        and -1.0 <= minimum_excess <= 1.0
        and -1.0 <= maximum_drawdown <= 0.0
        and 0.0 <= maximum_cost <= 0.2
        and -1.0 <= pause_drawdown < 0.0
        and -1.0 <= pause_excess <= 0.0
        and pause_drawdown <= maximum_drawdown
        and pause_excess <= minimum_excess
    )


def _validate_forward_controls(
    value: Any,
    registered_since: date | None,
    registered_until: date | None,
    errors: list[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append("forward_observation_controls is required")
        return {}
    if value.get("authorized") is not True:
        errors.append("forward_observation_controls.authorized must be true")
    if value.get("observation_mode") != "fixed_origin_forward":
        errors.append(
            "forward_observation_controls.observation_mode must be fixed_origin_forward"
        )
    warmup_since = _parse_compact_date(
        value.get("warmup_since"),
        "forward_observation_controls.warmup_since",
        errors,
    )
    cutoff = _parse_compact_date(
        value.get("baseline_cutoff"),
        "forward_observation_controls.baseline_cutoff",
        errors,
    )
    if registered_since and warmup_since and warmup_since != registered_since:
        errors.append("forward warmup_since must equal registered_date_range.since")
    if registered_until and cutoff and cutoff != registered_until:
        errors.append("forward baseline_cutoff must equal registered_date_range.until")
    minimum_days = _integer_or_zero(value.get("minimum_observation_trade_days"))
    minimum_rebalances = _integer_or_zero(value.get("minimum_rebalance_count"))
    review_frequency = _integer_or_zero(value.get("review_frequency_trade_days"))
    if not 60 <= minimum_days <= 252:
        errors.append("minimum_observation_trade_days must be between 60 and 252")
    if not 3 <= minimum_rebalances <= 52:
        errors.append("minimum_rebalance_count must be between 3 and 52")
    if not 5 <= review_frequency <= 20:
        errors.append("review_frequency_trade_days must be between 5 and 20")

    promotion = value.get("promotion_thresholds")
    pause = value.get("pause_thresholds")
    if not isinstance(promotion, dict):
        promotion = {}
        errors.append("forward promotion_thresholds are required")
    if not isinstance(pause, dict):
        pause = {}
        errors.append("forward pause_thresholds are required")
    minimum_excess = _finite_number(
        promotion.get("minimum_excess_return"),
        "promotion_thresholds.minimum_excess_return",
        errors,
    )
    maximum_drawdown = _finite_number(
        promotion.get("maximum_drawdown"),
        "promotion_thresholds.maximum_drawdown",
        errors,
    )
    maximum_cost_ratio = _finite_number(
        promotion.get("maximum_cumulative_cost_ratio"),
        "promotion_thresholds.maximum_cumulative_cost_ratio",
        errors,
    )
    pause_drawdown = _finite_number(
        pause.get("drawdown_at_or_below"),
        "pause_thresholds.drawdown_at_or_below",
        errors,
    )
    pause_excess = _finite_number(
        pause.get("excess_return_at_or_below"),
        "pause_thresholds.excess_return_at_or_below",
        errors,
    )
    if minimum_excess is not None and not -1.0 <= minimum_excess <= 1.0:
        errors.append("minimum_excess_return must be between -1 and 1")
    if maximum_drawdown is not None and not -1.0 <= maximum_drawdown <= 0.0:
        errors.append("promotion maximum_drawdown must be between -1 and 0")
    if maximum_cost_ratio is not None and not 0.0 <= maximum_cost_ratio <= 0.2:
        errors.append("maximum_cumulative_cost_ratio must be between 0 and 0.2")
    if pause_drawdown is not None and not -1.0 <= pause_drawdown < 0.0:
        errors.append("pause drawdown threshold must be between -1 and 0")
    if pause_excess is not None and not -1.0 <= pause_excess <= 0.0:
        errors.append("pause excess-return threshold must be between -1 and 0")
    if (
        pause_drawdown is not None
        and maximum_drawdown is not None
        and pause_drawdown > maximum_drawdown
    ):
        errors.append("pause drawdown threshold must be no higher than promotion drawdown")
    if (
        pause_excess is not None
        and minimum_excess is not None
        and pause_excess > minimum_excess
    ):
        errors.append("pause excess-return threshold must be no higher than promotion excess return")
    return {
        "authorized": value.get("authorized") is True,
        "observation_mode": value.get("observation_mode"),
        "warmup_since": _compact_date_text(value.get("warmup_since")),
        "baseline_cutoff": _compact_date_text(value.get("baseline_cutoff")),
        "minimum_observation_trade_days": minimum_days,
        "minimum_rebalance_count": minimum_rebalances,
        "review_frequency_trade_days": review_frequency,
        "promotion_thresholds": {
            "minimum_excess_return": minimum_excess,
            "maximum_drawdown": maximum_drawdown,
            "maximum_cumulative_cost_ratio": maximum_cost_ratio,
        },
        "pause_thresholds": {
            "drawdown_at_or_below": pause_drawdown,
            "excess_return_at_or_below": pause_excess,
        },
    }


def _parse_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError:
        errors.append(f"{field} must be timezone-aware ISO-8601")
        return None


def _parse_iso_date(value: Any, field: str, errors: list[str]) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return None


def _parse_compact_date(value: Any, field: str, errors: list[str]) -> date | None:
    try:
        return datetime.strptime(_compact_date_text(value), "%Y%m%d").date()
    except ValueError:
        errors.append(f"{field} must use YYYYMMDD or YYYY-MM-DD")
        return None


def _parse_date_without_errors(value: Any) -> date | None:
    try:
        return datetime.strptime(_compact_date_text(value), "%Y%m%d").date()
    except ValueError:
        return None


def _compact_date_text(value: Any) -> str:
    return str(value or "").replace("-", "")


def _integer_or_zero(value: Any) -> int:
    try:
        number = float(value)
        return int(number) if math.isfinite(number) else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _finite_number(
    value: Any, field: str, errors: list[str]
) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not math.isfinite(number):
        errors.append(f"{field} must be finite")
        return None
    return number


def _is_within_project(path: str) -> bool:
    project_root = os.path.abspath(str(PROJECT_ROOT))
    try:
        lexical_match = os.path.normcase(
            os.path.commonpath([project_root, os.path.abspath(path)])
        ) == os.path.normcase(project_root)
        resolved_root = os.path.realpath(project_root)
        resolved_match = os.path.normcase(
            os.path.commonpath([resolved_root, os.path.realpath(path)])
        ) == os.path.normcase(resolved_root)
        return lexical_match or resolved_match
    except ValueError:
        return False
