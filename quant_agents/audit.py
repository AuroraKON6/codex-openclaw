from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: str, payload: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
            dir=directory,
        ) as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, default=str)
            file.write("\n")
            temporary_path = file.name
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def collect_source_provenance(workspace_root: str | None = None) -> dict[str, Any]:
    root = os.path.abspath(
        workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    base = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": root,
        "repository_available": False,
        "repository_root": None,
        "head_commit": None,
        "branch": None,
        "dirty": True,
        "tracked_file_count": 0,
        "changed_file_count": 0,
        "untracked_file_count": 0,
        "status_sha256": None,
        "release_ready": False,
        "reason": "Git repository could not be inspected",
    }
    try:
        repository = _run_git(root, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError) as exc:
        base["reason"] = f"Git inspection failed: {exc}"
        return base
    if repository.returncode != 0:
        base["reason"] = "workspace is not inside an inspectable Git repository"
        return base

    repository_root = repository.stdout.strip()
    head = _run_git(root, "rev-parse", "HEAD")
    branch = _run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    status = _run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
    tracked = _run_git(root, "ls-files")
    status_text = status.stdout.replace("\r\n", "\n")
    status_lines = [line for line in status_text.splitlines() if line]
    tracked_lines = [line for line in tracked.stdout.splitlines() if line]
    untracked_count = sum(line.startswith("??") for line in status_lines)
    changed_count = len(status_lines) - untracked_count
    head_commit = head.stdout.strip() if head.returncode == 0 else None
    if head_commit and not re.fullmatch(r"[0-9a-fA-F]{40,64}", head_commit):
        head_commit = None
    reasons = []
    if not head_commit:
        reasons.append("repository has no committed HEAD")
    if not tracked_lines:
        reasons.append("repository has no tracked source files")
    if status_lines:
        reasons.append(
            f"workspace is dirty ({changed_count} changed, {untracked_count} untracked)"
        )
    if status.returncode != 0 or tracked.returncode != 0:
        reasons.append("Git status or tracked-file inventory failed")

    base.update(
        {
            "repository_available": True,
            "repository_root": repository_root,
            "head_commit": head_commit,
            "branch": branch.stdout.strip() if branch.returncode == 0 else None,
            "dirty": bool(status_lines) or status.returncode != 0,
            "tracked_file_count": len(tracked_lines),
            "changed_file_count": changed_count,
            "untracked_file_count": untracked_count,
            "status_sha256": hashlib.sha256(status_text.encode("utf-8")).hexdigest(),
            "release_ready": not reasons,
            "reason": "; ".join(reasons) if reasons else "clean committed source baseline",
        }
    )
    return base


def _run_git(root: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", root, *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )


def build_file_manifest(
    root_dir: str,
    relative_paths: list[str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = []
    for relative_path in sorted(set(relative_paths)):
        absolute_path = os.path.join(root_dir, relative_path)
        if not os.path.isfile(absolute_path):
            continue
        files.append(
            {
                "path": relative_path.replace("\\", "/"),
                "bytes": os.path.getsize(absolute_path),
                "sha256": sha256_file(absolute_path),
            }
        )
    identity = {"files": files, "metadata": metadata or {}}
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_id": canonical_json_sha256(identity),
        "files": files,
        "metadata": metadata or {},
    }
