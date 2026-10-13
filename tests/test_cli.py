import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from quant_agents.__main__ import cmd_health


class CliHealthTests(unittest.TestCase):
    @staticmethod
    def _args(**overrides):
        values = {
            "mock": False,
            "runtime_only": False,
            "no_tushare": False,
            "no_ping": False,
            "input": "strategy_round.example.json",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_source_failure_stops_before_license_data_and_pi(self):
        source = {
            "release_ready": False,
            "head_commit": None,
            "reason": "no controlled commit",
        }
        with patch(
            "quant_agents.__main__.collect_source_provenance", return_value=source
        ), patch(
            "quant_agents.__main__.evaluate_secret_scan_receipt",
            return_value={"ok": True, "errors": [], "receipt_summary": {}},
        ), patch(
            "quant_agents.__main__.evaluate_source_review_decision",
            return_value={"review_claim_valid": True, "status": "valid"},
        ), patch(
            "quant_agents.__main__.evaluate_data_license"
        ) as license_gate, patch(
            "quant_agents.__main__.evaluate_research_protocol"
        ) as protocol_gate, patch(
            "quant_agents.__main__.evaluate_execution_cost_evidence"
        ) as cost_gate, patch(
            "quant_agents.pi_client.PiClient.inspect_runtime"
        ) as pi_runtime, redirect_stdout(io.StringIO()):
            exit_code = cmd_health(self._args())
        self.assertEqual(exit_code, 1)
        license_gate.assert_not_called()
        protocol_gate.assert_not_called()
        cost_gate.assert_not_called()
        pi_runtime.assert_not_called()

    def test_license_failure_stops_before_tushare_and_pi(self):
        source = {
            "release_ready": True,
            "head_commit": "a" * 40,
            "reason": "clean committed source baseline",
        }
        with patch(
            "quant_agents.__main__.collect_source_provenance", return_value=source
        ), patch(
            "quant_agents.__main__.evaluate_secret_scan_receipt",
            return_value={"ok": True, "errors": [], "receipt_summary": {}},
        ), patch(
            "quant_agents.__main__.evaluate_source_review_decision",
            return_value={"review_claim_valid": True, "status": "valid"},
        ), patch(
            "quant_agents.__main__.evaluate_data_license",
            side_effect=RuntimeError("license missing"),
        ), patch(
            "quant_agents.__main__.evaluate_research_protocol"
        ) as protocol_gate, patch(
            "quant_agents.__main__.evaluate_execution_cost_evidence"
        ) as cost_gate, patch(
            "quant_agents.data_client.DataClient.health"
        ) as data_health, patch(
            "quant_agents.pi_client.PiClient.inspect_runtime"
        ) as pi_runtime, redirect_stdout(io.StringIO()):
            exit_code = cmd_health(self._args())
        self.assertEqual(exit_code, 1)
        protocol_gate.assert_not_called()
        cost_gate.assert_not_called()
        data_health.assert_not_called()
        pi_runtime.assert_not_called()

    def test_protocol_failure_stops_before_cost_tushare_and_pi(self):
        source = {
            "release_ready": True,
            "head_commit": "a" * 40,
            "reason": "clean committed source baseline",
        }
        with patch(
            "quant_agents.__main__.collect_source_provenance", return_value=source
        ), patch(
            "quant_agents.__main__.evaluate_secret_scan_receipt",
            return_value={"ok": True, "errors": [], "receipt_summary": {}},
        ), patch(
            "quant_agents.__main__.evaluate_source_review_decision",
            return_value={"review_claim_valid": True, "status": "valid"},
        ), patch(
            "quant_agents.__main__.evaluate_data_license",
            return_value={"status": "approved"},
        ), patch(
            "quant_agents.__main__.evaluate_research_protocol",
            side_effect=RuntimeError("protocol missing"),
        ), patch(
            "quant_agents.__main__.evaluate_execution_cost_evidence"
        ) as cost_gate, patch(
            "quant_agents.data_client.DataClient.health"
        ) as data_health, patch(
            "quant_agents.pi_client.PiClient.inspect_runtime"
        ) as pi_runtime, redirect_stdout(io.StringIO()):
            exit_code = cmd_health(self._args())
        self.assertEqual(exit_code, 1)
        cost_gate.assert_not_called()
        data_health.assert_not_called()
        pi_runtime.assert_not_called()

    def test_cost_calibration_failure_stops_before_tushare_and_pi(self):
        source = {
            "release_ready": True,
            "head_commit": "a" * 40,
            "reason": "clean committed source baseline",
        }
        with patch(
            "quant_agents.__main__.collect_source_provenance", return_value=source
        ), patch(
            "quant_agents.__main__.evaluate_secret_scan_receipt",
            return_value={"ok": True, "errors": [], "receipt_summary": {}},
        ), patch(
            "quant_agents.__main__.evaluate_source_review_decision",
            return_value={"review_claim_valid": True, "status": "valid"},
        ), patch(
            "quant_agents.__main__.evaluate_data_license",
            return_value={"status": "approved"},
        ), patch(
            "quant_agents.__main__.evaluate_research_protocol",
            return_value={
                "status": "approved_for_backtest",
                "protocol_id": "test-protocol",
                "protocol_version": 1,
            },
        ), patch(
            "quant_agents.__main__.evaluate_experiment_registry",
            return_value={
                "status": "ready_for_reservation",
                "registry_id": "registry-001",
            },
        ), patch(
            "quant_agents.__main__.evaluate_execution_cost_evidence",
            side_effect=RuntimeError("cost evidence missing"),
        ) as cost_gate, patch(
            "quant_agents.data_client.DataClient.health"
        ) as data_health, patch(
            "quant_agents.pi_client.PiClient.inspect_runtime"
        ) as pi_runtime, redirect_stdout(io.StringIO()):
            exit_code = cmd_health(self._args())
        self.assertEqual(exit_code, 1)
        cost_gate.assert_called_once()
        data_health.assert_not_called()
        pi_runtime.assert_not_called()

    def test_registry_failure_stops_before_cost_tushare_and_pi(self):
        source = {
            "release_ready": True,
            "head_commit": "a" * 40,
            "reason": "clean committed source baseline",
        }
        with patch(
            "quant_agents.__main__.collect_source_provenance", return_value=source
        ), patch(
            "quant_agents.__main__.evaluate_secret_scan_receipt",
            return_value={"ok": True, "errors": [], "receipt_summary": {}},
        ), patch(
            "quant_agents.__main__.evaluate_source_review_decision",
            return_value={"review_claim_valid": True, "status": "valid"},
        ), patch(
            "quant_agents.__main__.evaluate_data_license",
            return_value={"status": "approved"},
        ), patch(
            "quant_agents.__main__.evaluate_research_protocol",
            return_value={
                "status": "approved_for_backtest",
                "protocol_id": "test-protocol",
                "protocol_version": 1,
            },
        ), patch(
            "quant_agents.__main__.evaluate_experiment_registry",
            side_effect=RuntimeError("registry missing"),
        ), patch(
            "quant_agents.__main__.evaluate_execution_cost_evidence"
        ) as cost_gate, patch(
            "quant_agents.data_client.DataClient.health"
        ) as data_health, patch(
            "quant_agents.pi_client.PiClient.inspect_runtime"
        ) as pi_runtime, redirect_stdout(io.StringIO()):
            exit_code = cmd_health(self._args())
        self.assertEqual(exit_code, 1)
        cost_gate.assert_not_called()
        data_health.assert_not_called()
        pi_runtime.assert_not_called()

    def test_secret_scan_failure_stops_before_license_tushare_and_pi(self):
        source = {
            "release_ready": True,
            "head_commit": "a" * 40,
            "reason": "clean committed source baseline",
        }
        with patch(
            "quant_agents.__main__.collect_source_provenance", return_value=source
        ), patch(
            "quant_agents.__main__.evaluate_secret_scan_receipt",
            return_value={
                "ok": False,
                "errors": ["secret scan receipt is missing"],
                "receipt_summary": {},
            },
        ), patch(
            "quant_agents.__main__.evaluate_data_license"
        ) as license_gate, patch(
            "quant_agents.__main__.evaluate_research_protocol"
        ) as protocol_gate, patch(
            "quant_agents.__main__.evaluate_execution_cost_evidence"
        ) as cost_gate, patch(
            "quant_agents.data_client.DataClient.health"
        ) as data_health, patch(
            "quant_agents.pi_client.PiClient.inspect_runtime"
        ) as pi_runtime, redirect_stdout(io.StringIO()):
            exit_code = cmd_health(self._args())
        self.assertEqual(exit_code, 1)
        license_gate.assert_not_called()
        protocol_gate.assert_not_called()
        cost_gate.assert_not_called()
        data_health.assert_not_called()
        pi_runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
