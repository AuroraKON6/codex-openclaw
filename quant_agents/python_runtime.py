from __future__ import annotations

import hashlib
import os
import platform
import re
import site
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT


PYTHON_RUNTIME_SCHEMA_VERSION = 1
EXPECTED_PYTHON_MINOR = "3.11"
EXPECTED_IMPLEMENTATION = "CPython"
EXPECTED_PLATFORM = "Windows"
BOOTSTRAP_DISTRIBUTIONS = {"pip", "setuptools", "wheel"}
_PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\?$")
_HASH_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})$")


def normalize_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def parse_locked_requirements(path: str | Path) -> dict[str, Any]:
    lock_path = Path(path)
    packages: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    current_name: str | None = None

    try:
        lines = lock_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {"packages": {}, "errors": [f"requirements lock is unavailable: {exc}"]}

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pin = _PIN_PATTERN.fullmatch(line)
        if pin:
            name = normalize_distribution_name(pin.group(1))
            if name in packages:
                errors.append(f"duplicate locked distribution at line {line_number}: {name}")
            packages[name] = {
                "name": name,
                "version": pin.group(2),
                "hashes": [],
            }
            current_name = name
            continue
        wheel_hash = _HASH_PATTERN.fullmatch(line)
        if wheel_hash and current_name:
            packages[current_name]["hashes"].append(wheel_hash.group(1))
            continue
        errors.append(f"unsupported requirements lock entry at line {line_number}")
        current_name = None

    if not packages:
        errors.append("requirements lock contains no exact package pins")
    for name, package in packages.items():
        if not package["hashes"]:
            errors.append(f"locked distribution has no SHA-256 hash: {name}")
    return {"packages": packages, "errors": errors}


def inspect_python_runtime(project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    root = Path(project_root).resolve()
    lock_path = root / "requirements.txt"
    version_path = root / ".python-version"
    expected_venv = root / ".venv"
    expected_executable = expected_venv / "Scripts" / "python.exe"
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    try:
        configured_minor = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        configured_minor = ""
        errors.append(f".python-version is unavailable: {exc}")

    actual_version = platform.python_version()
    actual_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    actual_implementation = platform.python_implementation()
    actual_platform = platform.system()
    actual_executable = Path(sys.executable).resolve()
    actual_prefix = Path(sys.prefix).resolve()

    _record_check(
        checks,
        errors,
        "python_version",
        configured_minor == EXPECTED_PYTHON_MINOR
        and actual_minor == EXPECTED_PYTHON_MINOR,
        (
            f"expected {EXPECTED_PYTHON_MINOR}; configured "
            f"{configured_minor or 'missing'}; running {actual_version}"
        ),
    )
    _record_check(
        checks,
        errors,
        "python_implementation",
        actual_implementation == EXPECTED_IMPLEMENTATION,
        f"expected {EXPECTED_IMPLEMENTATION}; running {actual_implementation}",
    )
    _record_check(
        checks,
        errors,
        "operating_system",
        actual_platform == EXPECTED_PLATFORM,
        f"expected {EXPECTED_PLATFORM}; running {actual_platform}",
    )
    _record_check(
        checks,
        errors,
        "project_venv",
        _same_path(actual_executable, expected_executable)
        and _same_path(actual_prefix, expected_venv)
        and sys.prefix != sys.base_prefix,
        f"expected executable {expected_executable}; running {actual_executable}",
    )
    _record_check(
        checks,
        errors,
        "user_site_disabled",
        site.ENABLE_USER_SITE is False,
        f"site.ENABLE_USER_SITE={site.ENABLE_USER_SITE!r}",
    )

    lock = parse_locked_requirements(lock_path)
    errors.extend(lock["errors"])
    locked_packages = lock["packages"]
    installed_packages = _installed_distributions()
    mismatches = []
    for name, package in sorted(locked_packages.items()):
        installed_version = installed_packages.get(name)
        if installed_version != package["version"]:
            mismatches.append(
                {
                    "name": name,
                    "expected": package["version"],
                    "installed": installed_version,
                }
            )
    unexpected = sorted(
        name
        for name in installed_packages
        if name not in locked_packages and name not in BOOTSTRAP_DISTRIBUTIONS
    )
    package_contract_ok = not lock["errors"] and not mismatches and not unexpected
    _record_check(
        checks,
        errors,
        "locked_distributions",
        package_contract_ok,
        (
            f"locked={len(locked_packages)}, mismatched={len(mismatches)}, "
            f"unexpected={len(unexpected)}"
        ),
    )

    lock_sha256 = _sha256_optional(lock_path)
    return {
        "schema_version": PYTHON_RUNTIME_SCHEMA_VERSION,
        "ok": not errors,
        "target": "windows-cpython-3.11-project-venv",
        "project_root": str(root),
        "expected_executable": str(expected_executable),
        "executable": str(actual_executable),
        "expected_python_minor": EXPECTED_PYTHON_MINOR,
        "configured_python_minor": configured_minor or None,
        "python_version": actual_version,
        "implementation": actual_implementation,
        "platform": actual_platform,
        "venv_prefix": str(actual_prefix),
        "user_site_enabled": site.ENABLE_USER_SITE,
        "requirements_lock": str(lock_path),
        "requirements_lock_sha256": lock_sha256,
        "locked_package_count": len(locked_packages),
        "installed_distribution_count": len(installed_packages),
        "package_mismatches": mismatches,
        "unexpected_distributions": unexpected,
        "bootstrap_distributions": sorted(
            name for name in installed_packages if name in BOOTSTRAP_DISTRIBUTIONS
        ),
        "checks": checks,
        "errors": list(dict.fromkeys(errors)),
        "network_calls_performed": False,
        "workspace_mutations_performed": False,
    }


def _installed_distributions() -> dict[str, str]:
    installed: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        installed[normalize_distribution_name(str(name))] = distribution.version
    return installed


def _record_check(
    checks: list[dict[str, Any]],
    errors: list[str],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append({"name": name, "status": "passed" if passed else "failed", "detail": detail})
    if not passed:
        errors.append(f"{name}: {detail}")


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
        os.path.realpath(right)
    )


def _sha256_optional(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None
