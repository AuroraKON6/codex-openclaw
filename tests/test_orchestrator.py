import tempfile
import unittest
import os
import json
from unittest.mock import patch

from quant_agents.agents.data_agent import DataAgent
from quant_agents.orchestrator import (
    _generate_summary,
    _preflight_dependencies,
    _preflight_pi,
    run_pipeline,
)

from test_input_validation import valid_input


class OrchestratorTests(unittest.TestCase):
    def test_mock_summary_enforces_commercial_gate_order(self):
        state = {
            "mock": True,
            "runtime": "mock",
            "errors": [],
            "source_provenance": {
                "release_ready": False,
                "reason": "repository has no committed HEAD",
            },
            "agent_outputs": {
                "review_agent": {
                    "conclusion": "mock",
                    "trigger_level": "CRITICAL",
                    "key_risks": [],
                    "human_confirmation_needed": [],
                    "next_actions": ["配置并验证 TUSHARE_TOKEN"],
                    "disclaimer": "仅供研究，不构成真实资金买卖建议。",
                }
            },
            "agent_results": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            _generate_summary(state, directory)
            with open(os.path.join(directory, "summary.md"), encoding="utf-8") as file:
                summary = file.read()

        source_index = summary.index("先生成并校验 source review packet")
        roles_index = summary.index("任命 GM、Quant、Validator")
        evidence_index = summary.index("在仓库外完成数据授权")
        g1_index = summary.index("重跑 project-readiness")
        credentials_index = summary.index("G1 GO 前不得配置或调用真实 Tushare")
        baseline_index = summary.index("首个真实 7/7 baseline")
        self.assertEqual(
            [
                source_index,
                roles_index,
                evidence_index,
                g1_index,
                credentials_index,
                baseline_index,
            ],
            sorted(
                [
                    source_index,
                    roles_index,
                    evidence_index,
                    g1_index,
                    credentials_index,
                    baseline_index,
                ]
            ),
        )
        self.assertNotIn("\n- 配置并验证 TUSHARE_TOKEN\n", summary)

    def test_real_preflight_follows_commercial_gate_order(self):
        order = []

        def record(name, result):
            def callback(*args, **kwargs):
                order.append(name)
                return result

            return callback

        with patch(
            "quant_agents.orchestrator.inspect_python_runtime",
            side_effect=record("python_runtime", {"ok": True, "errors": []}),
        ), patch(
            "quant_agents.orchestrator.evaluate_secret_scan_receipt",
            side_effect=record(
                "secret_scan", {"ok": True, "errors": [], "receipt_summary": {}}
            ),
        ), patch(
            "quant_agents.orchestrator.evaluate_source_review_decision",
            side_effect=record(
                "source_review_decision",
                {
                    "review_claim_valid": True,
                    "status": "VALID_DUAL_FILE_REVIEW_CLAIM",
                    "packet_id": "packet",
                },
            ),
        ), patch(
            "quant_agents.orchestrator.evaluate_data_license",
            side_effect=record("license", {"status": "approved"}),
        ), patch(
            "quant_agents.orchestrator.evaluate_research_protocol",
            side_effect=record(
                "research_protocol",
                {
                    "status": "approved_for_backtest",
                    "protocol_id": "test-protocol",
                    "protocol_version": 1,
                },
            ),
        ), patch(
            "quant_agents.orchestrator.evaluate_experiment_registry",
            side_effect=record(
                "experiment_registry",
                {"status": "ready_for_reservation", "ledger_integrity_ok": True},
            ),
        ), patch(
            "quant_agents.orchestrator.build_policy_snapshot",
            side_effect=record(
                "market_rules", {"rulebook_sha256": "a" * 64, "policy_ids": ["test"]}
            ),
        ), patch(
            "quant_agents.orchestrator.evaluate_execution_cost_evidence",
            side_effect=record(
                "execution_cost",
                {
                    "status": "approved_for_internal_research",
                    "cost_model_fingerprint": "b" * 64,
                },
            ),
        ), patch(
            "quant_agents.orchestrator.Config.validate",
            side_effect=record("config", []),
        ), patch(
            "quant_agents.orchestrator.DataClient.health",
            side_effect=record("tushare", {"ok": True}),
        ), patch(
            "quant_agents.orchestrator._preflight_pi",
            side_effect=record("pi", []),
        ):
            preflight = _preflight_dependencies("pi", valid_input())

        self.assertEqual(
            order,
            [
                "python_runtime",
                "secret_scan",
                "source_review_decision",
                "license",
                "research_protocol",
                "experiment_registry",
                "market_rules",
                "execution_cost",
                "config",
                "tushare",
                "pi",
            ],
        )
        self.assertEqual(
            [row["name"] for row in preflight["checks"]],
            [
                "python_runtime_contract",
                "secret_scan",
                "source_review_decision",
                "data_license",
                "research_protocol_registration",
                "experiment_registry_reservation",
                "a_share_market_rules",
                "execution_cost_calibration",
                "tushare",
            ],
        )

    def test_reserved_experiment_is_finalized_when_later_preflight_fails(self):
        source = {
            "release_ready": True,
            "head_commit": "a" * 40,
            "reason": "clean committed source baseline",
        }
        reservation = {
            "status": "reserved",
            "registry_id": "registry-001",
            "registry_dir": "C:\\external-registry",
            "registry_metadata_sha256": "1" * 64,
            "reservation_entry_hash": "2" * 64,
            "ledger_integrity_ok": True,
            "live_execution_authorized": False,
            "external_distribution_authorized": False,
            "broker_connection_enabled": False,
        }
        finalized = {
            **reservation,
            "status": "finalized",
            "finalization_entry_hash": "3" * 64,
            "state_contract_sha256": "4" * 64,
        }
        protocol = {"status": "approved_for_backtest"}
        with tempfile.TemporaryDirectory() as directory, patch(
            "quant_agents.orchestrator.collect_source_provenance",
            return_value=source,
        ), patch(
            "quant_agents.orchestrator.evaluate_secret_scan_receipt",
            return_value={"ok": True, "errors": [], "receipt_summary": {}},
        ), patch(
            "quant_agents.orchestrator.evaluate_source_review_decision",
            return_value={
                "review_claim_valid": True,
                "status": "VALID_DUAL_FILE_REVIEW_CLAIM",
                "packet_id": "packet",
            },
        ), patch(
            "quant_agents.orchestrator.evaluate_data_license",
            return_value={"status": "approved"},
        ), patch(
            "quant_agents.orchestrator.evaluate_research_protocol",
            return_value=protocol,
        ), patch(
            "quant_agents.orchestrator.reserve_experiment",
            return_value=reservation,
        ), patch(
            "quant_agents.orchestrator.build_policy_snapshot",
            return_value={"rulebook_sha256": "a" * 64, "policy_ids": ["test"]},
        ), patch(
            "quant_agents.orchestrator.evaluate_execution_cost_evidence",
            side_effect=RuntimeError("cost gate failed"),
        ), patch(
            "quant_agents.orchestrator.finalize_experiment",
            return_value=finalized,
        ) as finalize, patch(
            "quant_agents.orchestrator.DataClient.health"
        ) as data_health, patch(
            "quant_agents.orchestrator._preflight_pi"
        ) as pi_preflight:
            with self.assertRaisesRegex(RuntimeError, "cost gate failed"):
                run_pipeline(valid_input(), directory, mock=False, runtime="pi")
            with open(os.path.join(directory, "state.json"), encoding="utf-8") as file:
                state = json.load(file)
        finalize.assert_called_once()
        data_health.assert_not_called()
        pi_preflight.assert_not_called()
        self.assertEqual(
            state["business_controls"]["experiment_registry_gate"]["status"],
            "finalized",
        )
        self.assertEqual(state["model_usage"]["total_tokens"], 0)

    def test_source_revision_blocks_before_external_preflight(self):
        source = {
            "release_ready": False,
            "reason": "repository has no committed HEAD",
        }
        with tempfile.TemporaryDirectory() as directory, patch(
            "quant_agents.orchestrator.collect_source_provenance",
            return_value=source,
        ), patch("quant_agents.orchestrator._preflight_dependencies") as preflight:
            with self.assertRaisesRegex(RuntimeError, "Source revision preflight failed"):
                run_pipeline(valid_input(), directory, mock=False, runtime="pi")
            preflight.assert_not_called()

    def test_pi_preflight_records_runtime_policy_and_live_ping(self):
        runtime = {
            "ok": True,
            "errors": [],
            "pi_package": "@earendil-works/pi-coding-agent",
            "pi_version": "0.84.2",
            "node_version": "24.16.0",
            "runtime_lock_sha256": "a" * 64,
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "model_available": True,
            "policy": {
                "all_tools_disabled": True,
                "extensions_disabled": True,
                "skills_disabled": True,
                "prompt_templates_disabled": True,
                "themes_disabled": True,
                "context_files_disabled": True,
                "project_resources_ignored": True,
                "startup_network_disabled": True,
            },
        }
        ping = {
            "ok": True,
            "parsed": {"status": "ok", "runtime": "pi"},
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "session_id": "session",
            "response_id": "response",
            "usage": {"totalTokens": 10},
        }
        with patch("quant_agents.orchestrator.PiClient.inspect_runtime", return_value=runtime), patch(
            "quant_agents.orchestrator.PiClient.ping", return_value=ping
        ):
            checks = _preflight_pi()
        self.assertEqual(
            [check["name"] for check in checks],
            [
                "pi_runtime_integrity",
                "pi_security_policy",
                "pi_model_catalog",
                "pi_llm_ping",
            ],
        )
        self.assertTrue(checks[1]["all_tools_disabled"])

    def test_failed_data_agent_blocks_downstream_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(DataAgent, "mock_execute", side_effect=RuntimeError("data failed")):
                state = run_pipeline(valid_input(), directory, mock=True, runtime="pi")
            statuses = {row["agent"]: row["status"] for row in state["agent_results"]}
            self.assertEqual(statuses["data_agent"], "error")
            self.assertEqual(statuses["strategy_agent"], "blocked")
            self.assertEqual(statuses["backtest_agent"], "blocked")
            self.assertEqual(statuses["review_agent"], "blocked")
            self.assertTrue(state["agent_outputs"]["review_agent"]["deterministic_fallback"])
            self.assertEqual(state["status"], "completed_with_errors")

    def test_duplicate_request_creates_failure_audit_and_requires_latest_retry(self):
        with tempfile.TemporaryDirectory() as runs_root:
            first_dir = os.path.join(runs_root, "run-1")
            state = run_pipeline(
                valid_input(), first_dir, mock=True, runtime="pi", request_id="request-1"
            )
            self.assertEqual(state["status"], "completed")
            second_dir = os.path.join(runs_root, "run-2")
            with self.assertRaisesRegex(RuntimeError, "already belongs"):
                run_pipeline(
                    valid_input(),
                    second_dir,
                    mock=True,
                    runtime="pi",
                    request_id="request-1",
                )
            self.assertTrue(os.path.isfile(os.path.join(second_dir, "run_manifest.json")))


if __name__ == "__main__":
    unittest.main()
