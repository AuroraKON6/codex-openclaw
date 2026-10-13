from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .pi_client import PI_SECURITY_FLAGS


DEFAULT_SKILLS_ROOT = PROJECT_ROOT / ".pi" / "skills"
DEFAULT_LOCK_PATH = PROJECT_ROOT / "governance" / "pi_skills.lock.json"
ALLOWED_FILE_SUFFIXES = {".json", ".md", ".txt", ".yaml", ".yml"}
FORBIDDEN_EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cjs",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".jar",
    ".js",
    ".mjs",
    ".ps1",
    ".py",
    ".sh",
    ".ts",
    ".wasm",
}
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & 0x400)


def _parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must begin with YAML frontmatter")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _collect_files(skill_dir: Path) -> tuple[dict[str, str], list[str]]:
    files: dict[str, str] = {}
    link_errors: list[str] = []
    for directory, dirnames, filenames in os.walk(skill_dir, followlinks=False):
        directory_path = Path(directory)
        safe_dirs = []
        for dirname in dirnames:
            child = directory_path / dirname
            if _is_link_or_reparse(child):
                link_errors.append(str(child))
            else:
                safe_dirs.append(dirname)
        dirnames[:] = safe_dirs
        for filename in filenames:
            path = directory_path / filename
            if _is_link_or_reparse(path):
                link_errors.append(str(path))
                continue
            relative = path.relative_to(skill_dir).as_posix()
            files[relative] = sha256_file(path)
    return dict(sorted(files.items())), link_errors


def audit_project_skills(
    skills_root: str | Path = DEFAULT_SKILLS_ROOT,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
) -> dict[str, Any]:
    root = Path(skills_root).resolve()
    lock_file = Path(lock_path).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        errors.append(f"Skills root does not exist: {root}")
    if not lock_file.is_file():
        errors.append(f"Skills lock does not exist: {lock_file}")
    if errors:
        return _audit_result(root, lock_file, [], errors, warnings)

    try:
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot parse skills lock: {exc}")
        return _audit_result(root, lock_file, [], errors, warnings)

    if lock.get("schema_version") != 1:
        errors.append("Skills lock schema_version must be 1")
    policy = lock.get("policy") if isinstance(lock.get("policy"), dict) else {}
    if policy.get("production_skills_enabled") is not False:
        errors.append("Production skills must remain disabled")
    if policy.get("allow_executable_skill_files") is not False:
        errors.append("Executable skill files must remain disallowed")
    if policy.get("required_pi_flag") != "--no-skills":
        errors.append("Skills lock must require the --no-skills production flag")
    if "--no-skills" not in PI_SECURITY_FLAGS:
        errors.append("Pi production command no longer contains --no-skills")

    locked_entries = lock.get("skills")
    if not isinstance(locked_entries, list):
        errors.append("Skills lock must contain a skills array")
        locked_entries = []
    locked_by_name: dict[str, dict[str, Any]] = {}
    for entry in locked_entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            errors.append("Every locked skill must have a string name")
            continue
        name = entry["name"]
        if name in locked_by_name:
            errors.append(f"Duplicate locked skill: {name}")
            continue
        locked_by_name[name] = entry

    actual_directories = sorted(
        path for path in root.iterdir() if path.is_dir() and not _is_link_or_reparse(path)
    )
    linked_directories = sorted(
        path for path in root.iterdir() if path.is_dir() and _is_link_or_reparse(path)
    )
    for path in linked_directories:
        errors.append(f"Linked or reparse-point skill directory is forbidden: {path}")

    inventory: list[dict[str, Any]] = []
    actual_names: set[str] = set()
    for skill_dir in actual_directories:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"Missing SKILL.md: {skill_dir}")
            continue
        try:
            frontmatter = _parse_frontmatter(skill_md)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"Invalid {skill_md}: {exc}")
            continue
        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")
        if not NAME_PATTERN.fullmatch(name):
            errors.append(f"Invalid skill name in {skill_md}: {name or 'missing'}")
        if name != skill_dir.name:
            errors.append(f"Skill name must match directory: {skill_dir.name} != {name}")
        if not description or len(description) > 1024:
            errors.append(f"Skill description is missing or too long: {skill_md}")
        if name in actual_names:
            errors.append(f"Duplicate discovered skill name: {name}")
        actual_names.add(name)

        files, link_errors = _collect_files(skill_dir)
        for path in link_errors:
            errors.append(f"Linked or reparse-point skill resource is forbidden: {path}")
        for relative in files:
            suffix = Path(relative).suffix.lower()
            if suffix in FORBIDDEN_EXECUTABLE_SUFFIXES:
                errors.append(f"Executable skill resource is forbidden: {name}/{relative}")
            elif suffix not in ALLOWED_FILE_SUFFIXES:
                errors.append(f"Unapproved skill resource type: {name}/{relative}")

        locked = locked_by_name.get(name)
        if locked is None:
            errors.append(f"Discovered skill is not locked: {name}")
        else:
            expected_path = f".pi/skills/{name}"
            if locked.get("path") != expected_path:
                errors.append(f"Locked path mismatch for {name}")
            if locked.get("production_enabled") is not False:
                errors.append(f"Production enablement is forbidden for {name}")
            expected_files = locked.get("files")
            if not isinstance(expected_files, dict):
                errors.append(f"Locked file inventory is missing for {name}")
            elif expected_files != files:
                missing = sorted(set(expected_files) - set(files))
                extra = sorted(set(files) - set(expected_files))
                changed = sorted(
                    path
                    for path in set(files) & set(expected_files)
                    if files[path] != expected_files[path]
                )
                errors.append(
                    f"Skill inventory drift for {name}: missing={missing}, extra={extra}, changed={changed}"
                )
            for source in locked.get("upstream_references", []):
                if not isinstance(source, dict):
                    errors.append(f"Invalid upstream reference for {name}")
                    continue
                commit = str(source.get("commit", ""))
                url = str(source.get("url", ""))
                if not url.startswith("https://github.com/") or not COMMIT_PATTERN.fullmatch(commit):
                    errors.append(f"Unpinned upstream reference for {name}")

        inventory.append(
            {
                "name": name,
                "path": str(skill_dir),
                "file_count": len(files),
                "files": files,
            }
        )

    for name in sorted(set(locked_by_name) - actual_names):
        errors.append(f"Locked skill is missing from disk: {name}")

    return _audit_result(root, lock_file, inventory, errors, warnings)


def _audit_result(
    root: Path,
    lock_file: Path,
    inventory: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "skills_root": str(root),
        "lock_path": str(lock_file),
        "skills_count": len(inventory),
        "locked_file_count": sum(item["file_count"] for item in inventory),
        "production_skills_enabled": False,
        "production_runtime_flag_verified": "--no-skills" in PI_SECURITY_FLAGS,
        "skills": inventory,
        "errors": errors,
        "warnings": warnings,
        "disclaimer": "Operator skills only; not market evidence or real trading advice.",
    }
