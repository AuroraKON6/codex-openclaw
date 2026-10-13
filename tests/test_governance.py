from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import date

from quant_agents.governance import (
    GovernanceGateError,
    evaluate_data_license,
    is_release_eligible_data_license,
)
from quant_agents.config import PROJECT_ROOT


def licensed_input():
    return {
        "governance": {
            "intended_use": "licensed_internal_research",
            "data_provider": "tushare",
            "external_distribution_requested": False,
            "human_review_required": True,
        }
    }


class GovernanceTests(unittest.TestCase):
    def test_public_terms_mode_stays_noncommercial(self):
        payload = licensed_input()
        payload["governance"]["intended_use"] = "personal_non_commercial_research"
        result = evaluate_data_license(payload)
        self.assertEqual(result["status"], "restricted_personal_non_commercial")
        self.assertFalse(result["commercial_use_permitted"])
        self.assertFalse(result["external_distribution_permitted"])

    def test_valid_signed_document_evidence_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            result = evaluate_data_license(
                licensed_input(), evidence_path=evidence_path, today=date(2026, 8, 13)
            )
            self.assertEqual(result["status"], "approved")
            self.assertTrue(result["commercial_use_permitted"])
            self.assertFalse(result["external_distribution_permitted"])
            self.assertEqual(len(result["evidence_file_sha256"]), 64)
            self.assertTrue(
                is_release_eligible_data_license(result, today=date(2026, 8, 13))
            )
            result["permitted_processors"] = []
            self.assertFalse(
                is_release_eligible_data_license(result, today=date(2026, 8, 13))
            )

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory, document_hash="0" * 64)
            with self.assertRaisesRegex(GovernanceGateError, "does not match"):
                evaluate_data_license(
                    licensed_input(), evidence_path=evidence_path, today=date(2026, 8, 13)
                )

    def test_expired_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory, valid_until="2026-08-12")
            with self.assertRaisesRegex(GovernanceGateError, "expired"):
                evaluate_data_license(
                    licensed_input(), evidence_path=evidence_path, today=date(2026, 8, 13)
                )

    def test_personal_terms_cannot_be_self_declared_as_organizational_license(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["separate_written_organizational_authorization"] = False
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(
                GovernanceGateError,
                "public Tushare terms are personal and non-commercial",
            ):
                evaluate_data_license(
                    licensed_input(), evidence_path=evidence_path, today=date(2026, 8, 13)
                )

    def test_retention_rights_must_cover_operational_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["maximum_retention_days"] = 30
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(GovernanceGateError, "RUN_RETENTION_DAYS"):
                evaluate_data_license(
                    licensed_input(), evidence_path=evidence_path, today=date(2026, 8, 13)
                )

    def test_stale_provider_terms_review_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = self._write_evidence(directory)
            with open(evidence_path, encoding="utf-8") as file:
                evidence = json.load(file)
            evidence["provider_terms_reviewed_at"] = "2026-06-01"
            with open(evidence_path, "w", encoding="utf-8") as file:
                json.dump(evidence, file)
            with self.assertRaisesRegex(GovernanceGateError, "terms review is stale"):
                evaluate_data_license(
                    licensed_input(), evidence_path=evidence_path, today=date(2026, 8, 13)
                )

    def test_repository_local_license_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            evidence_path = self._write_evidence(directory)
            with self.assertRaisesRegex(GovernanceGateError, "outside the project"):
                evaluate_data_license(
                    licensed_input(), evidence_path=evidence_path, today=date(2026, 8, 13)
                )

    def _write_evidence(
        self,
        directory: str,
        document_hash: str | None = None,
        valid_until: str = "2027-12-31",
    ) -> str:
        document_path = os.path.join(directory, "provider-approval.pdf")
        document = b"test-only signed provider approval artifact"
        with open(document_path, "wb") as file:
            file.write(document)
        actual_hash = hashlib.sha256(document).hexdigest()
        evidence = {
            "schema_version": 2,
            "provider": "tushare",
            "status": "APPROVED",
            "permitted_uses": ["licensed_internal_research"],
            "external_distribution_permitted": False,
            "licensee_legal_name": "Example Research Entity",
            "contract_reference": "CONTRACT-2026-001",
            "provider_approval_reference": "PROVIDER-APPROVAL-001",
            "provider_signatory_name": "Provider Signatory",
            "provider_signatory_title": "Enterprise Data Director",
            "licensee_approver_name": "Licensee Approver",
            "licensee_approver_title": "Data Owner",
            "separate_written_organizational_authorization": True,
            "organizational_use_permitted": True,
            "commercial_internal_research_permitted": True,
            "valid_from": "2026-01-01",
            "valid_until": valid_until,
            "provider_terms_url": "https://tushare.pro/document/1?doc_id=405",
            "provider_terms_reviewed_at": "2026-08-01",
            "permitted_endpoints": [
                "trade_cal",
                "index_weight",
                "daily",
                "adj_factor",
                "stk_limit",
                "suspend_d",
                "daily_basic",
            ],
            "permitted_processing": [
                "automated_api_access",
                "local_cache",
                "derived_analytics",
                "third_party_llm_processing",
            ],
            "permitted_processors": ["deepseek"],
            "maximum_retention_days": 365,
            "termination_disposition": "delete_or_return_per_provider_instruction",
            "supporting_document_type": "provider_signed_contract",
            "supporting_document_path": "provider-approval.pdf",
            "supporting_document_sha256": document_hash or actual_hash,
        }
        evidence_path = os.path.join(directory, "data-license.json")
        with open(evidence_path, "w", encoding="utf-8") as file:
            json.dump(evidence, file)
        return evidence_path


if __name__ == "__main__":
    unittest.main()
