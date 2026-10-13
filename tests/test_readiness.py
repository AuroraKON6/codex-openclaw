import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from quant_agents.__main__ import cmd_project_readiness
from quant_agents.readiness import build_project_readiness, latest_pi_acceptance


class ReadinessTests(unittest.TestCase):
    def test_collects_all_blockers_without_external_calls(self):
        source = {
            "repository_available": True,
            "head_commit": None,
            "branch": None,
            "dirty": True,
            "tracked_file_count": 0,
            "changed_file_count": 0,
            "untracked_file_count": 10,
            "status_sha256": "a" * 64,
            "release_ready": False,
            "reason": "repository has no committed HEAD",
        }
        runtime = {
            "ok": True,
            "errors": [],
            "node_version": "24.16.0",
            "pi_package": "@earendil-works/pi-coding-agent",
            "pi_version": "0.84.2",
            "expected_pi_version": "0.84.2",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "model_available": True,
            "runtime_lock_sha256": "b" * 64,
            "policy": {"all_tools_disabled": True},
        }
        with tempfile.TemporaryDirectory() as directory, patch(
            "quant_agents.readiness.collect_source_provenance", return_value=source
        ), patch(
            "quant_agents.readiness.evaluate_secret_scan_receipt",
            return_value={"ok": True, "errors": [], "receipt_summary": {}},
        ), patch(
            "quant_agents.readiness.evaluate_data_license",
            side_effect=RuntimeError("data license missing"),
        ), patch(
            "quant_agents.readiness.evaluate_research_protocol",
            side_effect=RuntimeError("protocol missing"),
        ), patch(
            "quant_agents.readiness.evaluate_execution_cost_evidence",
            side_effect=RuntimeError("cost evidence missing"),
        ), patch(
            "quant_agents.readiness.PiClient.inspect_runtime", return_value=runtime
        ), patch(
            "quant_agents.readiness.Config.validate",
            return_value=["TUSHARE_TOKEN not set"],
        ), patch(
            "quant_agents.pi_client.PiClient.ping"
        ) as ping:
            result = build_project_readiness(
                "strategy_round.example.json",
                runs_root=directory,
                acceptance_root=directory,
                planning_status_path=str(Path(directory) / "missing.json"),
            )

        names = {check["name"] for check in result["checks"]}
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["ready_for_human_g1_review"])
        self.assertFalse(result["g1_authorized"])
        self.assertFalse(result["real_run_authorized"])
        self.assertFalse(result["execution_policy"]["network_calls_performed"])
        self.assertFalse(result["execution_policy"]["paid_model_calls_performed"])
        self.assertTrue(
            {
                "source_baseline",
                "data_license",
                "research_protocol",
                "experiment_registry",
                "execution_cost",
                "provider_configuration",
                "pi_paid_acceptance",
            }.issubset(names)
        )
        ping.assert_not_called()

    def test_machine_ready_still_requires_human_g1_decision(self):
        current = datetime(2026, 9, 1, tzinfo=timezone.utc)
        source = {
            "repository_available": True,
            "head_commit": "a" * 40,
            "branch": "main",
            "dirty": False,
            "tracked_file_count": 120,
            "changed_file_count": 0,
            "untracked_file_count": 0,
            "status_sha256": "b" * 64,
            "release_ready": True,
            "reason": "clean committed source baseline",
        }
        license_gate = {"status": "approved"}
        protocol_gate = {"status": "approved_for_backtest"}
        registry_gate = {
            "status": "ready_for_reservation",
            "ledger_integrity_ok": True,
        }
        cost_gate = {"status": "approved_for_internal_research"}
        runtime = {
            "ok": True,
            "errors": [],
            "node_version": "24.16.0",
            "pi_package": "@earendil-works/pi-coding-agent",
            "pi_version": "0.84.2",
            "expected_pi_version": "0.84.2",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "model_available": True,
            "runtime_lock_sha256": "c" * 64,
            "policy": {"all_tools_disabled": True},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            planning = root / "planning.json"
            planning.write_text(
                json.dumps(
                    {
                        "role_assignments": {
                            "GM": "assigned",
                            "QUANT": "assigned",
                            "VALIDATOR": "assigned",
                        },
                        "budget_approval_status": "APPROVED",
                    }
                ),
                encoding="utf-8",
            )
            report_dir = root / "pi_runtime_acceptance_20260901_000000_000"
            report_dir.mkdir()
            (report_dir / "acceptance_report.json").write_text(
                json.dumps(_acceptance_report(current)),
                encoding="utf-8",
            )
            with patch(
                "quant_agents.readiness.collect_source_provenance", return_value=source
            ), patch(
                "quant_agents.readiness.evaluate_secret_scan_receipt",
                return_value={"ok": True, "errors": [], "receipt_summary": {}},
            ), patch(
                "quant_agents.readiness.evaluate_source_review_decision",
                return_value={
                    "review_claim_valid": True,
                    "status": "VALID_DUAL_FILE_REVIEW_CLAIM",
                },
            ), patch(
                "quant_agents.readiness.evaluate_data_license", return_value=license_gate
            ), patch(
                "quant_agents.readiness.is_release_eligible_data_license",
                return_value=True,
            ), patch(
                "quant_agents.readiness.evaluate_research_protocol",
                return_value=protocol_gate,
            ), patch(
                "quant_agents.readiness.is_release_eligible_research_protocol",
                return_value=True,
            ), patch(
                "quant_agents.readiness.evaluate_experiment_registry",
                return_value=registry_gate,
            ), patch(
                "quant_agents.readiness.evaluate_execution_cost_evidence",
                return_value=cost_gate,
            ), patch(
                "quant_agents.readiness.is_release_eligible_execution_cost",
                return_value=True,
            ), patch(
                "quant_agents.readiness.PiClient.inspect_runtime", return_value=runtime
            ), patch(
                "quant_agents.readiness.Config.validate", return_value=[]
            ), patch.object(
                __import__("quant_agents.readiness", fromlist=["Config"]).Config,
                "TUSHARE_TOKEN",
                "configured",
            ):
                result = build_project_readiness(
                    "strategy_round.example.json",
                    runs_root=directory,
                    acceptance_root=directory,
                    planning_status_path=str(planning),
                    now=current,
                )

        self.assertEqual(
            result["status"], "READY_FOR_HUMAN_G1_REVIEW_NOT_AUTHORIZED"
        )
        self.assertTrue(result["ready_for_human_g1_review"])
        self.assertTrue(result["phase_c_acceptance_complete"])
        self.assertFalse(result["g1_authorized"])
        self.assertFalse(result["real_run_authorized"])
        self.assertTrue(result["human_decision_required"])

    def test_stale_pi_acceptance_is_not_current(self):
        current = datetime(2026, 9, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "pi_runtime_acceptance_20260801_000000_000"
            report_dir.mkdir()
            report = _acceptance_report(current - timedelta(days=8))
            (report_dir / "acceptance_report.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            result = latest_pi_acceptance(directory, current, max_age_days=7)

        self.assertTrue(result["found"])
        self.assertTrue(result["contract_passed"])
        self.assertFalse(result["current"])
        self.assertGreater(result["age_days"], 7)

    def test_future_pi_acceptance_is_rejected(self):
        current = datetime(2026, 9, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "pi_runtime_acceptance_20260902_000000_000"
            report_dir.mkdir()
            report = _acceptance_report(current + timedelta(days=1))
            (report_dir / "acceptance_report.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            result = latest_pi_acceptance(directory, current, max_age_days=7)

        self.assertTrue(result["found"])
        self.assertTrue(result["contract_passed"])
        self.assertTrue(result["generated_in_future"])
        self.assertFalse(result["current"])

    def test_cli_require_ready_returns_blocked_exit_code(self):
        args = SimpleNamespace(
            input="strategy_round.example.json",
            runs_root="runs",
            acceptance_root="drill_reports",
            planning_status=None,
            skip_pi_inspect=True,
            acceptance_max_age_days=7,
            require_ready=True,
        )
        result = {
            "status": "BLOCKED",
            "real_run_authorized": False,
        }
        output = io.StringIO()
        with patch(
            "quant_agents.__main__.build_project_readiness", return_value=result
        ), redirect_stdout(output):
            exit_code = cmd_project_readiness(args)

        self.assertEqual(exit_code, 3)
        self.assertEqual(json.loads(output.getvalue()), result)


def _acceptance_report(generated_at):
    return {
        "status": "passed",
        "generated_at": generated_at.isoformat(),
        "acceptance_scope": "runtime_contract_only_not_market_research",
        "runtime": "pi",
        "pi_version": "0.84.2",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "usage": {"totalTokens": 10},
        "runtime_policy": {
            "all_tools_disabled": True,
            "context_files_disabled": True,
            "project_resources_ignored": True,
        },
    }


if __name__ == "__main__":
    unittest.main()
