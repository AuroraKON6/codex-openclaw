import json
import tempfile
import unittest
from pathlib import Path

from quant_agents.extension_governance import audit_project_extensions
from quant_agents.skill_governance import sha256_file


class ExtensionGovernanceTests(unittest.TestCase):
    def _fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "extensions"
        root.mkdir(parents=True)
        extension = root / "fixture-readonly.mjs"
        extension.write_text(
            'export default function (pi) { pi.registerCommand("status", {}); }\n',
            encoding="utf-8",
        )
        lock = Path(temporary.name) / "extensions.lock.json"
        lock.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "policy": {
                        "production_extensions_enabled": False,
                        "required_pi_flag": "--no-extensions",
                        "third_party_packages_installed": False,
                        "network_access_allowed": False,
                        "subprocess_access_allowed": False,
                        "write_access_allowed": False,
                    },
                    "extensions": [
                        {
                            "name": "fixture-readonly",
                            "path": ".pi/extensions/fixture-readonly.mjs",
                            "production_enabled": False,
                            "operator_load_mode": "explicit_cli_only",
                            "sha256": sha256_file(extension),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return temporary, root, extension, lock

    def test_project_extension_lock_passes(self):
        result = audit_project_extensions()
        self.assertEqual(result["status"], "passed", result["errors"])
        self.assertFalse(result["production_extensions_enabled"])
        self.assertTrue(result["production_runtime_flag_verified"])

    def test_hash_drift_is_rejected(self):
        temporary, root, extension, lock = self._fixture()
        with temporary:
            extension.write_text("export default function () {}\n", encoding="utf-8")
            result = audit_project_extensions(root, lock)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("hash drift" in error for error in result["errors"]))

    def test_network_or_subprocess_capability_is_rejected(self):
        temporary, root, extension, lock = self._fixture()
        with temporary:
            extension.write_text(
                'import "node:https"; export default function () {}\n',
                encoding="utf-8",
            )
            document = json.loads(lock.read_text(encoding="utf-8"))
            document["extensions"][0]["sha256"] = sha256_file(extension)
            lock.write_text(json.dumps(document), encoding="utf-8")
            result = audit_project_extensions(root, lock)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("Forbidden extension capabilities" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
