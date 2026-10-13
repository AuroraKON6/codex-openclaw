from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import date

from quant_agents.execution_cost_governance import (
    ExecutionCostGateError,
    evaluate_execution_cost_evidence,
    is_release_eligible_execution_cost,
)
from quant_agents.market_rules import load_market_rulebook
from quant_agents.config import PROJECT_ROOT
from test_input_validation import valid_input


class ExecutionCostGovernanceTests(unittest.TestCase):
    def test_valid_conservative_internal_research_evidence_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            result = evaluate_execution_cost_evidence(
                valid_input(), evidence_path=evidence_path, today=date(2026, 8, 25)
            )
            self.assertEqual(result["status"], "approved_for_internal_research")
            self.assertTrue(result["provisional"])
            self.assertFalse(result["live_execution_ready"])
            self.assertTrue(
                is_release_eligible_execution_cost(
                    result,
                    today=date(2026, 8, 25),
                )
            )

    def test_cost_model_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["calibrated_cost_model"]["slippage_bps"] = 1
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(ExecutionCostGateError, "does not match the run input"):
                evaluate_execution_cost_evidence(
                    valid_input(), evidence_path=evidence_path, today=date(2026, 8, 25)
                )

    def test_stale_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(
                directory,
                reviewed_at="2026-05-01",
            )
            with self.assertRaisesRegex(ExecutionCostGateError, "older than 90 days"):
                evaluate_execution_cost_evidence(
                    valid_input(), evidence_path=evidence_path, today=date(2026, 8, 25)
                )

    def test_independent_reviewer_must_be_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["independent_reviewer"] = evidence["quant_owner_approver"]
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(ExecutionCostGateError, "three distinct people"):
                evaluate_execution_cost_evidence(
                    valid_input(), evidence_path=evidence_path, today=date(2026, 8, 25)
                )

    def test_document_type_must_match_calibration_basis(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["supporting_document_type"] = "historical_execution_calibration_pack"
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(ExecutionCostGateError, "conservative assumptions require"):
                evaluate_execution_cost_evidence(
                    valid_input(), evidence_path=evidence_path, today=date(2026, 8, 25)
                )

    def test_conservative_basis_cannot_claim_execution_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["sample_order_count"] = 30
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(ExecutionCostGateError, "sample_order_count=0"):
                evaluate_execution_cost_evidence(
                    valid_input(), evidence_path=evidence_path, today=date(2026, 8, 25)
                )

    def test_repository_local_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            evidence_path = self._write_evidence(directory)
            with self.assertRaisesRegex(ExecutionCostGateError, "outside the project"):
                evaluate_execution_cost_evidence(
                    valid_input(), evidence_path=evidence_path, today=date(2026, 8, 25)
                )

    @staticmethod
    def _write_evidence(
        directory: str,
        reviewed_at: str = "2026-08-20",
    ) -> str:
        payload = valid_input()
        document = b"test-only broker schedule and internal cost calibration memo"
        document_path = os.path.join(directory, "cost-calibration.pdf")
        with open(document_path, "wb") as file:
            file.write(document)
        evidence = {
            "schema_version": 1,
            "status": "APPROVED_FOR_INTERNAL_RESEARCH",
            "scope": "CSI500",
            "calibration_basis": "approved_conservative_assumption",
            "provisional": True,
            "sample_order_count": 0,
            "calibrated_cost_model": payload["execution_controls"]["cost_model"],
            "simulation_notional_cny": payload["execution_controls"][
                "simulation_notional_cny"
            ],
            "max_participation_rate": payload["execution_controls"][
                "max_participation_rate"
            ],
            "minimum_daily_amount_cny": payload["execution_controls"][
                "minimum_daily_amount_cny"
            ],
            "market_rulebook_sha256": load_market_rulebook()[1],
            "double_cost_stress_required": True,
            "live_execution_ready": False,
            "quant_owner_approver": "Quant Owner",
            "independent_reviewer": "Independent Reviewer",
            "compliance_owner_approver": "Compliance Owner",
            "valid_from": "2026-01-01",
            "valid_until": "2027-12-31",
            "reviewed_at": reviewed_at,
            "supporting_document_type": "broker_fee_schedule_and_internal_cost_memo",
            "supporting_document_path": "cost-calibration.pdf",
            "supporting_document_sha256": hashlib.sha256(document).hexdigest(),
            "limitations": ["test-only provisional research assumption"],
        }
        evidence_path = os.path.join(directory, "execution-cost-evidence.json")
        with open(evidence_path, "w", encoding="utf-8") as file:
            json.dump(evidence, file)
        return evidence_path
