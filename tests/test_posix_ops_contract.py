"""Contracts for the cross-platform operations driver (tools/quant_ops.py).

The PowerShell contracts live in test_ops_contract.py and keep guarding the
retained Windows entry points. This module locks the macOS/Linux driver to the
same safety behavior so a port cannot silently weaken a gate:

- bootstrap stays hash-locked, wheel-only, pip-checked and contract-checked;
- every quant_agents invocation goes through the project venv interpreter;
- verify stays fully offline and keeps the blocking exit-code-3 smoke checks;
- the driver never installs a schedule, never falls back to Mock, and refuses
  to replace the PowerShell entry points on Windows.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (PROJECT_ROOT / name).read_text(encoding="utf-8")


class BootstrapContract(unittest.TestCase):
    def test_bootstrap_enforces_hashes_wheels_and_pip_check(self):
        text = _read("tools/quant_ops.py")
        for required in (
            '"--require-hashes"',
            '"--only-binary=:all:"',
            '"-m", "pip", "check"',
            '"python-runtime", "--require-ready"',
        ):
            self.assertIn(required, text)

    def test_shell_entry_uses_project_venv_or_base_interpreter_only(self):
        text = _read("quant.sh")
        self.assertIn(".venv/bin/python", text)
        self.assertIn("tools/quant_ops.py", text)
        self.assertNotRegex(text, r"(?m)^\s*(?:exec\s+)?python3?\s")

    def test_driver_never_invokes_path_python_for_quant_agents(self):
        text = _read("tools/quant_ops.py")
        for forbidden in ('"python3"', '"python3.11", "-m"', "os.system", "shell=True"):
            self.assertNotIn(forbidden, text)
        # Every subprocess that runs project code starts from the resolved
        # project interpreter, never from a bare interpreter name.
        for head in re.findall(
            r"\[\s*(\w+)\s*,\s*\"-m\",\s*\"(?:quant_agents|unittest|py_compile)\"", text
        ):
            self.assertEqual(head, "resolve_project_python()")

    def test_every_command_refuses_to_replace_the_powershell_entry(self):
        import inspect

        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        self.addCleanup(sys.path.pop, 0)
        import quant_ops

        for command in quant_ops.OPS_COMMANDS:
            handler = getattr(quant_ops, f"cmd_{command.replace('-', '_')}")
            body = "\n".join(inspect.getsource(handler).splitlines()[:4])
            self.assertIn('require_posix("', body, command)


class NoPaidCallsByDefaultContract(unittest.TestCase):
    PAID_OR_PRIVILEGED_MARKERS = (
        "invoke_pi_acceptance",
        "invoke_pi_skills_acceptance",
        "install_quant_schedule",
        "run_daily_research",
        "forward-record",
        "check_pi",
    )

    def test_verify_function_is_fully_offline(self):
        text = _read("tools/quant_ops.py")
        verify_body = text.split("def cmd_verify(", 1)[1].split("\n# --- backup, retention, drill", 1)[0]
        for marker in self.PAID_OR_PRIVILEGED_MARKERS:
            self.assertNotIn(marker, verify_body)
        for required in (
            "secret-scan",
            "source-candidate",
            "source-review-packet",
            "source-review-verify",
            "source-review-decision-template",
            "source-review-decision-verify",
            '"--mock"',
            "exit code 3",
        ):
            self.assertIn(required, verify_body)

    def test_weekly_without_dates_uses_the_last_seven_days(self):
        # The date logic is pure and platform-free, so it is tested directly
        # and stays green on the Windows CI runner, where the POSIX entry
        # itself must refuse (see the next test).
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        self.addCleanup(sys.path.pop, 0)
        import quant_ops

        fixed = datetime(2026, 11, 27, 13, 40, 59)
        self.assertEqual(quant_ops.weekly_window("", "", now=fixed), ("20261120", "20261127"))
        self.assertEqual(quant_ops.weekly_window("20261101", "", now=fixed), ("20261101", "20261127"))
        self.assertEqual(quant_ops.weekly_window("", "20261110", now=fixed), ("20261120", "20261110"))
        self.assertEqual(quant_ops.weekly_window("20261101", "20261110", now=fixed), ("20261101", "20261110"))
        self.assertEqual(
            quant_ops.weekly_window("", "", now=datetime(2026, 3, 1, 0, 0, 0)),
            ("20260222", "20260301"),
        )

    def test_weekly_passes_the_resolved_window_to_the_cli(self):
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        self.addCleanup(sys.path.pop, 0)
        import quant_ops

        recorded = {}

        def fake_run_python(args, **_):
            recorded["args"] = args
            return SimpleNamespace(returncode=0)

        fixed = datetime(2026, 11, 27, 13, 40, 59)
        # The platform refusal has its own test; it is neutralised here so the
        # forwarding check also holds under an os.name="nt" fixture.
        with patch.object(quant_ops, "require_posix"), patch.object(
            quant_ops, "load_env_file", return_value=False
        ), patch.object(
            quant_ops, "run_python", side_effect=fake_run_python
        ), patch.object(quant_ops, "weekly_window", return_value=quant_ops.weekly_window("", "", now=fixed)) as window:
            exit_code = quant_ops.cmd_weekly(["--mock"])
        self.assertEqual(exit_code, 0)
        window.assert_called_once_with("", "")
        args = recorded["args"]
        self.assertEqual(args[args.index("--since") + 1], "20261120")
        self.assertEqual(args[args.index("--until") + 1], "20261127")
        self.assertIn("--mock", args)

    def test_posix_entry_refuses_to_run_on_windows(self):
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        self.addCleanup(sys.path.pop, 0)
        import quant_ops

        with patch.object(quant_ops.os, "name", "nt"), patch.object(
            quant_ops, "run_python"
        ) as run_python:
            for command, args in (("cmd_weekly", ["--mock"]), ("cmd_run", ["--mock"])):
                with self.subTest(command=command), self.assertRaises(quant_ops.OpsError):
                    getattr(quant_ops, command)(args)
            run_python.assert_not_called()

    def test_run_never_falls_back_to_mock(self):
        text = _read("tools/quant_ops.py")
        # Module docstring maps the Windows names; the marker tuple names them
        # only to keep them out of verify.
        code = re.sub(
            r"PAID_OR_PRIVILEGED_MARKERS = \(.*?\)\n",
            "",
            text.split('"""', 2)[2],
            flags=re.S,
        )
        run_body = code.split("def cmd_run(", 1)[1].split("\ndef cmd_weekly", 1)[0]
        self.assertIn("Fallback: disabled (Mock requires --mock)", run_body)
        self.assertIn('if options.mock:\n        run_args.append("--mock")', run_body)
        self.assertNotIn("run_daily_research", code)
        self.assertNotIn("install_quant_schedule", code)
        self.assertNotIn("schtasks", code)
        self.assertNotIn("launchctl", text)

    def test_ops_console_stays_offline_and_tool_free(self):
        text = _read("tools/quant_ops.py")
        console_body = text.split("def cmd_ops_console(", 1)[1].split("\n# --- offline verification", 1)[0]
        for flag in (
            "--no-session",
            "--no-tools",
            "--no-extensions",
            "--no-skills",
            "--no-context-files",
            "--offline",
        ):
            self.assertIn(flag, console_body)
        self.assertEqual(console_body.count('"--extension"'), 1)
        self.assertIn('"--extension", str(PI_EXTENSION)', console_body)
        self.assertIn('"quant-ops-readonly.mjs"', text)
        self.assertNotIn("TUSHARE_TOKEN", console_body)
        self.assertIn('os.environ["PI_OFFLINE"] = "1"', console_body)
        self.assertIn('os.environ["PI_TELEMETRY"] = "0"', console_body)


class PlatformBoundaryContract(unittest.TestCase):
    def test_windows_entry_points_are_retained(self):
        for name in (
            "quant.ps1",
            "quant_python.ps1",
            "bootstrap_python.ps1",
            "lock_python_dependencies.ps1",
            "install_pi_runtime.ps1",
            "verify_quant_pipeline.ps1",
            "run_quant_agents.ps1",
            "run_daily_research.ps1",
            "install_quant_schedule.ps1",
            "check_quant_schedule.ps1",
            "disable_legacy_openclaw.ps1",
        ):
            self.assertTrue((PROJECT_ROOT / name).is_file(), name)

    def test_windows_security_acceptance_scripts_are_not_ported_or_gated_off(self):
        # Scheduled tasks and the legacy OpenClaw teardown are Windows
        # facilities; the driver must not grow a stand-in for them.
        driver = _read("tools/quant_ops.py")
        for windows_only in ("install_quant_schedule.ps1", "check_quant_schedule.ps1", "disable_legacy_openclaw.ps1"):
            self.assertNotIn(windows_only, driver)
        self.assertNotIn("Register-ScheduledTask", driver)

    def test_ci_keeps_the_windows_runner(self):
        text = _read(".github/workflows/ci.yml")
        self.assertIn("runs-on: windows-latest", text)
        self.assertIn("verify_quant_pipeline.ps1", text)

class LockAndImageBoundaryContract(unittest.TestCase):
    def test_lock_selector_refuses_unsupported_os_and_arch_before_writing(self):
        import platform

        # host_lock_file imports the contract module; load it now, outside the
        # platform patch, so an os.name fixture cannot skew pathlib during import.
        if "quant_agents.python_runtime" not in sys.modules:
            sys.path.insert(0, str(PROJECT_ROOT))
            self.addCleanup(sys.path.pop, 0)
            import quant_agents.python_runtime  # noqa: F401
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        self.addCleanup(sys.path.pop, 0)
        import quant_ops

        for os_name, machine in (("Linux", "x86_64"), ("Darwin", "x86_64"), ("SunOS", "sun4v")):
            with self.subTest(host=f"{os_name} {machine}"), patch.object(
                platform, "system", return_value=os_name
            ), patch.object(platform, "machine", return_value=machine):
                with self.assertRaises(quant_ops.OpsError):
                    quant_ops.host_lock_file()

    def test_lock_command_never_writes_without_apply(self):
        text = _read("tools/quant_ops.py")
        lock_body = text.split("def cmd_lock(", 1)[1].split("\n\ndef _PLATFORM_LOCK_LABELS", 1)[0]
        self.assertIn("if options.apply:", lock_body)
        self.assertIn("shutil.copyfile(candidate, lock_path)", lock_body)
        self.assertEqual(lock_body.count("copyfile"), 1)

    def test_build_context_excludes_local_configuration_at_any_depth(self):
        lines = [line.strip() for line in _read(".dockerignore").splitlines() if line.strip() and not line.startswith("#")]
        self.assertIn("**/.env", lines)
        self.assertIn("**/.env.*", lines)
        # The template stays in the context: its exception follows both excludes.
        self.assertLess(lines.index("**/.env"), lines.index("!**/.env.example"))
        self.assertLess(lines.index("**/.env.*"), lines.index("!**/.env.example"))

    def test_lock_selector_has_no_undefined_names(self):
        compile(_read("tools/quant_ops.py"), "tools/quant_ops.py", "exec")


class EnvTemplateContract(unittest.TestCase):
    def test_env_template_has_placeholders_and_no_real_paths_or_keys(self):
        text = _read(".env.example")
        self.assertIn("YOUR_KEY_HERE", text)
        self.assertIn("YOUR_TUSHARE_TOKEN_HERE", text)
        self.assertNotRegex(text, r"(?m)^[A-Z]:\\")
        self.assertNotRegex(text, r"(?m)^[A-Z_]+=(sk-|ghp_|eyJ)")
        for key in (
            "DATA_LICENSE_EVIDENCE_PATH",
            "RESEARCH_PROTOCOL_EVIDENCE_PATH",
            "EXECUTION_COST_EVIDENCE_PATH",
            "EXPERIMENT_REGISTRY_PATH",
            "SOURCE_REVIEW_DECISION_PATH",
        ):
            self.assertRegex(text, rf"(?m)^{key}=<ABSOLUTE_PATH_OUTSIDE_REPO>/")


if __name__ == "__main__":
    unittest.main()
