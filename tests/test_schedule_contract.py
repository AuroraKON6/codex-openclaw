"""Cross-script contract tests for the deployment-authorization lifecycle.

install_quant_schedule.ps1 writes the schema-3 authorization,
run_daily_research.ps1 enforces it at execution time, and
check_quant_schedule.ps1 re-verifies it plus the bound evidence. These tests
parse the three scripts so the contract cannot silently drift again (the
original schema 2/3 split was invisible to the Python suite).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SCHEMA_VERSION = "3"
EXPECTED_RUNTIME = "pi"
EXPECTED_MODEL = "deepseek-v4-pro"
EXPECTED_SCOPE = "scheduled_internal_research_only"
CAMPAIGN_OPEN_STATUSES = (
    "BLOCKED_NO_FORWARD_OBSERVATIONS",
    "OBSERVING_MINIMUM_NOT_MET",
    "CONTINUE_OBSERVATION",
    "ELIGIBLE_FOR_INDEPENDENT_VALIDATION",
)


def _read(name: str) -> str:
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


def _installer_authorization_block() -> str:
    text = _read("install_quant_schedule.ps1")
    match = re.search(
        r"\$authorization\s*=\s*\[ordered\]@\{(.*?)^\}", text, re.S | re.M
    )
    if not match:
        raise AssertionError("installer authorization block could not be located")
    return match.group(1)


def _installer_authorization_fields() -> set[str]:
    return set(re.findall(r"(?m)^\s+([A-Za-z_]\w*)\s*=", _installer_authorization_block()))


def _authorization_fields_read_by(name: str) -> set[str]:
    return set(re.findall(r"\$authorization\.([A-Za-z_]\w*)", _read(name)))


class ScheduleContractTests(unittest.TestCase):
    def test_all_three_scripts_agree_on_authorization_schema(self):
        installer = _installer_authorization_block()
        match = re.search(r"^\s+schema_version\s*=\s*(\d+)", installer, re.M)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), EXPECTED_SCHEMA_VERSION)
        for name in ("run_daily_research.ps1", "check_quant_schedule.ps1"):
            comparisons = re.findall(
                r"\$authorization\.schema_version\s+-ne\s+(\d+)", _read(name)
            )
            self.assertEqual(
                comparisons,
                [EXPECTED_SCHEMA_VERSION],
                f"{name} must require exactly authorization schema {EXPECTED_SCHEMA_VERSION}",
            )

    def test_runner_and_checker_pin_the_same_runtime_contract(self):
        for name in ("run_daily_research.ps1", "check_quant_schedule.ps1"):
            text = _read(name)
            self.assertIn(f'$authorization.runtime -ne "{EXPECTED_RUNTIME}"', text, name)
            self.assertIn(f'$authorization.model -ne "{EXPECTED_MODEL}"', text, name)

    def test_installer_writes_every_field_runner_and_checker_read(self):
        written = _installer_authorization_fields()
        for name in ("run_daily_research.ps1", "check_quant_schedule.ps1"):
            missing = _authorization_fields_read_by(name) - written
            self.assertEqual(
                missing,
                set(),
                f"{name} reads authorization fields the installer never writes",
            )

    def test_installer_scope_and_boundaries_are_enforced_by_all(self):
        block = _installer_authorization_block()
        self.assertIn(f"scope = \"{EXPECTED_SCOPE}\"", block)
        self.assertIn("broker_connection_enabled = $false", block)
        self.assertIn("external_distribution_approved = $false", block)
        self.assertIn("expires_at", block)
        for name in ("run_daily_research.ps1", "check_quant_schedule.ps1"):
            text = _read(name)
            self.assertIn("broker_connection_enabled -ne $false", text, name)
            self.assertIn("external_distribution_approved -ne $false", text, name)
            self.assertIn("expires_at", text, name)

    def test_checker_reverifies_the_same_bound_evidence_as_runner(self):
        shared_evidence = (
            ("experiment registry integrity", "experiment-status"),
            ("release approval", "release-verify"),
            ("campaign ledger", "forward-status"),
            ("registry metadata hash", "experiment_registry_metadata_sha256"),
            ("approval hash", "approval_sha256"),
            ("campaign metadata hash", "forward_campaign_metadata_sha256"),
            ("registry identity", "experiment_registry_id"),
            ("campaign identity", "forward_campaign_id"),
            ("candidate identity", "candidate_id"),
            ("source commit", "source_head_commit"),
        )
        runner = _read("run_daily_research.ps1")
        checker = _read("check_quant_schedule.ps1")
        for label, marker in shared_evidence:
            self.assertIn(marker, runner, f"runner must verify {label}")
            self.assertIn(marker, checker, f"checker must reverify {label}")

    def test_campaign_open_statuses_match_between_runner_and_checker(self):
        for name in ("run_daily_research.ps1", "check_quant_schedule.ps1"):
            for status in CAMPAIGN_OPEN_STATUSES:
                self.assertIn(status, _read(name), f"{name} missing status {status}")

    def test_installer_registers_one_hidden_nonelevated_single_action(self):
        text = _read("install_quant_schedule.ps1")
        self.assertEqual(
            len(re.findall(r"New-ScheduledTaskAction", text)),
            1,
            "installer must register exactly one task action",
        )
        self.assertLessEqual(
            len(re.findall(r"Register-ScheduledTask", text)),
            1,
            "installer must have a single registration path",
        )
        self.assertIn("-WindowStyle Hidden", text)
        self.assertIn("MultipleInstances IgnoreNew", text)
        self.assertIn("RunLevel Limited", text)
        self.assertIn("SupportsShouldProcess", text)

    def test_checker_enforces_task_hardening(self):
        text = _read("check_quant_schedule.ps1")
        self.assertIn('"IgnoreNew"', text)
        self.assertIn('"Limited"', text)
        self.assertIn("(?i)-WindowStyle\\s+Hidden", text)
        self.assertIn("exactly one action", text)
        self.assertIn("authorization SHA-256", text)


if __name__ == "__main__":
    unittest.main()
