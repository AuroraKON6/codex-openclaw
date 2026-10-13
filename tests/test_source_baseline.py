import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quant_agents.__main__ import cmd_source_candidate
from quant_agents.audit import canonical_json_sha256, sha256_file
from quant_agents.source_baseline import (
    REQUIRED_CANDIDATES,
    SourceCandidateError,
    build_source_candidate_manifest,
)


class SourceCandidateTests(unittest.TestCase):
    def test_clean_candidate_tree_is_ready_only_for_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = self._write_baseline(root)
            gate = self._secret_gate(root, candidates)
            with self._patched_inputs(candidates, gate):
                result = build_source_candidate_manifest(root, write=False)

        self.assertEqual(
            result["status"],
            "READY_FOR_HUMAN_FILE_REVIEW_NOT_AUTHORIZED",
        )
        self.assertTrue(result["ready_for_human_file_review"])
        self.assertFalse(result["source_baseline_authorized"])
        self.assertFalse(result["git_actions"]["git_add_performed"])
        self.assertEqual(result["summary"]["blocker_count"], 0)

    def test_manifest_identity_is_stable_across_generation_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = self._write_baseline(root)
            gate = self._secret_gate(root, candidates)
            with self._patched_inputs(candidates, gate):
                first = build_source_candidate_manifest(root, write=False)
                second = build_source_candidate_manifest(root, write=False)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])

    def test_stale_secret_receipt_blocks_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = self._write_baseline(root)
            gate = {
                "ok": False,
                "errors": ["candidate sources changed"],
                "receipt_summary": {},
            }
            with self._patched_inputs(candidates, gate):
                result = build_source_candidate_manifest(root, write=False)
        self.assertIn("SECRET_SCAN_RECEIPT_INVALID", self._codes(result))

    def test_forbidden_binary_and_large_candidates_block_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = self._write_baseline(root)
            artifact = root / "runs" / "state.bin"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(b"\x00" * 32)
            candidates.append("runs/state.bin")
            gate = self._secret_gate(root, candidates)
            with self._patched_inputs(candidates, gate):
                result = build_source_candidate_manifest(
                    root,
                    max_file_bytes=16,
                    write=False,
                )
        codes = self._codes(result)
        self.assertIn("FORBIDDEN_SOURCE_ARTIFACT", codes)
        self.assertIn("BINARY_CANDIDATE", codes)
        self.assertIn("CANDIDATE_TOO_LARGE", codes)

    def test_unpinned_dependency_contract_blocks_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = self._write_baseline(root)
            (root / "requirements.in").write_text(
                "httpx>=0.27\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text(
                "httpx>=0.27\n",
                encoding="utf-8",
            )
            gate = self._secret_gate(root, candidates)
            with self._patched_inputs(candidates, gate):
                result = build_source_candidate_manifest(root, write=False)
        codes = self._codes(result)
        self.assertIn("DIRECT_DEPENDENCIES_NOT_PINNED", codes)
        self.assertIn("PYTHON_DEPENDENCY_LOCK_INVALID", codes)

    def test_nonignored_output_inside_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch(
                "quant_agents.source_baseline.subprocess.run"
            ) as run:
                run.return_value.returncode = 1
                with self.assertRaises(SourceCandidateError):
                    build_source_candidate_manifest(
                        root,
                        output_path=root / "manifest.json",
                    )

    def test_cli_require_reviewable_returns_three_when_blocked(self):
        args = SimpleNamespace(
            output=None,
            secret_receipt=None,
            max_file_bytes=1024,
            require_reviewable=True,
        )
        with mock.patch(
            "quant_agents.__main__.build_source_candidate_manifest",
            return_value={"status": "BLOCKED"},
        ):
            self.assertEqual(cmd_source_candidate(args), 3)

    @staticmethod
    def _codes(result):
        return {item["code"] for item in result["blockers"]}

    @staticmethod
    def _write_baseline(root: Path):
        contents = {required: "baseline\n" for required in REQUIRED_CANDIDATES}
        contents[".python-version"] = "3.11\n"
        contents["requirements.in"] = (
            "httpx==0.28.1\n"
            "matplotlib==3.11.1\n"
            "tushare==1.4.29\n"
        )
        contents["requirements.txt"] = (
            "httpx==0.28.1 \\\n+    --hash=sha256:" + "a" * 64 + "\n"
            "matplotlib==3.11.1 \\\n+    --hash=sha256:" + "b" * 64 + "\n"
            "tushare==1.4.29 \\\n+    --hash=sha256:" + "c" * 64 + "\n"
        )
        for relative, content in contents.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return sorted(contents)

    @staticmethod
    def _secret_gate(root: Path, candidates):
        file_hashes = {
            relative: sha256_file(str(root / relative))
            for relative in candidates
        }
        return {
            "ok": True,
            "errors": [],
            "receipt_summary": {
                "candidate_files_sha256": canonical_json_sha256(file_hashes),
                "receipt_sha256": "d" * 64,
            },
        }

    @staticmethod
    def _patched_inputs(candidates, gate):
        return _PatchContext(candidates, gate)


class _PatchContext:
    def __init__(self, candidates, gate):
        self.candidates = candidates
        self.gate = gate
        self.stack = None

    def __enter__(self):
        self.stack = mock.patch.multiple(
            "quant_agents.source_baseline",
            list_scan_candidates=mock.DEFAULT,
            evaluate_secret_scan_receipt=mock.DEFAULT,
            collect_source_provenance=mock.DEFAULT,
        )
        patched = self.stack.__enter__()
        patched["list_scan_candidates"].return_value = list(self.candidates)
        patched["evaluate_secret_scan_receipt"].return_value = self.gate
        patched["collect_source_provenance"].return_value = {
            "head_commit": None,
            "tracked_file_count": 0,
            "changed_file_count": 0,
            "untracked_file_count": len(self.candidates),
            "release_ready": False,
            "reason": "repository has no committed HEAD",
        }
        return patched

    def __exit__(self, exc_type, exc, traceback):
        return self.stack.__exit__(exc_type, exc, traceback)
