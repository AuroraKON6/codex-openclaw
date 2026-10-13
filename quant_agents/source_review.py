from __future__ import annotations

import csv
import json
import os
import re
import shutil
import stat
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .audit import canonical_json_sha256, sha256_file, write_json_atomic
from .config import Config, PROJECT_ROOT
from .source_baseline import (
    SOURCE_CANDIDATE_POLICY_VERSION,
    SOURCE_CANDIDATE_SCHEMA_VERSION,
    build_source_candidate_manifest,
    require_safe_generated_output_path,
)


SOURCE_REVIEW_PACKET_SCHEMA_VERSION = 1
SOURCE_REVIEW_DECISION_SCHEMA_VERSION = 1
SOURCE_REVIEW_DECISION_MAX_AGE_DAYS = 30
DEFAULT_PACKET_ROOT = Path(".cache") / "source-baseline" / "review-packets"
DEFAULT_DECISION_TEMPLATE_ROOT = (
    Path(".cache") / "source-baseline" / "review-decision-templates"
)
PACKET_FILES = (
    "candidate_manifest.json",
    "review_request.json",
    "review_checklist.csv",
    "REVIEW_INSTRUCTIONS.md",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_REVIEW_ROLES = ("PLATFORM_REVIEWER", "SECURITY_REVIEWER")
_REQUIRED_ACKNOWLEDGEMENTS = (
    "reviewed_candidate_only",
    "private_repository_only",
    "credentials_real_data_approval_originals_excluded",
    "no_real_data_or_model_calls",
    "no_release_or_distribution",
    "no_trading_or_real_capital_actions",
)


class SourceReviewPacketError(RuntimeError):
    pass


def build_source_review_packet(
    project_root: str | Path = PROJECT_ROOT,
    output_root: str | Path | None = None,
    receipt_path: str | Path | None = None,
    max_file_bytes: int = 1024 * 1024,
    candidate_manifest: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest = candidate_manifest or build_source_candidate_manifest(
        project_root=root,
        receipt_path=receipt_path,
        max_file_bytes=max_file_bytes,
    )
    manifest_errors = _validate_candidate_manifest(manifest)
    if manifest_errors:
        return {
            "schema_version": SOURCE_REVIEW_PACKET_SCHEMA_VERSION,
            "report_type": "SOURCE_REVIEW_PACKET",
            "status": "BLOCKED",
            "packet_created": False,
            "source_baseline_authorized": False,
            "git_actions_performed": False,
            "candidate_status": manifest.get("status"),
            "candidate_manifest_sha256": manifest.get("manifest_sha256"),
            "errors": manifest_errors,
            "next_action": "Resolve candidate blockers and regenerate the Secret scan receipt.",
            "disclaimer": _disclaimer(),
        }

    packet_root = (
        Path(output_root).resolve()
        if output_root
        else root / DEFAULT_PACKET_ROOT
    )
    require_safe_generated_output_path(root, packet_root)
    packet_root.mkdir(parents=True, exist_ok=True)

    generated_at = _as_utc(now or datetime.now(timezone.utc))
    packet_name = (
        "source_review_"
        + generated_at.strftime("%Y%m%d_%H%M%S_%f")[:-3]
        + "_"
        + str(manifest["manifest_sha256"])[:12]
    )
    packet_dir = packet_root / packet_name
    if packet_dir.exists():
        raise SourceReviewPacketError(
            f"source review packet already exists and will not be overwritten: {packet_dir}"
        )

    staging = Path(tempfile.mkdtemp(prefix=".source-review-", dir=packet_root))
    try:
        write_json_atomic(str(staging / "candidate_manifest.json"), manifest)
        request = _review_request(manifest, generated_at)
        write_json_atomic(str(staging / "review_request.json"), request)
        _write_checklist(staging / "review_checklist.csv", manifest["files"])
        (staging / "REVIEW_INSTRUCTIONS.md").write_text(
            _instructions(manifest),
            encoding="utf-8",
        )
        artifact_hashes = {
            name: sha256_file(str(staging / name)) for name in PACKET_FILES
        }
        packet_identity = {
            "schema_version": SOURCE_REVIEW_PACKET_SCHEMA_VERSION,
            "generated_at": generated_at.isoformat(),
            "candidate_manifest_sha256": manifest["manifest_sha256"],
            "candidate_files_sha256": manifest["candidate_files_sha256"],
            "artifact_hashes": artifact_hashes,
        }
        packet_manifest = {
            **packet_identity,
            "report_type": "SOURCE_REVIEW_PACKET_MANIFEST",
            "status": "AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED",
            "packet_id": canonical_json_sha256(packet_identity),
            "candidate_file_count": len(manifest["files"]),
            "artifact_count": len(artifact_hashes),
            "source_baseline_authorized": False,
            "git_actions_performed": False,
            "artifact_hashes": artifact_hashes,
            "disclaimer": _disclaimer(),
        }
        write_json_atomic(str(staging / "packet_manifest.json"), packet_manifest)
        os.replace(staging, packet_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return {
        "schema_version": SOURCE_REVIEW_PACKET_SCHEMA_VERSION,
        "report_type": "SOURCE_REVIEW_PACKET",
        "status": "AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED",
        "packet_created": True,
        "packet_dir": str(packet_dir),
        "packet_id": packet_manifest["packet_id"],
        "candidate_manifest_sha256": manifest["manifest_sha256"],
        "candidate_files_sha256": manifest["candidate_files_sha256"],
        "candidate_file_count": len(manifest["files"]),
        "review_flag_count": len(manifest.get("review_flags", [])),
        "machine_blocker_count": len(manifest.get("blockers", [])),
        "packet_files": [*PACKET_FILES, "packet_manifest.json"],
        "source_baseline_authorized": False,
        "git_actions_performed": False,
        "human_review_required": True,
        "next_actions": [
            "PLATFORM_AND_SECURITY_REVIEW_EVERY_FILE",
            "RECORD_DECISION_IN_ORGANIZATION_SYSTEM",
            "CREATE_PRIVATE_BASELINE_ONLY_AFTER_APPROVAL",
            "RUN_CLEAN_CLONE_ACCEPTANCE",
        ],
        "disclaimer": _disclaimer(),
    }


def verify_source_review_packet(packet_dir: str | Path) -> dict[str, Any]:
    root = Path(os.path.abspath(os.fspath(packet_dir)))
    errors: list[str] = []
    expected_names = {*PACKET_FILES, "packet_manifest.json"}
    if not root.is_dir():
        errors.append("source review packet directory is missing")
        actual_names: set[str] = set()
    elif _is_link_or_reparse(root):
        errors.append("source review packet directory is a link or reparse point")
        actual_names = set()
    else:
        actual_names = {path.name for path in root.iterdir()}
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            unexpected = sorted(actual_names - expected_names)
            if missing:
                errors.append("packet files are missing: " + ", ".join(missing))
            if unexpected:
                errors.append("packet contains unexpected files: " + ", ".join(unexpected))

    packet_manifest = _read_json(root / "packet_manifest.json", errors)
    raw_artifact_hashes = packet_manifest.get("artifact_hashes")
    if isinstance(raw_artifact_hashes, dict):
        artifact_hashes = raw_artifact_hashes
    else:
        artifact_hashes = {}
        errors.append("packet artifact hash inventory is not an object")
    if set(artifact_hashes) != set(PACKET_FILES):
        errors.append("packet artifact hash inventory is incomplete")
    for name in PACKET_FILES:
        path = root / name
        expected_hash = artifact_hashes.get(name)
        if not path.is_file() or _is_link_or_reparse(path):
            errors.append(f"packet artifact is missing or unsafe: {name}")
            continue
        actual_hash = sha256_file(str(path))
        if not _SHA256.fullmatch(str(expected_hash)) or actual_hash != expected_hash:
            errors.append(f"packet artifact hash mismatch: {name}")

    packet_identity = {
        "schema_version": packet_manifest.get("schema_version"),
        "generated_at": packet_manifest.get("generated_at"),
        "candidate_manifest_sha256": packet_manifest.get(
            "candidate_manifest_sha256"
        ),
        "candidate_files_sha256": packet_manifest.get("candidate_files_sha256"),
        "artifact_hashes": artifact_hashes,
    }
    if packet_manifest.get("packet_id") != canonical_json_sha256(packet_identity):
        errors.append("packet identity is inconsistent")
    if (
        packet_manifest.get("schema_version") != SOURCE_REVIEW_PACKET_SCHEMA_VERSION
        or packet_manifest.get("report_type")
        != "SOURCE_REVIEW_PACKET_MANIFEST"
        or packet_manifest.get("status")
        != "AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED"
        or packet_manifest.get("source_baseline_authorized") is not False
        or packet_manifest.get("git_actions_performed") is not False
        or packet_manifest.get("artifact_count") != len(PACKET_FILES)
        or not _is_utc_timestamp(packet_manifest.get("generated_at"))
    ):
        errors.append("packet manifest control claims are invalid")

    candidate = _read_json(root / "candidate_manifest.json", errors)
    errors.extend(
        f"candidate manifest: {error}"
        for error in _validate_candidate_manifest(candidate)
    )
    raw_candidate_files = candidate.get("files")
    candidate_files = raw_candidate_files if isinstance(raw_candidate_files, list) else []
    candidate_summary = candidate.get("summary")
    if not isinstance(candidate_summary, dict):
        candidate_summary = {}
    candidate_review_flags = candidate.get("review_flags")
    if not isinstance(candidate_review_flags, list):
        candidate_review_flags = []
    request = _read_json(root / "review_request.json", errors)
    if (
        request.get("candidate_manifest_sha256") != candidate.get("manifest_sha256")
        or request.get("candidate_files_sha256")
        != candidate.get("candidate_files_sha256")
        or request.get("candidate_file_count") != len(candidate_files)
        or request.get("candidate_total_bytes")
        != candidate_summary.get("candidate_total_bytes")
        or request.get("generated_at") != packet_manifest.get("generated_at")
    ):
        errors.append("review request is not bound to the candidate inventory")
    if (
        request.get("schema_version") != SOURCE_REVIEW_PACKET_SCHEMA_VERSION
        or request.get("request_type") != "PRIVATE_SOURCE_BASELINE_FILE_REVIEW"
        or request.get("status")
        != "AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED"
        or request.get("machine_blocker_count") != 0
        or request.get("review_flag_count") != len(candidate_review_flags)
        or request.get("required_review_roles")
        != ["PLATFORM_REVIEWER", "SECURITY_REVIEWER"]
        or request.get("separation_of_duties_required") is not True
        or request.get("every_file_must_be_reviewed") is not True
        or request.get("review_decision_captured") is not False
        or request.get("organization_identity_verified") is not False
        or request.get("source_baseline_authorized") is not False
        or request.get("git_actions_performed") is not False
    ):
        errors.append("review request control claims are invalid")
    if (
        packet_manifest.get("candidate_manifest_sha256")
        != candidate.get("manifest_sha256")
        or packet_manifest.get("candidate_files_sha256")
        != candidate.get("candidate_files_sha256")
        or packet_manifest.get("candidate_file_count")
        != len(candidate_files)
    ):
        errors.append("packet manifest is not bound to the candidate inventory")
    _verify_checklist(root / "review_checklist.csv", candidate_files, errors)

    return {
        "schema_version": SOURCE_REVIEW_PACKET_SCHEMA_VERSION,
        "report_type": "SOURCE_REVIEW_PACKET_VERIFICATION",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "packet_dir": str(root),
        "packet_id": packet_manifest.get("packet_id"),
        "status": (
            "VERIFIED_AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED"
            if not errors
            else "TAMPERED_OR_INVALID"
        ),
        "ok": not errors,
        "candidate_file_count": len(candidate_files),
        "artifact_count": len(artifact_hashes),
        "application_hash_only_not_signature": True,
        "organization_identity_verified": False,
        "source_baseline_authorized": False,
        "git_actions_performed": False,
        "errors": list(dict.fromkeys(errors)),
        "disclaimer": _disclaimer(),
    }


def build_source_review_decision_template(
    packet_dir: str | Path,
    output_path: str | Path | None = None,
    project_root: str | Path = PROJECT_ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    verification = verify_source_review_packet(packet_dir)
    if verification.get("ok") is not True:
        return {
            "schema_version": SOURCE_REVIEW_DECISION_SCHEMA_VERSION,
            "report_type": "SOURCE_REVIEW_DECISION_TEMPLATE",
            "status": "BLOCKED",
            "template_created": False,
            "source_baseline_authorized": False,
            "git_actions_performed": False,
            "errors": verification.get("errors", ["source review packet is invalid"]),
            "disclaimer": _disclaimer(),
        }

    packet_root = Path(os.path.abspath(os.fspath(packet_dir)))
    read_errors: list[str] = []
    packet_manifest = _read_json(packet_root / "packet_manifest.json", read_errors)
    candidate = _read_json(packet_root / "candidate_manifest.json", read_errors)
    if read_errors:
        raise SourceReviewPacketError("; ".join(read_errors))

    generated_at = _as_utc(now or datetime.now(timezone.utc))
    if output_path:
        target = Path(os.path.abspath(os.fspath(output_path)))
    else:
        target = (
            root
            / DEFAULT_DECISION_TEMPLATE_ROOT
            / (
                "source_review_decision_template_"
                + generated_at.strftime("%Y%m%d_%H%M%S_%f")[:-3]
                + "_"
                + str(packet_manifest["packet_id"])[:12]
                + ".json"
            )
        )
    require_safe_generated_output_path(root, target)
    if target.exists():
        raise SourceReviewPacketError(
            f"source review decision template already exists and will not be overwritten: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)

    template = {
        "schema_version": SOURCE_REVIEW_DECISION_SCHEMA_VERSION,
        "document_type": "SOURCE_REVIEW_DECISION",
        "record_state": "TEMPLATE_NOT_EVIDENCE",
        "template_generated_at": generated_at.isoformat(),
        "packet_id": packet_manifest["packet_id"],
        "packet_generated_at": packet_manifest["generated_at"],
        "candidate_manifest_sha256": candidate["manifest_sha256"],
        "candidate_files_sha256": candidate["candidate_files_sha256"],
        "candidate_file_count": len(candidate["files"]),
        "review_flag_count": len(candidate.get("review_flags", [])),
        "external_review_system": "",
        "external_review_record_id": "",
        "review_outcome": "",
        "completed_at": "",
        "reviewers": [
            {
                "role": role,
                "reviewer_subject_id": "",
                "organization_identity_evidence_ref": "",
                "review_system_record_id": "",
                "reviewed_at": "",
                "decision": "",
                "every_file_reviewed": False,
                "reviewed_file_count": 0,
                "candidate_manifest_sha256": "",
                "candidate_files_sha256": "",
            }
            for role in _REQUIRED_REVIEW_ROLES
        ],
        "file_reviews": [
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "platform_decision": "",
                "security_decision": "",
                "platform_evidence_ref": "",
                "security_evidence_ref": "",
                "review_note": "",
            }
            for row in candidate["files"]
        ],
        "review_flag_resolutions": [
            {
                "code": flag.get("code"),
                "path": flag.get("path"),
                "resolution": "",
                "rationale": "",
                "evidence_ref": "",
            }
            for flag in candidate.get("review_flags", [])
        ],
        "rejected_files": [],
        "unresolved_files": [],
        "constraints_acknowledged": {
            name: False for name in _REQUIRED_ACKNOWLEDGEMENTS
        },
        "private_baseline_execution_authorized": False,
        "source_baseline_authorized": False,
        "git_actions_performed": False,
        "g1_authorized": False,
        "real_run_authorized": False,
        "disclaimer": _disclaimer(),
    }
    write_json_atomic(str(target), template)
    return {
        "schema_version": SOURCE_REVIEW_DECISION_SCHEMA_VERSION,
        "report_type": "SOURCE_REVIEW_DECISION_TEMPLATE",
        "status": "TEMPLATE_CREATED_NOT_REVIEW_EVIDENCE",
        "template_created": True,
        "template_path": str(target),
        "template_sha256": sha256_file(str(target)),
        "packet_id": packet_manifest["packet_id"],
        "candidate_manifest_sha256": candidate["manifest_sha256"],
        "candidate_files_sha256": candidate["candidate_files_sha256"],
        "candidate_file_count": len(candidate["files"]),
        "review_flag_count": len(candidate.get("review_flags", [])),
        "human_fields_blank": True,
        "source_baseline_authorized": False,
        "git_actions_performed": False,
        "g1_authorized": False,
        "real_run_authorized": False,
        "next_actions": [
            "COPY_TEMPLATE_TO_EXTERNAL_ORGANIZATION_REVIEW_SYSTEM",
            "COMPLETE_DISTINCT_PLATFORM_AND_SECURITY_PER_FILE_REVIEW",
            "RESOLVE_EVERY_MACHINE_REVIEW_FLAG",
            "VERIFY_COMPLETED_EXTERNAL_DECISION_WITH_SOURCE_REVIEW_DECISION_VERIFY",
        ],
        "disclaimer": _disclaimer(),
    }


def evaluate_source_review_decision(
    packet_dir: str | Path | None = None,
    decision_path: str | Path | None = None,
    project_root: str | Path = PROJECT_ROOT,
    secret_receipt_path: str | Path | None = None,
    current_candidate_manifest: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    current = _as_utc(now or datetime.now(timezone.utc))
    configured_packet = packet_dir or Config.SOURCE_REVIEW_PACKET_DIR
    configured_decision = decision_path or Config.SOURCE_REVIEW_DECISION_PATH
    errors: list[str] = []
    if not configured_packet:
        errors.append("SOURCE_REVIEW_PACKET_DIR is not set")
    if not configured_decision:
        errors.append("SOURCE_REVIEW_DECISION_PATH is not set")
    if errors:
        return _decision_result(errors=errors, verified_at=current)

    packet_root = Path(os.path.abspath(os.fspath(configured_packet)))
    decision_file = Path(os.path.abspath(os.fspath(configured_decision)))
    if _is_link_or_reparse(decision_file) or not decision_file.is_file():
        errors.append(
            "source review decision is missing, non-file, link, or reparse point"
        )
    if _path_is_within_project(decision_file, root):
        errors.append("source review decision must be stored outside the project repository")

    try:
        packet_verification = verify_source_review_packet(packet_root)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as exc:
        packet_verification = {
            "ok": False,
            "errors": [f"source review packet verification failed: {exc}"],
        }
    if packet_verification.get("ok") is not True:
        errors.append(
            "source review packet is invalid: "
            + "; ".join(packet_verification.get("errors", []))
        )

    packet_manifest: dict[str, Any] = {}
    candidate: dict[str, Any] = {}
    if packet_verification.get("ok") is True:
        packet_manifest = _read_json(packet_root / "packet_manifest.json", errors)
        candidate = _read_json(packet_root / "candidate_manifest.json", errors)

    decision: dict[str, Any] = {}
    if decision_file.is_file() and not _is_link_or_reparse(decision_file):
        decision = _read_json(decision_file, errors)

    if candidate:
        try:
            current_candidate = current_candidate_manifest or build_source_candidate_manifest(
                project_root=root,
                receipt_path=secret_receipt_path,
                max_file_bytes=int(candidate.get("policy", {}).get("max_file_bytes", 0)),
                write=False,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            current_candidate = {}
            errors.append(f"current source candidate cannot be evaluated: {exc}")
        current_errors = _validate_candidate_manifest(current_candidate)
        errors.extend(f"current source candidate: {error}" for error in current_errors)
        if (
            current_candidate.get("manifest_sha256") != candidate.get("manifest_sha256")
            or current_candidate.get("candidate_files_sha256")
            != candidate.get("candidate_files_sha256")
            or current_candidate.get("files") != candidate.get("files")
        ):
            errors.append("current source candidate does not exactly match the reviewed packet")

    if decision:
        _validate_source_review_decision(
            decision=decision,
            packet_manifest=packet_manifest,
            candidate=candidate,
            current=current,
            errors=errors,
        )

    return _decision_result(
        errors=errors,
        verified_at=current,
        packet_dir=packet_root,
        decision_path=decision_file,
        packet_manifest=packet_manifest,
        candidate=candidate,
        decision=decision,
    )


def _validate_source_review_decision(
    decision: dict[str, Any],
    packet_manifest: dict[str, Any],
    candidate: dict[str, Any],
    current: datetime,
    errors: list[str],
) -> None:
    if decision.get("schema_version") != SOURCE_REVIEW_DECISION_SCHEMA_VERSION:
        errors.append(
            f"source review decision schema_version must be {SOURCE_REVIEW_DECISION_SCHEMA_VERSION}"
        )
    if decision.get("document_type") != "SOURCE_REVIEW_DECISION":
        errors.append("source review decision document_type is invalid")
    if decision.get("record_state") != "COMPLETED_EXTERNAL_REVIEW_RECORD":
        errors.append("source review decision is still a template or incomplete")
    if decision.get("review_outcome") != "DUAL_FILE_REVIEW_PASSED":
        errors.append("source review outcome must be DUAL_FILE_REVIEW_PASSED")
    for field in ("external_review_system", "external_review_record_id"):
        if not _meaningful(decision.get(field)):
            errors.append(f"{field} is required and must not be a placeholder")

    expected_bindings = {
        "packet_id": packet_manifest.get("packet_id"),
        "packet_generated_at": packet_manifest.get("generated_at"),
        "candidate_manifest_sha256": candidate.get("manifest_sha256"),
        "candidate_files_sha256": candidate.get("candidate_files_sha256"),
        "candidate_file_count": len(candidate.get("files", [])),
        "review_flag_count": len(candidate.get("review_flags", [])),
    }
    for field, expected in expected_bindings.items():
        if decision.get(field) != expected:
            errors.append(f"source review decision {field} does not match the packet")

    packet_at = _parse_utc_timestamp(
        packet_manifest.get("generated_at"), "packet generated_at", errors
    )
    completed_at = _parse_utc_timestamp(
        decision.get("completed_at"), "decision completed_at", errors
    )
    if packet_at and completed_at and completed_at < packet_at:
        errors.append("decision completed_at must not precede packet generation")
    if completed_at and completed_at > current:
        errors.append("decision completed_at must not be in the future")
    if (
        completed_at
        and completed_at <= current
        and current - completed_at > timedelta(days=SOURCE_REVIEW_DECISION_MAX_AGE_DAYS)
    ):
        errors.append(
            "source review decision is older than "
            f"{SOURCE_REVIEW_DECISION_MAX_AGE_DAYS} days"
        )

    reviewers = decision.get("reviewers")
    if not isinstance(reviewers, list) or len(reviewers) != len(_REQUIRED_REVIEW_ROLES):
        errors.append("source review decision must contain exactly two reviewer records")
        reviewers = []
    reviewer_by_role: dict[str, dict[str, Any]] = {}
    for reviewer in reviewers:
        if not isinstance(reviewer, dict):
            errors.append("source review reviewer record is not an object")
            continue
        role = str(reviewer.get("role", ""))
        if role in reviewer_by_role:
            errors.append(f"source review reviewer role is duplicated: {role}")
        reviewer_by_role[role] = reviewer
    if set(reviewer_by_role) != set(_REQUIRED_REVIEW_ROLES):
        errors.append("source review roles must be PLATFORM_REVIEWER and SECURITY_REVIEWER")

    subject_ids: list[str] = []
    for role in _REQUIRED_REVIEW_ROLES:
        reviewer = reviewer_by_role.get(role)
        if not reviewer:
            continue
        subject_id = str(reviewer.get("reviewer_subject_id", "")).strip()
        if not _meaningful(subject_id):
            errors.append(f"{role} reviewer_subject_id is required")
        else:
            subject_ids.append(subject_id.casefold())
        for field in (
            "organization_identity_evidence_ref",
            "review_system_record_id",
        ):
            if not _meaningful(reviewer.get(field)):
                errors.append(f"{role} {field} is required")
        if reviewer.get("decision") != "APPROVED":
            errors.append(f"{role} decision must be APPROVED")
        if reviewer.get("every_file_reviewed") is not True:
            errors.append(f"{role} must attest every_file_reviewed=true")
        if reviewer.get("reviewed_file_count") != len(candidate.get("files", [])):
            errors.append(f"{role} reviewed_file_count does not match the packet")
        if reviewer.get("candidate_manifest_sha256") != candidate.get("manifest_sha256"):
            errors.append(f"{role} candidate_manifest_sha256 does not match the packet")
        if reviewer.get("candidate_files_sha256") != candidate.get(
            "candidate_files_sha256"
        ):
            errors.append(f"{role} candidate_files_sha256 does not match the packet")
        reviewed_at = _parse_utc_timestamp(
            reviewer.get("reviewed_at"), f"{role} reviewed_at", errors
        )
        if packet_at and reviewed_at and reviewed_at < packet_at:
            errors.append(f"{role} reviewed_at must not precede packet generation")
        if completed_at and reviewed_at and reviewed_at > completed_at:
            errors.append(f"{role} reviewed_at must not follow decision completion")
        if reviewed_at and reviewed_at > current:
            errors.append(f"{role} reviewed_at must not be in the future")
    if len(subject_ids) == len(_REQUIRED_REVIEW_ROLES) and len(set(subject_ids)) != len(
        subject_ids
    ):
        errors.append("Platform and Security reviewers must be distinct identities")

    expected_files = candidate.get("files", [])
    file_reviews = decision.get("file_reviews")
    if not isinstance(file_reviews, list) or len(file_reviews) != len(expected_files):
        errors.append("file_reviews must contain exactly one row for every candidate file")
        file_reviews = []
    for index, (review, expected) in enumerate(
        zip(file_reviews, expected_files), start=1
    ):
        if not isinstance(review, dict) or not isinstance(expected, dict):
            errors.append(f"file review row {index} is invalid")
            continue
        if review.get("path") != expected.get("path") or review.get("sha256") != expected.get(
            "sha256"
        ):
            errors.append(f"file review row {index} does not match the candidate inventory")
        for reviewer_name in ("platform", "security"):
            if review.get(f"{reviewer_name}_decision") != "APPROVED":
                errors.append(
                    f"file review row {index} {reviewer_name}_decision must be APPROVED"
                )
            if not _meaningful(review.get(f"{reviewer_name}_evidence_ref")):
                errors.append(
                    f"file review row {index} {reviewer_name}_evidence_ref is required"
                )

    expected_flags = candidate.get("review_flags", [])
    resolutions = decision.get("review_flag_resolutions")
    if not isinstance(resolutions, list) or len(resolutions) != len(expected_flags):
        errors.append("every machine review flag must have exactly one resolution")
        resolutions = []
    for index, (resolution, expected) in enumerate(
        zip(resolutions, expected_flags), start=1
    ):
        if not isinstance(resolution, dict) or not isinstance(expected, dict):
            errors.append(f"review flag resolution row {index} is invalid")
            continue
        if (
            resolution.get("code") != expected.get("code")
            or resolution.get("path") != expected.get("path")
        ):
            errors.append(f"review flag resolution row {index} does not match the packet")
        if resolution.get("resolution") != "RESOLVED":
            errors.append(f"review flag resolution row {index} must be RESOLVED")
        if not _meaningful(resolution.get("rationale")):
            errors.append(f"review flag resolution row {index} rationale is required")
        if not _meaningful(resolution.get("evidence_ref")):
            errors.append(f"review flag resolution row {index} evidence_ref is required")

    if decision.get("rejected_files") != []:
        errors.append("rejected_files must be empty for a passed dual review")
    if decision.get("unresolved_files") != []:
        errors.append("unresolved_files must be empty for a passed dual review")
    acknowledgements = decision.get("constraints_acknowledged")
    if not isinstance(acknowledgements, dict) or set(acknowledgements) != set(
        _REQUIRED_ACKNOWLEDGEMENTS
    ):
        errors.append("source review constraint acknowledgement inventory is invalid")
    elif any(acknowledgements.get(name) is not True for name in _REQUIRED_ACKNOWLEDGEMENTS):
        errors.append("every source review constraint must be acknowledged")
    for field in (
        "private_baseline_execution_authorized",
        "source_baseline_authorized",
        "git_actions_performed",
        "g1_authorized",
        "real_run_authorized",
    ):
        if decision.get(field) is not False:
            errors.append(f"source review decision must keep {field}=false")


def _decision_result(
    errors: list[str],
    verified_at: datetime,
    packet_dir: Path | None = None,
    decision_path: Path | None = None,
    packet_manifest: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet_manifest = packet_manifest or {}
    candidate = candidate or {}
    decision = decision or {}
    unique_errors = list(dict.fromkeys(errors))
    valid = not unique_errors
    return {
        "schema_version": SOURCE_REVIEW_DECISION_SCHEMA_VERSION,
        "report_type": "SOURCE_REVIEW_DECISION_VERIFICATION",
        "verified_at": verified_at.isoformat(),
        "status": (
            "VALID_DUAL_FILE_REVIEW_CLAIM_AWAITING_PRIVATE_BASELINE_EXECUTION_AUTHORIZATION"
            if valid
            else "BLOCKED_OR_INVALID"
        ),
        "ok": valid,
        "review_claim_valid": valid,
        "packet_dir": str(packet_dir) if packet_dir else None,
        "decision_path": str(decision_path) if decision_path else None,
        "packet_id": packet_manifest.get("packet_id"),
        "candidate_manifest_sha256": candidate.get("manifest_sha256"),
        "candidate_files_sha256": candidate.get("candidate_files_sha256"),
        "candidate_file_count": len(candidate.get("files", [])),
        "review_flag_count": len(candidate.get("review_flags", [])),
        "decision_file_sha256": (
            sha256_file(str(decision_path))
            if decision_path and decision_path.is_file() and not _is_link_or_reparse(decision_path)
            else None
        ),
        "external_review_system": decision.get("external_review_system"),
        "external_review_record_id": decision.get("external_review_record_id"),
        "review_outcome": decision.get("review_outcome"),
        "completed_at": decision.get("completed_at"),
        "identity_assurance": "evidence_references_claimed_application_not_identity_authenticated",
        "application_hash_only_not_signature": True,
        "organization_identity_verified": False,
        "private_baseline_execution_authorized": False,
        "source_baseline_authorized": False,
        "git_actions_performed": False,
        "g1_authorized": False,
        "real_run_authorized": False,
        "errors": unique_errors,
        "next_action": (
            "HUMAN_PLATFORM_OWNER_AUTHORIZE_AND_CREATE_EXACT_PRIVATE_BASELINE"
            if valid
            else "COMPLETE_AND_EXPORT_DISTINCT_PLATFORM_AND_SECURITY_REVIEW_EVIDENCE"
        ),
        "disclaimer": _disclaimer(),
    }


def _validate_candidate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["source candidate manifest is not a JSON object"]
    files = manifest.get("files")
    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        policy = {}
        errors.append("source candidate policy is missing")
    summary = manifest.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        errors.append("source candidate summary is missing")
    secret_scan = manifest.get("secret_scan")
    if not isinstance(secret_scan, dict):
        secret_scan = {}
        errors.append("source candidate Secret scan binding is missing")
    receipt_summary = secret_scan.get("receipt_summary")
    if not isinstance(receipt_summary, dict):
        receipt_summary = {}
    git_actions = manifest.get("git_actions")
    if not isinstance(git_actions, dict):
        git_actions = {}
        errors.append("source candidate Git action claims are missing")
    blockers = manifest.get("blockers")
    if not isinstance(blockers, list):
        blockers = []
        errors.append("source candidate blocker inventory is invalid")
    review_flags = manifest.get("review_flags")
    if not isinstance(review_flags, list):
        review_flags = []
        errors.append("source candidate review flag inventory is invalid")
    max_file_bytes = policy.get("max_file_bytes")
    if (
        isinstance(max_file_bytes, bool)
        or not isinstance(max_file_bytes, int)
        or max_file_bytes <= 0
    ):
        errors.append("source candidate max_file_bytes policy is invalid")
    if manifest.get("schema_version") != SOURCE_CANDIDATE_SCHEMA_VERSION:
        errors.append("source candidate schema version is unsupported")
    if manifest.get("policy_version") != SOURCE_CANDIDATE_POLICY_VERSION:
        errors.append("source candidate policy version is not current")
    if manifest.get("status") != "READY_FOR_HUMAN_FILE_REVIEW_NOT_AUTHORIZED":
        errors.append("source candidate is not ready for human file review")
    if manifest.get("ready_for_human_file_review") is not True:
        errors.append("source candidate reviewable flag is not true")
    if manifest.get("source_baseline_authorized") is not False:
        errors.append("source candidate incorrectly claims baseline authorization")
    if manifest.get("source_release_ready") is not False:
        errors.append("source candidate incorrectly claims release readiness")
    if manifest.get("human_review_required") is not True:
        errors.append("source candidate does not require human review")
    if blockers:
        errors.append("source candidate contains machine blockers")
    if secret_scan.get("ok") is not True:
        errors.append("source candidate is not bound to a passed Secret scan")
    if not _SHA256.fullmatch(str(receipt_summary.get("receipt_sha256", ""))):
        errors.append("source candidate Secret scan receipt identity is invalid")
    if not isinstance(files, list) or not files:
        errors.append("source candidate file inventory is missing")
        return errors

    top_level_flag_pairs: list[tuple[str, str]] = []
    for flag in review_flags:
        if not isinstance(flag, dict):
            errors.append("source candidate review flag row is not an object")
            continue
        code = flag.get("code")
        path = flag.get("path")
        if not isinstance(code, str) or not code.strip():
            errors.append("source candidate review flag code is invalid")
            continue
        if not isinstance(path, str) or not path.strip():
            errors.append("source candidate review flag path is invalid")
            continue
        top_level_flag_pairs.append((code, path))

    file_hashes = {
        str(row.get("path")): row.get("sha256")
        for row in files
        if isinstance(row, dict)
    }
    if len(file_hashes) != len(files):
        errors.append("candidate file paths are missing or duplicated")
    candidate_total_bytes = 0
    row_flag_pairs: list[tuple[str, str]] = []
    for row in files:
        if not isinstance(row, dict):
            errors.append("candidate file row is not an object")
            continue
        row_path = row.get("path")
        if not isinstance(row_path, str) or not row_path.strip() or not _SHA256.fullmatch(
            str(row.get("sha256", ""))
        ):
            errors.append("candidate file row has an invalid path or SHA-256")
        if row.get("binary") is not False or row.get("link_or_reparse") is not False:
            errors.append("candidate file row claims binary, link, or reparse content")
        byte_count = row.get("bytes")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            errors.append("candidate file row has an invalid byte count")
        else:
            candidate_total_bytes += byte_count
        row_review_flags = row.get("review_flags")
        if not isinstance(row_review_flags, list) or not all(
            isinstance(flag, str) for flag in row_review_flags
        ):
            errors.append("candidate file row has invalid review flags")
        else:
            if len(set(row_review_flags)) != len(row_review_flags):
                errors.append("candidate file row contains duplicated review flags")
            row_flag_pairs.extend((flag, row_path) for flag in row_review_flags)
    if len(set(top_level_flag_pairs)) != len(top_level_flag_pairs):
        errors.append("source candidate review flag inventory contains duplicates")
    if Counter(top_level_flag_pairs) != Counter(row_flag_pairs):
        errors.append("source candidate review flags are inconsistent with file rows")
    candidate_files_sha256 = canonical_json_sha256(file_hashes)
    if manifest.get("candidate_files_sha256") != candidate_files_sha256:
        errors.append("candidate file inventory identity is inconsistent")
    if summary.get("candidate_file_count") != len(files):
        errors.append("candidate file count is inconsistent")
    if summary.get("candidate_total_bytes") != candidate_total_bytes:
        errors.append("candidate total bytes are inconsistent")
    if summary.get("blocker_count") != len(blockers):
        errors.append("candidate blocker count is inconsistent")
    if summary.get("review_flag_count") != len(review_flags):
        errors.append("candidate review flag count is inconsistent")
    identity = {
        "schema_version": manifest.get("schema_version"),
        "policy_version": manifest.get("policy_version"),
        "max_file_bytes": policy.get("max_file_bytes"),
        "candidate_files_sha256": candidate_files_sha256,
        "files": files,
        "secret_scan_receipt_sha256": receipt_summary.get("receipt_sha256"),
    }
    if manifest.get("manifest_sha256") != canonical_json_sha256(identity):
        errors.append("candidate manifest identity is inconsistent")
    if any(
        git_actions.get(name) is not False
        for name in (
            "git_add_performed",
            "commit_performed",
            "tag_performed",
            "remote_created",
        )
    ):
        errors.append("source candidate contains an invalid Git action claim")
    return errors


def _review_request(
    manifest: dict[str, Any], generated_at: datetime
) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_REVIEW_PACKET_SCHEMA_VERSION,
        "request_type": "PRIVATE_SOURCE_BASELINE_FILE_REVIEW",
        "status": "AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED",
        "generated_at": generated_at.isoformat(),
        "candidate_manifest_sha256": manifest["manifest_sha256"],
        "candidate_files_sha256": manifest["candidate_files_sha256"],
        "candidate_file_count": len(manifest["files"]),
        "candidate_total_bytes": manifest["summary"]["candidate_total_bytes"],
        "machine_blocker_count": len(manifest.get("blockers", [])),
        "review_flag_count": len(manifest.get("review_flags", [])),
        "required_review_roles": ["PLATFORM_REVIEWER", "SECURITY_REVIEWER"],
        "separation_of_duties_required": True,
        "every_file_must_be_reviewed": True,
        "review_decision_captured": False,
        "organization_identity_verified": False,
        "source_baseline_authorized": False,
        "git_actions_performed": False,
        "forbidden_until_human_approval": [
            "GIT_ADD_ALL",
            "COMMIT",
            "TAG",
            "PUSH_OR_REMOTE_CREATION",
            "REAL_DATA_OR_MODEL_RUN",
            "RELEASE_OR_DISTRIBUTION",
        ],
        "acceptance_criteria": [
            "Every candidate file is reviewed against the checklist.",
            "All review flags are explicitly resolved.",
            "No credential, real data, approval original, runtime output, or cache is included.",
            "Platform and Security decisions are recorded by distinct organization identities.",
            "A clean private commit and tag are independently reproduced from this exact candidate identity.",
            "Clean-clone tests, Mock E2E, Secret scan, and source provenance pass.",
        ],
        "disclaimer": _disclaimer(),
    }


def _write_checklist(path: Path, files: list[dict[str, Any]]) -> None:
    fields = (
        "index",
        "path",
        "category",
        "extension",
        "bytes",
        "sha256",
        "machine_review_flags",
        "human_decision",
        "reviewer_note",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(files, start=1):
            writer.writerow(
                {
                    "index": index,
                    "path": _spreadsheet_safe(str(row.get("path", ""))),
                    "category": _spreadsheet_safe(str(row.get("category", ""))),
                    "extension": _spreadsheet_safe(str(row.get("extension", ""))),
                    "bytes": int(row.get("bytes", 0) or 0),
                    "sha256": str(row.get("sha256", "")),
                    "machine_review_flags": ";".join(row.get("review_flags", [])),
                    "human_decision": "",
                    "reviewer_note": "",
                }
            )


def _verify_checklist(
    path: Path, files: list[Any], errors: list[str]
) -> None:
    expected_fields = [
        "index",
        "path",
        "category",
        "extension",
        "bytes",
        "sha256",
        "machine_review_flags",
        "human_decision",
        "reviewer_note",
    ]
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
    except (OSError, csv.Error) as exc:
        errors.append(f"review checklist cannot be read: {exc}")
        return
    if reader.fieldnames != expected_fields:
        errors.append("review checklist columns are invalid")
    if len(rows) != len(files):
        errors.append("review checklist row count does not match candidate inventory")
        return
    for index, (row, candidate) in enumerate(zip(rows, files), start=1):
        if not isinstance(candidate, dict):
            errors.append(f"review checklist candidate row {index} is invalid")
            continue
        review_flags = candidate.get("review_flags")
        if not isinstance(review_flags, list) or not all(
            isinstance(flag, str) for flag in review_flags
        ):
            review_flags = []
        if (
            set(row) != set(expected_fields)
            or row.get("index") != str(index)
            or row.get("path") != _spreadsheet_safe(str(candidate.get("path", "")))
            or row.get("category")
            != _spreadsheet_safe(str(candidate.get("category", "")))
            or row.get("extension")
            != _spreadsheet_safe(str(candidate.get("extension", "")))
            or row.get("bytes") != str(candidate.get("bytes", 0))
            or row.get("sha256") != str(candidate.get("sha256", ""))
            or row.get("machine_review_flags") != ";".join(review_flags)
            or row.get("human_decision") != ""
            or row.get("reviewer_note") != ""
        ):
            errors.append(f"review checklist row {index} is inconsistent or pre-decided")


def _instructions(manifest: dict[str, Any]) -> str:
    return f"""# Source Review Instructions

This packet covers {len(manifest['files'])} files and candidate identity `{manifest['candidate_files_sha256']}`.

1. Keep all machine-generated packet files read-only; make a controlled copy for annotations.
2. Platform and Security reviewers must inspect every checklist row and resolve every machine flag.
3. Reject credentials, real data, approval originals, runtime outputs, caches, archives, databases, executables, and unreviewed third-party code.
4. Record reviewer identities, timestamps, decisions, and exceptions in the organization review system; local edits do not authenticate identity.
5. Only after approval, create the least-privilege private remote and reviewed commit/tag without using an unreviewed `git add .` shortcut.
6. From a clean clone, rerun bootstrap, tests, Mock E2E, Secret scan, source-candidate, Pi no-ping inspection, and provenance verification.

This packet does not approve a source baseline, real data, model calls, release, trading, or real-capital actions.
"""


def _spreadsheet_safe(value: str) -> str:
    if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


def _read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    if _is_link_or_reparse(path) or not path.is_file():
        errors.append(f"cannot read {path.name}: missing, non-file, link, or reparse point")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read {path.name}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.name} is not a JSON object")
        return {}
    return value


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _is_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _parse_utc_timestamp(
    value: Any, field: str, errors: list[str]
) -> datetime | None:
    if not _is_utc_timestamp(value):
        errors.append(f"{field} must be an ISO-8601 UTC timestamp")
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _meaningful(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.upper().startswith(("REPLACE_", "TODO", "TBD"))


def _path_is_within_project(path: Path, project_root: Path) -> bool:
    candidates = [path]
    try:
        candidates.append(path.resolve(strict=False))
    except OSError:
        pass
    for candidate in candidates:
        try:
            candidate.relative_to(project_root)
            return True
        except ValueError:
            continue
    return False


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _disclaimer() -> str:
    return (
        "Machine-generated review aid only. It does not authenticate reviewers, "
        "authorize Git actions, release research, or permit trading or real-capital actions."
    )
