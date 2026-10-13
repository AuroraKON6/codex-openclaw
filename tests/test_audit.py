import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from quant_agents.audit import (
    build_file_manifest,
    collect_source_provenance,
    sha256_file,
    write_json_atomic,
)


class AuditTests(unittest.TestCase):
    def test_atomic_json_and_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "records.json")
            write_json_atomic(path, {"records": [{"value": 1}]})
            with open(path, "r", encoding="utf-8") as file:
                self.assertEqual(json.load(file)["records"][0]["value"], 1)

            first = build_file_manifest(directory, ["records.json"], {"source": "test"})
            second = build_file_manifest(directory, ["records.json"], {"source": "test"})
            self.assertEqual(first["snapshot_id"], second["snapshot_id"])
            self.assertEqual(first["files"][0]["sha256"], sha256_file(path))

            write_json_atomic(path, {"records": [{"value": 2}]})
            changed = build_file_manifest(directory, ["records.json"], {"source": "test"})
            self.assertNotEqual(first["snapshot_id"], changed["snapshot_id"])

    def test_source_provenance_accepts_only_clean_committed_repository(self):
        commit = "a" * 40

        def fake_run(command, **_kwargs):
            arguments = tuple(command[3:])
            outputs = {
                ("rev-parse", "--show-toplevel"): (0, "C:/repo\n"),
                ("rev-parse", "HEAD"): (0, f"{commit}\n"),
                ("symbolic-ref", "--quiet", "--short", "HEAD"): (0, "main\n"),
                ("status", "--porcelain=v1", "--untracked-files=all"): (0, ""),
                ("ls-files",): (0, "quant_agents/audit.py\nREADME.md\n"),
            }
            return_code, stdout = outputs[arguments]
            return subprocess.CompletedProcess(command, return_code, stdout, "")

        with patch("quant_agents.audit.subprocess.run", side_effect=fake_run):
            result = collect_source_provenance("C:/repo")

        self.assertTrue(result["release_ready"])
        self.assertEqual(result["head_commit"], commit)
        self.assertEqual(result["tracked_file_count"], 2)
        self.assertEqual(result["untracked_file_count"], 0)


if __name__ == "__main__":
    unittest.main()
