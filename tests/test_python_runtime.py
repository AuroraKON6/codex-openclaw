import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from quant_agents.__main__ import cmd_health, cmd_python_runtime
from quant_agents.orchestrator import PipelinePreflightError, _preflight_dependencies, run_pipeline
from quant_agents.python_runtime import (
    inspect_python_runtime,
    normalize_distribution_name,
    parse_locked_requirements,
)

from test_input_validation import valid_input


class PythonRuntimeTests(unittest.TestCase):
    def test_current_project_runtime_satisfies_contract(self):
        result = inspect_python_runtime()

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["target"], "windows-cpython-3.11-project-venv")
        self.assertEqual(result["locked_package_count"], 32)
        self.assertEqual(result["package_mismatches"], [])
        self.assertEqual(result["unexpected_distributions"], [])
        self.assertFalse(result["user_site_enabled"])

    def test_lock_parser_requires_exact_pin_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "requirements.txt"
            lock_path.write_text(
                "demo-package==1.2.3 \\\n"
                "    --hash=sha256:" + "a" * 64 + "\n"
                "unlocked>=2\n",
                encoding="utf-8",
            )
            result = parse_locked_requirements(lock_path)

        self.assertIn("demo-package", result["packages"])
        self.assertTrue(result["packages"]["demo-package"]["hashes"])
        self.assertTrue(any("unsupported" in error for error in result["errors"]))

    def test_distribution_names_are_canonicalized(self):
        self.assertEqual(normalize_distribution_name("Typing_Extensions"), "typing-extensions")
        self.assertEqual(normalize_distribution_name("demo.package"), "demo-package")

    def test_version_mismatch_and_unexpected_distribution_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".python-version").write_text("3.11\n", encoding="utf-8")
            (root / "requirements.txt").write_text(
                "demo==1.0 \\\n    --hash=sha256:" + "b" * 64 + "\n",
                encoding="utf-8",
            )
            with patch(
                "quant_agents.python_runtime._same_path", return_value=True
            ), patch(
                "quant_agents.python_runtime._installed_distributions",
                return_value={"demo": "2.0", "extra": "1.0"},
            ):
                result = inspect_python_runtime(root)

        self.assertFalse(result["ok"])
        self.assertEqual(result["package_mismatches"][0]["name"], "demo")
        self.assertEqual(result["unexpected_distributions"], ["extra"])

    def test_python_runtime_cli_has_strict_exit(self):
        result = {"ok": False, "errors": ["wrong interpreter"]}
        with patch(
            "quant_agents.__main__.inspect_python_runtime", return_value=result
        ), redirect_stdout(io.StringIO()) as output:
            exit_code = cmd_python_runtime(SimpleNamespace(require_ready=True))

        self.assertEqual(exit_code, 3)
        self.assertEqual(json.loads(output.getvalue()), result)

    def test_health_blocks_before_other_gates_on_wrong_interpreter(self):
        args = SimpleNamespace(
            mock=False,
            runtime_only=False,
            no_tushare=False,
            no_ping=False,
            input="strategy_round.example.json",
        )
        report = {
            "target": "windows-cpython-3.11-project-venv",
            "executable": "C:\\wrong\\python.exe",
            "implementation": "CPython",
            "python_version": "3.8.5",
            "requirements_lock_sha256": None,
            "locked_package_count": 0,
            "ok": False,
            "errors": ["python_version: expected 3.11"],
        }
        with patch(
            "quant_agents.__main__.inspect_python_runtime", return_value=report
        ), patch(
            "quant_agents.__main__.collect_source_provenance"
        ) as source, redirect_stdout(io.StringIO()):
            exit_code = cmd_health(args)

        self.assertEqual(exit_code, 1)
        source.assert_not_called()

    def test_real_preflight_blocks_before_secret_or_external_calls(self):
        report = {"ok": False, "errors": ["wrong interpreter"]}
        with patch(
            "quant_agents.orchestrator.inspect_python_runtime", return_value=report
        ), patch(
            "quant_agents.orchestrator.evaluate_secret_scan_receipt"
        ) as secret_scan:
            with self.assertRaises(PipelinePreflightError) as raised:
                _preflight_dependencies("pi", valid_input())

        secret_scan.assert_not_called()
        self.assertEqual(
            raised.exception.preflight["checks"][0]["name"],
            "python_runtime_contract",
        )
        self.assertEqual(raised.exception.preflight["checks"][0]["status"], "failed")

    def test_mock_run_refuses_wrong_project_runtime(self):
        report = {"ok": False, "errors": ["wrong interpreter"]}
        with tempfile.TemporaryDirectory() as directory, patch(
            "quant_agents.orchestrator.inspect_python_runtime", return_value=report
        ):
            with self.assertRaises(PipelinePreflightError):
                run_pipeline(valid_input(), directory, mock=True, runtime="pi")
            state = json.loads(
                Path(directory, "state.json").read_text(encoding="utf-8")
            )

        self.assertEqual(state["status"], "preflight_failed")
        self.assertTrue(state["mock"])
        self.assertEqual(state["preflight"]["checks"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
