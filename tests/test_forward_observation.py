from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import patch

from quant_agents.audit import canonical_json_sha256, write_json_atomic
from quant_agents.forward_observation import (
    ForwardObservationError,
    _evaluate_observation_decision,
    campaign_status,
    close_campaign,
    initialize_campaign,
    record_observation,
)
from quant_agents.research_protocol import build_model_contract_fingerprint

from test_input_validation import valid_input


class ForwardObservationTests(unittest.TestCase):
    def setUp(self):
        self.registry_verification = patch(
            "quant_agents.forward_observation.verify_experiment_registry_gate",
            return_value={"eligible": True, "status": "passed"},
        ).start()
        self.addCleanup(patch.stopall)

    def test_blocked_baseline_does_not_create_campaign_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline_dir = self._write_baseline(directory)
            campaign_root = os.path.join(directory, "not-created")
            with patch(
                "quant_agents.forward_observation.verify_run_integrity",
                return_value={"ok": True, "manifest_snapshot_id": "b" * 64},
            ), patch(
                "quant_agents.forward_observation.verify_release_approval",
                return_value={"status": "REJECTED"},
            ), self.assertRaisesRegex(ForwardObservationError, "five-role approval"):
                initialize_campaign(
                    baseline_dir,
                    os.path.join(directory, "approval.json"),
                    campaign_root,
                )
            self.assertFalse(os.path.exists(campaign_root))

    def test_campaign_starts_blocked_without_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline_dir = self._write_baseline(directory)
            campaign_root = os.path.join(directory, "campaigns")
            with self._verified_release():
                result = initialize_campaign(
                    baseline_dir,
                    os.path.join(directory, "approval.json"),
                    campaign_root,
                    now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
                )
            self.assertEqual(result["status"], "BLOCKED_NO_FORWARD_OBSERVATIONS")
            self.assertTrue(result["ledger_integrity_ok"])
            self.assertFalse(result["live_execution_ready"])
            self.assertTrue(os.path.isfile(os.path.join(result["campaign_dir"], "campaign.json")))

    def test_record_is_idempotent_and_rejects_rewritten_history(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline_dir = self._write_baseline(directory)
            with self._verified_release():
                campaign = initialize_campaign(
                    baseline_dir,
                    os.path.join(directory, "approval.json"),
                    os.path.join(directory, "campaigns"),
                )
            first_run = self._write_observation_run(
                directory,
                "forward-1",
                campaign,
                [
                    self._point("20250530", 1.0, 1.0),
                    self._point("20250602", 1.01, 1.005),
                    self._point("20250603", 1.02, 1.006),
                ],
            )
            with self._verified_observation("c" * 64):
                recorded = record_observation(campaign["campaign_dir"], first_run)
                repeated = record_observation(campaign["campaign_dir"], first_run)
            self.assertEqual(recorded["append_status"], "recorded")
            self.assertEqual(recorded["status"], "OBSERVING_MINIMUM_NOT_MET")
            self.assertEqual(repeated["append_status"], "no_op_already_recorded")

            rewritten_run = self._write_observation_run(
                directory,
                "forward-2",
                campaign,
                [
                    self._point("20250530", 1.0, 1.0),
                    self._point("20250602", 0.99, 1.005),
                    self._point("20250603", 1.02, 1.006),
                    self._point("20250604", 1.03, 1.007),
                ],
            )
            with self._verified_observation("d" * 64), self.assertRaisesRegex(
                ForwardObservationError, "history changed"
            ):
                record_observation(campaign["campaign_dir"], rewritten_run)

    def test_ledger_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline_dir = self._write_baseline(directory)
            with self._verified_release():
                campaign = initialize_campaign(
                    baseline_dir,
                    os.path.join(directory, "approval.json"),
                    os.path.join(directory, "campaigns"),
                )
            run_dir = self._write_observation_run(
                directory,
                "forward-1",
                campaign,
                [
                    self._point("20250530", 1.0, 1.0),
                    self._point("20250602", 1.01, 1.005),
                ],
            )
            with self._verified_observation("e" * 64):
                record_observation(campaign["campaign_dir"], run_dir)
            ledger_path = os.path.join(campaign["campaign_dir"], "observations.jsonl")
            with open(ledger_path, encoding="utf-8") as file:
                entry = json.loads(file.readline())
            entry["metrics"]["strategy_return"] = 99
            with open(ledger_path, "w", encoding="utf-8") as file:
                file.write(json.dumps(entry) + "\n")
            with self.assertRaisesRegex(ForwardObservationError, "hash mismatch"):
                campaign_status(campaign["campaign_dir"])

    def test_decision_never_promotes_beyond_independent_validation(self):
        controls = self._forward_controls()
        eligible, checks = _evaluate_observation_decision(
            {
                "observation_trade_days": 60,
                "rebalance_count": 6,
                "excess_return": 0.03,
                "maximum_drawdown": -0.10,
                "cumulative_transaction_cost_ratio": 0.01,
            },
            controls,
        )
        paused, _ = _evaluate_observation_decision(
            {
                "observation_trade_days": 60,
                "rebalance_count": 6,
                "excess_return": -0.25,
                "maximum_drawdown": -0.40,
                "cumulative_transaction_cost_ratio": 0.01,
            },
            controls,
        )
        self.assertEqual(eligible, "ELIGIBLE_FOR_INDEPENDENT_VALIDATION")
        self.assertTrue(all(row["passed"] for row in checks[-3:]))
        self.assertEqual(paused, "PAUSE_REVIEW_REQUIRED")

    def test_external_three_role_closure_is_tamper_evident(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline_dir = self._write_baseline(directory)
            with self._verified_release():
                campaign = initialize_campaign(
                    baseline_dir,
                    os.path.join(directory, "approval.json"),
                    os.path.join(directory, "campaigns"),
                )
            document_path = os.path.join(directory, "closure-ticket.pdf")
            document = b"test-only campaign closure evidence"
            with open(document_path, "wb") as file:
                file.write(document)
            decision_path = os.path.join(directory, "closure.json")
            write_json_atomic(
                decision_path,
                {
                    "schema_version": 1,
                    "campaign_id": campaign["campaign_id"],
                    "decision": "RETIRED",
                    "effective_at": "2026-08-25T10:00:00+00:00",
                    "reason": "test retirement",
                    "evidence_reference": "CHANGE-001",
                    "live_execution_authorized": False,
                    "approvals": [
                        {
                            "role": role,
                            "decision": "APPROVED",
                            "approver": f"{role}-person",
                            "evidence_reference": f"APPROVAL-{role}",
                        }
                        for role in (
                            "model_owner",
                            "compliance_owner",
                            "platform_owner",
                        )
                    ],
                    "supporting_document_path": document_path,
                    "supporting_document_sha256": hashlib.sha256(document).hexdigest(),
                },
            )
            result = close_campaign(
                campaign["campaign_dir"],
                decision_path,
                now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(result["status"], "RETIRED")
            self.assertEqual(len(result["closure_file_sha256"]), 64)
            closure_path = os.path.join(campaign["campaign_dir"], "closure.json")
            with open(closure_path, encoding="utf-8") as file:
                closure = json.load(file)
            closure["reason"] = "tampered"
            write_json_atomic(closure_path, closure)
            with self.assertRaisesRegex(ForwardObservationError, "closure hash mismatch"):
                campaign_status(campaign["campaign_dir"])

    @staticmethod
    @contextmanager
    def _verified_release():
        with patch(
            "quant_agents.forward_observation.verify_run_integrity",
            return_value={"ok": True, "manifest_snapshot_id": "b" * 64},
        ), patch(
            "quant_agents.forward_observation.verify_release_approval",
            return_value={"status": "APPROVED_FOR_INTERNAL_REVIEW"},
        ):
            yield

    @staticmethod
    @contextmanager
    def _verified_observation(snapshot_id: str):
        with patch(
            "quant_agents.forward_observation.verify_run_integrity",
            return_value={"ok": True, "manifest_snapshot_id": snapshot_id},
        ), patch(
            "quant_agents.forward_observation.is_release_eligible_data_license",
            return_value=True,
        ), patch(
            "quant_agents.forward_observation.is_release_eligible_execution_cost",
            return_value=True,
        ), patch(
            "quant_agents.forward_observation.is_current_model_pricing",
            return_value=True,
        ):
            yield

    def _write_baseline(self, directory: str) -> str:
        baseline_dir = os.path.join(directory, "baseline")
        os.makedirs(baseline_dir)
        payload = valid_input()
        fingerprint = canonical_json_sha256(payload)
        gate = self._protocol_gate(payload, fingerprint, "development_backtest")
        state = {
            "schema_version": 7,
            "run_id": "baseline",
            "input_fingerprint": fingerprint,
            "input": payload,
            "pi_runtime": {
                "package": "pi",
                "version": "0.84.2",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
            },
            "config": {"deepseek_pricing": {"baseline_id": "test-pricing"}},
            "source_provenance": {
                "release_ready": True,
                "head_commit": "a" * 40,
            },
            "business_controls": {
                "research_protocol_gate": gate,
                "data_license_gate": {"evidence_file_sha256": "3" * 64},
                "execution_cost_gate": {
                    "cost_model_fingerprint": "4" * 64,
                    "evidence_file_sha256": "5" * 64,
                    "market_rulebook_sha256": "6" * 64,
                },
                "broker_connection_enabled": False,
                "external_distribution_approved": False,
            },
        }
        write_json_atomic(os.path.join(baseline_dir, "state.json"), state)
        write_json_atomic(os.path.join(baseline_dir, "input.json"), payload)
        return baseline_dir

    def _write_observation_run(
        self,
        directory: str,
        run_id: str,
        campaign: dict,
        equity_curve: list[dict],
    ) -> str:
        run_dir = os.path.join(directory, run_id)
        os.makedirs(os.path.join(run_dir, "backtest"))
        baseline_input = valid_input()
        payload = copy.deepcopy(baseline_input)
        payload["date_range"]["until"] = equity_curve[-1]["trade_date"]
        payload["schedule_context"] = {
            "run_class": "forward_observation_refresh",
            "campaign_id": campaign["campaign_id"],
            "resolved_trade_date": equity_curve[-1]["trade_date"],
            "research_protocol_id": "test-protocol-v1",
            "research_protocol_version": 1,
            "model_contract_sha256": build_model_contract_fingerprint(payload),
        }
        fingerprint = canonical_json_sha256(payload)
        gate = self._protocol_gate(payload, fingerprint, "forward_observation_refresh")
        state = {
            "schema_version": 7,
            "run_id": run_id,
            "status": "completed",
            "error_count": 0,
            "success_count": 7,
            "mock": False,
            "runtime": "pi",
            "data_mode": "REAL_TUSHARE",
            "metrics_source": "REAL_TUSHARE",
            "input": payload,
            "input_fingerprint": fingerprint,
            "pi_runtime": {
                "package": "pi",
                "version": "0.84.2",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
            },
            "config": {"deepseek_pricing": {"baseline_id": "test-pricing"}},
            "backtest_assurance": {
                "decision": "PASSED_FOR_INTERNAL_RESEARCH",
                "release_gate_passed": True,
            },
            "robustness_validation": {"decision": "PASSED", "failed_checks": []},
            "budget_gate": {"status": "passed"},
            "source_provenance": {
                "release_ready": True,
                "head_commit": "a" * 40,
            },
            "agent_outputs": {"data_agent": {"snapshot_id": "snapshot-1"}},
            "business_controls": {
                "research_protocol_gate": gate,
                "data_license_gate": {"evidence_file_sha256": "3" * 64},
                "execution_cost_gate": {
                    "cost_model_fingerprint": "4" * 64,
                    "evidence_file_sha256": "5" * 64,
                    "market_rulebook_sha256": "6" * 64,
                },
                "broker_connection_enabled": False,
                "external_distribution_approved": False,
            },
        }
        backtest = {
            "equity_curve": equity_curve,
            "rebalance_log": [
                {"effective_date": row["trade_date"]}
                for row in equity_curve
                if row["trade_date"] > "20250530"
            ],
        }
        write_json_atomic(os.path.join(run_dir, "state.json"), state)
        write_json_atomic(os.path.join(run_dir, "input.json"), payload)
        write_json_atomic(os.path.join(run_dir, "backtest", "backtest_agent.json"), backtest)
        return run_dir

    def _protocol_gate(
        self, payload: dict, fingerprint: str, run_class: str
    ) -> dict:
        baseline = valid_input()
        return {
            "schema_version": 1,
            "status": "approved_for_backtest",
            "protocol_id": "test-protocol-v1",
            "protocol_version": 1,
            "change_type": "initial_registration",
            "scope": "CSI500",
            "hypothesis_id": "test-momentum-v1",
            "run_class": run_class,
            "binding_mode": (
                "exact_registered_input"
                if run_class == "development_backtest"
                else "forward_schedule_model_contract"
            ),
            "registered_input_sha256": canonical_json_sha256(baseline),
            "evaluated_input_sha256": fingerprint,
            "model_contract_sha256": build_model_contract_fingerprint(payload),
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
            "registered_at": "2026-08-19T00:00:00+00:00",
            "reviewed_at": "2026-08-20",
            "valid_from": "2026-01-01",
            "valid_until": "2027-12-31",
            "forward_observation_controls": self._forward_controls(),
            "limitations": ["test-only evidence"],
        }

    @staticmethod
    def _forward_controls() -> dict:
        return {
            "authorized": True,
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
                "excess_return_at_or_below": -0.20,
            },
        }

    @staticmethod
    def _point(trade_date: str, strategy: float, benchmark: float) -> dict:
        return {
            "trade_date": trade_date,
            "strategy_index": strategy,
            "benchmark_index": benchmark,
            "invested_ratio": 0.9,
            "transaction_cost_ratio": 0.0001,
        }


if __name__ == "__main__":
    unittest.main()
