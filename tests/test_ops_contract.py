"""Operational cross-script contracts outside the schedule lifecycle.

The schedule authorization lifecycle has its own contract tests
(test_schedule_contract.py). This module locks the remaining operator-facing
scripts and the CI workflow to their documented safety behavior so the
following cannot silently regress:

- the legacy OpenClaw teardown targets exactly three named tasks and two
  named ports and never force-kills processes (handoff §10.1, §23.7);
- the read-only ops console creates no autostart and stays offline
  (blueprint §12.6, §15.1);
- the daily runner never falls back to Mock (ADR-0003);
- the Python runtime bootstrap pins the approved CPython 3.11 venv;
- CI runs only the fully offline software verification — no paid or
  privileged commands, no provider or data credentials (ADR-0003, ADR-0004).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LEGACY_TASK_NAMES = (
    "OpenClaw Gateway",
    "OpenClaw Gateway (quant-research)",
    "OpenClaw Gateway Watchdog (quant-research)",
)
LEGACY_PORTS = ("18789", "18790")

# Commands that trigger paid LLM usage, licensed data usage, production
# schedule installation, or forward-ledger writes. They must never appear in
# CI or in the offline verification script.
PAID_OR_PRIVILEGED_MARKERS = (
    "invoke_pi_acceptance",
    "invoke_pi_skills_acceptance",
    "install_quant_schedule",
    "run_daily_research",
    "forward-record",
    "check_pi",
)


def _read(name: str) -> str:
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


class LegacyOpenClawTeardownContract(unittest.TestCase):
    """disable_legacy_openclaw.ps1 must stay surgical, never destructive."""

    def test_default_targets_are_exactly_the_three_legacy_tasks_and_ports(self):
        text = _read("disable_legacy_openclaw.ps1")
        for task_name in LEGACY_TASK_NAMES:
            self.assertIn(f'"{task_name}"', text)
        self.assertIn("@(18789, 18790)", text)
        self.assertNotIn("18791", text)

    def test_never_force_kills_processes_or_services(self):
        text = _read("disable_legacy_openclaw.ps1")
        for forbidden in (
            "Stop-Process",
            "taskkill",
            "Stop-Service",
            "Restart-Computer",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("SupportsShouldProcess", text)
        self.assertIn("no process was force-killed", text)


class OpsConsoleContract(unittest.TestCase):
    """open_pi_ops_console.ps1 is an interactive, offline, read-only console."""

    def test_creates_no_autostart_or_service(self):
        text = _read("open_pi_ops_console.ps1")
        for forbidden in (
            "Register-ScheduledTask",
            "New-ScheduledTask",
            "schtasks",
            "New-Service",
            "reg add",
        ):
            self.assertNotIn(forbidden, text)

    def test_console_stays_offline_and_tool_free(self):
        text = _read("open_pi_ops_console.ps1")
        for flag in (
            "--no-session",
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-context-files",
            "--offline",
        ):
            self.assertIn(flag, text)
        self.assertIn('PI_OFFLINE = "1"', text)
        self.assertIn('PI_TELEMETRY = "0"', text)

    def test_only_mounts_the_audited_readonly_extension(self):
        text = _read("open_pi_ops_console.ps1")
        self.assertEqual(text.count("--extension "), 1)
        self.assertIn("quant-ops-readonly.mjs", text)
        lock_text = _read("governance/pi_extensions.lock.json")
        self.assertIn("quant-ops-readonly.mjs", lock_text)
        self.assertNotIn("TUSHARE_TOKEN", text)


class DailyRunnerContract(unittest.TestCase):
    def test_runner_never_falls_back_to_mock_and_pins_pi(self):
        text = _read("run_daily_research.ps1")
        self.assertNotIn("-Mock", text)
        self.assertIn('"-Runtime", "pi"', text)
        # Explicit operator retry must point at the latest prior run.
        self.assertIn("-RetryOf must equal the latest prior run ID", text)


class PythonRuntimeScriptsContract(unittest.TestCase):
    def test_quant_python_pins_venv_and_approved_311(self):
        text = _read("quant_python.ps1")
        self.assertIn(".venv\\Scripts\\python.exe", text)
        self.assertIn("3\\.11", text)

    def test_bootstrap_requires_approved_311_and_supports_offline_wheelhouse(self):
        text = _read("bootstrap_python.ps1")
        self.assertIn("-3.11", text)
        self.assertIn(".venv", text)
        self.assertIn("Wheelhouse", text)


class NoPaidCallsByDefaultContract(unittest.TestCase):
    def test_verify_pipeline_is_fully_offline(self):
        text = _read("verify_quant_pipeline.ps1")
        for marker in PAID_OR_PRIVILEGED_MARKERS:
            self.assertNotIn(marker, text)
        for required in (
            "secret-scan",
            "source-candidate",
            "source-review-packet",
            "source-review-verify",
            "source-review-decision-template",
            "source-review-decision-verify",
            "-Mock",
            "exit code 3",
        ):
            self.assertIn(required, text)

    def test_ci_workflow_only_runs_the_offline_verification(self):
        text = _read(".github/workflows/ci.yml")
        self.assertIn("verify_quant_pipeline.ps1", text)
        for marker in PAID_OR_PRIVILEGED_MARKERS:
            self.assertNotIn(marker, text)
        for secret in ("TUSHARE_TOKEN", "DEEPSEEK_API_KEY"):
            self.assertNotIn(secret, text)

    def test_check_pi_ping_is_opt_out_via_noping(self):
        text = _read("check_pi.ps1")
        self.assertIn("[switch]$NoPing", text)
        self.assertIn('"--no-ping"', text)


class AdrCatalogContract(unittest.TestCase):
    """The ADR index must list exactly the twelve accepted decision files."""

    def test_index_links_twelve_existing_adr_files(self):
        index = _read("docs/adr/README.md")
        links = re.findall(r"\((ADR-\d{4}-[a-z0-9-]+\.md)\)", index)
        self.assertEqual(len(links), 12)
        for name in links:
            self.assertTrue(
                (PROJECT_ROOT / "docs" / "adr" / name).is_file(),
                f"ADR index references missing file: {name}",
            )
        on_disk = sorted(
            path.name
            for path in (PROJECT_ROOT / "docs" / "adr").glob("ADR-*.md")
        )
        self.assertEqual(sorted(links), on_disk)


if __name__ == "__main__":
    unittest.main()
