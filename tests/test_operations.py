import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from quant_agents.audit import canonical_json_sha256, write_json_atomic
from quant_agents.config import Config
from quant_agents.market_rules import load_market_rulebook
from quant_agents.operations import (
    ConcurrentRunError,
    DuplicateRequestError,
    RunLock,
    append_event,
    enforce_request_idempotency,
    evaluate_budget_gate,
    aggregate_model_usage,
    is_current_model_pricing,
    latest_run_status,
    recover_incomplete_runs,
    verify_event_chain,
)
from quant_agents.research_protocol import build_model_contract_fingerprint

from test_input_validation import valid_input


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.registry_verification = patch(
            "quant_agents.operations.verify_experiment_registry_gate",
            return_value={"eligible": True, "status": "passed"},
        ).start()
        self.addCleanup(patch.stopall)

    def test_lock_contention_and_stale_remote_reclaim(self):
        with tempfile.TemporaryDirectory() as runs_root:
            first = RunLock(runs_root, "run-1", os.path.join(runs_root, "run-1"))
            first.acquire()
            try:
                second = RunLock(runs_root, "run-2", os.path.join(runs_root, "run-2"))
                with self.assertRaises(ConcurrentRunError):
                    second.acquire()
                with open(first.lock_path, encoding="utf-8") as file:
                    metadata = json.load(file)
                metadata["hostname"] = "retired-worker"
                metadata["heartbeat_at"] = (
                    datetime.now(timezone.utc) - timedelta(hours=1)
                ).isoformat()
                write_json_atomic(first.lock_path, metadata)
                replacement = RunLock(
                    runs_root,
                    "run-3",
                    os.path.join(runs_root, "run-3"),
                    stale_seconds=1,
                )
                replacement.acquire()
                replacement.release()
                first.acquired = False
            finally:
                first.release()

    def test_event_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as run_dir:
            append_event(run_dir, "started", {"value": 1})
            append_event(run_dir, "finished", {"value": 2})
            path = os.path.join(run_dir, "operations", "events.jsonl")
            self.assertTrue(verify_event_chain(path)["ok"])
            with open(path, encoding="utf-8") as file:
                lines = file.readlines()
            event = json.loads(lines[0])
            event["details"]["value"] = 999
            lines[0] = json.dumps(event) + "\n"
            with open(path, "w", encoding="utf-8") as file:
                file.writelines(lines)
            result = verify_event_chain(path)
            self.assertFalse(result["ok"])
            self.assertTrue(any("hash mismatch" in error for error in result["errors"]))

    def test_request_retry_must_target_latest_failure(self):
        with tempfile.TemporaryDirectory() as runs_root:
            self._write_state(runs_root, "run-1", "req-1", "preflight_failed", "2026-01-01")
            with self.assertRaises(DuplicateRequestError):
                enforce_request_idempotency(runs_root, "req-1")
            enforce_request_idempotency(runs_root, "req-1", retry_of="run-1")
            self._write_state(
                runs_root, "run-2", "req-1", "completed_with_errors", "2026-01-02"
            )
            with self.assertRaisesRegex(DuplicateRequestError, "latest run is run-2"):
                enforce_request_idempotency(runs_root, "req-1", retry_of="run-1")
            enforce_request_idempotency(runs_root, "req-1", retry_of="run-2")

    def test_stale_running_state_is_recovered_not_resumed(self):
        with tempfile.TemporaryDirectory() as runs_root:
            run_dir = os.path.join(runs_root, "run-1")
            os.makedirs(run_dir)
            write_json_atomic(
                os.path.join(run_dir, "state.json"),
                {
                    "run_id": "run-1",
                    "status": "running",
                    "started_at": "2020-01-01T00:00:00+00:00",
                    "updated_at": "2020-01-01T00:00:00+00:00",
                    "total_agents": 7,
                    "success_count": 2,
                    "errors": [],
                },
            )
            recovered = recover_incomplete_runs(runs_root, stale_seconds=1)
            self.assertEqual(len(recovered), 1)
            with open(os.path.join(run_dir, "state.json"), encoding="utf-8") as file:
                state = json.load(file)
            self.assertEqual(state["status"], "interrupted")
            self.assertEqual(state["recovery"]["policy"], "mark_interrupted_no_in_place_resume")

    def test_budget_gate_blocks_excess_tokens(self):
        results = [{"agent": "test", "elapsed_s": 0.1, "usage": {"input": 20, "output": 1, "total": 21}}]
        with patch.object(Config, "MAX_LLM_TOTAL_TOKENS_PER_RUN", 10):
            gate = evaluate_budget_gate(results, None, 0.2)
        self.assertEqual(gate["status"], "failed")
        self.assertTrue(any("tokens" in breach for breach in gate["breaches"]))

    def test_budget_gate_uses_provider_reported_cost_when_higher(self):
        results = [
            {
                "agent": "test",
                "elapsed_s": 0.1,
                "usage": {
                    "input": 1,
                    "output": 1,
                    "totalTokens": 2,
                    "cost": {"total": 1.25},
                },
            }
        ]
        with patch.object(Config, "MAX_LLM_COST_USD_PER_RUN", 1.0):
            gate = evaluate_budget_gate(results, None, 0.2)
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["observed"]["budget_cost_usd"], 1.25)

    def test_estimated_cost_uses_peak_pricing_contingency(self):
        results = [
            {
                "agent": "test",
                "usage": {"input": 1_000_000, "output": 0, "total": 1_000_000},
            }
        ]
        with patch.object(Config, "DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M", 1.0), patch.object(
            Config, "DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER", 2.0
        ):
            usage = aggregate_model_usage(results)
        self.assertEqual(usage["estimated_cost_usd"], 1.0)
        self.assertEqual(usage["contingency_estimated_cost_usd"], 2.0)
        self.assertEqual(usage["budget_cost_usd"], 2.0)

    def test_pi_cache_categories_are_priced_without_double_subtraction(self):
        results = [
            {
                "agent": "test",
                "usage": {
                    "input": 100,
                    "cacheRead": 50,
                    "cacheWrite": 25,
                    "output": 20,
                    "totalTokens": 195,
                },
            }
        ]
        with patch.object(Config, "DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M", 1.0), patch.object(
            Config, "DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M", 0.1
        ), patch.object(Config, "DEEPSEEK_OUTPUT_USD_PER_M", 2.0):
            usage = aggregate_model_usage(results)
        self.assertEqual(usage["cache_miss_billable_tokens"], 125)
        self.assertEqual(usage["cache_read_tokens"], 50)
        self.assertEqual(usage["estimated_cost_usd"], 0.00017)

    def test_model_pricing_snapshot_rejects_tampering(self):
        state = {
            "config": Config.snapshot(),
            "model_usage": aggregate_model_usage([]),
        }
        self.assertTrue(is_current_model_pricing(state))
        state["model_usage"]["pricing"]["output_usd_per_m"] = 0.01
        self.assertFalse(is_current_model_pricing(state))

    def test_model_pricing_snapshot_rejects_unapproved_environment_rates(self):
        with patch.object(Config, "DEEPSEEK_OUTPUT_USD_PER_M", 0.87):
            state = {
                "config": Config.snapshot(),
                "model_usage": aggregate_model_usage([]),
            }
        self.assertFalse(is_current_model_pricing(state))

    def test_production_monitor_ignores_newer_mock_run(self):
        with tempfile.TemporaryDirectory() as runs_root:
            now = datetime.now(timezone.utc)
            self._write_monitor_state(
                runs_root,
                "real-run",
                mock=False,
                finished_at=(now - timedelta(minutes=30)).isoformat(),
            )
            self._write_monitor_state(
                runs_root,
                "mock-run",
                mock=True,
                finished_at=now.isoformat(),
            )
            with patch(
                "quant_agents.release.verify_run_integrity",
                return_value={"ok": True, "errors": [], "manifest_snapshot_id": "snapshot"},
            ):
                production = latest_run_status(runs_root)
                all_runs = latest_run_status(runs_root, include_mock=True)
            self.assertTrue(production["ok"], production["blockers"])
            self.assertEqual(production["run_id"], "real-run")
            self.assertEqual(production["scope"], "production_real_only")
            self.assertEqual(production["ignored_mock_count"], 1)
            self.assertEqual(all_runs["run_id"], "mock-run")
            self.assertFalse(all_runs["ok"])
            self.assertIn("mock run is not production evidence", all_runs["blockers"])

    def test_production_monitor_blocks_stale_run(self):
        with tempfile.TemporaryDirectory() as runs_root:
            self._write_monitor_state(
                runs_root,
                "real-run",
                mock=False,
                finished_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            )
            with patch(
                "quant_agents.release.verify_run_integrity",
                return_value={"ok": True, "errors": [], "manifest_snapshot_id": "snapshot"},
            ):
                result = latest_run_status(runs_root, max_age_hours=1)
            self.assertFalse(result["ok"])
            self.assertTrue(any("older than" in blocker for blocker in result["blockers"]))

    def test_production_monitor_blocks_unverified_experiment_registry(self):
        with tempfile.TemporaryDirectory() as runs_root:
            self._write_monitor_state(
                runs_root,
                "real-run",
                mock=False,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            self.registry_verification.return_value = {
                "eligible": False,
                "status": "failed",
                "errors": ["ledger mismatch"],
            }
            with patch(
                "quant_agents.release.verify_run_integrity",
                return_value={
                    "ok": True,
                    "errors": [],
                    "manifest_snapshot_id": "snapshot",
                },
            ):
                result = latest_run_status(runs_root)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["experiment_registry"])

    def test_production_monitor_binds_latest_run_to_forward_ledger(self):
        with tempfile.TemporaryDirectory() as runs_root:
            now = datetime.now(timezone.utc)
            self._write_monitor_state(
                runs_root,
                "real-run",
                mock=False,
                finished_at=now.isoformat(),
            )
            campaign = {
                "ledger_integrity_ok": True,
                "status": "OBSERVING_MINIMUM_NOT_MET",
                "protocol_id": "test-protocol-v1",
                "protocol_version": 1,
                "latest_observation": {"run_id": "real-run"},
            }
            with patch(
                "quant_agents.release.verify_run_integrity",
                return_value={"ok": True, "errors": [], "manifest_snapshot_id": "snapshot"},
            ), patch(
                "quant_agents.forward_observation.campaign_status",
                return_value=campaign,
            ):
                result = latest_run_status(
                    runs_root, campaign_dir=os.path.join(runs_root, "external-campaign")
                )
            self.assertTrue(result["ok"], result["blockers"])
            self.assertTrue(result["checks"]["forward_campaign_current_run"])

            campaign["status"] = "PAUSE_REVIEW_REQUIRED"
            with patch(
                "quant_agents.release.verify_run_integrity",
                return_value={"ok": True, "errors": [], "manifest_snapshot_id": "snapshot"},
            ), patch(
                "quant_agents.forward_observation.campaign_status",
                return_value=campaign,
            ):
                paused = latest_run_status(
                    runs_root, campaign_dir=os.path.join(runs_root, "external-campaign")
                )
            self.assertFalse(paused["ok"])
            self.assertTrue(
                any("requires intervention" in blocker for blocker in paused["blockers"])
            )

    @staticmethod
    def _write_state(runs_root, run_id, request_id, status, started_at):
        run_dir = os.path.join(runs_root, run_id)
        os.makedirs(run_dir)
        write_json_atomic(
            os.path.join(run_dir, "state.json"),
            {
                "schema_version": 7,
                "run_id": run_id,
                "request_id": request_id,
                "status": status,
                "started_at": started_at,
            },
        )

    @staticmethod
    def _write_monitor_state(runs_root, run_id, mock, finished_at):
        run_dir = os.path.join(runs_root, run_id)
        os.makedirs(os.path.join(run_dir, "operations"))
        market_rulebook_sha256 = load_market_rulebook()[1]
        input_data = valid_input()
        input_fingerprint = canonical_json_sha256(input_data)
        model_contract_sha256 = build_model_contract_fingerprint(input_data)
        run_finished_at = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        review_date = run_finished_at.date().isoformat()
        registered_at = (run_finished_at - timedelta(days=1)).isoformat()
        write_json_atomic(
            os.path.join(run_dir, "state.json"),
            {
                "schema_version": 7,
                "run_id": run_id,
                "status": "completed",
                "finished_at": finished_at,
                "mock": mock,
                "runtime": "mock" if mock else "pi",
                "success_count": 7,
                "error_count": 0,
                "data_mode": "MOCK" if mock else "REAL_TUSHARE",
                "metrics_source": "MOCK" if mock else "REAL_TUSHARE",
                "input": input_data,
                "input_fingerprint": input_fingerprint,
                "backtest_assurance": {
                    "decision": "NOT_APPLICABLE_MOCK"
                    if mock
                    else "PASSED_FOR_INTERNAL_RESEARCH",
                    "release_gate_passed": not mock,
                },
                "robustness_validation": {
                    "decision": "NOT_APPLICABLE_MOCK" if mock else "PASSED",
                    "failed_checks": ["real_tushare_metrics"] if mock else [],
                },
                "budget_gate": {
                    "status": "passed",
                    "observed": {"budget_cost_usd": 0.1},
                },
                "config": Config.snapshot(),
                "model_usage": aggregate_model_usage([]),
                "source_provenance": {"release_ready": not mock},
                "business_controls": {
                    "data_license_gate": {
                        "schema_version": 2,
                        "status": "mock" if mock else "approved",
                        "commercial_use_permitted": not mock,
                        "organizational_use_permitted": not mock,
                        "commercial_internal_research_permitted": not mock,
                        "separate_written_organizational_authorization": not mock,
                        "external_distribution_permitted": False,
                        "permitted_processing": [
                            "automated_api_access",
                            "derived_analytics",
                            "local_cache",
                            "third_party_llm_processing",
                        ],
                        "permitted_processors": ["deepseek"],
                        "maximum_retention_days": Config.RUN_RETENTION_DAYS,
                        "valid_from": "2026-01-01",
                        "valid_until": "2027-12-31",
                        "provider_terms_reviewed_at": review_date,
                        "identity_assurance": "document_hash_only_not_signature_authenticated",
                        "evidence_file_sha256": "b" * 64,
                        "supporting_document_sha256": "c" * 64,
                    },
                    "research_protocol_gate": {
                        "schema_version": 1,
                        "status": "mock" if mock else "approved_for_backtest",
                        "protocol_id": "test-protocol-v1",
                        "protocol_version": 1,
                        "change_type": "initial_registration",
                        "scope": "CSI500",
                        "hypothesis_id": "test-momentum-v1",
                        "run_class": "development_backtest",
                        "binding_mode": "exact_registered_input",
                        "registered_input_sha256": input_fingerprint,
                        "evaluated_input_sha256": input_fingerprint,
                        "model_contract_sha256": model_contract_sha256,
                        "approval_roles": [
                            "compliance_owner",
                            "independent_model_validator",
                            "quant_owner",
                        ],
                        "approval_evidence_references": ["a", "b", "c"],
                        "live_execution_authorized": False,
                        "external_distribution_authorized": False,
                        "identity_and_timestamp_assurance": "external_record_claim_bound_by_hash_not_cryptographically_authenticated",
                        "evidence_file_sha256": "1" * 64,
                        "supporting_document_sha256": "2" * 64,
                        "supporting_document_type": "organization_research_registry_export",
                        "registered_at": registered_at,
                        "reviewed_at": review_date,
                        "valid_from": "2026-01-01",
                        "valid_until": "2027-12-31",
                        "forward_observation_controls": {
                            "authorized": not mock,
                            "observation_mode": "fixed_origin_forward",
                            "warmup_since": "20250101",
                            "baseline_cutoff": "20250530",
                            "minimum_observation_trade_days": 60,
                            "minimum_rebalance_count": 3,
                            "review_frequency_trade_days": 5,
                            "promotion_thresholds": {
                                "minimum_excess_return": 0.0,
                                "maximum_drawdown": -0.25,
                                "maximum_cumulative_cost_ratio": 0.05,
                            },
                            "pause_thresholds": {
                                "drawdown_at_or_below": -0.35,
                                "excess_return_at_or_below": -0.2,
                            },
                        },
                        "limitations": ["test-only evidence"],
                    },
                    "execution_cost_gate": {
                        "schema_version": 1,
                        "status": "mock"
                        if mock
                        else "approved_for_internal_research",
                        "double_cost_stress_required": not mock,
                        "live_execution_ready": False,
                        "cost_model_id": "test-cost-v1",
                        "cost_model_fingerprint": "d" * 64,
                        "market_rulebook_sha256": market_rulebook_sha256,
                        "evidence_file_sha256": "e" * 64,
                        "supporting_document_sha256": "f" * 64,
                        "supporting_document_type": "broker_fee_schedule_and_internal_cost_memo",
                        "calibration_basis": "approved_conservative_assumption",
                        "sample_order_count": 0,
                        "valid_from": "2026-01-01",
                        "valid_until": "2027-12-31",
                        "reviewed_at": review_date,
                        "identity_assurance": "document_hash_only_not_approver_identity_authenticated",
                        "provisional": True,
                        "limitations": ["test-only provisional evidence"],
                    },
                    "broker_connection_enabled": False,
                    "external_distribution_approved": False,
                },
                "preflight": {
                    "checks": []
                    if mock
                    else [
                        {
                            "name": "a_share_market_rules",
                            "status": "ok",
                            "detail": {
                                "rulebook_sha256": market_rulebook_sha256,
                                "policy_ids": ["cn-a-share-2026-07-06"],
                            },
                        },
                        {
                            "name": "research_protocol_registration",
                            "status": "ok",
                            "detail": {
                                "evidence_file_sha256": "1" * 64,
                                "model_contract_sha256": model_contract_sha256,
                            },
                        },
                        {
                            "name": "execution_cost_calibration",
                            "status": "ok",
                            "detail": {"cost_model_fingerprint": "d" * 64},
                        },
                        {
                            "name": "pi_llm_ping",
                            "status": "ok",
                            "provider": "deepseek",
                            "model": Config.DEEPSEEK_MODEL,
                        }
                    ]
                },
            },
        )
        write_json_atomic(
            os.path.join(run_dir, "operations", "alerts.json"),
            {"schema_version": 1, "alerts": []},
        )


if __name__ == "__main__":
    unittest.main()
