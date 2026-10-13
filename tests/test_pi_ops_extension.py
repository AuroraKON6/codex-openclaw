import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_PATH = PROJECT_ROOT / ".pi" / "extensions" / "quant-ops-readonly.mjs"


class PiOpsExtensionTests(unittest.TestCase):
    def _write_run(self, root: Path, run_id: str, mock: bool, severity: str):
        run = root / "runs" / run_id
        (run / "operations").mkdir(parents=True)
        (run / "release").mkdir()
        (run / "state.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "mock": mock,
                    "runtime": "mock" if mock else "pi",
                    "status": "completed" if mock else "preflight_failed",
                    "success_count": 7 if mock else 0,
                    "total_agents": 7,
                    "data_mode": "MOCK" if mock else "UNAVAILABLE",
                    "model_usage": {"total_tokens": 0, "estimated_cost_usd": 0},
                    "business_controls": {
                        "experiment_registry_gate": {
                            "status": "not_evaluated_mock" if mock else "finalized",
                            "registry_id": "registry-001" if not mock else None,
                            "ledger_integrity_ok": not mock,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        (run / "operations" / "alerts.json").write_text(
            json.dumps({"alerts": [{"severity": severity, "code": "FIXTURE"}]}),
            encoding="utf-8",
        )
        (run / "release" / "release_candidate.json").write_text(
            json.dumps({"status": "BLOCKED"}),
            encoding="utf-8",
        )

    def test_collects_real_and_mock_without_registering_llm_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self._write_run(workspace, "20260825_120000_001", False, "CRITICAL")
            self._write_run(workspace, "20260825_130000_001", True, "WARNING")
            script = r'''
import { pathToFileURL } from "node:url";
const module = await import(pathToFileURL(process.argv[1]).href);
let registered;
const pi = { registerCommand(name, definition) { registered = { name, definition }; } };
module.default(pi);
let widget;
let notice;
await registered.definition.handler("", {
  cwd: process.argv[2],
  ui: {
    setWidget(_name, value) { widget = value; },
    notify(message, kind) { notice = { message, kind }; },
  },
});
console.log(JSON.stringify({
  command: registered.name,
  status: module.collectQuantOpsStatus(process.argv[2]),
  widget,
  notice,
}));
'''
            process = subprocess.run(
                ["node", "--input-type=module", "-e", script, str(EXTENSION_PATH), str(workspace)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["command"], "quant-status")
        self.assertFalse(result["status"]["latest_real"]["mock"])
        self.assertTrue(result["status"]["latest_mock"]["mock"])
        self.assertEqual(result["status"]["latest_real"]["alert_severity"], "CRITICAL")
        self.assertEqual(
            result["status"]["latest_real"]["experiment_registry_status"],
            "finalized",
        )
        self.assertTrue(any("[MOCK]" in line for line in result["widget"]))
        self.assertIn("read_only", result["status"]["mode"])


if __name__ == "__main__":
    unittest.main()
