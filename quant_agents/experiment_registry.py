from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterator

from .audit import canonical_json_sha256, sha256_file, write_json_atomic
from .config import Config, PROJECT_ROOT
from .research_protocol import (
    build_model_contract_fingerprint,
    is_release_eligible_research_protocol,
)


REGISTRY_SCHEMA_VERSION = 1
LEDGER_ENTRY_SCHEMA_VERSION = 1
PROJECT_ID = "csi500-quant-research"
REGISTRY_FILENAME = "registry.json"
LEDGER_FILENAME = "experiments.jsonl"
REQUIRED_APPROVAL_ROLES = {
    "compliance_owner",
    "independent_model_validator",
    "platform_owner",
    "quant_owner",
}
REQUIRED_RUN_CLASSES = {
    "development_backtest",
    "forward_observation_refresh",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_REVISION = re.compile(r"^[0-9a-fA-F]{40,64}$")


class ExperimentRegistryError(RuntimeError):
    pass


def initialize_experiment_registry(
    evidence_path: str,
    registry_root: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    evidence_file = _require_external_file(evidence_path, "registry evidence")
    root = _external_path(registry_root, "experiment registry")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    evidence = _load_json(evidence_file, "registry evidence")
    normalized = _validate_registry_evidence(evidence, evidence_file, current)

    registry_path = os.path.join(root, REGISTRY_FILENAME)
    if os.path.isfile(registry_path):
        existing = load_registry_metadata(root, now=current)
        if existing.get("evidence_file_sha256") != normalized["evidence_file_sha256"]:
            raise ExperimentRegistryError(
                "registry already exists with different authorization evidence"
            )
        return registry_status(root, now=current)

    os.makedirs(root, exist_ok=True)
    metadata = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "project_id": PROJECT_ID,
        "registry_id": normalized["registry_id"],
        "status": "ACTIVE",
        "created_at": current.isoformat(),
        "registered_at": normalized["registered_at"],
        "valid_from": normalized["valid_from"],
        "valid_until": normalized["valid_until"],
        "system_of_record_reference": normalized["system_of_record_reference"],
        "allowed_run_classes": normalized["allowed_run_classes"],
        "retention_days": normalized["retention_days"],
        "approval_roles": normalized["approval_roles"],
        "approval_evidence_references": normalized[
            "approval_evidence_references"
        ],
        "evidence_path": evidence_file,
        "evidence_file_sha256": normalized["evidence_file_sha256"],
        "supporting_document_path": normalized["supporting_document_path"],
        "supporting_document_sha256": normalized[
            "supporting_document_sha256"
        ],
        "supporting_document_type": normalized["supporting_document_type"],
        "append_only": True,
        "storage_enforcement": "application_hash_chain_not_worm",
        "identity_and_timestamp_assurance": (
            "external_record_claim_bound_by_hash_not_cryptographically_authenticated"
        ),
        "live_execution_authorized": False,
        "external_distribution_authorized": False,
        "broker_connection_enabled": False,
        "disclaimer": (
            "Internal research experiment registry only; it cannot authorize orders, "
            "broker connectivity, external distribution, or real-capital advice."
        ),
    }
    metadata["registry_identity_sha256"] = _registry_identity_sha256(metadata)
    write_json_atomic(registry_path, metadata)
    ledger_path = os.path.join(root, LEDGER_FILENAME)
    try:
        with open(ledger_path, "x", encoding="utf-8"):
            pass
    except FileExistsError:
        if os.path.getsize(ledger_path) != 0:
            raise ExperimentRegistryError(
                "ledger appeared during initialization and is not empty"
            )
    return registry_status(root, now=current)


def load_registry_metadata(
    registry_dir: str,
    expected_metadata_sha256: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _require_external_directory(registry_dir)
    path = os.path.join(root, REGISTRY_FILENAME)
    if not os.path.isfile(path):
        raise ExperimentRegistryError(f"registry metadata is missing: {path}")
    actual_sha256 = sha256_file(path)
    if expected_metadata_sha256 and actual_sha256 != expected_metadata_sha256.lower():
        raise ExperimentRegistryError("registry metadata SHA-256 mismatch")
    metadata = _load_json(path, "registry metadata")
    errors: list[str] = []
    if metadata.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        errors.append(f"registry schema_version must be {REGISTRY_SCHEMA_VERSION}")
    if metadata.get("project_id") != PROJECT_ID:
        errors.append(f"registry project_id must be {PROJECT_ID}")
    if metadata.get("status") != "ACTIVE":
        errors.append("registry status must be ACTIVE")
    if metadata.get("append_only") is not True:
        errors.append("registry append_only must be true")
    if metadata.get("storage_enforcement") != "application_hash_chain_not_worm":
        errors.append("registry storage enforcement declaration is invalid")
    if metadata.get("live_execution_authorized") is not False:
        errors.append("registry live_execution_authorized must be false")
    if metadata.get("external_distribution_authorized") is not False:
        errors.append("registry external_distribution_authorized must be false")
    if metadata.get("broker_connection_enabled") is not False:
        errors.append("registry broker_connection_enabled must be false")
    allowed = set(metadata.get("allowed_run_classes", []))
    if not REQUIRED_RUN_CLASSES.issubset(allowed):
        errors.append("registry does not allow all required research run classes")
    try:
        retention_days = int(metadata.get("retention_days", 0))
    except (TypeError, ValueError):
        retention_days = 0
    if retention_days < Config.RUN_RETENTION_DAYS:
        errors.append("registry retention is shorter than the run retention policy")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    valid_from = _parse_date(metadata.get("valid_from"), "valid_from", errors)
    valid_until = _parse_date(metadata.get("valid_until"), "valid_until", errors)
    if valid_from and current.date() < valid_from:
        errors.append("registry authorization is not yet effective")
    if valid_until and current.date() > valid_until:
        errors.append("registry authorization has expired")
    if valid_from and valid_until and valid_until < valid_from:
        errors.append("registry valid_until predates valid_from")
    registered_at = _parse_timestamp(
        metadata.get("registered_at"), "registered_at", errors
    )
    if registered_at and registered_at > current:
        errors.append("registry registered_at must not be in the future")
    if metadata.get("registry_identity_sha256") != _registry_identity_sha256(
        metadata
    ):
        errors.append("registry identity hash is invalid")
    evidence_path = str(metadata.get("evidence_path", ""))
    supporting_path = str(metadata.get("supporting_document_path", ""))
    _verify_bound_external_file(
        evidence_path,
        metadata.get("evidence_file_sha256"),
        "registry evidence",
        errors,
    )
    _verify_bound_external_file(
        supporting_path,
        metadata.get("supporting_document_sha256"),
        "registry supporting document",
        errors,
    )
    roles = set(metadata.get("approval_roles", []))
    if roles != REQUIRED_APPROVAL_ROLES:
        errors.append("registry approval roles are incomplete or unexpected")
    references = metadata.get("approval_evidence_references", [])
    if not isinstance(references, list) or len(set(references)) != len(
        REQUIRED_APPROVAL_ROLES
    ):
        errors.append("registry approval evidence references are incomplete")
    if errors:
        raise ExperimentRegistryError("; ".join(dict.fromkeys(errors)))
    result = dict(metadata)
    result["registry_dir"] = root
    result["registry_metadata_sha256"] = actual_sha256
    return result


def evaluate_experiment_registry(
    input_data: dict[str, Any],
    protocol_gate: dict[str, Any],
    registry_dir: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = registry_dir or Config.EXPERIMENT_REGISTRY_PATH
    if not root:
        raise ExperimentRegistryError("EXPERIMENT_REGISTRY_PATH not set")
    metadata = load_registry_metadata(root, now=now)
    input_fingerprint = canonical_json_sha256(input_data)
    model_contract_sha256 = build_model_contract_fingerprint(input_data)
    if not is_release_eligible_research_protocol(
        protocol_gate,
        input_fingerprint=input_fingerprint,
        model_contract_fingerprint=model_contract_sha256,
        today=(now or datetime.now(timezone.utc)).date(),
    ):
        raise ExperimentRegistryError(
            "experiment registry requires a current exact-bound research protocol"
        )
    run_class = str(protocol_gate.get("run_class", ""))
    if run_class not in metadata.get("allowed_run_classes", []):
        raise ExperimentRegistryError(
            f"research run_class is not authorized by registry: {run_class or 'missing'}"
        )
    return {
        "schema_version": 1,
        "status": "ready_for_reservation",
        "registry_id": metadata.get("registry_id"),
        "registry_dir": metadata.get("registry_dir"),
        "registry_metadata_sha256": metadata.get("registry_metadata_sha256"),
        "run_class": run_class,
        "protocol_id": protocol_gate.get("protocol_id"),
        "protocol_version": protocol_gate.get("protocol_version"),
        "input_fingerprint": input_fingerprint,
        "model_contract_sha256": model_contract_sha256,
        "ledger_integrity_ok": _ledger_integrity(metadata),
        "storage_enforcement": metadata.get("storage_enforcement"),
        "identity_and_timestamp_assurance": metadata.get(
            "identity_and_timestamp_assurance"
        ),
        "live_execution_authorized": False,
        "external_distribution_authorized": False,
        "broker_connection_enabled": False,
    }


def reserve_experiment(
    registry_dir: str,
    run_id: str,
    run_dir: str,
    input_data: dict[str, Any],
    source_provenance: dict[str, Any],
    protocol_gate: dict[str, Any],
    request_id: str | None = None,
    retry_of: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    readiness = evaluate_experiment_registry(
        input_data, protocol_gate, registry_dir=registry_dir, now=now
    )
    source_revision = str(source_provenance.get("head_commit", ""))
    if source_provenance.get("release_ready") is not True or not _SOURCE_REVISION.fullmatch(
        source_revision
    ):
        raise ExperimentRegistryError(
            "experiment reservation requires a clean committed source revision"
        )
    if not str(run_id).strip():
        raise ExperimentRegistryError("run_id is required for experiment reservation")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    metadata = load_registry_metadata(
        registry_dir,
        expected_metadata_sha256=readiness["registry_metadata_sha256"],
        now=current,
    )
    entry = {
        "schema_version": LEDGER_ENTRY_SCHEMA_VERSION,
        "registry_id": metadata["registry_id"],
        "event_type": "RESERVED",
        "recorded_at": current.isoformat(),
        "run_id": str(run_id),
        "run_dir": os.path.abspath(run_dir),
        "request_id": request_id,
        "retry_of": retry_of,
        "runtime": "pi",
        "mock": False,
        "input_fingerprint": readiness["input_fingerprint"],
        "model_contract_sha256": readiness["model_contract_sha256"],
        "protocol_id": protocol_gate.get("protocol_id"),
        "protocol_version": protocol_gate.get("protocol_version"),
        "protocol_evidence_sha256": protocol_gate.get("evidence_file_sha256"),
        "run_class": readiness["run_class"],
        "source_head_commit": source_revision.lower(),
        "source_provenance_sha256": canonical_json_sha256(source_provenance),
        "intended_use": input_data.get("governance", {}).get(
            "intended_use", "unknown"
        ),
        "previous_entry_hash": None,
        "broker_connection_enabled": False,
        "live_execution_authorized": False,
        "external_distribution_authorized": False,
        "disclaimer": "Research experiment only; no real-capital action is authorized.",
    }
    ledger_path = os.path.join(metadata["registry_dir"], LEDGER_FILENAME)
    append_status = "reserved"
    with _registry_lock(metadata["registry_dir"]):
        entries = _read_and_verify_ledger(metadata, ledger_path)
        same_run = [row for row in entries if row.get("run_id") == str(run_id)]
        if same_run:
            reservation = same_run[0]
            if any(row.get("event_type") == "FINALIZED" for row in same_run):
                raise ExperimentRegistryError(
                    f"run_id is already finalized in experiment registry: {run_id}"
                )
            if _reservation_contract(reservation) != _reservation_contract(entry):
                raise ExperimentRegistryError(
                    f"run_id already has a different experiment reservation: {run_id}"
                )
            entry = reservation
            append_status = "no_op_already_reserved"
        else:
            entry["sequence"] = len(entries) + 1
            entry["previous_entry_hash"] = (
                entries[-1].get("entry_hash") if entries else None
            )
            entry["entry_hash"] = canonical_json_sha256(entry)
            _append_json_line(ledger_path, entry)
            _read_and_verify_ledger(metadata, ledger_path)
    return {
        **readiness,
        "status": "reserved",
        "append_status": append_status,
        "reservation_entry_hash": entry.get("entry_hash"),
        "reservation_recorded_at": entry.get("recorded_at"),
        "finalization_entry_hash": None,
        "state_contract_sha256": None,
    }


def finalize_experiment(
    state: dict[str, Any],
    registry_gate: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    gate = registry_gate or state.get("business_controls", {}).get(
        "experiment_registry_gate", {}
    )
    if gate.get("status") not in {"reserved", "finalized"}:
        raise ExperimentRegistryError("run has no valid experiment reservation")
    root = str(gate.get("registry_dir", ""))
    metadata = load_registry_metadata(
        root,
        expected_metadata_sha256=str(gate.get("registry_metadata_sha256", "")),
        now=now,
    )
    run_id = str(state.get("run_id", ""))
    contract = build_experiment_outcome_contract(state)
    contract_sha256 = canonical_json_sha256(contract)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ledger_path = os.path.join(metadata["registry_dir"], LEDGER_FILENAME)
    append_status = "finalized"
    with _registry_lock(metadata["registry_dir"]):
        entries = _read_and_verify_ledger(metadata, ledger_path)
        same_run = [row for row in entries if row.get("run_id") == run_id]
        reservations = [
            row for row in same_run if row.get("event_type") == "RESERVED"
        ]
        finalizations = [
            row for row in same_run if row.get("event_type") == "FINALIZED"
        ]
        if len(reservations) != 1:
            raise ExperimentRegistryError(
                f"run must have exactly one reservation before finalization: {run_id}"
            )
        reservation = reservations[0]
        if reservation.get("entry_hash") != gate.get("reservation_entry_hash"):
            raise ExperimentRegistryError("state reservation hash differs from ledger")
        if finalizations:
            finalization = finalizations[0]
            if finalization.get("state_contract_sha256") != contract_sha256:
                raise ExperimentRegistryError(
                    "run is already finalized with a different outcome contract"
                )
            append_status = "no_op_already_finalized"
        else:
            finalization = {
                "schema_version": LEDGER_ENTRY_SCHEMA_VERSION,
                "registry_id": metadata["registry_id"],
                "event_type": "FINALIZED",
                "recorded_at": current.isoformat(),
                "sequence": len(entries) + 1,
                "run_id": run_id,
                "reservation_entry_hash": reservation.get("entry_hash"),
                "outcome_status": state.get("status"),
                "clean_completed": state.get("status") == "completed"
                and int(state.get("error_count", 0)) == 0,
                "state_contract_sha256": contract_sha256,
                "outcome": contract,
                "previous_entry_hash": entries[-1].get("entry_hash") if entries else None,
                "broker_connection_enabled": False,
                "live_execution_authorized": False,
                "external_distribution_authorized": False,
                "disclaimer": "Recorded research outcome only; no real-capital action is authorized.",
            }
            finalization["entry_hash"] = canonical_json_sha256(finalization)
            _append_json_line(ledger_path, finalization)
            _read_and_verify_ledger(metadata, ledger_path)
    result = dict(gate)
    result.update(
        {
            "status": "finalized",
            "append_status": append_status,
            "ledger_integrity_ok": True,
            "finalization_entry_hash": finalization.get("entry_hash"),
            "finalization_recorded_at": finalization.get("recorded_at"),
            "state_contract_sha256": contract_sha256,
            "outcome_status": state.get("status"),
            "clean_completed": state.get("status") == "completed"
            and int(state.get("error_count", 0)) == 0,
        }
    )
    return result


def verify_experiment_registry_gate(
    state: dict[str, Any],
    registry_dir: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    gate = state.get("business_controls", {}).get("experiment_registry_gate", {})
    configured_root = registry_dir or Config.EXPERIMENT_REGISTRY_PATH
    result = {
        "schema_version": 1,
        "status": "failed",
        "eligible": False,
        "errors": [],
        "run_id": state.get("run_id"),
    }
    if not configured_root:
        result["errors"].append("EXPERIMENT_REGISTRY_PATH not set")
        return result
    try:
        expected_root = _require_external_directory(configured_root)
        gate_root = _require_external_directory(str(gate.get("registry_dir", "")))
        if os.path.normcase(expected_root) != os.path.normcase(gate_root):
            raise ExperimentRegistryError(
                "run registry path differs from the configured external registry"
            )
        metadata = load_registry_metadata(
            expected_root,
            expected_metadata_sha256=str(gate.get("registry_metadata_sha256", "")),
            now=now,
        )
        entries = _read_and_verify_ledger(
            metadata, os.path.join(expected_root, LEDGER_FILENAME)
        )
        run_entries = [
            row for row in entries if row.get("run_id") == state.get("run_id")
        ]
        reservations = [
            row for row in run_entries if row.get("event_type") == "RESERVED"
        ]
        finalizations = [
            row for row in run_entries if row.get("event_type") == "FINALIZED"
        ]
        if len(reservations) != 1 or len(finalizations) != 1:
            raise ExperimentRegistryError(
                "run must have exactly one reservation and one finalization"
            )
        reservation = reservations[0]
        finalization = finalizations[0]
        expected_contract_sha256 = canonical_json_sha256(
            build_experiment_outcome_contract(state)
        )
        checks = {
            "gate_finalized": gate.get("status") == "finalized",
            "registry_id": gate.get("registry_id") == metadata.get("registry_id"),
            "reservation_hash": gate.get("reservation_entry_hash")
            == reservation.get("entry_hash"),
            "finalization_hash": gate.get("finalization_entry_hash")
            == finalization.get("entry_hash"),
            "reservation_link": finalization.get("reservation_entry_hash")
            == reservation.get("entry_hash"),
            "outcome_contract": finalization.get("state_contract_sha256")
            == expected_contract_sha256
            == gate.get("state_contract_sha256"),
            "outcome_status": finalization.get("outcome_status")
            == state.get("status"),
            "clean_completed": finalization.get("clean_completed") is True
            and state.get("status") == "completed"
            and int(state.get("error_count", 0)) == 0,
            "runtime_pi": state.get("runtime") == "pi" and not state.get("mock"),
            "safety_boundary": all(
                row.get("broker_connection_enabled") is False
                and row.get("live_execution_authorized") is False
                and row.get("external_distribution_authorized") is False
                for row in run_entries
            ),
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise ExperimentRegistryError(
                "experiment registry checks failed: " + ", ".join(failed)
            )
    except (OSError, RuntimeError, ValueError) as exc:
        result["errors"].append(str(exc))
        return result
    result.update(
        {
            "status": "passed",
            "eligible": True,
            "errors": [],
            "checks": checks,
            "registry_id": metadata.get("registry_id"),
            "registry_metadata_sha256": metadata.get(
                "registry_metadata_sha256"
            ),
            "reservation_entry_hash": reservation.get("entry_hash"),
            "finalization_entry_hash": finalization.get("entry_hash"),
            "ledger_integrity_ok": True,
        }
    )
    return result


def is_release_eligible_experiment_registry(
    state: dict[str, Any], registry_dir: str | None = None
) -> bool:
    return verify_experiment_registry_gate(state, registry_dir=registry_dir).get(
        "eligible"
    ) is True


def registry_status(
    registry_dir: str,
    runs_root: str | None = None,
    stale_hours: float = 4.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    if stale_hours <= 0:
        raise ValueError("stale_hours must be positive")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    metadata = load_registry_metadata(registry_dir, now=current)
    entries = _read_and_verify_ledger(
        metadata, os.path.join(metadata["registry_dir"], LEDGER_FILENAME)
    )
    by_run: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_run.setdefault(str(entry.get("run_id")), []).append(entry)
    pending = []
    finalized = []
    failed = []
    for run_id, run_entries in by_run.items():
        reservation = next(
            row for row in run_entries if row.get("event_type") == "RESERVED"
        )
        finalization = next(
            (row for row in run_entries if row.get("event_type") == "FINALIZED"),
            None,
        )
        if finalization:
            finalized.append(run_id)
            if not finalization.get("clean_completed"):
                failed.append(run_id)
            continue
        recorded_at = _parse_timestamp_strict(
            reservation.get("recorded_at"), "reservation recorded_at"
        )
        age_hours = max(0.0, (current - recorded_at).total_seconds() / 3600)
        pending.append(
            {
                "run_id": run_id,
                "recorded_at": reservation.get("recorded_at"),
                "age_hours": round(age_hours, 2),
                "stale": age_hours > stale_hours,
            }
        )
    missing_run_ids = _find_unregistered_external_runs(runs_root, set(by_run))
    stale_run_ids = [row["run_id"] for row in pending if row["stale"]]
    ok = not stale_run_ids and not missing_run_ids
    return {
        "schema_version": 1,
        "generated_at": current.isoformat(),
        "ok": ok,
        "status": "HEALTHY" if ok else "ATTENTION_REQUIRED",
        "registry_id": metadata.get("registry_id"),
        "registry_dir": metadata.get("registry_dir"),
        "registry_metadata_sha256": metadata.get("registry_metadata_sha256"),
        "ledger_integrity_ok": True,
        "entry_count": len(entries),
        "reservation_count": len(by_run),
        "finalized_count": len(finalized),
        "failed_or_blocked_count": len(failed),
        "pending_reservations": pending,
        "stale_reservation_run_ids": stale_run_ids,
        "unregistered_external_run_ids": missing_run_ids,
        "storage_enforcement": metadata.get("storage_enforcement"),
        "identity_and_timestamp_assurance": metadata.get(
            "identity_and_timestamp_assurance"
        ),
        "live_execution_authorized": False,
        "external_distribution_authorized": False,
        "broker_connection_enabled": False,
        "human_confirmation_needed": [
            "Platform operations must investigate every stale reservation and append a recovered final outcome rather than deleting ledger lines.",
            "Compliance must retain the external system-of-record export; the local hash chain detects changes but is not WORM storage or a digital signature.",
        ],
    }


def build_experiment_outcome_contract(state: dict[str, Any]) -> dict[str, Any]:
    controls = state.get("business_controls", {})
    protocol = controls.get("research_protocol_gate", {})
    data_output = state.get("agent_outputs", {}).get("data_agent", {})
    usage = state.get("model_usage", {})
    return {
        "run_id": state.get("run_id"),
        "input_fingerprint": state.get("input_fingerprint"),
        "request_id": state.get("request_id"),
        "retry_of": state.get("retry_of"),
        "runtime": state.get("runtime"),
        "mock": state.get("mock"),
        "source_head_commit": state.get("source_provenance", {}).get(
            "head_commit"
        ),
        "status": state.get("status"),
        "success_count": int(state.get("success_count", 0)),
        "error_count": int(state.get("error_count", 0)),
        "data_mode": state.get("data_mode"),
        "metrics_source": state.get("metrics_source"),
        "data_snapshot_id": data_output.get("snapshot_id"),
        "protocol_id": protocol.get("protocol_id"),
        "protocol_version": protocol.get("protocol_version"),
        "model_contract_sha256": protocol.get("model_contract_sha256"),
        "backtest_assurance_decision": state.get("backtest_assurance", {}).get(
            "decision"
        ),
        "backtest_release_gate_passed": state.get("backtest_assurance", {}).get(
            "release_gate_passed"
        ),
        "robustness_decision": state.get("robustness_validation", {}).get(
            "decision"
        ),
        "robustness_failed_checks": state.get("robustness_validation", {}).get(
            "failed_checks", []
        ),
        "budget_status": state.get("budget_gate", {}).get("status"),
        "model_total_tokens": int(usage.get("total_tokens", 0)),
        "model_budget_cost_usd": usage.get("budget_cost_usd", 0),
        "broker_connection_enabled": controls.get("broker_connection_enabled"),
        "external_distribution_approved": controls.get(
            "external_distribution_approved"
        ),
    }


def _validate_registry_evidence(
    evidence: dict[str, Any], evidence_path: str, current: datetime
) -> dict[str, Any]:
    errors: list[str] = []
    if evidence.get("schema_version") != 1:
        errors.append("registry evidence schema_version must be 1")
    if evidence.get("project_id") != PROJECT_ID:
        errors.append(f"registry evidence project_id must be {PROJECT_ID}")
    registry_id = str(evidence.get("registry_id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{5,127}", registry_id):
        errors.append("registry_id is missing or invalid")
    if evidence.get("status") != "ACTIVE":
        errors.append("registry evidence status must be ACTIVE")
    if evidence.get("append_only") is not True:
        errors.append("registry evidence append_only must be true")
    if evidence.get("live_execution_authorized") is not False:
        errors.append("registry evidence live_execution_authorized must be false")
    if evidence.get("external_distribution_authorized") is not False:
        errors.append("registry evidence external_distribution_authorized must be false")
    system_reference = str(
        evidence.get("system_of_record_reference", "")
    ).strip()
    if not system_reference:
        errors.append("system_of_record_reference is required")
    allowed_run_classes = sorted(set(evidence.get("allowed_run_classes", [])))
    if not REQUIRED_RUN_CLASSES.issubset(allowed_run_classes):
        errors.append("evidence must authorize both required research run classes")
    try:
        retention_days = int(evidence.get("retention_days", 0))
    except (TypeError, ValueError):
        retention_days = 0
    if retention_days < Config.RUN_RETENTION_DAYS:
        errors.append("evidence retention is shorter than the run retention policy")
    valid_from = _parse_date(evidence.get("valid_from"), "valid_from", errors)
    valid_until = _parse_date(evidence.get("valid_until"), "valid_until", errors)
    if valid_from and current.date() < valid_from:
        errors.append("registry evidence is not yet effective")
    if valid_until and current.date() > valid_until:
        errors.append("registry evidence has expired")
    if valid_from and valid_until and valid_until < valid_from:
        errors.append("registry evidence valid_until predates valid_from")
    registered_at = _parse_timestamp(
        evidence.get("registered_at"), "registered_at", errors
    )
    if registered_at and registered_at > current:
        errors.append("registry evidence registered_at must not be in the future")
    approvals = evidence.get("approvals")
    if not isinstance(approvals, list):
        approvals = []
        errors.append("registry approvals must be a list")
    by_role = {
        str(row.get("role")): row
        for row in approvals
        if isinstance(row, dict) and row.get("role")
    }
    if set(by_role) != REQUIRED_APPROVAL_ROLES:
        errors.append("registry requires exactly four independent approval roles")
    approvers = []
    references = []
    for role in REQUIRED_APPROVAL_ROLES:
        approval = by_role.get(role, {})
        if str(approval.get("decision", "")).upper() != "APPROVED":
            errors.append(f"registry {role} decision must be APPROVED")
        approver = str(approval.get("approver", "")).strip()
        if not approver:
            errors.append(f"registry {role} approver is required")
        else:
            approvers.append(approver.casefold())
        reference = str(approval.get("evidence_reference", "")).strip()
        if not reference:
            errors.append(f"registry {role} evidence_reference is required")
        else:
            references.append(reference)
        approved_at = _parse_timestamp(
            approval.get("approved_at"), f"registry {role} approved_at", errors
        )
        if approved_at and approved_at > current:
            errors.append(f"registry {role} approved_at must not be in the future")
    if len(set(approvers)) != len(REQUIRED_APPROVAL_ROLES):
        errors.append("registry approval roles require four distinct people")
    if len(set(references)) != len(REQUIRED_APPROVAL_ROLES):
        errors.append("registry approval evidence references must be distinct")
    supporting_path = str(evidence.get("supporting_document_path", "")).strip()
    if supporting_path and not os.path.isabs(supporting_path):
        supporting_path = os.path.abspath(
            os.path.join(os.path.dirname(evidence_path), supporting_path)
        )
    if not supporting_path or not os.path.isfile(supporting_path):
        errors.append("registry supporting document is missing")
    elif _is_within_project(supporting_path):
        errors.append("registry supporting document must be outside the repository")
    expected_supporting_sha256 = str(
        evidence.get("supporting_document_sha256", "")
    ).lower()
    if not _SHA256.fullmatch(expected_supporting_sha256):
        errors.append("registry supporting_document_sha256 is invalid")
    elif supporting_path and os.path.isfile(supporting_path):
        if sha256_file(supporting_path) != expected_supporting_sha256:
            errors.append("registry supporting document SHA-256 mismatch")
    supporting_type = str(
        evidence.get("supporting_document_type", "")
    ).strip()
    if not supporting_type:
        errors.append("registry supporting_document_type is required")
    if errors:
        raise ExperimentRegistryError("; ".join(dict.fromkeys(errors)))
    return {
        "registry_id": registry_id,
        "registered_at": registered_at.isoformat() if registered_at else None,
        "valid_from": valid_from.isoformat() if valid_from else None,
        "valid_until": valid_until.isoformat() if valid_until else None,
        "system_of_record_reference": system_reference,
        "allowed_run_classes": allowed_run_classes,
        "retention_days": retention_days,
        "approval_roles": sorted(REQUIRED_APPROVAL_ROLES),
        "approval_evidence_references": sorted(references),
        "evidence_file_sha256": sha256_file(evidence_path),
        "supporting_document_path": os.path.abspath(supporting_path),
        "supporting_document_sha256": expected_supporting_sha256,
        "supporting_document_type": supporting_type,
    }


def _read_and_verify_ledger(
    metadata: dict[str, Any], ledger_path: str
) -> list[dict[str, Any]]:
    if not os.path.isfile(ledger_path):
        raise ExperimentRegistryError(f"experiment ledger is missing: {ledger_path}")
    entries: list[dict[str, Any]] = []
    previous_hash = None
    previous_recorded_at: datetime | None = None
    run_states: dict[str, str] = {}
    with open(ledger_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} is invalid JSON"
                ) from exc
            if not isinstance(loaded, dict):
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} is not an object"
                )
            entry = dict(loaded)
            claimed_hash = entry.pop("entry_hash", None)
            calculated_hash = canonical_json_sha256(entry)
            entry["entry_hash"] = claimed_hash
            if claimed_hash != calculated_hash:
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} hash mismatch"
                )
            if entry.get("schema_version") != LEDGER_ENTRY_SCHEMA_VERSION:
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} schema mismatch"
                )
            if entry.get("registry_id") != metadata.get("registry_id"):
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} registry mismatch"
                )
            if entry.get("sequence") != line_number:
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} sequence mismatch"
                )
            if entry.get("previous_entry_hash") != previous_hash:
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} chain mismatch"
                )
            recorded_at = _parse_timestamp_strict(
                entry.get("recorded_at"), f"ledger line {line_number} recorded_at"
            )
            if previous_recorded_at and recorded_at < previous_recorded_at:
                raise ExperimentRegistryError(
                    "experiment ledger timestamps must not move backwards"
                )
            if any(
                entry.get(field) is not False
                for field in (
                    "broker_connection_enabled",
                    "live_execution_authorized",
                    "external_distribution_authorized",
                )
            ):
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} safety boundary is invalid"
                )
            run_id = str(entry.get("run_id", ""))
            event_type = entry.get("event_type")
            if not run_id or event_type not in {"RESERVED", "FINALIZED"}:
                raise ExperimentRegistryError(
                    f"experiment ledger line {line_number} identity is invalid"
                )
            prior_state = run_states.get(run_id)
            if event_type == "RESERVED":
                if prior_state is not None:
                    raise ExperimentRegistryError(
                        f"experiment run has duplicate reservation: {run_id}"
                    )
                run_states[run_id] = "RESERVED"
            else:
                if prior_state != "RESERVED":
                    raise ExperimentRegistryError(
                        f"experiment finalization has no open reservation: {run_id}"
                    )
                reservation = next(
                    row
                    for row in entries
                    if row.get("run_id") == run_id
                    and row.get("event_type") == "RESERVED"
                )
                if entry.get("reservation_entry_hash") != reservation.get(
                    "entry_hash"
                ):
                    raise ExperimentRegistryError(
                        f"experiment finalization reservation link is invalid: {run_id}"
                    )
                run_states[run_id] = "FINALIZED"
            previous_hash = claimed_hash
            previous_recorded_at = recorded_at
            entries.append(entry)
    return entries


def _ledger_integrity(metadata: dict[str, Any]) -> bool:
    _read_and_verify_ledger(
        metadata, os.path.join(metadata["registry_dir"], LEDGER_FILENAME)
    )
    return True


def _reservation_contract(entry: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "registry_id",
        "event_type",
        "run_id",
        "run_dir",
        "request_id",
        "retry_of",
        "runtime",
        "mock",
        "input_fingerprint",
        "model_contract_sha256",
        "protocol_id",
        "protocol_version",
        "protocol_evidence_sha256",
        "run_class",
        "source_head_commit",
        "source_provenance_sha256",
        "intended_use",
        "broker_connection_enabled",
        "live_execution_authorized",
        "external_distribution_authorized",
    )
    return {field: entry.get(field) for field in fields}


def _registry_identity_sha256(metadata: dict[str, Any]) -> str:
    return canonical_json_sha256(
        {
            "project_id": metadata.get("project_id"),
            "registry_id": metadata.get("registry_id"),
            "registered_at": metadata.get("registered_at"),
            "valid_from": metadata.get("valid_from"),
            "valid_until": metadata.get("valid_until"),
            "system_of_record_reference": metadata.get(
                "system_of_record_reference"
            ),
            "allowed_run_classes": metadata.get("allowed_run_classes"),
            "retention_days": metadata.get("retention_days"),
            "approval_roles": metadata.get("approval_roles"),
            "evidence_file_sha256": metadata.get("evidence_file_sha256"),
            "supporting_document_sha256": metadata.get(
                "supporting_document_sha256"
            ),
            "append_only": metadata.get("append_only"),
            "live_execution_authorized": metadata.get(
                "live_execution_authorized"
            ),
            "external_distribution_authorized": metadata.get(
                "external_distribution_authorized"
            ),
            "broker_connection_enabled": metadata.get(
                "broker_connection_enabled"
            ),
        }
    )


def _find_unregistered_external_runs(
    runs_root: str | None, registered_run_ids: set[str]
) -> list[str]:
    if not runs_root or not os.path.isdir(runs_root):
        return []
    missing = []
    for entry in os.scandir(runs_root):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        state_path = os.path.join(entry.path, "state.json")
        if not os.path.isfile(state_path):
            continue
        try:
            state = _load_json(state_path, "run state")
        except ExperimentRegistryError:
            continue
        if state.get("mock") or state.get("runtime") != "pi":
            continue
        checks = {
            row.get("name")
            for row in state.get("preflight", {}).get("checks", [])
            if isinstance(row, dict)
        }
        made_external_progress = bool(
            {"tushare", "pi_llm_ping"}.intersection(checks)
            or state.get("model_usage", {}).get("calls_with_usage", 0)
        )
        if made_external_progress and str(state.get("run_id")) not in registered_run_ids:
            missing.append(str(state.get("run_id") or entry.name))
    return sorted(set(missing))


@contextmanager
def _registry_lock(registry_dir: str) -> Iterator[None]:
    lock_path = os.path.join(registry_dir, ".append.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ExperimentRegistryError(
            f"experiment registry append lock already exists: {lock_path}; inspect before removal"
        ) from exc
    try:
        payload = json.dumps(
            {
                "pid": os.getpid(),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            }
        ).encode("utf-8")
        os.write(descriptor, payload)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.isfile(lock_path):
            os.unlink(lock_path)


def _append_json_line(path: str, payload: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        file.flush()
        os.fsync(file.fileno())


def _require_external_file(path: str, label: str) -> str:
    absolute = os.path.abspath(path)
    if _is_within_project(absolute):
        raise ExperimentRegistryError(f"{label} must be outside the project repository")
    if not os.path.isfile(absolute):
        raise ExperimentRegistryError(f"{label} does not exist: {absolute}")
    return absolute


def _external_path(path: str, label: str) -> str:
    if not str(path).strip():
        raise ExperimentRegistryError(f"{label} path is required")
    absolute = os.path.abspath(path)
    if _is_within_project(absolute):
        raise ExperimentRegistryError(f"{label} must be outside the project repository")
    return absolute


def _require_external_directory(path: str) -> str:
    absolute = _external_path(path, "experiment registry")
    if not os.path.isdir(absolute):
        raise ExperimentRegistryError(
            f"experiment registry directory does not exist: {absolute}"
        )
    return absolute


def _is_within_project(path: str) -> bool:
    project_root = os.path.abspath(str(PROJECT_ROOT))
    try:
        lexical = os.path.normcase(
            os.path.commonpath([project_root, os.path.abspath(path)])
        ) == os.path.normcase(project_root)
        resolved_root = os.path.realpath(project_root)
        resolved = os.path.normcase(
            os.path.commonpath([resolved_root, os.path.realpath(path)])
        ) == os.path.normcase(resolved_root)
        return lexical or resolved
    except ValueError:
        return False


def _verify_bound_external_file(
    path: str, expected_sha256: Any, label: str, errors: list[str]
) -> None:
    if not path or not os.path.isfile(path):
        errors.append(f"{label} is missing")
        return
    if _is_within_project(path):
        errors.append(f"{label} must be outside the repository")
        return
    expected = str(expected_sha256 or "").lower()
    if not _SHA256.fullmatch(expected):
        errors.append(f"{label} SHA-256 is invalid")
        return
    if sha256_file(path) != expected:
        errors.append(f"{label} SHA-256 mismatch")


def _load_json(path: str, label: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentRegistryError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExperimentRegistryError(f"{label} must be a JSON object")
    return value


def _parse_date(value: Any, field: str, errors: list[str]) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{field} must use YYYY-MM-DD")
        return None


def _parse_timestamp(
    value: Any, field: str, errors: list[str]
) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError:
        errors.append(f"{field} must be timezone-aware ISO-8601")
        return None


def _parse_timestamp_strict(value: Any, field: str) -> datetime:
    errors: list[str] = []
    parsed = _parse_timestamp(value, field, errors)
    if not parsed:
        raise ExperimentRegistryError("; ".join(errors))
    return parsed
