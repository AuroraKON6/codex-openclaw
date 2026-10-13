from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime
from typing import Any

from .audit import canonical_json_sha256, sha256_file
from .config import Config, PROJECT_ROOT
from .market_rules import load_market_rulebook, validate_cost_model


COST_EVIDENCE_SCHEMA_VERSION = 1
COST_REVIEW_MAX_AGE_DAYS = 90
SUPPORTED_CALIBRATION_BASES = {
    "approved_conservative_assumption",
    "historical_execution_sample",
}
SUPPORTED_DOCUMENT_TYPES = {
    "broker_fee_schedule_and_internal_cost_memo",
    "historical_execution_calibration_pack",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExecutionCostGateError(RuntimeError):
    pass


def evaluate_execution_cost_evidence(
    input_data: dict[str, Any],
    evidence_path: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    execution_controls = input_data.get("execution_controls", {})
    expected_cost_model = validate_cost_model(execution_controls.get("cost_model"))
    expected_contract = {
        "scope": str(input_data.get("scope", "")).upper(),
        "cost_model": expected_cost_model,
        "simulation_notional_cny": float(
            execution_controls.get("simulation_notional_cny", 0.0)
        ),
        "max_participation_rate": float(
            execution_controls.get("max_participation_rate", 0.0)
        ),
        "minimum_daily_amount_cny": float(
            execution_controls.get("minimum_daily_amount_cny", 0.0)
        ),
    }
    expected_fingerprint = canonical_json_sha256(expected_contract)
    path = os.path.abspath(
        evidence_path or Config.EXECUTION_COST_EVIDENCE_PATH or ""
    )
    if not evidence_path and not Config.EXECUTION_COST_EVIDENCE_PATH:
        raise ExecutionCostGateError(
            "real internal research requires EXECUTION_COST_EVIDENCE_PATH; "
            "an unverified cost_assumption_source string is not calibration evidence"
        )
    if not os.path.isfile(path):
        raise ExecutionCostGateError(
            f"execution-cost evidence file does not exist: {path}"
        )
    if _is_within_project(path):
        raise ExecutionCostGateError(
            "execution-cost evidence must be stored outside the project repository"
        )
    try:
        with open(path, "r", encoding="utf-8") as file:
            evidence = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionCostGateError(
            f"cannot read execution-cost evidence: {exc}"
        ) from exc

    errors: list[str] = []
    if evidence.get("schema_version") != COST_EVIDENCE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {COST_EVIDENCE_SCHEMA_VERSION}")
    if str(evidence.get("status", "")).upper() != "APPROVED_FOR_INTERNAL_RESEARCH":
        errors.append("status must be APPROVED_FOR_INTERNAL_RESEARCH")
    if str(evidence.get("scope", "")).upper() != expected_contract["scope"]:
        errors.append(f"scope must be {expected_contract['scope']}")
    if evidence.get("live_execution_ready") is not False:
        errors.append("live_execution_ready must be false")
    if evidence.get("double_cost_stress_required") is not True:
        errors.append("double_cost_stress_required must be true")
    if str(evidence.get("market_rulebook_sha256", "")) != load_market_rulebook()[1]:
        errors.append("market_rulebook_sha256 does not match the current rulebook")

    try:
        calibrated_cost_model = validate_cost_model(
            evidence.get("calibrated_cost_model")
        )
    except ValueError as exc:
        errors.append(f"calibrated_cost_model is invalid: {exc}")
        calibrated_cost_model = {}
    observed_contract = {
        "scope": str(evidence.get("scope", "")).upper(),
        "cost_model": calibrated_cost_model,
        "simulation_notional_cny": _number_or_zero(
            evidence.get("simulation_notional_cny")
        ),
        "max_participation_rate": _number_or_zero(
            evidence.get("max_participation_rate")
        ),
        "minimum_daily_amount_cny": _number_or_zero(
            evidence.get("minimum_daily_amount_cny")
        ),
    }
    if canonical_json_sha256(observed_contract) != expected_fingerprint:
        errors.append(
            "evidence cost model, notional, participation, or liquidity floor does not "
            "match the run input"
        )

    basis = str(evidence.get("calibration_basis", ""))
    if basis not in SUPPORTED_CALIBRATION_BASES:
        errors.append(
            "calibration_basis must be approved_conservative_assumption or "
            "historical_execution_sample"
        )
    sample_order_count = _integer_or_zero(evidence.get("sample_order_count"))
    if basis == "approved_conservative_assumption":
        if evidence.get("provisional") is not True:
            errors.append("conservative assumptions must be marked provisional=true")
        if sample_order_count != 0:
            errors.append(
                "conservative assumptions must set sample_order_count=0; use the "
                "historical basis when execution samples are claimed"
            )
    elif basis == "historical_execution_sample":
        if evidence.get("provisional") is not False:
            errors.append("historical execution calibration must set provisional=false")
        if sample_order_count < 30:
            errors.append("historical execution calibration requires at least 30 orders")
        sample_start = _parse_iso_date(
            evidence.get("sample_start"), "sample_start", errors
        )
        sample_end = _parse_iso_date(evidence.get("sample_end"), "sample_end", errors)
        if sample_start and sample_end and sample_start > sample_end:
            errors.append("sample_start must not be after sample_end")

    document_type = str(evidence.get("supporting_document_type", ""))
    if document_type not in SUPPORTED_DOCUMENT_TYPES:
        errors.append("supporting_document_type is not supported")
    if (
        basis == "approved_conservative_assumption"
        and document_type != "broker_fee_schedule_and_internal_cost_memo"
    ):
        errors.append(
            "conservative assumptions require broker_fee_schedule_and_internal_cost_memo"
        )
    if (
        basis == "historical_execution_sample"
        and document_type != "historical_execution_calibration_pack"
    ):
        errors.append(
            "historical execution calibration requires historical_execution_calibration_pack"
        )
    for field in (
        "quant_owner_approver",
        "independent_reviewer",
        "compliance_owner_approver",
        "valid_from",
        "valid_until",
        "reviewed_at",
        "supporting_document_path",
        "supporting_document_sha256",
    ):
        value = str(evidence.get(field, "")).strip()
        if not value or value.upper().startswith("REPLACE_"):
            errors.append(f"{field} is required")
    quant_owner = str(evidence.get("quant_owner_approver", "")).strip().casefold()
    reviewer = str(evidence.get("independent_reviewer", "")).strip().casefold()
    compliance_owner = str(
        evidence.get("compliance_owner_approver", "")
    ).strip().casefold()
    populated_approvers = [
        value for value in (quant_owner, reviewer, compliance_owner) if value
    ]
    if len(set(populated_approvers)) != len(populated_approvers):
        errors.append(
            "quant_owner_approver, independent_reviewer, and compliance_owner_approver "
            "must be three distinct people"
        )

    evaluation_date = today or date.today()
    valid_from = _parse_iso_date(evidence.get("valid_from"), "valid_from", errors)
    valid_until = _parse_iso_date(evidence.get("valid_until"), "valid_until", errors)
    reviewed_at = _parse_iso_date(evidence.get("reviewed_at"), "reviewed_at", errors)
    if valid_from and evaluation_date < valid_from:
        errors.append("cost calibration is not yet effective")
    if valid_until and evaluation_date > valid_until:
        errors.append("cost calibration has expired")
    if valid_from and valid_until and valid_from > valid_until:
        errors.append("valid_from must not be after valid_until")
    if reviewed_at and reviewed_at > evaluation_date:
        errors.append("reviewed_at must not be in the future")
    if basis == "historical_execution_sample" and reviewed_at:
        sample_end = _parse_iso_date(evidence.get("sample_end"), "sample_end", [])
        if sample_end and sample_end > reviewed_at:
            errors.append("sample_end must not be after reviewed_at")
    if reviewed_at and (evaluation_date - reviewed_at).days > COST_REVIEW_MAX_AGE_DAYS:
        errors.append(
            f"cost calibration review is older than {COST_REVIEW_MAX_AGE_DAYS} days"
        )

    document_path = str(evidence.get("supporting_document_path", "")).strip()
    if document_path and not os.path.isabs(document_path):
        document_path = os.path.abspath(os.path.join(os.path.dirname(path), document_path))
    if document_path and _is_within_project(document_path):
        errors.append("supporting cost document must be stored outside the project repository")
    expected_hash = str(evidence.get("supporting_document_sha256", "")).lower()
    if expected_hash and not _SHA256.fullmatch(expected_hash):
        errors.append("supporting_document_sha256 must be a lowercase SHA-256 value")
    if document_path and not os.path.isfile(document_path):
        errors.append(f"supporting cost document does not exist: {document_path}")
    elif document_path and expected_hash and sha256_file(document_path) != expected_hash:
        errors.append("supporting cost document SHA-256 does not match evidence")

    limitations = evidence.get("limitations")
    if not isinstance(limitations, list) or not any(
        str(item).strip() for item in limitations
    ):
        errors.append("limitations must contain at least one material limitation")
    if errors:
        raise ExecutionCostGateError(
            "execution-cost gate failed: " + "; ".join(errors)
        )

    return {
        "schema_version": COST_EVIDENCE_SCHEMA_VERSION,
        "status": "approved_for_internal_research",
        "scope": expected_contract["scope"],
        "cost_model_id": expected_cost_model["model_id"],
        "cost_model_fingerprint": expected_fingerprint,
        "calibration_basis": basis,
        "provisional": evidence["provisional"],
        "sample_order_count": sample_order_count,
        "market_rulebook_sha256": evidence["market_rulebook_sha256"],
        "valid_from": evidence["valid_from"],
        "valid_until": evidence["valid_until"],
        "reviewed_at": evidence["reviewed_at"],
        "double_cost_stress_required": True,
        "live_execution_ready": False,
        "supporting_document_type": document_type,
        "supporting_document_sha256": expected_hash,
        "evidence_file_sha256": sha256_file(path),
        "identity_assurance": "document_hash_only_not_approver_identity_authenticated",
        "limitations": [str(item).strip() for item in limitations if str(item).strip()],
    }


def is_release_eligible_execution_cost(
    cost_gate: dict[str, Any],
    today: date | None = None,
) -> bool:
    try:
        valid_from = datetime.strptime(
            str(cost_gate.get("valid_from", "")), "%Y-%m-%d"
        ).date()
        valid_until = datetime.strptime(
            str(cost_gate.get("valid_until", "")), "%Y-%m-%d"
        ).date()
        reviewed_at = datetime.strptime(
            str(cost_gate.get("reviewed_at", "")), "%Y-%m-%d"
        ).date()
        current_rulebook_sha256 = load_market_rulebook()[1]
    except (OSError, RuntimeError, ValueError):
        return False
    evaluation_date = today or date.today()
    return (
        cost_gate.get("schema_version") == COST_EVIDENCE_SCHEMA_VERSION
        and cost_gate.get("status") == "approved_for_internal_research"
        and cost_gate.get("calibration_basis") in SUPPORTED_CALIBRATION_BASES
        and (
            (
                cost_gate.get("calibration_basis")
                == "approved_conservative_assumption"
                and cost_gate.get("provisional") is True
                and cost_gate.get("sample_order_count") == 0
                and cost_gate.get("supporting_document_type")
                == "broker_fee_schedule_and_internal_cost_memo"
            )
            or (
                cost_gate.get("calibration_basis") == "historical_execution_sample"
                and cost_gate.get("provisional") is False
                and _integer_or_zero(cost_gate.get("sample_order_count")) >= 30
                and cost_gate.get("supporting_document_type")
                == "historical_execution_calibration_pack"
            )
        )
        and cost_gate.get("double_cost_stress_required") is True
        and cost_gate.get("live_execution_ready") is False
        and bool(str(cost_gate.get("cost_model_id", "")).strip())
        and bool(_SHA256.fullmatch(str(cost_gate.get("cost_model_fingerprint", ""))))
        and cost_gate.get("market_rulebook_sha256") == current_rulebook_sha256
        and bool(_SHA256.fullmatch(str(cost_gate.get("evidence_file_sha256", ""))))
        and bool(
            _SHA256.fullmatch(str(cost_gate.get("supporting_document_sha256", "")))
        )
        and cost_gate.get("identity_assurance")
        == "document_hash_only_not_approver_identity_authenticated"
        and isinstance(cost_gate.get("limitations"), list)
        and any(str(item).strip() for item in cost_gate.get("limitations", []))
        and valid_from <= evaluation_date <= valid_until
        and reviewed_at <= evaluation_date
        and (evaluation_date - reviewed_at).days <= COST_REVIEW_MAX_AGE_DAYS
    )


def _parse_iso_date(value: Any, field: str, errors: list[str]) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return None


def _number_or_zero(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _integer_or_zero(value: Any) -> int:
    try:
        number = float(value)
        return int(number) if math.isfinite(number) else 0
    except (TypeError, ValueError, OverflowError):
        return 0


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
