import json
import re
import unittest
from pathlib import Path


class UpstreamReferenceCatalogTests(unittest.TestCase):
    def test_catalog_is_pinned_and_non_executable(self):
        path = Path(__file__).resolve().parents[1] / "governance" / "upstream_references.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(catalog["schema_version"], 1)
        self.assertGreaterEqual(len(catalog["references"]), 8)
        names = set()
        for reference in catalog["references"]:
            self.assertRegex(reference["commit"], re.compile(r"^[0-9a-f]{40}$"))
            self.assertTrue(reference["url"].startswith("https://github.com/"))
            self.assertNotIn(reference["name"], names)
            names.add(reference["name"])
        rqalpha = next(item for item in catalog["references"] if item["name"] == "ricequant/rqalpha")
        self.assertEqual(rqalpha["decision"], "reference_only_no_code_or_dependency")
        subagents = next(item for item in catalog["references"] if item["name"] == "jwu/pi-subagents")
        self.assertIn("rejected", subagents["decision"])


if __name__ == "__main__":
    unittest.main()
