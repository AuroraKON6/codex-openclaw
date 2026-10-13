from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import collect_source_provenance
from .config import Config, PROJECT_ROOT
from .execution_cost_governance import (
    evaluate_execution_cost_evidence,
    is_release_eligible_execution_cost,
)
from .experiment_registry import evaluate_experiment_registry
from .governance import evaluate_data_license, is_release_eligible_data_license
from .input_validation import validate_research_input
from .pi_client import PiClient
from .python_runtime import inspect_python_runtime
from .research_protocol import (
    evaluate_research_protocol,
    is_release_eligible_research_protocol,
)
from .secret_scan import evaluate_secret_scan_receipt
from .source_review import evaluate_source_review_decision


READINESS_SCHEMA_VERSION = 1
DEFAULT_ACCEPTANCE_MAX_AGE_DAYS = 7
DEFAULT_PLANNING_STATUS_PATH = PROJECT_ROOT / "governance" / "project_execution_status.json"


CHECK_ACTIONS = {
    "input_contract": "Freeze and validate the exact CSI500 research input.",
    "python_runtime": "Bootstrap and use the locked Windows CPython 3.11 project environment.",
    "source_baseline": "Establish a reviewed private clean commit, tag, and remote.",
    "secret_scan": "Review the candidate tree and regenerate the secret-scan receipt.",
    "source_review_decision": "Obtain distinct Platform and Security per-file review evidence outside the repository.",
    "data_license": "Obtain current written organizational data authorization outside the repository.",
    "research_protocol": "Register the exact research protocol in an external organization system.",
    "experiment_registry": "Activate and approve the external experiment registry.",
    "execution_cost": "Approve current execution-cost evidence with an independent reviewer.",
    "local_pi_runtime": "Install and verify the pinned offline Pi runtime and no-tools policy.",
    "planning_roles": "Assign the required organization roles with separation of duties.",
    "budget_approval": "Approve the bounded paid runtime and data acceptance budget.",
    "provider_configuration": "Inject approved DeepSeek and Tushare credentials through protected storage.",
    "pi_paid_acceptance": "Run a current paid no-tools Pi contract acceptance after authorization.",
}


def build_project_readiness(
    input_path: str,
    runs_root: str = "runs",
    acceptance_root: str = "drill_reports",
    planning_status_path: str | None = None,
    inspect_pi: bool = True,
    acceptance_max_age_days: int = DEFAULT_ACCEPTANCE_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _as_utc(now or datetime.now(timezone.utc))
    checks: list[dict[str, Any]] = []

    input_data = _load_input_check(input_path, checks)
    _python_runtime_check(checks)
    _secret_scan_check(checks)
    _source_review_decision_check(checks, current)
    _source_check(checks)

    protocol_gate: dict[str, Any] | None = None
    if input_data is not None:
        _data_license_check(input_data, current, checks)
        protocol_gate = _research_protocol_check(input_data, current, checks)
        _experiment_registry_check(input_data, protocol_gate, current, checks)
        _execution_cost_check(input_data, current, checks)
    else:
        _dependency_blocked(
            checks,
            "data_license",
            "G1_REVIEW",
            "DATA_COMPLIANCE",
            "Input contract is unavailable.",
        )
        _dependency_blocked(
            checks,
            "research_protocol",
            "G1_REVIEW",
            "QUANT_VALIDATOR_COMPLIANCE",
            "Input contract is unavailable.",
        )
        _dependency_blocked(
            checks,
            "experiment_registry",
            "G1_REVIEW",
            "PLATFORM_COMPLIANCE",
            "Input contract and research protocol are unavailable.",
        )
        _dependency_blocked(
            checks,
            "execution_cost",
            "G1_REVIEW",
            "QUANT_COST_REVIEWER_COMPLIANCE",
            "Input contract is unavailable.",
        )

    _local_pi_check(checks, inspect_pi)
    _planning_activation_checks(
        checks,
        planning_status_path or str(DEFAULT_PLANNING_STATUS_PATH),
    )
    _provider_configuration_check(checks)
    _pi_acceptance_check(
        checks,
        acceptance_root,
        current,
        acceptance_max_age_days,
    )
    latest_mock = _latest_mock_evidence(runs_root)

    g1_checks = [check for check in checks if check["required_for"] == "G1_REVIEW"]
    phase_c_checks = [
        check
        for check in checks
        if check["required_for"] in {"G1_REVIEW", "PHASE_C_ACCEPTANCE"}
    ]
    g1_ready = bool(g1_checks) and all(
        check["status"] == "passed" for check in g1_checks
    )
    phase_c_complete = bool(phase_c_checks) and all(
        check["status"] == "passed" for check in phase_c_checks
    )
    blockers = [
        {
            "code": f"{check['name'].upper()}_BLOCKED",
            "required_for": check["required_for"],
            "owner_role": check["owner_role"],
            "summary": check["summary"],
            "next_action": CHECK_ACTIONS.get(check["name"], "Resolve the reported check."),
        }
        for check in checks
        if check["status"] == "blocked"
    ]

    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "generated_at": current.isoformat(),
        "report_type": "OFFLINE_PROJECT_READINESS",
        "status": (
            "READY_FOR_HUMAN_G1_REVIEW_NOT_AUTHORIZED" if g1_ready else "BLOCKED"
        ),
        "current_gate": "G0",
        "ready_for_human_g1_review": g1_ready,
        "phase_c_acceptance_complete": phase_c_complete,
        "g1_authorized": False,
        "real_run_authorized": False,
        "human_decision_required": True,
        "execution_policy": {
            "network_calls_performed": False,
            "paid_model_calls_performed": False,
            "data_provider_calls_performed": False,
            "workspace_mutations_performed": False,
            "pi_ping_performed": False,
            "pi_runtime_inspection_offline": inspect_pi,
        },
        "checks": checks,
        "blockers": blockers,
        "latest_mock_evidence": latest_mock,
        "disclaimer": (
            "Offline readiness only. This report cannot approve data use, a real run, "
            "release, trading, or real-capital actions."
        ),
    }


def _load_input_check(
    input_path: str, checks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    try:
        with open(input_path, "r", encoding="utf-8") as file:
            input_data = json.load(file)
        validate_research_input(input_data)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        _add_check(
            checks,
            "input_contract",
            "blocked",
            "G1_REVIEW",
            "QUANT_VALIDATOR",
            str(exc),
            {"input_path": os.path.abspath(input_path)},
        )
        return None
    _add_check(
        checks,
        "input_contract",
        "passed",
        "G1_REVIEW",
        "QUANT_VALIDATOR",
        "The input contract is structurally valid for CSI500 internal research.",
        {
            "input_path": os.path.abspath(input_path),
            "scope": str(input_data.get("scope", "")).upper(),
            "date_range": input_data.get("date_range", {}),
            "factor_count": len(input_data.get("strategy_params", {}).get("factors", [])),
        },
    )
    return input_data


def _source_check(checks: list[dict[str, Any]]) -> None:
    source = collect_source_provenance()
    passed = source.get("release_ready") is True
    _add_check(
        checks,
        "source_baseline",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "PLATFORM_SECURITY",
        str(source.get("reason", "Source status is unavailable.")),
        {
            "repository_available": source.get("repository_available", False),
            "head_commit": source.get("head_commit"),
            "branch": source.get("branch"),
            "dirty": source.get("dirty", True),
            "tracked_file_count": source.get("tracked_file_count", 0),
            "changed_file_count": source.get("changed_file_count", 0),
            "untracked_file_count": source.get("untracked_file_count", 0),
            "status_sha256": source.get("status_sha256"),
        },
    )


def _python_runtime_check(checks: list[dict[str, Any]]) -> None:
    try:
        runtime = inspect_python_runtime()
        passed = runtime.get("ok") is True
        summary = (
            "The locked Windows CPython 3.11 project environment passed."
            if passed
            else "; ".join(runtime.get("errors", ["Python runtime check failed."]))
        )
        details = {
            "target": runtime.get("target"),
            "executable": runtime.get("executable"),
            "python_version": runtime.get("python_version"),
            "implementation": runtime.get("implementation"),
            "platform": runtime.get("platform"),
            "user_site_enabled": runtime.get("user_site_enabled"),
            "requirements_lock_sha256": runtime.get("requirements_lock_sha256"),
            "locked_package_count": runtime.get("locked_package_count", 0),
            "package_mismatch_count": len(runtime.get("package_mismatches", [])),
            "unexpected_distribution_count": len(
                runtime.get("unexpected_distributions", [])
            ),
            "errors": runtime.get("errors", []),
        }
    except (OSError, RuntimeError, ValueError) as exc:
        passed = False
        summary = str(exc)
        details = {"inspection_failed": True}
    _add_check(
        checks,
        "python_runtime",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "PLATFORM_SECURITY",
        summary,
        details,
    )


def _secret_scan_check(checks: list[dict[str, Any]]) -> None:
    result = evaluate_secret_scan_receipt()
    _add_check(
        checks,
        "secret_scan",
        "passed" if result.get("ok") else "blocked",
        "G1_REVIEW",
        "SECURITY",
        (
            "The current commit-candidate tree matches a passed secret-scan receipt."
            if result.get("ok")
            else "; ".join(result.get("errors", []))
        ),
        result.get("receipt_summary", {}),
    )


def _source_review_decision_check(
    checks: list[dict[str, Any]], current: datetime
) -> None:
    try:
        gate = evaluate_source_review_decision(now=current)
        passed = gate.get("review_claim_valid") is True
        summary = (
            "The exact candidate has a structurally valid distinct Platform/Security file-review claim."
            if passed
            else "; ".join(gate.get("errors", ["Source review decision is unavailable."]))
        )
        details = _select(
            gate,
            "status",
            "packet_dir",
            "decision_path",
            "packet_id",
            "candidate_manifest_sha256",
            "candidate_files_sha256",
            "candidate_file_count",
            "review_flag_count",
            "decision_file_sha256",
            "identity_assurance",
            "application_hash_only_not_signature",
            "organization_identity_verified",
            "private_baseline_execution_authorized",
            "source_baseline_authorized",
            "g1_authorized",
            "real_run_authorized",
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        passed = False
        summary = str(exc)
        details = {
            "packet_path_set": bool(Config.SOURCE_REVIEW_PACKET_DIR),
            "decision_path_set": bool(Config.SOURCE_REVIEW_DECISION_PATH),
        }
    _add_check(
        checks,
        "source_review_decision",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "PLATFORM_SECURITY",
        summary,
        details,
    )


def _data_license_check(
    input_data: dict[str, Any], current: datetime, checks: list[dict[str, Any]]
) -> None:
    try:
        gate = evaluate_data_license(input_data, today=current.date())
        passed = is_release_eligible_data_license(gate, today=current.date())
        summary = (
            "Current organizational data authorization is release-eligible."
            if passed
            else f"Data-license status is {gate.get('status', 'unknown')}."
        )
        details = _select(
            gate,
            "status",
            "provider",
            "valid_from",
            "valid_until",
            "provider_terms_reviewed_at",
            "evidence_file_sha256",
            "supporting_document_sha256",
            "identity_assurance",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        passed = False
        summary = str(exc)
        details = {"evidence_path_set": bool(Config.DATA_LICENSE_EVIDENCE_PATH)}
    _add_check(
        checks,
        "data_license",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "DATA_COMPLIANCE",
        summary,
        details,
    )


def _research_protocol_check(
    input_data: dict[str, Any], current: datetime, checks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    try:
        gate = evaluate_research_protocol(input_data, now=current)
        passed = is_release_eligible_research_protocol(gate, today=current.date())
        summary = (
            "The external research protocol is current and contract-bound."
            if passed
            else f"Research-protocol status is {gate.get('status', 'unknown')}."
        )
        details = _select(
            gate,
            "status",
            "protocol_id",
            "protocol_version",
            "run_class",
            "valid_from",
            "valid_until",
            "registered_at",
            "reviewed_at",
            "model_contract_sha256",
            "evidence_file_sha256",
            "identity_and_timestamp_assurance",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        gate = None
        passed = False
        summary = str(exc)
        details = {"evidence_path_set": bool(Config.RESEARCH_PROTOCOL_EVIDENCE_PATH)}
    _add_check(
        checks,
        "research_protocol",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "QUANT_VALIDATOR_COMPLIANCE",
        summary,
        details,
    )
    return gate if passed else None


def _experiment_registry_check(
    input_data: dict[str, Any],
    protocol_gate: dict[str, Any] | None,
    current: datetime,
    checks: list[dict[str, Any]],
) -> None:
    if protocol_gate is None:
        _dependency_blocked(
            checks,
            "experiment_registry",
            "G1_REVIEW",
            "PLATFORM_COMPLIANCE",
            "A current exact-bound research protocol is required before registry evaluation.",
            {"registry_path_set": bool(Config.EXPERIMENT_REGISTRY_PATH)},
        )
        return
    try:
        gate = evaluate_experiment_registry(input_data, protocol_gate, now=current)
        passed = gate.get("status") == "ready_for_reservation" and gate.get(
            "ledger_integrity_ok"
        ) is True
        summary = (
            "The external registry is ready to reserve the frozen experiment."
            if passed
            else f"Experiment-registry status is {gate.get('status', 'unknown')}."
        )
        details = _select(
            gate,
            "status",
            "registry_id",
            "registry_metadata_sha256",
            "run_class",
            "protocol_id",
            "protocol_version",
            "ledger_integrity_ok",
            "storage_enforcement",
            "identity_and_timestamp_assurance",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        passed = False
        summary = str(exc)
        details = {"registry_path_set": bool(Config.EXPERIMENT_REGISTRY_PATH)}
    _add_check(
        checks,
        "experiment_registry",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "PLATFORM_COMPLIANCE",
        summary,
        details,
    )


def _execution_cost_check(
    input_data: dict[str, Any], current: datetime, checks: list[dict[str, Any]]
) -> None:
    try:
        gate = evaluate_execution_cost_evidence(input_data, today=current.date())
        passed = is_release_eligible_execution_cost(gate, today=current.date())
        summary = (
            "Execution-cost evidence is current and independently reviewed."
            if passed
            else f"Execution-cost status is {gate.get('status', 'unknown')}."
        )
        details = _select(
            gate,
            "status",
            "cost_model_id",
            "cost_model_fingerprint",
            "calibration_basis",
            "provisional",
            "valid_from",
            "valid_until",
            "reviewed_at",
            "market_rulebook_sha256",
            "evidence_file_sha256",
            "supporting_document_sha256",
            "identity_assurance",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        passed = False
        summary = str(exc)
        details = {"evidence_path_set": bool(Config.EXECUTION_COST_EVIDENCE_PATH)}
    _add_check(
        checks,
        "execution_cost",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "QUANT_COST_REVIEWER_COMPLIANCE",
        summary,
        details,
    )


def _local_pi_check(checks: list[dict[str, Any]], inspect_pi: bool) -> None:
    if not inspect_pi:
        _add_check(
            checks,
            "local_pi_runtime",
            "blocked",
            "G1_REVIEW",
            "MODEL_PLATFORM",
            "Offline Pi runtime inspection was explicitly skipped.",
            {"inspection_skipped": True},
        )
        return
    runtime = PiClient().inspect_runtime(list_models=True)
    policy = runtime.get("policy", {})
    passed = runtime.get("ok") is True and policy.get("all_tools_disabled") is True
    _add_check(
        checks,
        "local_pi_runtime",
        "passed" if passed else "blocked",
        "G1_REVIEW",
        "MODEL_PLATFORM",
        (
            "Pinned Pi runtime and offline model catalog passed."
            if passed
            else "; ".join(runtime.get("errors", []))
        ),
        {
            "node_version": runtime.get("node_version"),
            "pi_package": runtime.get("pi_package"),
            "pi_version": runtime.get("pi_version"),
            "expected_pi_version": runtime.get("expected_pi_version"),
            "provider": runtime.get("provider"),
            "model": runtime.get("model"),
            "model_available": runtime.get("model_available", False),
            "runtime_lock_sha256": runtime.get("runtime_lock_sha256"),
            "policy": policy,
        },
    )


def _planning_activation_checks(
    checks: list[dict[str, Any]], planning_status_path: str
) -> None:
    try:
        status = json.loads(Path(planning_status_path).read_text(encoding="utf-8"))
        roles = status.get("role_assignments", {})
        unassigned = sorted(
            key
            for key, value in roles.items()
            if str(value).strip().upper() in {"", "UNASSIGNED", "UNVERIFIED"}
        )
        role_passed = bool(roles) and not unassigned
        budget_status = str(status.get("budget_approval_status", "UNAPPROVED")).upper()
        budget_passed = budget_status == "APPROVED"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        roles = {}
        unassigned = []
        role_passed = False
        budget_status = "UNAVAILABLE"
        budget_passed = False
        planning_error = str(exc)
    else:
        planning_error = ""

    _add_check(
        checks,
        "planning_roles",
        "passed" if role_passed else "blocked",
        "G1_REVIEW",
        "GM",
        (
            "All required planning roles are assigned; organization identity evidence still requires human verification."
            if role_passed
            else planning_error
            or f"{len(unassigned)} required planning roles remain unassigned."
        ),
        {
            "planning_status_path": os.path.abspath(planning_status_path),
            "required_role_count": len(roles),
            "unassigned_role_count": len(unassigned),
            "local_record_is_identity_evidence": False,
        },
    )
    _add_check(
        checks,
        "budget_approval",
        "passed" if budget_passed else "blocked",
        "G1_REVIEW",
        "GM_FINANCE",
        (
            "The planning tracker records an approved bounded acceptance budget; human evidence remains authoritative."
            if budget_passed
            else f"Planning budget status is {budget_status}."
        ),
        {
            "planning_budget_status": budget_status,
            "local_record_is_budget_authority": False,
        },
    )


def _provider_configuration_check(checks: list[dict[str, Any]]) -> None:
    errors = Config.validate(require_deepseek=True, require_tushare=True)
    _add_check(
        checks,
        "provider_configuration",
        "passed" if not errors else "blocked",
        "PHASE_C_ACCEPTANCE",
        "MODEL_DATA_FINANCE",
        (
            "Required protected credentials and bounded provider configuration are present."
            if not errors
            else "; ".join(errors)
        ),
        {
            "deepseek_api_key_set": bool(Config.DEEPSEEK_API_KEY),
            "tushare_token_set": bool(Config.TUSHARE_TOKEN),
            "deepseek_model": Config.DEEPSEEK_MODEL,
            "pi_version": Config.PI_VERSION,
            "pricing_reviewed_at": Config.DEEPSEEK_PRICING_REVIEWED_DATE,
            "credential_values_included": False,
        },
    )


def _pi_acceptance_check(
    checks: list[dict[str, Any]],
    acceptance_root: str,
    current: datetime,
    max_age_days: int,
) -> None:
    result = latest_pi_acceptance(acceptance_root, current, max_age_days)
    _add_check(
        checks,
        "pi_paid_acceptance",
        "passed" if result.get("current") else "blocked",
        "PHASE_C_ACCEPTANCE",
        "MODEL_PLATFORM_GM",
        str(result.get("summary", "Pi paid acceptance is unavailable.")),
        result,
    )


def latest_pi_acceptance(
    acceptance_root: str,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_ACCEPTANCE_MAX_AGE_DAYS,
) -> dict[str, Any]:
    if max_age_days <= 0:
        raise ValueError("acceptance_max_age_days must be positive")
    current = _as_utc(now or datetime.now(timezone.utc))
    reports: list[tuple[datetime, Path, dict[str, Any]]] = []
    for path in Path(acceptance_root).glob(
        "pi_runtime_acceptance_*/acceptance_report.json"
    ):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            generated_at = _parse_datetime(report.get("generated_at"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        reports.append((generated_at, path, report))
    if not reports:
        return {
            "found": False,
            "current": False,
            "max_age_days": max_age_days,
            "summary": "No Pi paid acceptance report was found.",
        }

    generated_at, path, report = max(reports, key=lambda item: item[0])
    generated_in_future = generated_at > current
    age_days = max(0.0, (current - generated_at).total_seconds() / 86400)
    policy = report.get("runtime_policy", {})
    usage = report.get("usage", {})
    contract_passed = (
        report.get("status") == "passed"
        and report.get("acceptance_scope")
        == "runtime_contract_only_not_market_research"
        and report.get("runtime") == "pi"
        and report.get("pi_version") == Config.PI_VERSION
        and report.get("provider") == "deepseek"
        and report.get("model") == Config.DEEPSEEK_MODEL
        and int(usage.get("totalTokens", 0) or 0) > 0
        and policy.get("all_tools_disabled") is True
        and policy.get("context_files_disabled") is True
        and policy.get("project_resources_ignored") is True
    )
    current_acceptance = (
        contract_passed and not generated_in_future and age_days <= max_age_days
    )
    return {
        "found": True,
        "current": current_acceptance,
        "report_path": str(path.resolve()),
        "generated_at": generated_at.isoformat(),
        "age_days": round(age_days, 2),
        "max_age_days": max_age_days,
        "generated_in_future": generated_in_future,
        "contract_passed": contract_passed,
        "runtime": report.get("runtime"),
        "pi_version": report.get("pi_version"),
        "provider": report.get("provider"),
        "model": report.get("model"),
        "total_tokens_positive": int(usage.get("totalTokens", 0) or 0) > 0,
        "all_tools_disabled": policy.get("all_tools_disabled") is True,
        "summary": (
            "A current paid Pi no-tools contract acceptance is available."
            if current_acceptance
            else "The latest Pi acceptance is missing, stale, or contract-incomplete."
        ),
    }


def _latest_mock_evidence(runs_root: str) -> dict[str, Any]:
    candidates: list[tuple[datetime, Path, dict[str, Any]]] = []
    root = Path(runs_root)
    if not root.is_dir():
        return {"found": False, "status": "not_available"}
    for state_path in root.glob("*/state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("mock") is not True:
                continue
            finished_at = _parse_datetime(state.get("finished_at"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        candidates.append((finished_at, state_path.parent, state))
    if not candidates:
        return {"found": False, "status": "not_available"}

    finished_at, run_dir, state = max(candidates, key=lambda item: item[0])
    integrity = _load_optional_json(run_dir / "operations" / "integrity_verification.json")
    release = _load_optional_json(run_dir / "release" / "release_candidate.json")
    total_agents = int(state.get("total_agents", 0) or 0)
    success_count = int(state.get("success_count", 0) or 0)
    passed = (
        state.get("status") == "completed"
        and total_agents > 0
        and success_count == total_agents
        and int(state.get("error_count", 0) or 0) == 0
        and integrity.get("ok") is True
        and release.get("status") == "BLOCKED"
    )
    return {
        "found": True,
        "status": "passed" if passed else "failed",
        "mode": "MOCK",
        "run_id": state.get("run_id"),
        "finished_at": finished_at.isoformat(),
        "success_count": success_count,
        "total_agents": total_agents,
        "error_count": int(state.get("error_count", 0) or 0),
        "integrity_ok": integrity.get("ok") is True,
        "checked_file_count": integrity.get("checked_file_count", 0),
        "event_count": integrity.get("event_chain", {}).get("event_count", 0),
        "release_status": release.get("status"),
        "release_blocker_count": len(release.get("blockers", [])),
        "real_evidence": False,
    }


def _dependency_blocked(
    checks: list[dict[str, Any]],
    name: str,
    required_for: str,
    owner_role: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> None:
    _add_check(
        checks,
        name,
        "blocked",
        required_for,
        owner_role,
        summary,
        details or {"dependency_blocked": True},
    )


def _add_check(
    checks: list[dict[str, Any]],
    name: str,
    status: str,
    required_for: str,
    owner_role: str,
    summary: str,
    details: dict[str, Any],
) -> None:
    checks.append(
        {
            "name": name,
            "status": status,
            "required_for": required_for,
            "owner_role": owner_role,
            "summary": summary,
            "details": details,
        }
    )


def _select(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value.get(key) for key in keys}


def _load_optional_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse_datetime(value: Any) -> datetime:
    if not value:
        raise ValueError("timestamp is missing")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
