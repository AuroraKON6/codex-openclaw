from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Any

from .audit import sha256_file
from .config import Config, PROJECT_ROOT


LICENSE_SCHEMA_VERSION = 2
PUBLIC_TUSHARE_TERMS_URL = "https://tushare.pro/document/1?doc_id=405"
LICENSE_TERMS_REVIEW_MAX_AGE_DAYS = 30
REQUIRED_TUSHARE_ENDPOINTS = {
    "trade_cal",
    "index_weight",
    "daily",
    "adj_factor",
    "stk_limit",
    "suspend_d",
    "daily_basic",
}
REQUIRED_PROCESSING_RIGHTS = {
    "automated_api_access",
    "derived_analytics",
    "local_cache",
    "third_party_llm_processing",
}
SUPPORTED_AUTHORIZATION_DOCUMENT_TYPES = {
    "provider_enterprise_order_form",
    "provider_signed_contract",
    "provider_written_amendment",
}
SUPPORTED_INTENDED_USES = {
    "personal_non_commercial_research",
    "licensed_internal_research",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class GovernanceGateError(RuntimeError):
    pass


def validate_governance_input(payload: dict[str, Any]) -> None:
    governance = payload.get("governance")
    if not isinstance(governance, dict):
        raise ValueError("governance is required")
    intended_use = str(governance.get("intended_use", "")).lower()
    if intended_use not in SUPPORTED_INTENDED_USES:
        raise ValueError(
            "governance.intended_use must be personal_non_commercial_research "
            "or licensed_internal_research"
        )
    if governance.get("external_distribution_requested") is not False:
        raise ValueError("governance.external_distribution_requested must be false")
    if governance.get("human_review_required") is not True:
        raise ValueError("governance.human_review_required must be true")
    if str(governance.get("data_provider", "tushare")).lower() != "tushare":
        raise ValueError("this implementation currently supports governance.data_provider=tushare")


def evaluate_data_license(
    input_data: dict[str, Any],
    evidence_path: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    governance = input_data.get("governance", {})
    intended_use = str(governance.get("intended_use", "")).lower()
    if intended_use == "personal_non_commercial_research":
        return {
            "schema_version": LICENSE_SCHEMA_VERSION,
            "status": "restricted_personal_non_commercial",
            "provider": "tushare",
            "intended_use": intended_use,
            "commercial_use_permitted": False,
            "organizational_use_permitted": False,
            "external_distribution_permitted": False,
            "basis": "Tushare public data-service terms",
            "terms_url": PUBLIC_TUSHARE_TERMS_URL,
        }
    if intended_use != "licensed_internal_research":
        raise GovernanceGateError(f"unsupported intended use: {intended_use or 'missing'}")

    path = os.path.abspath(evidence_path or Config.DATA_LICENSE_EVIDENCE_PATH or "")
    if not evidence_path and not Config.DATA_LICENSE_EVIDENCE_PATH:
        raise GovernanceGateError(
            "licensed_internal_research requires DATA_LICENSE_EVIDENCE_PATH; "
            "the public Tushare terms are non-commercial and personal-use only"
        )
    if not os.path.isfile(path):
        raise GovernanceGateError(f"data-license evidence file does not exist: {path}")
    if _is_within_project(path):
        raise GovernanceGateError(
            "data-license evidence must be stored outside the project repository"
        )
    try:
        with open(path, "r", encoding="utf-8") as file:
            evidence = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceGateError(f"cannot read data-license evidence: {exc}") from exc

    errors = []
    if evidence.get("schema_version") != LICENSE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {LICENSE_SCHEMA_VERSION}")
    if str(evidence.get("provider", "")).lower() != "tushare":
        errors.append("provider must be tushare")
    if str(evidence.get("status", "")).upper() != "APPROVED":
        errors.append("status must be APPROVED")
    if intended_use not in {
        str(item).lower() for item in evidence.get("permitted_uses", [])
    }:
        errors.append(f"permitted_uses must include {intended_use}")
    if evidence.get("external_distribution_permitted") is not False:
        errors.append("external_distribution_permitted must be false for this system")
    if evidence.get("separate_written_organizational_authorization") is not True:
        errors.append(
            "separate_written_organizational_authorization must be true because public "
            "Tushare terms are personal and non-commercial"
        )
    if evidence.get("organizational_use_permitted") is not True:
        errors.append("organizational_use_permitted must be true")
    if evidence.get("commercial_internal_research_permitted") is not True:
        errors.append("commercial_internal_research_permitted must be true")
    if evidence.get("provider_terms_url") != PUBLIC_TUSHARE_TERMS_URL:
        errors.append(f"provider_terms_url must be {PUBLIC_TUSHARE_TERMS_URL}")
    document_type = str(evidence.get("supporting_document_type", ""))
    if document_type not in SUPPORTED_AUTHORIZATION_DOCUMENT_TYPES:
        errors.append(
            "supporting_document_type must identify a provider contract, amendment, "
            "or enterprise order form"
        )
    for field in (
        "licensee_legal_name",
        "contract_reference",
        "provider_approval_reference",
        "provider_signatory_name",
        "provider_signatory_title",
        "licensee_approver_name",
        "licensee_approver_title",
        "valid_from",
        "valid_until",
        "provider_terms_reviewed_at",
        "supporting_document_path",
        "supporting_document_sha256",
    ):
        if not str(evidence.get(field, "")).strip():
            errors.append(f"{field} is required")

    endpoints = {str(item) for item in evidence.get("permitted_endpoints", [])}
    missing_endpoints = sorted(REQUIRED_TUSHARE_ENDPOINTS.difference(endpoints))
    if missing_endpoints:
        errors.append("permitted_endpoints missing: " + ", ".join(missing_endpoints))

    processing_rights = {
        str(item).lower() for item in evidence.get("permitted_processing", [])
    }
    missing_processing = sorted(REQUIRED_PROCESSING_RIGHTS.difference(processing_rights))
    if missing_processing:
        errors.append(
            "permitted_processing missing: " + ", ".join(missing_processing)
        )
    processors = {
        str(item).lower() for item in evidence.get("permitted_processors", [])
    }
    if "deepseek" not in processors:
        errors.append(
            "permitted_processors must include deepseek because derived research context "
            "is sent to the approved Pi LLM runtime"
        )
    try:
        maximum_retention_days = int(evidence.get("maximum_retention_days", 0))
    except (TypeError, ValueError):
        maximum_retention_days = 0
    if maximum_retention_days < Config.RUN_RETENTION_DAYS:
        errors.append(
            "maximum_retention_days must cover configured RUN_RETENTION_DAYS="
            f"{Config.RUN_RETENTION_DAYS}"
        )
    if evidence.get("termination_disposition") != "delete_or_return_per_provider_instruction":
        errors.append(
            "termination_disposition must be delete_or_return_per_provider_instruction"
        )

    valid_from = _parse_iso_date(evidence.get("valid_from"), "valid_from", errors)
    valid_until = _parse_iso_date(evidence.get("valid_until"), "valid_until", errors)
    terms_reviewed_at = _parse_iso_date(
        evidence.get("provider_terms_reviewed_at"),
        "provider_terms_reviewed_at",
        errors,
    )
    evaluation_date = today or date.today()
    if valid_from and evaluation_date < valid_from:
        errors.append("license is not yet effective")
    if valid_until and evaluation_date > valid_until:
        errors.append("license has expired")
    if valid_from and valid_until and valid_from > valid_until:
        errors.append("valid_from must not be after valid_until")
    if terms_reviewed_at and terms_reviewed_at > evaluation_date:
        errors.append("provider_terms_reviewed_at must not be in the future")
    if (
        terms_reviewed_at
        and (evaluation_date - terms_reviewed_at).days > LICENSE_TERMS_REVIEW_MAX_AGE_DAYS
    ):
        errors.append(
            "provider public terms review is stale; review must be refreshed within "
            f"{LICENSE_TERMS_REVIEW_MAX_AGE_DAYS} days"
        )

    document_path = str(evidence.get("supporting_document_path", "")).strip()
    if document_path and not os.path.isabs(document_path):
        document_path = os.path.abspath(os.path.join(os.path.dirname(path), document_path))
    if document_path and _is_within_project(document_path):
        errors.append("supporting authorization document must be outside the project repository")
    expected_hash = str(evidence.get("supporting_document_sha256", "")).lower()
    if expected_hash and not _SHA256.fullmatch(expected_hash):
        errors.append("supporting_document_sha256 must be a lowercase SHA-256 value")
    if document_path and not os.path.isfile(document_path):
        errors.append(f"supporting document does not exist: {document_path}")
    elif document_path and expected_hash:
        actual_hash = sha256_file(document_path)
        if actual_hash != expected_hash:
            errors.append("supporting document SHA-256 does not match evidence")

    if errors:
        raise GovernanceGateError("data-license gate failed: " + "; ".join(errors))

    return {
        "schema_version": LICENSE_SCHEMA_VERSION,
        "status": "approved",
        "provider": "tushare",
        "intended_use": intended_use,
        "commercial_use_permitted": True,
        "organizational_use_permitted": True,
        "commercial_internal_research_permitted": True,
        "separate_written_organizational_authorization": True,
        "external_distribution_permitted": False,
        "licensee_legal_name": evidence["licensee_legal_name"],
        "contract_reference": evidence["contract_reference"],
        "provider_approval_reference": evidence["provider_approval_reference"],
        "valid_from": evidence["valid_from"],
        "valid_until": evidence["valid_until"],
        "permitted_endpoints": sorted(endpoints),
        "permitted_processing": sorted(processing_rights),
        "permitted_processors": sorted(processors),
        "maximum_retention_days": maximum_retention_days,
        "termination_disposition": evidence["termination_disposition"],
        "provider_terms_url": PUBLIC_TUSHARE_TERMS_URL,
        "provider_terms_reviewed_at": evidence["provider_terms_reviewed_at"],
        "authorization_document_type": document_type,
        "identity_assurance": "document_hash_only_not_signature_authenticated",
        "evidence_file_sha256": sha256_file(path),
        "supporting_document_sha256": expected_hash,
    }


def is_release_eligible_data_license(
    license_gate: dict[str, Any],
    today: date | None = None,
) -> bool:
    processing_rights = {
        str(item).lower() for item in license_gate.get("permitted_processing", [])
    }
    processors = {
        str(item).lower() for item in license_gate.get("permitted_processors", [])
    }
    try:
        maximum_retention_days = int(license_gate.get("maximum_retention_days", 0))
    except (TypeError, ValueError):
        maximum_retention_days = 0
    try:
        valid_from = datetime.strptime(
            str(license_gate.get("valid_from", "")), "%Y-%m-%d"
        ).date()
        valid_until = datetime.strptime(
            str(license_gate.get("valid_until", "")), "%Y-%m-%d"
        ).date()
        terms_reviewed_at = datetime.strptime(
            str(license_gate.get("provider_terms_reviewed_at", "")), "%Y-%m-%d"
        ).date()
    except ValueError:
        return False
    evaluation_date = today or date.today()
    return (
        license_gate.get("schema_version") == LICENSE_SCHEMA_VERSION
        and license_gate.get("status") == "approved"
        and license_gate.get("commercial_use_permitted") is True
        and license_gate.get("organizational_use_permitted") is True
        and license_gate.get("commercial_internal_research_permitted") is True
        and license_gate.get("separate_written_organizational_authorization") is True
        and license_gate.get("external_distribution_permitted") is False
        and REQUIRED_PROCESSING_RIGHTS.issubset(processing_rights)
        and "deepseek" in processors
        and maximum_retention_days >= Config.RUN_RETENTION_DAYS
        and valid_from <= evaluation_date <= valid_until
        and terms_reviewed_at <= evaluation_date
        and (evaluation_date - terms_reviewed_at).days
        <= LICENSE_TERMS_REVIEW_MAX_AGE_DAYS
        and license_gate.get("identity_assurance")
        == "document_hash_only_not_signature_authenticated"
        and bool(_SHA256.fullmatch(str(license_gate.get("evidence_file_sha256", ""))))
        and bool(
            _SHA256.fullmatch(
                str(license_gate.get("supporting_document_sha256", ""))
            )
        )
    )


def build_business_controls(
    input_data: dict[str, Any],
    mock: bool,
    license_gate: dict[str, Any] | None = None,
    execution_cost_gate: dict[str, Any] | None = None,
    research_protocol_gate: dict[str, Any] | None = None,
    experiment_registry_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    governance = input_data.get("governance", {})
    return {
        "real_order_execution_enabled": False,
        "broker_connection_enabled": False,
        "llm_may_compute_performance_metrics": False,
        "human_review_required": True,
        "point_in_time_membership_required": True,
        "tradeability_data_required": True,
        "external_distribution_approved": False,
        "external_distribution_requested": False,
        "intended_use": governance.get("intended_use", "unknown"),
        "data_provider": governance.get("data_provider", "tushare"),
        "data_license_gate": license_gate
        or {
            "status": "not_evaluated_mock" if mock else "unavailable",
            "commercial_use_permitted": False,
            "external_distribution_permitted": False,
        },
        "research_protocol_gate": research_protocol_gate
        or {
            "status": "not_evaluated_mock" if mock else "unavailable",
            "live_execution_authorized": False,
            "external_distribution_authorized": False,
        },
        "experiment_registry_gate": experiment_registry_gate
        or {
            "status": "not_evaluated_mock" if mock else "unavailable",
            "ledger_integrity_ok": False,
            "live_execution_authorized": False,
            "external_distribution_authorized": False,
            "broker_connection_enabled": False,
        },
        "execution_cost_gate": execution_cost_gate
        or {
            "status": "not_evaluated_mock" if mock else "unavailable",
            "live_execution_ready": False,
        },
    }


def _parse_iso_date(value: Any, field: str, errors: list[str]) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return None


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
