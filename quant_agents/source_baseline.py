"""Pre-commit source-candidate inventory for the private baseline gate."""

from __future__ import annotations

import re
import stat
import subprocess
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .audit import (
    canonical_json_sha256,
    collect_source_provenance,
    sha256_file,
    write_json_atomic,
)
from .config import Config, PROJECT_ROOT
from .secret_scan import evaluate_secret_scan_receipt, list_scan_candidates

SOURCE_CANDIDATE_SCHEMA_VERSION = 1
SOURCE_CANDIDATE_POLICY_VERSION = "2026-09-02.1"
DEFAULT_MAX_FILE_BYTES = 1024 * 1024
DEFAULT_OUTPUT_RELATIVE = (
    Path(".cache") / "source-baseline" / "candidate_manifest.json"
)

REQUIRED_CANDIDATES = (
    ".env.example",
    ".gitignore",
    ".python-version",
    "AGENTS.md",
    "README.md",
    "bootstrap_python.ps1",
    "lock_python_dependencies.ps1",
    "pi_runtime/package-lock.json",
    "pi_runtime/package.json",
    "quant_agents/__init__.py",
    "quant_agents/__main__.py",
    "quant_agents/python_runtime.py",
    "quant_agents/source_review.py",
    "quant_python.ps1",
    "quant.ps1",
    "requirements.in",
    "requirements.txt",
    "tools/build_python_lock.py",
)

_FORBIDDEN_PREFIXES = (
    ".cache/",
    ".git/",
    ".pi/git/",
    ".pi/npm/",
    ".tmp/",
    ".venv/",
    "build/",
    "dist/",
    "drill_reports/",
    "runs/",
    "scheduled_inputs/",
)
_FORBIDDEN_SEGMENTS = {"__pycache__", "node_modules"}
_FORBIDDEN_NAMES = {".env", "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}
_FORBIDDEN_EXTENSIONS = {
    ".7z",
    ".bin",
    ".crt",
    ".db",
    ".dll",
    ".exe",
    ".feather",
    ".gz",
    ".key",
    ".log",
    ".npy",
    ".npz",
    ".p12",
    ".parquet",
    ".pem",
    ".pickle",
    ".pkl",
    ".pfx",
    ".pyc",
    ".pyo",
    ".rar",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".zip",
}
_SUSPICIOUS_NAME = re.compile(
    r"(^|[_.-])(credential|password|private|secret|token)([_.-]|$)",
    re.IGNORECASE,
)
_PINNED_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*==[^\s\\]+"
)


class SourceCandidateError(RuntimeError):
    pass


def build_source_candidate_manifest(
    project_root: str | Path = PROJECT_ROOT,
    receipt_path: str | Path | None = None,
    output_path: str | Path | None = None,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    write: bool = True,
) -> dict[str, Any]:
    if max_file_bytes <= 0:
        raise ValueError("max_file_bytes must be positive")
    root = Path(project_root).resolve()
    target = (
        Path(output_path).resolve()
        if output_path
        else root / DEFAULT_OUTPUT_RELATIVE
    )
    if write:
        require_safe_generated_output_path(root, target)

    candidates = list_scan_candidates(root)
    normalized_candidates = [name.replace("\\", "/") for name in candidates]
    blockers: list[dict[str, Any]] = []
    review_flags: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    collision_index: dict[str, list[str]] = {}

    for relative in normalized_candidates:
        collision_key = unicodedata.normalize("NFC", relative).casefold()
        collision_index.setdefault(collision_key, []).append(relative)
    for colliding in collision_index.values():
        if len(colliding) > 1:
            blockers.append(
                _blocker(
                    "PORTABLE_PATH_COLLISION",
                    None,
                    "Case-insensitive or Unicode-normalized candidate paths collide.",
                    paths=sorted(colliding),
                )
            )

    for relative in normalized_candidates:
        row, row_blockers, row_flags = _inspect_candidate(
            root, relative, max_file_bytes
        )
        rows.append(row)
        blockers.extend(row_blockers)
        review_flags.extend(row_flags)

    candidate_set = set(normalized_candidates)
    for required in REQUIRED_CANDIDATES:
        if required not in candidate_set:
            blockers.append(
                _blocker(
                    "REQUIRED_SOURCE_MISSING",
                    required,
                    "A required baseline source or dependency-control file is missing.",
                )
            )

    blockers.extend(_inspect_python_dependency_contract(root, candidate_set))
    secret_gate = evaluate_secret_scan_receipt(
        receipt_path or Config.SECRET_SCAN_RECEIPT_PATH,
        root,
    )
    if secret_gate.get("ok") is not True:
        blockers.append(
            _blocker(
                "SECRET_SCAN_RECEIPT_INVALID",
                None,
                "The current candidate tree is not bound to a passed Secret scan receipt.",
                errors=list(secret_gate.get("errors", [])),
            )
        )

    file_hashes = {
        row["path"]: row["sha256"]
        for row in rows
        if isinstance(row.get("sha256"), str) and row.get("sha256")
    }
    candidate_files_sha256 = canonical_json_sha256(file_hashes)
    receipt_summary = dict(secret_gate.get("receipt_summary", {}))
    receipt_candidate_hash = receipt_summary.get("candidate_files_sha256")
    if (
        secret_gate.get("ok") is True
        and receipt_candidate_hash != candidate_files_sha256
    ):
        blockers.append(
            _blocker(
                "SECRET_SCAN_IDENTITY_MISMATCH",
                None,
                "The Secret scan receipt and source manifest identify different candidates.",
            )
        )

    category_counts = Counter(row["category"] for row in rows)
    extension_counts = Counter(row["extension"] or "<none>" for row in rows)
    source = collect_source_provenance(str(root))
    identity = {
        "schema_version": SOURCE_CANDIDATE_SCHEMA_VERSION,
        "policy_version": SOURCE_CANDIDATE_POLICY_VERSION,
        "max_file_bytes": max_file_bytes,
        "candidate_files_sha256": candidate_files_sha256,
        "files": rows,
        "secret_scan_receipt_sha256": receipt_summary.get("receipt_sha256"),
    }
    reviewable = not blockers
    manifest: dict[str, Any] = {
        "schema_version": SOURCE_CANDIDATE_SCHEMA_VERSION,
        "policy_version": SOURCE_CANDIDATE_POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_type": "PRE_COMMIT_SOURCE_CANDIDATE",
        "status": (
            "READY_FOR_HUMAN_FILE_REVIEW_NOT_AUTHORIZED"
            if reviewable
            else "BLOCKED"
        ),
        "ready_for_human_file_review": reviewable,
        "source_baseline_authorized": False,
        "source_release_ready": False,
        "human_review_required": True,
        "git_actions": {
            "git_add_performed": False,
            "commit_performed": False,
            "tag_performed": False,
            "remote_created": False,
        },
        "workspace": {
            "root": str(root),
            "head_commit": source.get("head_commit"),
            "tracked_file_count": source.get("tracked_file_count"),
            "changed_file_count": source.get("changed_file_count"),
            "untracked_file_count": source.get("untracked_file_count"),
            "release_ready": source.get("release_ready") is True,
            "reason": source.get("reason"),
        },
        "policy": {
            "max_file_bytes": max_file_bytes,
            "required_candidates": list(REQUIRED_CANDIDATES),
            "links_and_reparse_points_allowed": False,
            "binary_candidates_allowed": False,
            "generated_or_runtime_artifacts_allowed": False,
            "python_baseline": (
                "CPython 3.11 with hash-locked requirements.txt"
            ),
        },
        "summary": {
            "candidate_file_count": len(rows),
            "candidate_total_bytes": sum(
                int(row.get("bytes", 0)) for row in rows
            ),
            "category_counts": dict(sorted(category_counts.items())),
            "extension_counts": dict(sorted(extension_counts.items())),
            "blocker_count": len(blockers),
            "review_flag_count": len(review_flags),
        },
        "candidate_files_sha256": candidate_files_sha256,
        "manifest_sha256": canonical_json_sha256(identity),
        "secret_scan": {
            "ok": secret_gate.get("ok") is True,
            "receipt_summary": receipt_summary,
        },
        "blockers": blockers,
        "review_flags": review_flags,
        "files": rows,
        "next_actions": (
            [
                "COMPLETE_PER_FILE_HUMAN_REVIEW",
                "CREATE_REVIEWED_PRIVATE_COMMIT_AND_TAG",
                "PUSH_TO_APPROVED_PRIVATE_REMOTE",
                "RUN_CLEAN_CLONE_ACCEPTANCE",
            ]
            if reviewable
            else [
                "RESOLVE_ALL_SOURCE_CANDIDATE_BLOCKERS",
                "REISSUE_SECRET_SCAN_RECEIPT",
            ]
        ),
        "disclaimer": (
            "This pre-commit manifest does not stage, commit, approve, release, "
            "or authorize real data, model calls, trading, or real-capital actions."
        ),
    }
    if write:
        write_json_atomic(str(target), manifest)
    return manifest


def _inspect_candidate(
    root: Path, relative: str, max_file_bytes: int
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    path = PurePosixPath(relative)
    unsafe = path.is_absolute() or ".." in path.parts or not path.parts
    absolute = root.joinpath(*path.parts)
    extension = path.suffix.casefold()
    category = _category(relative, extension)
    row: dict[str, Any] = {
        "path": relative,
        "category": category,
        "extension": extension,
        "bytes": 0,
        "sha256": None,
        "binary": False,
        "link_or_reparse": False,
        "review_flags": [],
    }
    if unsafe:
        blockers.append(
            _blocker(
                "UNSAFE_CANDIDATE_PATH",
                relative,
                "Candidate path escapes the project root.",
            )
        )
        return row, blockers, flags
    if _is_link_or_reparse(absolute):
        row["link_or_reparse"] = True
        blockers.append(
            _blocker(
                "LINK_OR_REPARSE_CANDIDATE",
                relative,
                "Links and reparse points are not allowed in the source baseline.",
            )
        )
        return row, blockers, flags
    if not absolute.is_file():
        blockers.append(
            _blocker(
                "NON_REGULAR_CANDIDATE",
                relative,
                "Candidate is missing or is not a regular file.",
            )
        )
        return row, blockers, flags

    size = absolute.stat().st_size
    row["bytes"] = size
    row["sha256"] = sha256_file(str(absolute))
    with absolute.open("rb") as file:
        sample = file.read(8192)
    binary = b"\x00" in sample
    row["binary"] = binary
    if size > max_file_bytes:
        blockers.append(
            _blocker(
                "CANDIDATE_TOO_LARGE",
                relative,
                f"Candidate exceeds the {max_file_bytes}-byte policy limit.",
                bytes=size,
            )
        )
    if binary:
        blockers.append(
            _blocker(
                "BINARY_CANDIDATE",
                relative,
                "Binary content is not allowed in the reviewed source baseline.",
            )
        )

    lower = relative.casefold()
    if _forbidden_path(path, lower, extension):
        blockers.append(
            _blocker(
                "FORBIDDEN_SOURCE_ARTIFACT",
                relative,
                "Generated, runtime, credential, archive, database, or executable artifacts are forbidden.",
            )
        )
    if _SUSPICIOUS_NAME.search(path.name):
        flag = {
            "code": "SUSPICIOUS_FILENAME_REQUIRES_REVIEW",
            "path": relative,
        }
        flags.append(flag)
        row["review_flags"].append(flag["code"])
    if ".example." in lower or lower.endswith(".example"):
        flag = {
            "code": "EXAMPLE_MUST_NOT_BE_APPROVAL_EVIDENCE",
            "path": relative,
        }
        flags.append(flag)
        row["review_flags"].append(flag["code"])
    return row, blockers, flags


def _inspect_python_dependency_contract(
    root: Path, candidates: set[str]
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    version_path = root / ".python-version"
    if (
        ".python-version" in candidates
        and version_path.read_text(encoding="utf-8").strip() != "3.11"
    ):
        blockers.append(
            _blocker(
                "PYTHON_BASELINE_INVALID",
                ".python-version",
                "The supported source baseline must be CPython 3.11.",
            )
        )

    direct_path = root / "requirements.in"
    if "requirements.in" in candidates:
        direct_lines = _requirement_lines(
            direct_path.read_text(encoding="utf-8")
        )
        unpinned = [line for line in direct_lines if "==" not in line]
        if not direct_lines or unpinned:
            blockers.append(
                _blocker(
                    "DIRECT_DEPENDENCIES_NOT_PINNED",
                    "requirements.in",
                    "Every reviewed direct dependency must use an exact == pin.",
                    unpinned_count=len(unpinned),
                )
            )

    lock_path = root / "requirements.txt"
    if "requirements.txt" in candidates:
        lock_text = lock_path.read_text(encoding="utf-8")
        pins = [
            line
            for line in lock_text.splitlines()
            if _PINNED_REQUIREMENT.match(line)
        ]
        hash_count = lock_text.count("--hash=sha256:")
        if len(pins) < 3 or hash_count < len(pins):
            blockers.append(
                _blocker(
                    "PYTHON_DEPENDENCY_LOCK_INVALID",
                    "requirements.txt",
                    "The Python lock must contain exact transitive pins with SHA-256 hashes.",
                    pinned_requirement_count=len(pins),
                    hash_count=hash_count,
                )
            )
        if "--index-url" in lock_text or "--trusted-host" in lock_text:
            blockers.append(
                _blocker(
                    "DEPENDENCY_LOCK_EMBEDS_INDEX",
                    "requirements.txt",
                    "The committed lock must not embed a machine-specific package index or trusted host.",
                )
            )
    return blockers


def _requirement_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]


def _forbidden_path(
    path: PurePosixPath, lower: str, extension: str
) -> bool:
    if lower in _FORBIDDEN_NAMES or path.name.casefold() in _FORBIDDEN_NAMES:
        return True
    if any(lower.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES):
        return True
    if any(part.casefold() in _FORBIDDEN_SEGMENTS for part in path.parts):
        return True
    return extension in _FORBIDDEN_EXTENSIONS


def _category(relative: str, extension: str) -> str:
    lower = relative.casefold()
    if lower.startswith("tests/"):
        return "automated_test"
    if lower.startswith("quant_agents/"):
        return "python_control_plane"
    if lower.startswith(".pi/skills/"):
        return "operator_skill"
    if lower.startswith(".pi/extensions/"):
        return "operator_extension"
    if lower.startswith("governance/"):
        return "governance"
    if lower.startswith("pi_runtime/"):
        return "runtime_lock"
    if extension == ".ps1":
        return "windows_operations"
    if extension == ".md":
        return "documentation"
    return "project_configuration"


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(
            attributes
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
    except OSError:
        return False


def require_safe_generated_output_path(
    project_root: str | Path, target_path: str | Path
) -> None:
    root = Path(project_root).resolve()
    target = Path(target_path).resolve()
    try:
        relative = target.relative_to(root)
    except ValueError:
        return
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "check-ignore",
            "--quiet",
            "--no-index",
            "--",
            relative.as_posix(),
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise SourceCandidateError(
            "source-candidate output inside the project must be Git-ignored "
            "to avoid self-reference"
        )


def _blocker(
    code: str, path: str | None, summary: str, **details: Any
) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "summary": summary}
    if path:
        result["path"] = path
    if details:
        result["details"] = details
    return result
