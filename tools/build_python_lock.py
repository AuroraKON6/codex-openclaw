from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from packaging.utils import canonicalize_name, parse_wheel_filename


def build_lock(resolved_path: Path, wheelhouse: Path, output_path: Path) -> dict:
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
        "# Hash-locked Windows CPython 3.11 runtime dependencies.",
        "# Resolved with pip-tools 7.6.1 and verified from one selected wheel per pin.",
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
    args = parser.parse_args()
    result = build_lock(
        Path(args.resolved),
        Path(args.wheelhouse),
        Path(args.output),
    )
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
