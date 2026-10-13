import re
import tempfile
import unittest
from pathlib import Path

from tools.build_python_lock import build_lock


ROOT = Path(__file__).resolve().parents[1]


class PythonRuntimeContractTests(unittest.TestCase):
    def test_supported_python_baseline_is_exactly_311(self):
        self.assertEqual(
            (ROOT / ".python-version").read_text(encoding="utf-8").strip(),
            "3.11",
        )

    def test_direct_and_transitive_dependencies_are_hash_locked(self):
        direct = self._requirements(ROOT / "requirements.in")
        self.assertGreaterEqual(len(direct), 3)
        self.assertTrue(all("==" in line for line in direct))

        lock = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        pins = re.findall(
            r"(?m)^[A-Za-z0-9][A-Za-z0-9_.-]*==[^\s\\]+",
            lock,
        )
        self.assertGreaterEqual(len(pins), len(direct))
        self.assertGreaterEqual(lock.count("--hash=sha256:"), len(pins))
        self.assertNotIn("--index-url", lock)
        self.assertNotIn("--trusted-host", lock)

    def test_operational_scripts_do_not_invoke_path_python(self):
        exempt = {
            "bootstrap_python.ps1",
            "lock_python_dependencies.ps1",
            "quant_python.ps1",
        }
        for path in ROOT.glob("*.ps1"):
            if path.name in exempt:
                continue
            text = path.read_text(encoding="utf-8-sig")
            if "quant_agents" not in text and "-m py_compile" not in text:
                continue
            self.assertNotRegex(text, r"(?im)&\s*python(?:\.exe)?\b", path.name)
            self.assertNotIn("Get-Command python", text, path.name)
            self.assertIn("Resolve-QuantPython", text, path.name)

    def test_bootstrap_enforces_hashes_wheels_and_pip_check(self):
        text = (ROOT / "bootstrap_python.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"--require-hashes"', text)
        self.assertIn('"--only-binary=:all:"', text)
        self.assertIn("-m pip check", text)
        self.assertIn("python-runtime --require-ready", text)
        self.assertIn("Resolve-QuantPython", text)

    def test_quant_wrapper_uses_only_project_python(self):
        text = (ROOT / "quant.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Resolve-QuantPython", text)
        self.assertIn("& $python -m quant_agents", text)

    def test_platform_lock_builder_hashes_selected_wheel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resolved = root / "resolved.txt"
            wheelhouse = root / "wheelhouse"
            output = root / "requirements.txt"
            wheelhouse.mkdir()
            resolved.write_text("demo-package==1.2.3\n", encoding="utf-8")
            (wheelhouse / "demo_package-1.2.3-py3-none-any.whl").write_bytes(
                b"reviewed wheel bytes"
            )
            result = build_lock(resolved, wheelhouse, output)
            lock = output.read_text(encoding="utf-8")
        self.assertEqual(result["pin_count"], 1)
        self.assertIn("demo-package==1.2.3", lock)
        self.assertRegex(lock, r"--hash=sha256:[0-9a-f]{64}")

    @staticmethod
    def _requirements(path):
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
