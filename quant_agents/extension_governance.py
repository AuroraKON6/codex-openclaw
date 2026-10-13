from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .pi_client import PI_SECURITY_FLAGS
from .skill_governance import sha256_file


DEFAULT_EXTENSIONS_ROOT = PROJECT_ROOT / ".pi" / "extensions"
DEFAULT_LOCK_PATH = PROJECT_ROOT / "governance" / "pi_extensions.lock.json"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_SOURCE_TOKENS = (
    "node:child_process",
    "node:http",
    "node:https",
    "node:net",
    "node:tls",
    "fetch(",
    "pi.exec(",
    "process.env",
    "registerTool(",
    "registerProvider(",
    "writeFile",
    "appendFile",
    "createWriteStream",
    "rmSync",
    "unlink",
    "rename",
    "chmod",
    "chown",
)


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & 0x400)


def audit_project_extensions(
    extensions_root: str | Path = DEFAULT_EXTENSIONS_ROOT,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> dict[str, Any]:
    root = Path(extensions_root).resolve()
    lock_file = Path(lock_path).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    inventory: list[dict[str, Any]] = []

    if not root.is_dir():
        errors.append(f"Extensions root does not exist: {root}")
    if not lock_file.is_file():
        errors.append(f"Extensions lock does not exist: {lock_file}")
    if errors:
        return _result(root, lock_file, inventory, errors, warnings)

    try:
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot parse extensions lock: {exc}")
        return _result(root, lock_file, inventory, errors, warnings)

    if lock.get("schema_version") != 1:
        errors.append("Extensions lock schema_version must be 1")
    policy = lock.get("policy") if isinstance(lock.get("policy"), dict) else {}
    if policy.get("production_extensions_enabled") is not False:
        errors.append("Production extensions must remain disabled")
    if policy.get("required_pi_flag") != "--no-extensions":
        errors.append("Extensions lock must require --no-extensions")
    if policy.get("third_party_packages_installed") is not False:
        errors.append("Third-party Pi packages must not be installed in this workspace")
    for capability in ("network_access_allowed", "subprocess_access_allowed", "write_access_allowed"):
        if policy.get(capability) is not False:
            errors.append(f"Operator extension policy must set {capability}=false")
    if "--no-extensions" not in PI_SECURITY_FLAGS:
        errors.append("Pi production command no longer contains --no-extensions")

    locked_entries = lock.get("extensions")
    if not isinstance(locked_entries, list):
        errors.append("Extensions lock must contain an extensions array")
        locked_entries = []
    locked_by_path: dict[str, dict[str, Any]] = {}
    for entry in locked_entries:
        if not isinstance(entry, dict):
            errors.append("Every extension lock entry must be an object")
            continue
        name = str(entry.get("name", ""))
        relative_path = str(entry.get("path", ""))
        if not NAME_PATTERN.fullmatch(name):
            errors.append(f"Invalid extension name: {name or 'missing'}")
        if not relative_path.startswith(".pi/extensions/") or not relative_path.endswith(".mjs"):
            errors.append(f"Invalid extension path: {relative_path or 'missing'}")
        if relative_path in locked_by_path:
            errors.append(f"Duplicate locked extension path: {relative_path}")
        locked_by_path[relative_path] = entry
        if entry.get("production_enabled") is not False:
            errors.append(f"Production enablement is forbidden for extension {name}")
        if entry.get("operator_load_mode") != "explicit_cli_only":
            errors.append(f"Extension {name} must use explicit_cli_only loading")
        for source in entry.get("upstream_references", []):
            if not isinstance(source, dict):
                errors.append(f"Invalid upstream reference for extension {name}")
                continue
            if not str(source.get("url", "")).startswith("https://github.com/"):
                errors.append(f"Invalid upstream URL for extension {name}")
            if not COMMIT_PATTERN.fullmatch(str(source.get("commit", ""))):
                errors.append(f"Unpinned upstream reference for extension {name}")

    actual_paths: set[str] = set()
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        safe_dirs: list[str] = []
        for dirname in dirnames:
            child = directory_path / dirname
            if _is_link_or_reparse(child):
                errors.append(f"Linked extension directory is forbidden: {child}")
            else:
                safe_dirs.append(dirname)
        dirnames[:] = safe_dirs
        for filename in filenames:
            path = directory_path / filename
            if _is_link_or_reparse(path):
                errors.append(f"Linked extension file is forbidden: {path}")
                continue
            locked_path = f".pi/extensions/{path.relative_to(root).as_posix()}"
            actual_paths.add(locked_path)
            if path.suffix.lower() != ".mjs":
                errors.append(f"Only dependency-free .mjs operator extensions are allowed: {path}")
                continue
            try:
                source_text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"Cannot read extension {path}: {exc}")
                continue
            found_tokens = sorted(token for token in FORBIDDEN_SOURCE_TOKENS if token in source_text)
            if found_tokens:
                errors.append(f"Forbidden extension capabilities in {locked_path}: {found_tokens}")
            locked = locked_by_path.get(locked_path)
            digest = sha256_file(path)
            if locked is None:
                errors.append(f"Discovered extension is not locked: {locked_path}")
            elif locked.get("sha256") != digest:
                errors.append(f"Extension hash drift: {locked_path}")
            inventory.append(
                {
                    "name": locked.get("name") if locked else path.stem,
                    "path": locked_path,
                    "sha256": digest,
                }
            )

    for missing in sorted(set(locked_by_path) - actual_paths):
        errors.append(f"Locked extension is missing from disk: {missing}")

    return _result(root, lock_file, inventory, errors, warnings)


def _result(
    root: Path,
    lock_file: Path,
    inventory: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "extensions_root": str(root),
        "lock_path": str(lock_file),
        "extension_count": len(inventory),
        "production_extensions_enabled": False,
        "production_runtime_flag_verified": "--no-extensions" in PI_SECURITY_FLAGS,
        "extensions": inventory,
        "errors": errors,
        "warnings": warnings,
        "disclaimer": "Interactive operator extension only; no market analysis or trading advice.",
    }
