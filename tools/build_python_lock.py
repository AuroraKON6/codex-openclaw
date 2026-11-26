from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from packaging.utils import canonicalize_name, parse_wheel_filename


def locked_pins(lock_path: Path) -> list[tuple[str, str]]:
    """Canonical (name, version) pairs of a committed lock, in file order."""

    pins = []
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s\\]+)", line)
        if match:
            pins.append((canonicalize_name(match.group(1)), match.group(2)))
    return pins


def build_lock(
    resolved_path: Path,
    wheelhouse: Path,
    output_path: Path,
    platform_label: str = "Windows CPython 3.11",
    origin_note: str = (
        "Resolved with pip-tools 7.6.1 and verified from one selected wheel per pin."
    ),
) -> dict:
    wheels = {}
    for path in sorted(wheelhouse.glob("*.whl")):
        name, version, _build, _tags = parse_wheel_filename(path.name)
        key = canonicalize_name(name)
        if key in wheels:
            raise ValueError(f"duplicate wheel for {key}")
        wheels[key] = {
            "version": str(version),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    pins = []
    for line in resolved_path.read_text(encoding="utf-8").splitlines():
        match = re.match(
            r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s]+)$",
            line,
        )
        if match:
            pins.append((canonicalize_name(match.group(1)), match.group(2)))
    if len(pins) != len(wheels):
        raise ValueError(
            f"pin/wheel mismatch: {len(pins)} pins, {len(wheels)} wheels"
        )

    lines = [
        f"# Hash-locked {platform_label} runtime dependencies.",
        f"# {origin_note}",
        "# Regenerate through the reviewed lock workflow; do not edit pins or hashes manually.",
    ]
    for name, version in pins:
        wheel = wheels.get(name)
        if not wheel:
            raise ValueError(f"wheel is missing for {name}")
        if wheel["version"] != version:
            raise ValueError(
                f"version mismatch for {name}: {version} != {wheel['version']}"
            )
        lines.extend(
            [
                f"{name}=={version} \\",
                f"    --hash=sha256:{wheel['sha256']}",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "pin_count": len(pins),
        "wheel_count": len(wheels),
        "lock_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "output": str(output_path.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved", required=True)
    parser.add_argument("--wheelhouse", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--platform-label",
        default="Windows CPython 3.11",
        help="wheel platform recorded in the lock header, e.g. 'macOS arm64 CPython 3.11'",
    )
    parser.add_argument(
        "--origin-note",
        default=(
            "Resolved with pip-tools 7.6.1 and verified from one selected wheel per pin."
        ),
        help="reviewed provenance sentence recorded in the lock header",
    )
    args = parser.parse_args()
    result = build_lock(
        Path(args.resolved),
        Path(args.wheelhouse),
        Path(args.output),
        platform_label=args.platform_label,
        origin_note=args.origin_note,
    )
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
