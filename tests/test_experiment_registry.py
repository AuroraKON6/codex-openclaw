from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from quant_agents.audit import canonical_json_sha256
from quant_agents.config import Config, PROJECT_ROOT
from quant_agents.experiment_registry import (
    ExperimentRegistryError,
    finalize_experiment,
    initialize_experiment_registry,
    registry_status,
    reserve_experiment,
    verify_experiment_registry_gate,
)
from quant_agents.research_protocol import build_model_contract_fingerprint

from test_input_validation import valid_input


class ExperimentRegistryTests(unittest.TestCase):
    now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)

    def test_external_registry_reserves_and_finalizes_one_run(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._initialize(directory)
            payload = valid_input()
            protocol = self._protocol_gate(payload)
            gate = reserve_experiment(
                registry,
                run_id="run-001",
                run_dir=os.path.join(PROJECT_ROOT, "runs", "run-001"),
                input_data=payload,
                source_provenance=self._source(),
                protocol_gate=protocol,
                request_id="request-001",
                now=self.now,
            )
            state = self._state(payload, protocol, gate)
            finalized = finalize_experiment(
                state, gate, now=self.now + timedelta(minutes=1)
            )
            state["business_controls"]["experiment_registry_gate"] = finalized
            with patch.object(Config, "EXPERIMENT_REGISTRY_PATH", registry):
                verification = verify_experiment_registry_gate(
                    state, now=self.now + timedelta(minutes=2)
                )
            status = registry_status(
                registry, now=self.now + timedelta(minutes=2)
            )
        self.assertTrue(verification["eligible"], verification["errors"])
        self.assertEqual(status["reservation_count"], 1)
        self.assertEqual(status["finalized_count"], 1)
        self.assertEqual(status["pending_reservations"], [])

    def test_reservation_and_finalization_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._initialize(directory)
            payload = valid_input()
            protocol = self._protocol_gate(payload)
            arguments = {
                "registry_dir": registry,
                "run_id": "run-001",
                "run_dir": os.path.join(PROJECT_ROOT, "runs", "run-001"),
                "input_data": payload,
                "source_provenance": self._source(),
                "protocol_gate": protocol,
                "request_id": "request-001",
                "now": self.now,
            }
            first = reserve_experiment(**arguments)
            second = reserve_experiment(**arguments)
            state = self._state(payload, protocol, first)
            final_first = finalize_experiment(
                state, first, now=self.now + timedelta(minutes=1)
            )
            state["business_controls"]["experiment_registry_gate"] = final_first
            final_second = finalize_experiment(
                state, final_first, now=self.now + timedelta(minutes=2)
            )
            status = registry_status(
                registry, now=self.now + timedelta(minutes=3)
            )
        self.assertEqual(second["append_status"], "no_op_already_reserved")
        self.assertEqual(final_second["append_status"], "no_op_already_finalized")
        self.assertEqual(status["entry_count"], 2)

    def test_failed_run_is_recorded_but_not_release_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._initialize(directory)
            payload = valid_input()
            protocol = self._protocol_gate(payload)
            gate = reserve_experiment(
                registry,
                "run-failed",
                os.path.join(PROJECT_ROOT, "runs", "run-failed"),
                payload,
                self._source(),
                protocol,
                now=self.now,
            )
            state = self._state(payload, protocol, gate)
            state["run_id"] = "run-failed"
            state["status"] = "preflight_failed"
            state["success_count"] = 0
            state["error_count"] = 7
            finalized = finalize_experiment(
                state, gate, now=self.now + timedelta(minutes=1)
            )
            state["business_controls"]["experiment_registry_gate"] = finalized
            with patch.object(Config, "EXPERIMENT_REGISTRY_PATH", registry):
                verification = verify_experiment_registry_gate(state, now=self.now)
            status = registry_status(registry, now=self.now)
        self.assertFalse(verification["eligible"])
        self.assertEqual(status["failed_or_blocked_count"], 1)
        self.assertEqual(status["pending_reservations"], [])

    def test_ledger_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._initialize(directory)
            payload = valid_input()
            reserve_experiment(
                registry,
                "run-001",
                os.path.join(PROJECT_ROOT, "runs", "run-001"),
                payload,
                self._source(),
                self._protocol_gate(payload),
                now=self.now,
            )
            ledger_path = os.path.join(registry, "experiments.jsonl")
            with open(ledger_path, encoding="utf-8") as file:
                entry = json.loads(file.readline())
            entry["source_head_commit"] = "f" * 40
            with open(ledger_path, "w", encoding="utf-8") as file:
                file.write(json.dumps(entry) + "\n")
            with self.assertRaisesRegex(ExperimentRegistryError, "hash mismatch"):
                registry_status(registry, now=self.now)

    def test_stale_unfinalized_reservation_requires_attention(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._initialize(directory)
            payload = valid_input()
            reserve_experiment(
                registry,
                "run-orphan",
                os.path.join(PROJECT_ROOT, "runs", "run-orphan"),
                payload,
                self._source(),
                self._protocol_gate(payload),
                now=self.now,
            )
            status = registry_status(
                registry,
                stale_hours=1,
                now=self.now + timedelta(hours=2),
            )
        self.assertFalse(status["ok"])
        self.assertEqual(status["stale_reservation_run_ids"], ["run-orphan"])

    def test_repository_local_registry_is_rejected_before_creation(self):
        with tempfile.TemporaryDirectory() as evidence_dir, tempfile.TemporaryDirectory(
            dir=PROJECT_ROOT
        ) as project_dir:
            evidence = self._write_evidence(evidence_dir)
            local_registry = os.path.join(project_dir, "registry")
            with self.assertRaisesRegex(ExperimentRegistryError, "outside"):
                initialize_experiment_registry(
                    evidence, local_registry, now=self.now
                )
            self.assertFalse(os.path.exists(local_registry))

    def _initialize(self, directory: str) -> str:
        evidence_dir = os.path.join(directory, "evidence")
        os.makedirs(evidence_dir)
        evidence = self._write_evidence(evidence_dir)
        registry = os.path.join(directory, "registry")
        initialize_experiment_registry(evidence, registry, now=self.now)
        return registry

    def _write_evidence(self, directory: str) -> str:
        document_path = os.path.join(directory, "registry-export.pdf")
        document = b"test-only external organization experiment registry export"
        with open(document_path, "wb") as file:
            file.write(document)
        evidence = {
            "schema_version": 1,
            "project_id": "csi500-quant-research",
            "registry_id": "ORG-CSI500-EXPERIMENTS-2026",
            "status": "ACTIVE",
            "registered_at": "2026-08-20T09:00:00+00:00",
            "valid_from": "2026-08-20",
            "valid_until": "2027-08-20",
            "system_of_record_reference": "research-registry://CSI500/2026",
            "allowed_run_classes": [
                "development_backtest",
                "forward_observation_refresh",
            ],
            "retention_days": 730,
            "append_only": True,
            "live_execution_authorized": False,
            "external_distribution_authorized": False,
            "approvals": [
                self._approval("quant_owner", "Quant Owner", "APP-Q-001", 10),
                self._approval(
                    "independent_model_validator",
                    "Independent Validator",
                    "APP-V-001",
                    11,
                ),
                self._approval(
                    "compliance_owner", "Compliance Owner", "APP-C-001", 12
                ),
                self._approval(
                    "platform_owner", "Platform Owner", "APP-P-001", 13
                ),
            ],
            "supporting_document_path": document_path,
            "supporting_document_sha256": hashlib.sha256(document).hexdigest(),
            "supporting_document_type": "organization_experiment_registry_export",
        }
        path = os.path.join(directory, "registry-evidence.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(evidence, file)
        return path

    @staticmethod
    def _approval(role: str, approver: str, reference: str, hour: int) -> dict:
        return {
            "role": role,
            "decision": "APPROVED",
            "approver": approver,
            "approved_at": f"2026-08-20T{hour:02d}:00:00+00:00",
            "evidence_reference": reference,
        }

    @staticmethod
    def _source() -> dict:
        return {
            "schema_version": 1,
            "release_ready": True,
            "head_commit": "a" * 40,
            "reason": "clean committed source baseline",
        }

    @staticmethod
    def _protocol_gate(payload: dict) -> dict:
        fingerprint = canonical_json_sha256(payload)
        return {
            "schema_version": 1,
            "status": "approved_for_backtest",
            "protocol_id": "test-protocol-v1",
            "protocol_version": 1,
            "change_type": "initial_registration",
            "scope": "CSI500",
            "hypothesis_id": "test-momentum-v1",
            "run_class": "development_backtest",
            "binding_mode": "exact_registered_input",
            "registered_input_sha256": fingerprint,
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
            "forward_observation_controls": {
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
                    "excess_return_at_or_below": -0.2,
                },
            },
            "limitations": ["test-only evidence"],
        }

    @staticmethod
    def _state(payload: dict, protocol: dict, gate: dict) -> dict:
        return {
            "run_id": "run-001",
            "input_fingerprint": canonical_json_sha256(payload),
            "request_id": "request-001",
            "retry_of": None,
            "runtime": "pi",
            "mock": False,
            "source_provenance": ExperimentRegistryTests._source(),
            "status": "completed",
            "success_count": 7,
            "error_count": 0,
            "data_mode": "REAL_TUSHARE",
            "metrics_source": "REAL_TUSHARE",
            "agent_outputs": {"data_agent": {"snapshot_id": "snapshot-001"}},
            "backtest_assurance": {
                "decision": "PASSED_FOR_INTERNAL_RESEARCH",
                "release_gate_passed": True,
            },
            "robustness_validation": {"decision": "PASSED", "failed_checks": []},
            "budget_gate": {"status": "passed"},
            "model_usage": {"total_tokens": 100, "budget_cost_usd": 0.01},
            "business_controls": {
                "research_protocol_gate": protocol,
                "experiment_registry_gate": gate,
                "broker_connection_enabled": False,
                "external_distribution_approved": False,
            },
        }


if __name__ == "__main__":
    unittest.main()
