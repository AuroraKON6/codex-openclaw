import csv
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quant_agents.__main__ import (
    cmd_source_review_decision_template,
    cmd_source_review_decision_verify,
    cmd_source_review_packet,
    cmd_source_review_verify,
)
from quant_agents.audit import canonical_json_sha256, sha256_file
from quant_agents.source_baseline import (
    SOURCE_CANDIDATE_POLICY_VERSION,
    SourceCandidateError,
)
from quant_agents.source_review import (
    SourceReviewPacketError,
    build_source_review_decision_template,
    build_source_review_packet,
    evaluate_source_review_decision,
    verify_source_review_packet,
)


class SourceReviewPacketTests(unittest.TestCase):
    def test_packet_binds_manifest_checklist_and_instructions(self):
        manifest = self._manifest()
        current = datetime(2026, 9, 5, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
                now=current,
            )
            packet_dir = Path(result["packet_dir"])
            packet_manifest = json.loads(
                (packet_dir / "packet_manifest.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                set(packet_manifest["artifact_hashes"]),
                {
                    "candidate_manifest.json",
                    "review_request.json",
                    "review_checklist.csv",
                    "REVIEW_INSTRUCTIONS.md",
                },
            )
            for name, expected_hash in packet_manifest["artifact_hashes"].items():
                self.assertEqual(sha256_file(str(packet_dir / name)), expected_hash)
            verification = verify_source_review_packet(packet_dir)

        self.assertEqual(
            result["status"], "AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED"
        )
        self.assertFalse(result["source_baseline_authorized"])
        self.assertFalse(result["git_actions_performed"])
        self.assertTrue(verification["ok"], verification["errors"])
        self.assertTrue(verification["application_hash_only_not_signature"])

    def test_checklist_is_formula_safe_and_has_blank_human_fields(self):
        manifest = self._manifest(path="=danger.py")
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )
            with Path(result["packet_dir"], "review_checklist.csv").open(
                encoding="utf-8-sig", newline=""
            ) as file:
                row = next(csv.DictReader(file))

        self.assertEqual(row["path"], "'=danger.py")
        self.assertEqual(row["human_decision"], "")
        self.assertEqual(row["reviewer_note"], "")

    def test_tampered_candidate_identity_blocks_packet_creation(self):
        manifest = self._manifest()
        manifest["files"][0]["sha256"] = "f" * 64
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["packet_created"])
        self.assertTrue(any("identity" in error for error in result["errors"]))

    def test_existing_packet_is_never_overwritten(self):
        manifest = self._manifest()
        current = datetime(2026, 9, 5, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
                now=current,
            )
            with self.assertRaises(SourceReviewPacketError):
                build_source_review_packet(
                    project_root=project,
                    output_root=output,
                    candidate_manifest=manifest,
                    now=current,
                )

    def test_packet_verifier_detects_artifact_tampering(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )
            checklist = Path(result["packet_dir"], "review_checklist.csv")
            with checklist.open("a", encoding="utf-8") as file:
                file.write("tampered\n")
            verification = verify_source_review_packet(result["packet_dir"])

        self.assertFalse(verification["ok"])
        self.assertEqual(verification["status"], "TAMPERED_OR_INVALID")
        self.assertTrue(any("hash mismatch" in error for error in verification["errors"]))

    def test_packet_verifier_rejects_recomputed_weakened_review_controls(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )
            packet_dir = Path(result["packet_dir"])
            request_path = packet_dir / "review_request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["required_review_roles"] = ["PLATFORM_REVIEWER"]
            request_path.write_text(json.dumps(request), encoding="utf-8")

            packet_path = packet_dir / "packet_manifest.json"
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["artifact_hashes"]["review_request.json"] = sha256_file(
                str(request_path)
            )
            identity = {
                "schema_version": packet["schema_version"],
                "generated_at": packet["generated_at"],
                "candidate_manifest_sha256": packet["candidate_manifest_sha256"],
                "candidate_files_sha256": packet["candidate_files_sha256"],
                "artifact_hashes": packet["artifact_hashes"],
            }
            packet["packet_id"] = canonical_json_sha256(identity)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            verification = verify_source_review_packet(packet_dir)

        self.assertFalse(verification["ok"])
        self.assertIn("review request control claims are invalid", verification["errors"])

    def test_packet_verifier_handles_malformed_inventory_without_crashing(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )
            packet_dir = Path(result["packet_dir"])
            candidate_path = packet_dir / "candidate_manifest.json"
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["files"] = {"not": "a list"}
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            verification = verify_source_review_packet(packet_dir)

        self.assertFalse(verification["ok"])
        self.assertEqual(verification["candidate_file_count"], 0)

    def test_packet_verifier_handles_invalid_byte_count_without_crashing(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )
            candidate_path = Path(result["packet_dir"], "candidate_manifest.json")
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["files"][0]["bytes"] = "invalid"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            verification = verify_source_review_packet(result["packet_dir"])

        self.assertFalse(verification["ok"])
        self.assertTrue(
            any("invalid byte count" in error for error in verification["errors"])
        )

    def test_in_project_packet_root_must_be_git_ignored(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch(
                "quant_agents.source_baseline.subprocess.run"
            ) as run:
                run.return_value.returncode = 1
                with self.assertRaises(SourceCandidateError):
                    build_source_review_packet(
                        project_root=root,
                        output_root=root / "review-packets",
                        candidate_manifest=manifest,
                    )

    def test_cli_uses_blocked_exit_without_claiming_authorization(self):
        args = SimpleNamespace(
            output_root=None,
            secret_receipt=None,
            max_file_bytes=1024,
        )
        result = {
            "status": "BLOCKED",
            "packet_created": False,
            "source_baseline_authorized": False,
        }
        with mock.patch(
            "quant_agents.__main__.build_source_review_packet",
            return_value=result,
        ), redirect_stdout(io.StringIO()) as output:
            exit_code = cmd_source_review_packet(args)

        self.assertEqual(exit_code, 3)
        self.assertFalse(json.loads(output.getvalue())["source_baseline_authorized"])

    def test_cli_verifier_returns_blocked_exit_for_invalid_packet(self):
        args = SimpleNamespace(packet_dir="invalid")
        result = {
            "status": "TAMPERED_OR_INVALID",
            "ok": False,
            "source_baseline_authorized": False,
        }
        with mock.patch(
            "quant_agents.__main__.verify_source_review_packet",
            return_value=result,
        ), redirect_stdout(io.StringIO()) as output:
            exit_code = cmd_source_review_verify(args)

        self.assertEqual(exit_code, 3)
        self.assertFalse(json.loads(output.getvalue())["source_baseline_authorized"])

    def test_decision_template_is_blank_and_binds_every_file(self):
        manifest = self._manifest(
            review_flags=[
                {"code": "EXAMPLE_MUST_NOT_BE_APPROVAL_EVIDENCE", "path": "src/app.py"}
            ]
        )
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            packet = build_source_review_packet(
                project_root=project,
                output_root=Path(output) / "packets",
                candidate_manifest=manifest,
                now=datetime(2026, 9, 5, tzinfo=timezone.utc),
            )
            template = build_source_review_decision_template(
                packet["packet_dir"],
                output_path=Path(output) / "decision-template.json",
                project_root=project,
                now=datetime(2026, 9, 5, 1, tzinfo=timezone.utc),
            )
            payload = json.loads(
                Path(template["template_path"]).read_text(encoding="utf-8")
            )

        self.assertEqual(template["status"], "TEMPLATE_CREATED_NOT_REVIEW_EVIDENCE")
        self.assertTrue(template["human_fields_blank"])
        self.assertEqual(len(payload["file_reviews"]), 1)
        self.assertEqual(len(payload["review_flag_resolutions"]), 1)
        self.assertEqual(payload["reviewers"][0]["reviewer_subject_id"], "")
        self.assertFalse(payload["private_baseline_execution_authorized"])

    def test_valid_external_decision_is_only_a_review_claim(self):
        manifest = self._manifest(
            review_flags=[
                {"code": "SUSPICIOUS_FILENAME_REQUIRES_REVIEW", "path": "src/app.py"}
            ]
        )
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            decision_path = self._completed_decision(
                project, output, manifest, flagged=True
            )
            result = evaluate_source_review_decision(
                packet_dir=self._packet_dir,
                decision_path=decision_path,
                project_root=project,
                current_candidate_manifest=manifest,
                now=datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            )

        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(result["review_claim_valid"])
        self.assertFalse(result["organization_identity_verified"])
        self.assertFalse(result["private_baseline_execution_authorized"])
        self.assertFalse(result["source_baseline_authorized"])

    def test_decision_rejects_same_reviewer_identity(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            decision_path = self._completed_decision(project, output, manifest)
            payload = json.loads(Path(decision_path).read_text(encoding="utf-8"))
            payload["reviewers"][1]["reviewer_subject_id"] = payload["reviewers"][0][
                "reviewer_subject_id"
            ]
            Path(decision_path).write_text(
                json.dumps(payload), encoding="utf-8"
            )
            result = evaluate_source_review_decision(
                self._packet_dir,
                decision_path,
                project,
                current_candidate_manifest=manifest,
                now=datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any("distinct identities" in error for error in result["errors"])
        )

    def test_decision_rejects_file_hash_mismatch(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            decision_path = self._completed_decision(project, output, manifest)
            payload = json.loads(Path(decision_path).read_text(encoding="utf-8"))
            payload["file_reviews"][0]["sha256"] = "f" * 64
            Path(decision_path).write_text(
                json.dumps(payload), encoding="utf-8"
            )
            result = evaluate_source_review_decision(
                self._packet_dir,
                decision_path,
                project,
                current_candidate_manifest=manifest,
                now=datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            )

        self.assertFalse(result["ok"])
        self.assertTrue(
            any("does not match the candidate inventory" in error for error in result["errors"])
        )

    def test_decision_rejects_unresolved_machine_flag(self):
        manifest = self._manifest(
            review_flags=[
                {"code": "SUSPICIOUS_FILENAME_REQUIRES_REVIEW", "path": "src/app.py"}
            ]
        )
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            decision_path = self._completed_decision(
                project, output, manifest, flagged=True
            )
            payload = json.loads(Path(decision_path).read_text(encoding="utf-8"))
            payload["review_flag_resolutions"][0]["resolution"] = "UNRESOLVED"
            Path(decision_path).write_text(
                json.dumps(payload), encoding="utf-8"
            )
            result = evaluate_source_review_decision(
                self._packet_dir,
                decision_path,
                project,
                current_candidate_manifest=manifest,
                now=datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            )

        self.assertFalse(result["ok"])
        self.assertTrue(any("must be RESOLVED" in error for error in result["errors"]))

    def test_decision_must_be_external_and_candidate_must_be_current(self):
        manifest = self._manifest()
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            decision_path = self._completed_decision(project, output, manifest)
            local_decision = Path(project) / "decision.json"
            shutil.copyfile(decision_path, local_decision)
            result = evaluate_source_review_decision(
                self._packet_dir,
                local_decision,
                project,
                current_candidate_manifest=manifest,
                now=datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            )
            changed = json.loads(Path(decision_path).read_text(encoding="utf-8"))
            changed_manifest = json.loads(json.dumps(manifest))
            changed_manifest["files"][0]["bytes"] = 13
            stale_result = evaluate_source_review_decision(
                self._packet_dir,
                decision_path,
                project,
                current_candidate_manifest=changed_manifest,
                now=datetime(2026, 9, 5, 4, tzinfo=timezone.utc),
            )

        self.assertFalse(result["ok"])
        self.assertTrue(any("outside the project" in error for error in result["errors"]))
        self.assertFalse(stale_result["ok"])
        self.assertTrue(
            any("exactly match the reviewed packet" in error for error in stale_result["errors"])
        )

    def test_decision_cli_uses_strict_exit_codes(self):
        template_args = SimpleNamespace(
            packet_dir="packet",
            output="decision.json",
        )
        template_result = {
            "status": "TEMPLATE_CREATED_NOT_REVIEW_EVIDENCE",
            "template_created": True,
            "source_baseline_authorized": False,
        }
        with mock.patch(
            "quant_agents.__main__.build_source_review_decision_template",
            return_value=template_result,
        ), redirect_stdout(io.StringIO()) as output:
            template_exit = cmd_source_review_decision_template(template_args)
        self.assertEqual(template_exit, 0)
        self.assertEqual(json.loads(output.getvalue()), template_result)

        verify_args = SimpleNamespace(
            packet_dir="packet", decision="decision.json", secret_receipt=None
        )
        verify_result = {
            "status": "BLOCKED_OR_INVALID",
            "review_claim_valid": False,
            "source_baseline_authorized": False,
        }
        with mock.patch(
            "quant_agents.__main__.evaluate_source_review_decision",
            return_value=verify_result,
        ), redirect_stdout(io.StringIO()) as output:
            verify_exit = cmd_source_review_decision_verify(verify_args)
        self.assertEqual(verify_exit, 3)
        self.assertEqual(json.loads(output.getvalue()), verify_result)

    def test_decision_verifier_converts_packet_exception_to_blocked_result(self):
        with mock.patch(
            "quant_agents.source_review.verify_source_review_packet",
            side_effect=OSError("packet unavailable"),
        ):
            result = evaluate_source_review_decision(
                packet_dir="packet",
                decision_path="D:/controlled/decision.json",
                project_root="E:/project",
            )

        self.assertFalse(result["ok"])
        self.assertTrue(any("packet verification failed" in error for error in result["errors"]))

    def test_packet_rejects_malformed_top_level_review_flag(self):
        manifest = self._manifest()
        manifest["review_flags"] = ["not-an-object"]
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(
            any("review flag row is not an object" in error for error in result["errors"])
        )

    def test_packet_rejects_review_flag_not_bound_to_file_row(self):
        manifest = self._manifest(
            review_flags=[
                {
                    "code": "SUSPICIOUS_FILENAME_REQUIRES_REVIEW",
                    "path": "other.py",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as output:
            result = build_source_review_packet(
                project_root=project,
                output_root=output,
                candidate_manifest=manifest,
            )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(
            any("inconsistent with file rows" in error for error in result["errors"])
        )

    @staticmethod
    def _manifest(path="src/app.py", review_flags=None):
        review_flags = review_flags or []
        files = [
            {
                "path": path,
                "category": "python_control_plane",
                "extension": ".py",
                "bytes": 12,
                "sha256": "a" * 64,
                "binary": False,
                "link_or_reparse": False,
                "review_flags": [flag["code"] for flag in review_flags],
            }
        ]
        candidate_files_sha256 = canonical_json_sha256({path: "a" * 64})
        identity = {
            "schema_version": 1,
            "policy_version": SOURCE_CANDIDATE_POLICY_VERSION,
            "max_file_bytes": 1024,
            "candidate_files_sha256": candidate_files_sha256,
            "files": files,
            "secret_scan_receipt_sha256": "b" * 64,
        }
        return {
            "schema_version": 1,
            "policy_version": SOURCE_CANDIDATE_POLICY_VERSION,
            "status": "READY_FOR_HUMAN_FILE_REVIEW_NOT_AUTHORIZED",
            "ready_for_human_file_review": True,
            "source_baseline_authorized": False,
            "source_release_ready": False,
            "human_review_required": True,
            "git_actions": {
                "git_add_performed": False,
                "commit_performed": False,
                "tag_performed": False,
                "remote_created": False,
            },
            "policy": {"max_file_bytes": 1024},
            "summary": {
                "candidate_file_count": 1,
                "candidate_total_bytes": 12,
                "blocker_count": 0,
                "review_flag_count": len(review_flags),
            },
            "candidate_files_sha256": candidate_files_sha256,
            "manifest_sha256": canonical_json_sha256(identity),
            "secret_scan": {
                "ok": True,
                "receipt_summary": {"receipt_sha256": "b" * 64},
            },
            "blockers": [],
            "review_flags": review_flags,
            "files": files,
        }

    def _completed_decision(self, project, output, manifest, flagged=False):
        packet = build_source_review_packet(
            project_root=project,
            output_root=Path(output) / "packets",
            candidate_manifest=manifest,
            now=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
        self._packet_dir = packet["packet_dir"]
        template = build_source_review_decision_template(
            self._packet_dir,
            output_path=Path(output) / "decision.json",
            project_root=project,
            now=datetime(2026, 9, 5, 1, tzinfo=timezone.utc),
        )
        path = Path(template["template_path"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(
            {
                "record_state": "COMPLETED_EXTERNAL_REVIEW_RECORD",
                "external_review_system": "organization-review-system",
                "external_review_record_id": "SRC-REVIEW-001",
                "review_outcome": "DUAL_FILE_REVIEW_PASSED",
                "completed_at": "2026-09-05T03:00:00+00:00",
                "constraints_acknowledged": {
                    key: True for key in payload["constraints_acknowledged"]
                },
            }
        )
        for index, reviewer in enumerate(payload["reviewers"], start=1):
            reviewer.update(
                {
                    "reviewer_subject_id": f"reviewer-{index}",
                    "organization_identity_evidence_ref": f"IDENTITY-{index}",
                    "review_system_record_id": f"RECORD-{index}",
                    "reviewed_at": f"2026-09-05T0{index}:30:00+00:00",
                    "decision": "APPROVED",
                    "every_file_reviewed": True,
                    "reviewed_file_count": len(manifest["files"]),
                    "candidate_manifest_sha256": manifest["manifest_sha256"],
                    "candidate_files_sha256": manifest["candidate_files_sha256"],
                }
            )
        for row in payload["file_reviews"]:
            row.update(
                {
                    "platform_decision": "APPROVED",
                    "security_decision": "APPROVED",
                    "platform_evidence_ref": "FILE-PLATFORM-001",
                    "security_evidence_ref": "FILE-SECURITY-001",
                }
            )
        for row in payload["review_flag_resolutions"]:
            row.update(
                {
                    "resolution": "RESOLVED",
                    "rationale": "Reviewed against the controlled source policy.",
                    "evidence_ref": "FLAG-001",
                }
            )
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)


if __name__ == "__main__":
    unittest.main()
