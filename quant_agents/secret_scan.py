"""Read-only secret scanning for the source release gate.

The scanner enumerates every file a commit would include (tracked plus
not-ignored untracked candidates), applies fixed regex rules, and records a
receipt. Findings store only the candidate path, line number, and rule
identifier -- never the matched secret value. The receipt is bound to the
exact candidate content hashes, so any source change invalidates it and the
gate requires a fresh scan.

False-positive handling: an operator reviews the reported file and line,
removes the secret or adjusts the versioned rules, and re-runs the scan.
There is deliberately no per-finding ignore mechanism that would allow
blanket suppression.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import canonical_json_sha256, sha256_file, write_json_atomic
from .config import Config, PROJECT_ROOT

SCAN_SCHEMA_VERSION = 1
SCAN_RULES_VERSION = "2026-08-29.1"
DEFAULT_RECEIPT_PATH = PROJECT_ROOT / ".cache" / "secret-scan" / "receipt.json"

# Per-occurrence human-review marker. A finding on a line carrying this
# marker is recorded as reviewed=true and no longer blocks the gate. There
# is deliberately no path-level or global ignore: every accepted occurrence
# stays visible in the receipt.
REVIEW_MARKER = "quant-secret-scan-allow"

_SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("bearer_style_api_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{32,}\b")),
    (
        "jwt_token",
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
        ),
    ),
    (
        "tushare_token_assignment",
        re.compile(r"TUSHARE_TOKEN\s*[:=]\s*['\"]?[0-9A-Za-z]{16,}"),
    ),
    (
        "deepseek_key_assignment",
        re.compile(r"DEEPSEEK_API_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    ),
)


class SecretScanError(RuntimeError):
    pass


def list_scan_candidates(project_root: Path = PROJECT_ROOT) -> list[str]:
    """List tracked plus not-ignored untracked files (what a commit would include)."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode != 0:
        raise SecretScanError(
            "git candidate enumeration failed: " + (result.stderr or "").strip()
        )
    return sorted(name for name in result.stdout.split("\0") if name)


def scan_candidate_files(
    candidates: list[str], project_root: Path = PROJECT_ROOT
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Scan candidates and return (findings, per-file SHA-256 map).

    Findings never contain matched secret material -- only path, line, rule,
    and whether a human marked the occurrence as a reviewed test fixture.
    """
    findings: list[dict[str, Any]] = []
    file_hashes: dict[str, str] = {}
    for relative in candidates:
        absolute = project_root / relative
        try:
            data = absolute.read_bytes()
        except OSError as exc:
            raise SecretScanError(f"cannot read candidate {relative}: {exc}") from exc
        file_hashes[relative.replace("\\", "/")] = sha256_file(absolute)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        lines = text.splitlines()
        for rule_id, pattern in _SECRET_RULES:
            for match in pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                line_text = lines[line_number - 1] if line_number <= len(lines) else ""
                findings.append(
                    {
                        "file": relative.replace("\\", "/"),
                        "line": line_number,
                        "rule": rule_id,
                        "reviewed": REVIEW_MARKER in line_text,
                    }
                )
    return findings, file_hashes


def build_receipt_for_candidates(
    candidates: list[str],
    project_root: Path,
    output_path: str | Path | None,
) -> dict[str, Any]:
    findings, file_hashes = scan_candidate_files(candidates, project_root)
    unreviewed = sum(1 for finding in findings if not finding.get("reviewed"))
    receipt: dict[str, Any] = {
        "schema_version": SCAN_SCHEMA_VERSION,
        "rules_version": SCAN_RULES_VERSION,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "candidate_file_count": len(candidates),
        "candidate_files_sha256": canonical_json_sha256(file_hashes),
        "finding_count": len(findings),
        "unreviewed_finding_count": unreviewed,
        "findings": findings,
        "status": "passed" if unreviewed == 0 else "failed",
    }
    receipt["receipt_sha256"] = canonical_json_sha256(receipt)
    target = Path(output_path or Config.SECRET_SCAN_RECEIPT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(target, receipt)
    return receipt


def build_secret_scan_receipt(
    output_path: str | Path | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    candidates = list_scan_candidates(project_root)
    return build_receipt_for_candidates(candidates, project_root, output_path)


def evaluate_receipt_against_scan(
    receipt: dict[str, Any], findings: list[dict[str, Any]], file_hashes: dict[str, str]
) -> dict[str, Any]:
    """Re-verify a stored receipt against a fresh scan of the same tree."""
    errors: list[str] = []
    expected_hash = receipt.get("receipt_sha256")
    recomputed = dict(receipt)
    recomputed.pop("receipt_sha256", None)
    if expected_hash != canonical_json_sha256(recomputed):
        errors.append("secret scan receipt hash does not match its contents")
    if receipt.get("schema_version") != SCAN_SCHEMA_VERSION:
        errors.append("secret scan receipt schema version is unexpected")
    if receipt.get("rules_version") != SCAN_RULES_VERSION:
        errors.append(
            "secret scan receipt was produced by different rules; re-run secret-scan"
        )
    if receipt.get("candidate_files_sha256") != canonical_json_sha256(file_hashes):
        errors.append("candidate sources changed after the secret scan receipt")
    if receipt.get("findings") != findings:
        errors.append("recorded findings do not match a fresh scan")
    if receipt.get("status") != "passed" or receipt.get(
        "unreviewed_finding_count", 0
    ) != 0:
        unreviewed_rules = sorted(
            {
                finding["rule"]
                for finding in receipt.get("findings", [])
                if not finding.get("reviewed")
            }
        )
        errors.append(
            "secret scan reported unreviewed findings in rules "
            + ", ".join(unreviewed_rules)
            if unreviewed_rules
            else "secret scan receipt is not in passed state"
        )
    return {
        "ok": not errors,
        "errors": errors,
        "receipt_summary": {
            "rules_version": receipt.get("rules_version"),
            "candidate_file_count": receipt.get("candidate_file_count"),
            "candidate_files_sha256": receipt.get("candidate_files_sha256"),
            "finding_count": receipt.get("finding_count"),
            "unreviewed_finding_count": receipt.get("unreviewed_finding_count"),
            "scanned_at": receipt.get("scanned_at"),
            "receipt_sha256": receipt.get("receipt_sha256"),
        },
    }


def evaluate_secret_scan_receipt(
    receipt_path: str | Path | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    path = Path(receipt_path or Config.SECRET_SCAN_RECEIPT_PATH)
    if not path.is_file():
        return {
            "ok": False,
            "errors": [
                "secret scan receipt is missing; run "
                "`python -m quant_agents secret-scan` after reviewing the tree"
            ],
            "receipt_summary": {},
        }
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "errors": [f"secret scan receipt is unreadable: {exc}"],
            "receipt_summary": {},
        }
    if not isinstance(receipt, dict):
        return {
            "ok": False,
            "errors": ["secret scan receipt is not a JSON object"],
            "receipt_summary": {},
        }
    candidates = list_scan_candidates(project_root)
    findings, file_hashes = scan_candidate_files(candidates, project_root)
    return evaluate_receipt_against_scan(receipt, findings, file_hashes)
