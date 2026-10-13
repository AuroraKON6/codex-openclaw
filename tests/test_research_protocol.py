from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from quant_agents.audit import canonical_json_sha256
from quant_agents.config import PROJECT_ROOT
from quant_agents.research_protocol import (
    ResearchProtocolGateError,
    build_model_contract_fingerprint,
    evaluate_research_protocol,
    is_release_eligible_research_protocol,
)

from test_input_validation import valid_input


class ResearchProtocolTests(unittest.TestCase):
    def test_exact_external_registration_passes(self):
        payload = valid_input()
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory, payload)
            gate = evaluate_research_protocol(
                payload,
                evidence_path=evidence_path,
                now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
            )
        self.assertEqual(gate["status"], "approved_for_backtest")
        self.assertEqual(gate["binding_mode"], "exact_registered_input")
        self.assertTrue(
            is_release_eligible_research_protocol(
                gate,
                input_fingerprint=canonical_json_sha256(payload),
                model_contract_fingerprint=build_model_contract_fingerprint(payload),
                today=datetime(2026, 8, 25).date(),
            )
        )

    def test_parameter_policy_without_external_evidence_fails(self):
        with self.assertRaisesRegex(
            ResearchProtocolGateError, "self-declaration"
        ):
            evaluate_research_protocol(valid_input(), evidence_path="")

    def test_mutated_strategy_contract_is_rejected(self):
        registered = valid_input()
        observed = copy.deepcopy(registered)
        observed["strategy_params"]["max_positions"] = 11
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory, registered)
            with self.assertRaisesRegex(
                ResearchProtocolGateError, "model_contract_sha256"
            ):
                evaluate_research_protocol(
                    observed,
                    evidence_path=evidence_path,
                    now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
                )

    def test_forward_refresh_preserves_registered_contract_and_origin(self):
        registered = valid_input()
        observed = copy.deepcopy(registered)
        observed["date_range"]["until"] = "20260825"
        observed["schedule_context"] = {
            "run_class": "forward_observation_refresh",
            "research_protocol_id": "CSI500-MOMENTUM-2026-001",
            "research_protocol_version": 1,
            "model_contract_sha256": build_model_contract_fingerprint(registered),
        }
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory, registered)
            gate = evaluate_research_protocol(
                observed,
                evidence_path=evidence_path,
                now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
            )
        self.assertEqual(gate["run_class"], "forward_observation_refresh")
        self.assertEqual(gate["binding_mode"], "forward_schedule_model_contract")

    def test_repository_local_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            evidence_path = self._write_evidence(directory, valid_input())
            with self.assertRaisesRegex(
                ResearchProtocolGateError, "outside the project"
            ):
                evaluate_research_protocol(
                    valid_input(),
                    evidence_path=evidence_path,
                    now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
                )

    def test_approval_roles_must_be_distinct(self):
        payload = valid_input()
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory, payload)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["approvals"][1]["approver"] = evidence["approvals"][0][
                "approver"
            ]
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(
                ResearchProtocolGateError, "three distinct people"
            ):
                evaluate_research_protocol(
                    payload,
                    evidence_path=evidence_path,
                    now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
                )

    @staticmethod
    def _write_evidence(directory: str, payload: dict) -> str:
        document_path = os.path.join(directory, "research-registry-export.pdf")
        document = b"test-only external research registry export"
        with open(document_path, "wb") as file:
            file.write(document)
        document_sha256 = hashlib.sha256(document).hexdigest()
        date_range = payload["date_range"]
        evidence = {
            "schema_version": 1,
            "status": "APPROVED_FOR_BACKTEST",
            "protocol_id": "CSI500-MOMENTUM-2026-001",
            "protocol_version": 1,
            "change_type": "initial_registration",
            "supersedes_protocol_id": "",
            "change_reason": "",
            "scope": "CSI500",
            "hypothesis_id": payload["validation_controls"]["hypothesis_id"],
            "parameter_selection_policy": "pre_registered_no_search",
            "parameter_search_count": 0,
            "registered_input_sha256": canonical_json_sha256(payload),
            "model_contract_sha256": build_model_contract_fingerprint(payload),
            "registered_date_range": date_range,
            "registered_at": "2026-08-20T09:00:00+00:00",
            "reviewed_at": "2026-08-20",
            "valid_from": "2026-08-20",
            "valid_until": "2027-02-20",
            "registered_before_execution_attested": True,
            "live_execution_authorized": False,
            "external_distribution_authorized": False,
            "system_of_record": {
                "type": "organization_research_registry_export",
                "record_id": "REG-2026-001",
                "record_reference": "research-registry://REG-2026-001",
            },
            "approvals": [
                {
                    "role": "quant_owner",
                    "decision": "APPROVED",
                    "approver": "Quant Owner",
                    "approved_at": "2026-08-20T10:00:00+00:00",
                    "evidence_reference": "APPROVAL-Q-001",
                },
                {
                    "role": "independent_model_validator",
                    "decision": "APPROVED",
                    "approver": "Independent Validator",
                    "approved_at": "2026-08-20T11:00:00+00:00",
                    "evidence_reference": "APPROVAL-V-001",
                },
                {
                    "role": "compliance_owner",
                    "decision": "APPROVED",
                    "approver": "Compliance Owner",
                    "approved_at": "2026-08-20T12:00:00+00:00",
                    "evidence_reference": "APPROVAL-C-001",
                },
            ],
            "forward_observation_controls": {
                "authorized": True,
                "observation_mode": "fixed_origin_forward",
                "warmup_since": date_range["since"],
                "baseline_cutoff": date_range["until"],
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
            },
            "supporting_document_type": "organization_research_registry_export",
            "supporting_document_path": document_path,
            "supporting_document_sha256": document_sha256,
            "limitations": [
                "Local validation binds the external record by hash but does not authenticate organizational identities or timestamps."
            ],
        }
        evidence_path = os.path.join(directory, "research-protocol-v1.json")
        with open(evidence_path, "w", encoding="utf-8") as file:
            json.dump(evidence, file)
        return evidence_path


if __name__ == "__main__":
    unittest.main()
