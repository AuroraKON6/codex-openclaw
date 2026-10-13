import tempfile
import unittest
from pathlib import Path

from quant_agents.audit import canonical_json_sha256
from quant_agents.secret_scan import (
    REVIEW_MARKER,
    SCAN_RULES_VERSION,
    SCAN_SCHEMA_VERSION,
    SecretScanError,
    evaluate_receipt_against_scan,
    scan_candidate_files,
)


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class SecretScanTests(unittest.TestCase):
    def test_planted_assignment_is_reported_without_its_value(self):
        planted = "TUSHARE_TOKEN=abcdef1234567890abcdef1234567890"  # quant-secret-scan-allow
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "config/note.env", planted)
            findings, hashes = scan_candidate_files(["config/note.env"], root)
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["file"], "config/note.env")
        self.assertEqual(finding["line"], 1)
        self.assertEqual(finding["rule"], "tushare_token_assignment")
        self.assertFalse(finding["reviewed"])
        serialized = canonical_json_sha256(findings)
        self.assertNotIn(planted.split("=", 1)[1], serialized)
        self.assertEqual(len(hashes), 1)

    def test_common_secret_formats_are_detected(self):
        marker = "  # " + REVIEW_MARKER
        samples = {
            "private_key_block": "-----BEGIN RSA PRIVATE KEY-----",  # quant-secret-scan-allow
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",  # quant-secret-scan-allow
            "github_token": "ghp_0123456789abcdefghijklmnopqrstuvwxyz",  # quant-secret-scan-allow
            "bearer_style_api_key": "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6",  # quant-secret-scan-allow
            "jwt_token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dosdfsdfsdffsdfdsfsdfdsfsdfsdfdsfsdfdsf",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (rule, content) in enumerate(samples.items()):
                _write(root, f"sample_{index}.txt", "prefix\n" + content + marker + "\n")
            findings, _ = scan_candidate_files(
                [f"sample_{index}.txt" for index in range(len(samples))], root
            )
        reported = {finding["rule"] for finding in findings}
        for rule in samples:
            self.assertIn(rule, reported)
        for finding in findings:
            self.assertTrue(finding["reviewed"])

    def test_clean_source_yields_no_findings(self):
        content = (
            "DEEPSEEK_API_KEY=YOUR_KEY_HERE\n"
            "TUSHARE_TOKEN=PLACEHOLDER\n"
            "token = os.getenv(\"TUSHARE_TOKEN\", \"\")\n"
            "# See https://example.com/docs for details\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "settings.py", content)
            findings, _ = scan_candidate_files(["settings.py"], root)
        self.assertEqual(findings, [])

    def test_missing_candidate_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SecretScanError):
                scan_candidate_files(["missing.py"], Path(tmp))

    def _receipt_from(self, findings, hashes):
        unreviewed = sum(1 for finding in findings if not finding.get("reviewed"))
        receipt = {
            "schema_version": SCAN_SCHEMA_VERSION,
            "rules_version": SCAN_RULES_VERSION,
            "scanned_at": "2026-08-29T00:00:00+00:00",
            "candidate_file_count": len(hashes),
            "candidate_files_sha256": canonical_json_sha256(hashes),
            "finding_count": len(findings),
            "unreviewed_finding_count": unreviewed,
            "findings": findings,
            "status": "passed" if unreviewed == 0 else "failed",
        }
        receipt["receipt_sha256"] = canonical_json_sha256(receipt)
        return receipt

    def test_receipt_round_trip_passes_on_matching_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "clean.py", "value = 1 + 1\n")
            findings, hashes = scan_candidate_files(["clean.py"], root)
            receipt = self._receipt_from(findings, hashes)
            result = evaluate_receipt_against_scan(receipt, findings, hashes)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["receipt_summary"]["finding_count"], 0)

    def test_reviewed_marker_passes_until_a_new_unreviewed_hit_appears(self):
        marker = "  # " + REVIEW_MARKER
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "fixture.py", "AKIAIOSFODNN7EXAMPLE" + marker + "\n")  # quant-secret-scan-allow
            findings, hashes = scan_candidate_files(["fixture.py"], root)
            self.assertEqual(len(findings), 1)
            self.assertTrue(findings[0]["reviewed"])
            receipt = self._receipt_from(findings, hashes)
            result = evaluate_receipt_against_scan(receipt, findings, hashes)
            self.assertTrue(result["ok"], result["errors"])
            _write(root, "live.py", "AKIAIOSFODNN7EXAMPLE\n")  # quant-secret-scan-allow
            drifted_findings, drifted_hashes = scan_candidate_files(
                ["fixture.py", "live.py"], root
            )
        unreviewed = [
            finding for finding in drifted_findings if not finding["reviewed"]
        ]
        self.assertEqual(len(unreviewed), 1)
        result = evaluate_receipt_against_scan(receipt, drifted_findings, drifted_hashes)
        self.assertFalse(result["ok"])

    def test_source_drift_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "clean.py", "value = 1 + 1\n")
            receipt = self._receipt_from(*scan_candidate_files(["clean.py"], root))
            _write(root, "clean.py", "value = 2 + 2\n")
            findings, hashes = scan_candidate_files(["clean.py"], root)
            result = evaluate_receipt_against_scan(receipt, findings, hashes)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("changed after the secret scan" in error for error in result["errors"])
        )

    def test_tampered_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "clean.py", "value = 1\n")
            receipt = self._receipt_from(*scan_candidate_files(["clean.py"], root))
            findings, hashes = scan_candidate_files(["clean.py"], root)
        receipt["finding_count"] = 999
        result = evaluate_receipt_against_scan(receipt, findings, hashes)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("does not match its contents" in error for error in result["errors"])
        )

    def test_rules_version_drift_requires_rescan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "clean.py", "value = 1\n")
            receipt = self._receipt_from(*scan_candidate_files(["clean.py"], root))
            findings, hashes = scan_candidate_files(["clean.py"], root)
        receipt["rules_version"] = "2000-01-01.1"
        receipt["receipt_sha256"] = canonical_json_sha256(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
        result = evaluate_receipt_against_scan(receipt, findings, hashes)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("different rules" in error for error in result["errors"])
        )

    def test_receipt_cannot_claim_clean_when_findings_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "leak.py", "TUSHARE_TOKEN=abcdef1234567890abcdef\n")  # quant-secret-scan-allow
            findings, hashes = scan_candidate_files(["leak.py"], root)
            self.assertTrue(findings)
            receipt = self._receipt_from([], hashes)
            result = evaluate_receipt_against_scan(receipt, findings, hashes)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("do not match a fresh scan" in error for error in result["errors"])
        )


if __name__ == "__main__":
    unittest.main()
