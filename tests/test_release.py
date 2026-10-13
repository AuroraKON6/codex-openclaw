import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from quant_agents.orchestrator import run_pipeline
from quant_agents.release import (
    archive_run,
    build_retention_plan,
    prepare_release_candidate,
    verify_archive,
    verify_release_approval,
    verify_run_integrity,
)

from test_input_validation import valid_input


class ReleaseTests(unittest.TestCase):
    def test_mock_run_integrity_release_block_and_archive(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run-1")
            state = run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            self.assertEqual(state["schema_version"], 7)
            integrity = verify_run_integrity(run_dir)
            self.assertTrue(integrity["ok"], integrity["errors"])

            candidate = prepare_release_candidate(run_dir)
            self.assertEqual(candidate["status"], "BLOCKED")
            self.assertIn("mock runs are never releaseable", candidate["blockers"])
            self.assertIn(
                "deterministic backtest assurance did not pass",
                candidate["blockers"],
            )
            self.assertIn(
                "holdout, walk-forward, and stress validation did not pass",
                candidate["blockers"],
            )
            self.assertIn(
                "data-license gate lacks current organizational processing and retention rights",
                candidate["blockers"],
            )
            self.assertIn(
                "research protocol lacks current external registration and frozen-contract evidence",
                candidate["blockers"],
            )
            self.assertIn(
                "execution-cost calibration is not approved for internal research",
                candidate["blockers"],
            )

            approval_path = os.path.join(run_dir, "release", "approval_request.json")
            with open(approval_path, encoding="utf-8") as file:
                approval = json.load(file)
            approval["decision"] = "OPERATOR_DRAFT"
            with open(approval_path, "w", encoding="utf-8") as file:
                json.dump(approval, file)
            prepare_release_candidate(run_dir)
            with open(approval_path, encoding="utf-8") as file:
                preserved = json.load(file)
            self.assertEqual(preserved["decision"], "OPERATOR_DRAFT")

            archive_root = os.path.join(root, "archives")
            archived = archive_run(run_dir, archive_root)
            self.assertEqual(archived["status"], "archived")
            with zipfile.ZipFile(archived["archive"], "r") as archive:
                self.assertIsNone(archive.testzip())

    def test_manifest_detects_artifact_tamper(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run-1")
            run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            with open(os.path.join(run_dir, "summary.md"), "a", encoding="utf-8") as file:
                file.write("\nunauthorized change\n")
            integrity = verify_run_integrity(run_dir)
            self.assertFalse(integrity["ok"])
            self.assertTrue(any("summary.md" in error for error in integrity["errors"]))

    def test_tampered_candidate_cannot_bypass_current_release_gate(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run-1")
            run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            prepare_release_candidate(run_dir)
            candidate_path = os.path.join(run_dir, "release", "release_candidate.json")
            with open(candidate_path, encoding="utf-8") as file:
                candidate = json.load(file)
            candidate["status"] = "AWAITING_HUMAN_APPROVALS"
            candidate["blockers"] = []
            with open(candidate_path, "w", encoding="utf-8") as file:
                json.dump(candidate, file)
            approval_path = os.path.join(run_dir, "release", "approval_request.json")
            decision = verify_release_approval(run_dir, approval_path)
            self.assertEqual(decision["status"], "REJECTED")
            self.assertTrue(
                any("current release eligibility is blocked" in error for error in decision["errors"])
            )

    def test_uncommitted_source_revision_blocks_release(self):
        source = {
            "schema_version": 1,
            "head_commit": None,
            "dirty": True,
            "release_ready": False,
            "reason": "repository has no committed HEAD",
        }
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run-1")
            with patch(
                "quant_agents.orchestrator.collect_source_provenance",
                return_value=source,
            ):
                run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            candidate = prepare_release_candidate(run_dir)
            self.assertIn(
                "source revision is not a clean committed baseline",
                candidate["blockers"],
            )
            with open(os.path.join(run_dir, "run_manifest.json"), encoding="utf-8") as file:
                manifest = json.load(file)
            self.assertEqual(manifest["metadata"]["source_provenance"], source)

    def test_missing_python_runtime_evidence_blocks_release(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run-1")
            run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            state_path = os.path.join(run_dir, "state.json")
            with open(state_path, encoding="utf-8") as file:
                state = json.load(file)
            state["preflight"]["checks"] = [
                check
                for check in state["preflight"]["checks"]
                if check.get("name") != "python_runtime_contract"
            ]
            with open(state_path, "w", encoding="utf-8") as file:
                json.dump(state, file)

            candidate = prepare_release_candidate(run_dir)

        self.assertIn(
            "locked Windows CPython 3.11 project runtime evidence is missing or invalid",
            candidate["blockers"],
        )

    def test_existing_archive_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run-1")
            run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            archive_root = os.path.join(root, "archives")
            archived = archive_run(run_dir, archive_root)
            verification = verify_archive(
                archived["archive"], expected_sha256=archived["sha256"]
            )
            self.assertTrue(verification["ok"], verification["errors"])

            with open(archived["archive"], "ab") as file:
                file.write(b"unauthorized change")
            verification = verify_archive(archived["archive"])
            self.assertFalse(verification["ok"])
            with self.assertRaisesRegex(RuntimeError, "existing archive failed verification"):
                archive_run(run_dir, archive_root)

    def test_unmanifested_artifact_blocks_integrity_and_archive(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = os.path.join(root, "run-1")
            run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            with open(os.path.join(run_dir, "unexpected.bin"), "wb") as file:
                file.write(b"not manifested")
            integrity = verify_run_integrity(run_dir)
            self.assertFalse(integrity["ok"])
            self.assertTrue(
                any("unmanifested files" in error for error in integrity["errors"])
            )
            with self.assertRaisesRegex(RuntimeError, "failed integrity"):
                archive_run(run_dir, os.path.join(root, "archives"))

    def test_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            archive_path = os.path.join(root, "unsafe.zip")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "unsafe")
            result = verify_archive(archive_path)
            self.assertFalse(result["ok"])
            self.assertTrue(any("unsafe archive member" in error for error in result["errors"]))
            self.assertFalse(os.path.exists(os.path.join(root, "escape.txt")))

    def test_retention_plan_requires_backup_and_honors_legal_hold(self):
        with tempfile.TemporaryDirectory() as root:
            runs_root = os.path.join(root, "runs")
            run_dir = os.path.join(runs_root, "run-1")
            run_pipeline(valid_input(), run_dir, mock=True, runtime="pi")
            archive_root = os.path.join(root, "archives")

            before_backup = build_retention_plan(
                runs_root,
                archive_root,
                retention_days=365,
                now=datetime.now(timezone.utc) + timedelta(days=400),
            )
            self.assertFalse(before_backup["runs"][0]["eligible"])

            archive_run(run_dir, archive_root)
            after_backup = build_retention_plan(
                runs_root,
                archive_root,
                retention_days=365,
                now=datetime.now(timezone.utc) + timedelta(days=400),
            )
            self.assertTrue(after_backup["runs"][0]["eligible"])
            self.assertEqual(
                after_backup["runs"][0]["action"],
                "ELIGIBLE_FOR_MANUAL_DELETION",
            )
            self.assertFalse(after_backup["runs"][0]["deletion_performed"])

            os.makedirs(os.path.join(run_dir, "release"), exist_ok=True)
            with open(
                os.path.join(run_dir, "release", "legal_hold.json"),
                "w",
                encoding="utf-8",
            ) as file:
                json.dump({"active": True}, file)
            held = build_retention_plan(
                runs_root,
                archive_root,
                retention_days=365,
                now=datetime.now(timezone.utc) + timedelta(days=400),
            )
            self.assertFalse(held["runs"][0]["eligible"])
            self.assertIn("active legal hold", held["runs"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
