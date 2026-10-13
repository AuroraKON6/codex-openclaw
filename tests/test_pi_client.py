import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from quant_agents.config import Config
from quant_agents.base_agent import _merge_pi_usage
from quant_agents.pi_client import (
    PI_CHILD_ENV_ALLOWLIST,
    PI_SECURITY_FLAGS,
    PiClient,
    PiRuntimeError,
    extract_json_object,
    final_assistant_message,
    parse_pi_jsonl,
    verify_runtime_lock,
)


def _jsonl(provider="deepseek", model="deepseek-v4-pro", include_tool=False):
    events = [
        {"type": "session", "version": 3, "id": "session-1"},
        {"type": "agent_start"},
    ]
    if include_tool:
        events.append({"type": "tool_execution_start", "toolName": "bash"})
    events.append(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": '{"status":"ok"}'}],
                "provider": provider,
                "model": model,
                "usage": {
                    "input": 10,
                    "output": 3,
                    "totalTokens": 13,
                    "cost": {"total": 0.00001},
                },
                "stopReason": "stop",
                "responseId": "response-1",
            },
        }
    )
    events.append({"type": "agent_end", "willRetry": False})
    return "\n".join(json.dumps(event) for event in events) + "\n"


class PiClientTests(unittest.TestCase):
    def test_command_is_ephemeral_and_has_no_resources_or_tools(self):
        client = PiClient(cli_path="C:\\pi\\dist\\cli.js")
        command = client.build_command("system")
        self.assertIn("--mode", command)
        self.assertIn("json", command)
        self.assertIn("--provider", command)
        self.assertIn("deepseek", command)
        self.assertIn(Config.DEEPSEEK_MODEL, command)
        for flag in PI_SECURITY_FLAGS:
            self.assertIn(flag, command)
        self.assertNotIn("--api-key", command)

    def test_extract_json_object_handles_fenced_and_prefixed_output(self):
        self.assertEqual(extract_json_object('```json\n{"ok":true}\n```'), {"ok": True})
        self.assertEqual(
            extract_json_object('Result: {"text":"brace } inside", "ok":true} trailing'),
            {"text": "brace } inside", "ok": True},
        )

    def test_jsonl_requires_authoritative_assistant_message_end(self):
        events = parse_pi_jsonl(_jsonl())
        final = final_assistant_message(events)
        self.assertEqual(final["message"]["responseId"], "response-1")
        with self.assertRaises(PiRuntimeError):
            final_assistant_message([{"type": "agent_end"}])

    def test_jsonl_rejects_non_json_noise(self):
        with self.assertRaises(PiRuntimeError):
            parse_pi_jsonl('{"type":"agent_start"}\nnot-json\n')

    def test_agent_turn_captures_identity_usage_and_policy(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_jsonl(), stderr=""
        )
        with tempfile.TemporaryDirectory() as state_dir, patch(
            "quant_agents.pi_client.subprocess.run", return_value=completed
        ) as run:
            result = PiClient(
                cli_path="C:\\pi\\dist\\cli.js", state_dir=state_dir
            ).agent_turn_json("role", "system", "prompt")
        self.assertTrue(result["ok"])
        self.assertEqual(result["parsed"], {"status": "ok"})
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["model"], Config.DEEPSEEK_MODEL)
        self.assertEqual(result["session_id"], "session-1")
        self.assertEqual(result["usage"]["totalTokens"], 13)
        self.assertTrue(result["policy"]["all_tools_disabled"])
        self.assertEqual(run.call_args.kwargs["input"], "prompt")

    def test_agent_turn_rejects_provider_model_or_tool_drift(self):
        samples = [
            _jsonl(provider="other"),
            _jsonl(model="deepseek-v4-flash"),
            _jsonl(include_tool=True),
        ]
        with tempfile.TemporaryDirectory() as state_dir:
            for stdout in samples:
                completed = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=stdout, stderr=""
                )
                with self.subTest(stdout=stdout), patch(
                    "quant_agents.pi_client.subprocess.run", return_value=completed
                ):
                    result = PiClient(
                        cli_path="C:\\pi\\dist\\cli.js", state_dir=state_dir
                    ).agent_turn_json("role", "system", "prompt")
                    self.assertFalse(result["ok"])

    def test_runtime_lock_pins_version_and_integrity(self):
        result = verify_runtime_lock()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(len(result["sha256"]), 64)

    def test_repair_attempt_usage_is_summed_for_budgeting(self):
        merged = _merge_pi_usage(
            [
                {
                    "usage": {
                        "input": 10,
                        "output": 2,
                        "totalTokens": 12,
                        "cost": {"total": 0.1},
                    }
                },
                {
                    "usage": {
                        "input": 8,
                        "output": 3,
                        "totalTokens": 11,
                        "cost": {"total": 0.2},
                    }
                },
            ]
        )
        self.assertEqual(merged["totalTokens"], 23)
        self.assertAlmostEqual(merged["cost"]["total"], 0.3)

    def test_allowlist_excludes_project_secret_names(self):
        for name in (
            "TUSHARE_TOKEN",
            "DATA_LICENSE_EVIDENCE_PATH",
            "RESEARCH_PROTOCOL_EVIDENCE_PATH",
            "EXPERIMENT_REGISTRY_PATH",
            "EXECUTION_COST_EVIDENCE_PATH",
            "SECRET_SCAN_RECEIPT_PATH",
        ):
            self.assertNotIn(name, PI_CHILD_ENV_ALLOWLIST)

    def test_child_environment_is_allowlisted(self):
        planted = {
            "DEEPSEEK_API_KEY": "planted-provider-credential",
            "TUSHARE_TOKEN": "planted-data-credential",
            "DATA_LICENSE_EVIDENCE_PATH": "D:\\evidence\\license.json",
            "RESEARCH_PROTOCOL_EVIDENCE_PATH": "D:\\evidence\\protocol.json",
            "EXPERIMENT_REGISTRY_PATH": "D:\\registry",
            "EXECUTION_COST_EVIDENCE_PATH": "D:\\evidence\\cost.json",
            "UNRELATED_DESKTOP_SECRET": "planted-unrelated-value",
            "PATH": "C:\\Windows\\System32",
            "SystemRoot": "C:\\WINDOWS",
            "TEMP": "C:\\Temp",
        }
        with tempfile.TemporaryDirectory() as state_dir:
            client = PiClient(cli_path="C:\\pi\\dist\\cli.js", state_dir=state_dir)
            with patch.dict(os.environ, planted):
                environment = client._environment()
        self.assertIn("DEEPSEEK_API_KEY", environment)
        self.assertIn("PATH", environment)
        self.assertNotIn("TUSHARE_TOKEN", environment)
        for name in (
            "DATA_LICENSE_EVIDENCE_PATH",
            "RESEARCH_PROTOCOL_EVIDENCE_PATH",
            "EXPERIMENT_REGISTRY_PATH",
            "EXECUTION_COST_EVIDENCE_PATH",
            "UNRELATED_DESKTOP_SECRET",
        ):
            self.assertNotIn(name, environment)
        self.assertEqual(environment["PI_OFFLINE"], "1")
        self.assertEqual(environment["PI_TELEMETRY"], "0")
        self.assertEqual(os.path.abspath(environment["PI_CODING_AGENT_DIR"]), os.path.abspath(state_dir))

    def test_agent_turn_passes_allowlisted_env_to_subprocess(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_jsonl(), stderr=""
        )
        planted = {
            "DEEPSEEK_API_KEY": "planted-provider-credential",
            "TUSHARE_TOKEN": "planted-data-credential",
        }
        with tempfile.TemporaryDirectory() as state_dir, patch.dict(
            os.environ, planted
        ), patch(
            "quant_agents.pi_client.subprocess.run", return_value=completed
        ) as run:
            result = PiClient(
                cli_path="C:\\pi\\dist\\cli.js", state_dir=state_dir
            ).agent_turn_json("role", "system", "prompt")
        self.assertTrue(result["ok"])
        child_env = run.call_args.kwargs["env"]
        self.assertIn("DEEPSEEK_API_KEY", child_env)
        self.assertNotIn("TUSHARE_TOKEN", child_env)


if __name__ == "__main__":
    unittest.main()
