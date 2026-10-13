from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any

from .audit import canonical_json_sha256, sha256_file, write_json_atomic
from .config import Config, PROJECT_ROOT
from .governance import is_release_eligible_data_license
from .execution_cost_governance import is_release_eligible_execution_cost
from .research_protocol import (
    build_model_contract_fingerprint,
    is_release_eligible_research_protocol,
)
from .experiment_registry import verify_experiment_registry_gate
from .operations import is_current_model_pricing, verify_event_chain
from .secret_scan import evaluate_secret_scan_receipt
from .source_review import evaluate_source_review_decision


REQUIRED_APPROVAL_ROLES = {
    "data_owner",
    "quant_owner",
    "model_owner",
    "platform_owner",
    "compliance_owner",
}
_TRADING_ACTION = re.compile(
    r"(?:买入|卖出|加仓|减仓|建仓|清仓|止损|止盈|实盘下单|执行交易)"
    r"|\b(?:buy|sell|go long|go short|stop[- ]loss|take[- ]profit)\b",
    re.IGNORECASE,
)


def verify_run_integrity(run_dir: str) -> dict[str, Any]:
    root = os.path.abspath(run_dir)
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = os.path.join(root, "run_manifest.json")
    state_path = os.path.join(root, "state.json")
    input_path = os.path.join(root, "input.json")
    manifest = _read_json(manifest_path, errors, "run manifest")
    state = _read_json(state_path, errors, "state")
    input_data = _read_json(input_path, errors, "input")

    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list) or not files:
        errors.append("run manifest has no files")
        files = []
    for row in files:
        relative = str(row.get("path", ""))
        absolute = _safe_join(root, relative)
        if not absolute:
            errors.append(f"unsafe manifest path: {relative}")
            continue
        if not os.path.isfile(absolute):
            errors.append(f"missing artifact: {relative}")
            continue
        if os.path.getsize(absolute) != int(row.get("bytes", -1)):
            errors.append(f"size mismatch: {relative}")
        if sha256_file(absolute) != row.get("sha256"):
            errors.append(f"SHA-256 mismatch: {relative}")

    metadata = manifest.get("metadata", {}) if isinstance(manifest, dict) else {}
    expected_snapshot = canonical_json_sha256({"files": files, "metadata": metadata})
    if manifest.get("snapshot_id") != expected_snapshot:
        errors.append("run manifest snapshot_id mismatch")
    if state and input_data:
        input_fingerprint = canonical_json_sha256(input_data)
        if state.get("input_fingerprint") != input_fingerprint:
            errors.append("state input_fingerprint does not match input.json")
        if metadata.get("input_fingerprint") != input_fingerprint:
            errors.append("manifest input_fingerprint does not match input.json")
        if state.get("run_id") != os.path.basename(root):
            errors.append("state run_id does not match directory name")
        if metadata.get("run_id") != state.get("run_id"):
            errors.append("manifest run_id does not match state")
        if metadata.get("run_schema_version") != state.get("schema_version"):
            errors.append("manifest run schema does not match state")
        registry_gate = state.get("business_controls", {}).get(
            "experiment_registry_gate", {}
        )
        registry_bindings = {
            "experiment_registry_status": "status",
            "experiment_registry_id": "registry_id",
            "experiment_registry_metadata_sha256": "registry_metadata_sha256",
            "experiment_reservation_entry_hash": "reservation_entry_hash",
            "experiment_finalization_entry_hash": "finalization_entry_hash",
            "experiment_state_contract_sha256": "state_contract_sha256",
        }
        for manifest_field, gate_field in registry_bindings.items():
            if metadata.get(manifest_field) != registry_gate.get(gate_field):
                errors.append(
                    f"manifest {manifest_field} does not match experiment registry gate"
                )

    event_result = verify_event_chain(os.path.join(root, "operations", "events.jsonl"))
    if not event_result["ok"]:
        errors.extend(f"event chain: {item}" for item in event_result["errors"])

    manifested = {str(row.get("path", "")).replace("\\", "/") for row in files}
    ignored_prefixes = ("release/",)
    ignored_files = {
        "run_manifest.json",
        "operations/integrity_verification.json",
    }
    extras = []
    for directory, _, filenames in os.walk(root):
        for filename in filenames:
            relative = os.path.relpath(os.path.join(directory, filename), root).replace("\\", "/")
            if relative in ignored_files or relative.startswith(ignored_prefixes):
                continue
            if relative not in manifested:
                extras.append(relative)
    if extras:
        errors.append("unmanifested files: " + ", ".join(sorted(extras)))

    return {
        "schema_version": 1,
        "verified_at": _utc_now(),
        "run_dir": root,
        "run_id": state.get("run_id") if state else None,
        "manifest_snapshot_id": manifest.get("snapshot_id") if manifest else None,
        "ok": not errors,
        "checked_file_count": len(files),
        "event_chain": event_result,
        "errors": errors,
        "warnings": warnings,
    }


def write_integrity_report(run_dir: str) -> dict[str, Any]:
    result = verify_run_integrity(run_dir)
    write_json_atomic(
        os.path.join(run_dir, "operations", "integrity_verification.json"),
        result,
    )
    return result


def prepare_release_candidate(
    run_dir: str,
    target: str = "internal_research_review",
) -> dict[str, Any]:
    if target != "internal_research_review":
        raise RuntimeError("only target=internal_research_review is supported")
    integrity = write_integrity_report(run_dir)
    state = _load_required_json(os.path.join(run_dir, "state.json"))
    summary_path = os.path.join(run_dir, "summary.md")
    summary = ""
    if os.path.isfile(summary_path):
        with open(summary_path, "r", encoding="utf-8") as file:
            summary = file.read()

    blockers = _release_blockers(integrity, state, summary)

    candidate_identity = {
        "run_id": state.get("run_id"),
        "manifest_snapshot_id": integrity.get("manifest_snapshot_id"),
        "input_fingerprint": state.get("input_fingerprint"),
        "target": target,
    }
    candidate = {
        "schema_version": 1,
        "candidate_id": canonical_json_sha256(candidate_identity),
        "created_at": _utc_now(),
        **candidate_identity,
        "status": "BLOCKED" if blockers else "AWAITING_HUMAN_APPROVALS",
        "blockers": blockers,
        "release_scope": "internal review only; external distribution prohibited",
        "required_approval_roles": sorted(REQUIRED_APPROVAL_ROLES),
        "integrity_report": "operations/integrity_verification.json",
        "disclaimer": "This candidate is research-only and is not real-capital trading advice.",
    }
    release_dir = os.path.join(run_dir, "release")
    os.makedirs(release_dir, exist_ok=True)
    write_json_atomic(os.path.join(release_dir, "release_candidate.json"), candidate)
    approval_request = {
        "schema_version": 1,
        "candidate_id": candidate["candidate_id"],
        "manifest_snapshot_id": candidate["manifest_snapshot_id"],
        "target": target,
        "decision": "PENDING",
        "approvals": [
            {
                "role": role,
                "decision": "PENDING",
                "approver": "",
                "approved_at": "",
                "evidence_reference": "",
            }
            for role in sorted(REQUIRED_APPROVAL_ROLES)
        ],
    }
    approval_request_path = os.path.join(release_dir, "approval_request.json")
    existing_approval = None
    if os.path.isfile(approval_request_path):
        try:
            existing_approval = _load_required_json(approval_request_path)
        except RuntimeError:
            existing_approval = None
    if not existing_approval or existing_approval.get("candidate_id") != candidate["candidate_id"]:
        write_json_atomic(approval_request_path, approval_request)
    return candidate


def verify_release_approval(run_dir: str, approval_path: str) -> dict[str, Any]:
    candidate = _load_required_json(
        os.path.join(run_dir, "release", "release_candidate.json")
    )
    approval = _load_required_json(approval_path)
    errors = []
    integrity = verify_run_integrity(run_dir)
    state = _load_required_json(os.path.join(run_dir, "state.json"))
    summary_path = os.path.join(run_dir, "summary.md")
    summary = ""
    if os.path.isfile(summary_path):
        with open(summary_path, "r", encoding="utf-8") as file:
            summary = file.read()
    current_blockers = _release_blockers(integrity, state, summary)
    expected_identity = {
        "run_id": state.get("run_id"),
        "manifest_snapshot_id": integrity.get("manifest_snapshot_id"),
        "input_fingerprint": state.get("input_fingerprint"),
        "target": "internal_research_review",
    }
    if candidate.get("candidate_id") != canonical_json_sha256(expected_identity):
        errors.append("release candidate identity does not match current run")
    if current_blockers:
        errors.append("current release eligibility is blocked: " + "; ".join(current_blockers))
    if candidate.get("blockers") != current_blockers:
        errors.append("release candidate blockers do not match current eligibility")
    if candidate.get("status") == "BLOCKED":
        errors.append("release candidate is blocked")
    if approval.get("schema_version") != 1:
        errors.append("approval schema_version must be 1")
    if approval.get("candidate_id") != candidate.get("candidate_id"):
        errors.append("approval candidate_id mismatch")
    if approval.get("manifest_snapshot_id") != candidate.get("manifest_snapshot_id"):
        errors.append("approval manifest_snapshot_id mismatch")
    if approval.get("target") != "internal_research_review":
        errors.append("approval target must be internal_research_review")
    if str(approval.get("decision", "")).upper() != "APPROVED":
        errors.append("overall approval decision must be APPROVED")

    approvals = approval.get("approvals", [])
    by_role = {
        str(row.get("role")): row
        for row in approvals
        if isinstance(row, dict) and row.get("role")
    }
    missing = sorted(REQUIRED_APPROVAL_ROLES.difference(by_role))
    if missing:
        errors.append("missing approval roles: " + ", ".join(missing))
    approvers = []
    candidate_created = _parse_aware_timestamp(candidate.get("created_at"))
    now = datetime.now(timezone.utc)
    for role in REQUIRED_APPROVAL_ROLES:
        row = by_role.get(role, {})
        if str(row.get("decision", "")).upper() != "APPROVED":
            errors.append(f"{role} decision must be APPROVED")
        approver = str(row.get("approver", "")).strip()
        if not approver:
            errors.append(f"{role} approver is required")
        else:
            approvers.append(approver.lower())
        if not str(row.get("evidence_reference", "")).strip():
            errors.append(f"{role} evidence_reference is required")
        approved_at = _parse_aware_timestamp(row.get("approved_at"))
        if approved_at is None:
            errors.append(f"{role} approved_at must be ISO-8601")
        else:
            if candidate_created and approved_at < candidate_created:
                errors.append(f"{role} approved_at predates the release candidate")
            if approved_at > now:
                errors.append(f"{role} approved_at cannot be in the future")
    if len(set(approvers)) != len(approvers):
        errors.append("approval roles require distinct named approvers")

    if not integrity["ok"]:
        errors.append("run integrity changed after candidate preparation")
    if integrity.get("manifest_snapshot_id") != candidate.get("manifest_snapshot_id"):
        errors.append("current manifest no longer matches release candidate")

    decision = {
        "schema_version": 1,
        "verified_at": _utc_now(),
        "candidate_id": candidate.get("candidate_id"),
        "manifest_snapshot_id": candidate.get("manifest_snapshot_id"),
        "status": "APPROVED_FOR_INTERNAL_REVIEW" if not errors else "REJECTED",
        "external_distribution_approved": False,
        "approval_assurance": "local_file_only_not_identity_authenticated",
        "errors": errors,
    }
    write_json_atomic(
        os.path.join(run_dir, "release", "release_decision.json"), decision
    )
    return decision


def archive_run(run_dir: str, archive_root: str) -> dict[str, Any]:
    integrity = verify_run_integrity(run_dir)
    if not integrity["ok"]:
        raise RuntimeError("refusing to archive a run with failed integrity checks")
    root = os.path.abspath(run_dir)
    archive_root = os.path.abspath(archive_root)
    os.makedirs(archive_root, exist_ok=True)
    run_id = os.path.basename(root)
    snapshot = str(integrity["manifest_snapshot_id"])
    members = _directory_inventory(root, run_id)
    content_id = canonical_json_sha256(members)
    filename = f"{run_id}_{snapshot[:12]}_{content_id[:12]}.zip"
    destination = os.path.join(archive_root, filename)
    if os.path.exists(destination):
        existing = verify_archive(
            destination,
            expected_run_id=run_id,
            expected_manifest_snapshot_id=snapshot,
            source_run_dir=root,
        )
        if not existing["ok"]:
            raise RuntimeError(
                "existing archive failed verification: " + "; ".join(existing["errors"])
            )
        return {
            "status": "already_archived",
            "archive": destination,
            "sha256": existing["archive_sha256"],
            "run_id": run_id,
            "manifest_snapshot_id": snapshot,
            "archive_content_id": content_id,
            "receipt": _archive_receipt_path(destination),
            "verified": True,
        }
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(suffix=".zip.tmp", dir=archive_root)
        os.close(descriptor)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in members:
                absolute = os.path.join(root, member["source_path"])
                archive.write(absolute, arcname=member["path"])
        with zipfile.ZipFile(temporary, "r") as archive:
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise RuntimeError(f"archive verification failed for member: {corrupt_member}")
        archive_hash = sha256_file(temporary)
        os.replace(temporary, destination)
        temporary = None
        _write_text_atomic(destination + ".sha256", f"{archive_hash}  {filename}\n")
        finished_at = _parse_aware_or_local_timestamp(
            _load_required_json(os.path.join(root, "state.json")).get("finished_at")
        ) or datetime.now(timezone.utc)
        receipt = {
            "schema_version": 1,
            "created_at": _utc_now(),
            "archive_filename": filename,
            "archive_sha256": archive_hash,
            "archive_bytes": os.path.getsize(destination),
            "archive_content_id": content_id,
            "run_id": run_id,
            "manifest_snapshot_id": snapshot,
            "members": [
                {key: row[key] for key in ("path", "bytes", "sha256")}
                for row in members
            ],
            "retention_days": Config.RUN_RETENTION_DAYS,
            "deletion_eligible_after": (
                finished_at + timedelta(days=Config.RUN_RETENTION_DAYS)
            ).isoformat(),
            "legal_hold_checked_at_archive_time": _legal_hold_active(root),
            "source_integrity_ok": True,
        }
        write_json_atomic(_archive_receipt_path(destination), receipt)
        verified = verify_archive(
            destination,
            expected_sha256=archive_hash,
            expected_run_id=run_id,
            expected_manifest_snapshot_id=snapshot,
            source_run_dir=root,
        )
        if not verified["ok"]:
            raise RuntimeError(
                "archive restore verification failed: " + "; ".join(verified["errors"])
            )
        return {
            "status": "archived",
            "archive": destination,
            "sha256": archive_hash,
            "run_id": run_id,
            "manifest_snapshot_id": snapshot,
            "archive_content_id": content_id,
            "receipt": _archive_receipt_path(destination),
            "verified": True,
            "restore_tested": True,
        }
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def verify_archive(
    archive_path: str,
    expected_sha256: str | None = None,
    expected_run_id: str | None = None,
    expected_manifest_snapshot_id: str | None = None,
    source_run_dir: str | None = None,
) -> dict[str, Any]:
    path = os.path.abspath(archive_path)
    errors: list[str] = []
    warnings: list[str] = []
    if not os.path.isfile(path):
        return {
            "schema_version": 1,
            "verified_at": _utc_now(),
            "archive": path,
            "ok": False,
            "errors": ["archive is missing"],
            "warnings": [],
        }

    actual_hash = sha256_file(path)
    receipt = _read_json(_archive_receipt_path(path), errors, "archive receipt")
    sidecar_hash, sidecar_filename = _read_sha256_sidecar(path + ".sha256", errors)
    if expected_sha256 and actual_hash.lower() != expected_sha256.lower():
        errors.append("archive SHA-256 does not match the caller expectation")
    if receipt.get("archive_sha256") != actual_hash:
        errors.append("archive SHA-256 does not match the receipt")
    if receipt.get("archive_filename") != os.path.basename(path):
        errors.append("archive filename does not match the receipt")
    if sidecar_hash != actual_hash:
        errors.append("archive SHA-256 does not match the sidecar")
    if sidecar_filename != os.path.basename(path):
        errors.append("archive sidecar filename mismatch")

    actual_members: list[dict[str, Any]] = []
    top_levels: set[str] = set()
    extraction_root = None
    extracted_run_dir = None
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos if not info.is_dir()]
            if len(names) != len(set(names)):
                errors.append("archive contains duplicate member names")
            for info in infos:
                normalized = _validate_archive_member(info)
                if normalized is None:
                    errors.append(f"unsafe archive member: {info.filename}")
                    continue
                if info.is_dir():
                    continue
                parts = PurePosixPath(normalized).parts
                if parts:
                    top_levels.add(parts[0])
                digest = hashlib.sha256()
                with archive.open(info, "r") as member_file:
                    while chunk := member_file.read(1024 * 1024):
                        digest.update(chunk)
                actual_members.append(
                    {
                        "path": normalized,
                        "bytes": info.file_size,
                        "sha256": digest.hexdigest(),
                    }
                )
            corrupt_member = archive.testzip()
            if corrupt_member:
                errors.append(f"archive CRC verification failed: {corrupt_member}")
            if len(top_levels) != 1:
                errors.append("archive must contain exactly one top-level run directory")
            run_id = next(iter(top_levels), None)
            if expected_run_id and run_id != expected_run_id:
                errors.append("archive run_id does not match the caller expectation")
            if receipt.get("run_id") != run_id:
                errors.append("archive run_id does not match the receipt")
            expected_members = receipt.get("members", [])
            if sorted(actual_members, key=lambda row: row["path"]) != sorted(
                expected_members if isinstance(expected_members, list) else [],
                key=lambda row: str(row.get("path", "")),
            ):
                errors.append("archive member inventory does not match the receipt")
            content_id = canonical_json_sha256(
                [
                    {
                        "path": row["path"],
                        "bytes": row["bytes"],
                        "sha256": row["sha256"],
                        "source_path": row["path"].split("/", 1)[1]
                        if "/" in row["path"]
                        else "",
                    }
                    for row in sorted(actual_members, key=lambda item: item["path"])
                ]
            )
            if receipt.get("archive_content_id") != content_id:
                errors.append("archive content identity does not match the receipt")
            if not errors and run_id:
                extraction_root = tempfile.TemporaryDirectory()
                archive.extractall(extraction_root.name)
                extracted_run_dir = os.path.join(extraction_root.name, run_id)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        errors.append(f"cannot verify archive: {exc}")

    restored_integrity: dict[str, Any] = {}
    if extracted_run_dir and not errors:
        restored_integrity = verify_run_integrity(extracted_run_dir)
        if not restored_integrity["ok"]:
            errors.append(
                "restored run integrity failed: "
                + "; ".join(restored_integrity.get("errors", []))
            )
        restored_snapshot = restored_integrity.get("manifest_snapshot_id")
        if receipt.get("manifest_snapshot_id") != restored_snapshot:
            errors.append("restored manifest snapshot does not match the receipt")
        if (
            expected_manifest_snapshot_id
            and restored_snapshot != expected_manifest_snapshot_id
        ):
            errors.append("restored manifest snapshot does not match the caller expectation")
    if extraction_root is not None:
        extraction_root.cleanup()

    if source_run_dir:
        source_integrity = verify_run_integrity(source_run_dir)
        if not source_integrity["ok"]:
            errors.append("source run no longer passes integrity verification")
        elif (
            restored_integrity
            and source_integrity.get("manifest_snapshot_id")
            != restored_integrity.get("manifest_snapshot_id")
        ):
            errors.append("archive does not restore the current source run snapshot")
        source_members = _directory_inventory(
            os.path.abspath(source_run_dir), os.path.basename(os.path.abspath(source_run_dir))
        )
        expected_source_members = [
            {key: row[key] for key in ("path", "bytes", "sha256")}
            for row in source_members
        ]
        if sorted(actual_members, key=lambda row: row["path"]) != sorted(
            expected_source_members, key=lambda row: row["path"]
        ):
            errors.append("archive inventory does not match the current source run")

    return {
        "schema_version": 1,
        "verified_at": _utc_now(),
        "archive": path,
        "archive_sha256": actual_hash,
        "archive_bytes": os.path.getsize(path),
        "run_id": receipt.get("run_id"),
        "manifest_snapshot_id": receipt.get("manifest_snapshot_id"),
        "archive_content_id": receipt.get("archive_content_id"),
        "member_count": len(actual_members),
        "restore_tested": bool(restored_integrity),
        "restored_integrity_ok": restored_integrity.get("ok", False),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def build_retention_plan(
    runs_root: str,
    archive_root: str,
    retention_days: int = Config.RUN_RETENTION_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    if retention_days < 1:
        raise RuntimeError("retention_days must be at least 1")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise RuntimeError("retention plan time must be timezone-aware")
    current = current.astimezone(timezone.utc)
    runs_root = os.path.abspath(runs_root)
    archive_root = os.path.abspath(archive_root)
    receipts = _load_archive_receipts(archive_root)
    rows = []
    if os.path.isdir(runs_root):
        for entry in sorted(os.scandir(runs_root), key=lambda item: item.name):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            state_errors: list[str] = []
            state = _read_json(
                os.path.join(entry.path, "state.json"), state_errors, "state"
            )
            if state_errors:
                rows.append(
                    {
                        "run_id": entry.name,
                        "action": "RETAIN",
                        "eligible": False,
                        "reasons": state_errors,
                    }
                )
                continue
            finished_at = _parse_aware_or_local_timestamp(
                state.get("finished_at") or state.get("updated_at")
            )
            age_days = (
                (current - finished_at).total_seconds() / 86400
                if finished_at
                else None
            )
            integrity = verify_run_integrity(entry.path)
            snapshot = integrity.get("manifest_snapshot_id")
            matching_receipts = [
                receipt
                for receipt in receipts
                if receipt.get("run_id") == entry.name
                and receipt.get("manifest_snapshot_id") == snapshot
            ]
            archive_checks = [
                verify_archive(
                    receipt["_archive_path"],
                    expected_run_id=entry.name,
                    expected_manifest_snapshot_id=snapshot,
                )
                for receipt in matching_receipts
                if receipt.get("_archive_path")
            ]
            valid_archive = next((row for row in archive_checks if row["ok"]), None)
            legal_hold = _legal_hold_active(entry.path)
            reasons = []
            if age_days is None:
                reasons.append("run has no valid completion timestamp")
            elif age_days < retention_days:
                reasons.append("retention period has not elapsed")
            if legal_hold:
                reasons.append("active legal hold")
            if not integrity["ok"]:
                reasons.append("source run integrity is not valid")
            if not valid_archive:
                reasons.append("no independently verified archive and restore test")
            eligible = not reasons
            rows.append(
                {
                    "run_id": entry.name,
                    "status": state.get("status"),
                    "mock": bool(state.get("mock")),
                    "finished_at": state.get("finished_at"),
                    "age_days": round(age_days, 2) if age_days is not None else None,
                    "retention_days": retention_days,
                    "legal_hold": legal_hold,
                    "manifest_snapshot_id": snapshot,
                    "verified_archive": valid_archive.get("archive") if valid_archive else None,
                    "eligible": eligible,
                    "action": "ELIGIBLE_FOR_MANUAL_DELETION" if eligible else "RETAIN",
                    "reasons": reasons,
                    "deletion_performed": False,
                    "human_authorization_required": True,
                }
            )
    return {
        "schema_version": 1,
        "generated_at": current.isoformat(),
        "runs_root": runs_root,
        "archive_root": archive_root,
        "retention_days": retention_days,
        "policy": "plan_only_no_automatic_deletion",
        "run_count": len(rows),
        "eligible_count": sum(1 for row in rows if row.get("eligible")),
        "retain_count": sum(1 for row in rows if not row.get("eligible")),
        "runs": rows,
    }


def _directory_inventory(root: str, run_id: str) -> list[dict[str, Any]]:
    members = []
    for directory, directory_names, filenames in os.walk(root):
        directory_names.sort()
        for filename in sorted(filenames):
            absolute = os.path.join(directory, filename)
            if os.path.islink(absolute):
                raise RuntimeError(f"refusing to archive symbolic link: {absolute}")
            relative = os.path.relpath(absolute, root).replace("\\", "/")
            members.append(
                {
                    "path": f"{run_id}/{relative}",
                    "bytes": os.path.getsize(absolute),
                    "sha256": sha256_file(absolute),
                    "source_path": relative,
                }
            )
    return sorted(members, key=lambda row: row["path"])


def _archive_receipt_path(archive_path: str) -> str:
    return archive_path + ".receipt.json"


def _write_text_atomic(path: str, value: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".tmp",
            delete=False,
            encoding="ascii",
            newline="\n",
            dir=directory,
        ) as file:
            file.write(value)
            temporary = file.name
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _read_sha256_sidecar(path: str, errors: list[str]) -> tuple[str, str]:
    if not os.path.isfile(path):
        errors.append("archive SHA-256 sidecar is missing")
        return "", ""
    try:
        with open(path, "r", encoding="ascii") as file:
            lines = [line.strip() for line in file if line.strip()]
    except OSError as exc:
        errors.append(f"cannot read archive SHA-256 sidecar: {exc}")
        return "", ""
    if len(lines) != 1:
        errors.append("archive SHA-256 sidecar must contain exactly one record")
        return "", ""
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^/\\]+)", lines[0])
    if not match:
        errors.append("archive SHA-256 sidecar format is invalid")
        return "", ""
    return match.group(1).lower(), match.group(2)


def _validate_archive_member(info: zipfile.ZipInfo) -> str | None:
    raw = info.filename.replace("\\", "/")
    if not raw or raw.startswith("/") or "\x00" in raw:
        return None
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    if not path.parts or ":" in path.parts[0]:
        return None
    unix_mode = info.external_attr >> 16
    if unix_mode and stat.S_ISLNK(unix_mode):
        return None
    return path.as_posix()


def _load_archive_receipts(archive_root: str) -> list[dict[str, Any]]:
    if not os.path.isdir(archive_root):
        return []
    receipts = []
    for entry in os.scandir(archive_root):
        if not entry.is_file() or not entry.name.endswith(".zip.receipt.json"):
            continue
        errors: list[str] = []
        receipt = _read_json(entry.path, errors, "archive receipt")
        filename = str(receipt.get("archive_filename", ""))
        if errors or not filename or os.path.basename(filename) != filename:
            continue
        receipt["_archive_path"] = os.path.join(archive_root, filename)
        receipts.append(receipt)
    return receipts


def _legal_hold_active(run_dir: str) -> bool:
    candidates = (
        os.path.join(run_dir, "operations", "legal_hold.json"),
        os.path.join(run_dir, "release", "legal_hold.json"),
    )
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as file:
                value = json.load(file)
        except (OSError, json.JSONDecodeError):
            return True
        if not isinstance(value, dict) or value.get("active") is not False:
            return True
    return False


def _parse_aware_or_local_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.astimezone(timezone.utc)


def _find_preflight_check(state: dict[str, Any], name: str) -> dict[str, Any]:
    for check in state.get("preflight", {}).get("checks", []):
        if check.get("name") == name:
            return check
    return {}


def _release_blockers(
    integrity: dict[str, Any],
    state: dict[str, Any],
    summary: str,
) -> list[str]:
    blockers = []
    if not integrity["ok"]:
        blockers.append("artifact integrity verification failed")
    if state.get("schema_version") != 7:
        blockers.append("run schema is not 7")
    if state.get("status") != "completed" or state.get("error_count") != 0:
        blockers.append("pipeline is not a clean completed run")
    if state.get("mock"):
        blockers.append("mock runs are never releaseable")
    if state.get("runtime") != "pi":
        blockers.append("release requires runtime=pi")
    if state.get("data_mode") != "REAL_TUSHARE":
        blockers.append("release requires REAL_TUSHARE data")
    if state.get("metrics_source") != "REAL_TUSHARE":
        blockers.append("release requires deterministic REAL_TUSHARE metrics")
    assurance = state.get("backtest_assurance", {})
    if (
        assurance.get("decision") != "PASSED_FOR_INTERNAL_RESEARCH"
        or assurance.get("release_gate_passed") is not True
    ):
        blockers.append("deterministic backtest assurance did not pass")
    robustness = state.get("robustness_validation", {})
    if robustness.get("decision") != "PASSED" or robustness.get("failed_checks"):
        blockers.append("holdout, walk-forward, and stress validation did not pass")
    if state.get("success_count") != 7:
        blockers.append("all seven business agents must succeed")
    if state.get("source_provenance", {}).get("release_ready") is not True:
        blockers.append("source revision is not a clean committed baseline")
    python_runtime = _find_preflight_check(state, "python_runtime_contract")
    python_detail = python_runtime.get("detail", {})
    requirements_path = PROJECT_ROOT / "requirements.txt"
    current_lock_sha256 = (
        sha256_file(requirements_path) if requirements_path.is_file() else None
    )
    if (
        not python_runtime
        or python_runtime.get("status") != "ok"
        or python_detail.get("ok") is not True
        or python_detail.get("target") != "windows-cpython-3.11-project-venv"
        or python_detail.get("user_site_enabled") is not False
        or python_detail.get("requirements_lock_sha256") != current_lock_sha256
        or python_detail.get("package_mismatches")
        or python_detail.get("unexpected_distributions")
    ):
        blockers.append(
            "locked Windows CPython 3.11 project runtime evidence is missing or invalid"
        )
    secret_scan_gate = evaluate_secret_scan_receipt()
    if not secret_scan_gate.get("ok"):
        blockers.append(
            "secret scan receipt is missing, stale, tampered, or reports findings"
        )
    try:
        source_review_gate = evaluate_source_review_decision()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        source_review_gate = {
            "review_claim_valid": False,
            "errors": [str(exc)],
        }
    source_review_preflight = _find_preflight_check(state, "source_review_decision")
    source_review_detail = source_review_preflight.get("detail", {})
    if (
        source_review_gate.get("review_claim_valid") is not True
        or source_review_preflight.get("status") != "ok"
        or source_review_detail.get("packet_id")
        != source_review_gate.get("packet_id")
        or source_review_detail.get("decision_file_sha256")
        != source_review_gate.get("decision_file_sha256")
        or source_review_detail.get("candidate_manifest_sha256")
        != source_review_gate.get("candidate_manifest_sha256")
        or source_review_detail.get("candidate_files_sha256")
        != source_review_gate.get("candidate_files_sha256")
    ):
        blockers.append(
            "external Platform/Security source-review decision is missing, stale, or inconsistent"
        )
    controls = state.get("business_controls", {})
    license_gate = controls.get("data_license_gate", {})
    if not is_release_eligible_data_license(license_gate):
        blockers.append(
            "data-license gate lacks current organizational processing and retention rights"
        )
    research_protocol_gate = controls.get("research_protocol_gate", {})
    input_data = state.get("input", {})
    if not is_release_eligible_research_protocol(
        research_protocol_gate,
        input_fingerprint=state.get("input_fingerprint"),
        model_contract_fingerprint=(
            build_model_contract_fingerprint(input_data)
            if isinstance(input_data, dict)
            else None
        ),
    ):
        blockers.append(
            "research protocol lacks current external registration and frozen-contract evidence"
        )
    experiment_registry_gate = controls.get("experiment_registry_gate", {})
    experiment_registry_verification = verify_experiment_registry_gate(state)
    if experiment_registry_verification.get("eligible") is not True:
        blockers.append(
            "external experiment registry reservation/finalization is missing, stale, or inconsistent"
        )
    execution_cost_gate = controls.get("execution_cost_gate", {})
    if not is_release_eligible_execution_cost(execution_cost_gate):
        blockers.append(
            "execution-cost calibration is not approved for internal research"
        )
    if controls.get("external_distribution_approved") is not False:
        blockers.append("external distribution control is invalid")
    if controls.get("broker_connection_enabled") is not False:
        blockers.append("broker connection must remain disabled")
    if state.get("budget_gate", {}).get("status") != "passed":
        blockers.append("operational budget gate did not pass")
    if not is_current_model_pricing(state):
        blockers.append("DeepSeek pricing snapshot is stale or inconsistent")
    runtime_integrity = _find_preflight_check(state, "pi_runtime_integrity")
    if (
        not runtime_integrity
        or runtime_integrity.get("status") != "ok"
        or runtime_integrity.get("version") != Config.PI_VERSION
    ):
        blockers.append("pinned Pi runtime integrity check is missing or invalid")
    security = _find_preflight_check(state, "pi_security_policy")
    required_security = (
        "all_tools_disabled",
        "extensions_disabled",
        "skills_disabled",
        "prompt_templates_disabled",
        "themes_disabled",
        "context_files_disabled",
        "project_resources_ignored",
        "startup_network_disabled",
    )
    if not security or any(security.get(key) is not True for key in required_security):
        blockers.append("Pi no-tools security policy is missing or invalid")
    model_ping = _find_preflight_check(state, "pi_llm_ping")
    if (
        not model_ping
        or model_ping.get("provider") != "deepseek"
        or model_ping.get("model") != Config.DEEPSEEK_MODEL
    ):
        blockers.append("Pi DeepSeek V4 Pro live ping is missing or invalid")
    execution_cost_preflight = _find_preflight_check(
        state, "execution_cost_calibration"
    )
    if (
        not execution_cost_preflight
        or execution_cost_preflight.get("status") != "ok"
        or execution_cost_preflight.get("detail", {}).get("cost_model_fingerprint")
        != execution_cost_gate.get("cost_model_fingerprint")
    ):
        blockers.append("execution-cost preflight evidence is missing or inconsistent")
    research_protocol_preflight = _find_preflight_check(
        state, "research_protocol_registration"
    )
    if (
        not research_protocol_preflight
        or research_protocol_preflight.get("status") != "ok"
        or research_protocol_preflight.get("detail", {}).get("evidence_file_sha256")
        != research_protocol_gate.get("evidence_file_sha256")
        or research_protocol_preflight.get("detail", {}).get(
            "model_contract_sha256"
        )
        != research_protocol_gate.get("model_contract_sha256")
    ):
        blockers.append("research-protocol preflight evidence is missing or inconsistent")
    experiment_registry_preflight = _find_preflight_check(
        state, "experiment_registry_reservation"
    )
    if (
        not experiment_registry_preflight
        or experiment_registry_preflight.get("status") != "ok"
        or experiment_registry_preflight.get("detail", {}).get("status")
        != "reserved"
        or experiment_registry_preflight.get("detail", {}).get(
            "registry_metadata_sha256"
        )
        != experiment_registry_gate.get("registry_metadata_sha256")
        or experiment_registry_preflight.get("detail", {}).get(
            "reservation_entry_hash"
        )
        != experiment_registry_gate.get("reservation_entry_hash")
    ):
        blockers.append("experiment-registry preflight reservation is missing or inconsistent")
    if _TRADING_ACTION.search(summary):
        blockers.append("summary contains prohibited real-capital action language")
    return blockers


def _safe_join(root: str, relative: str) -> str | None:
    absolute = os.path.abspath(os.path.join(root, relative))
    try:
        common = os.path.commonpath([root, absolute])
    except ValueError:
        return None
    return absolute if common == root else None


def _read_json(path: str, errors: list[str], label: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        errors.append(f"{label} is missing")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            value = json.load(file)
        if not isinstance(value, dict):
            errors.append(f"{label} is not a JSON object")
            return {}
        return value
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read {label}: {exc}")
        return {}


def _load_required_json(path: str) -> dict[str, Any]:
    errors: list[str] = []
    value = _read_json(path, errors, os.path.basename(path))
    if errors:
        raise RuntimeError("; ".join(errors))
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_aware_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
