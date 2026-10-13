from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import Config, PROJECT_ROOT


PI_SECURITY_FLAGS = (
    "--no-session",
    "--no-tools",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
    "--no-approve",
    "--offline",
)
MINIMUM_NODE_VERSION = (22, 19, 0)

# Explicit allowlist for the Pi child-process environment. The child never
# needs data credentials, evidence paths, or other project secrets; anything
# not listed here is dropped before the subprocess starts. The DeepSeek API
# key is the only credential the child may see, and standard proxy variables
# are preserved so the provider endpoint stays reachable in restricted
# networks.
PI_CHILD_ENV_ALLOWLIST = (
    # Windows system essentials for spawning node.exe
    "PATH",
    "SystemRoot",
    "SystemDrive",
    "windir",
    "ComSpec",
    "PATHEXT",
    "TEMP",
    "TMP",
    # User profile locations read by Node (os.homedir) and its runtime
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    # Optional proxy configuration for provider connectivity
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    # DeepSeek provider credential (the only secret the child may see)
    "DEEPSEEK_API_KEY",
)


class PiRuntimeError(RuntimeError):
    pass


class PiClient:
    def __init__(
        self,
        cli_path: str | None = None,
        node_cli: str | None = None,
        state_dir: str | None = None,
        timeout: int | None = None,
    ):
        self.cli_path = os.path.abspath(cli_path or Config.PI_CLI_PATH)
        self.node_cli = node_cli or Config.PI_NODE_CLI
        self.state_dir = os.path.abspath(state_dir or Config.PI_STATE_DIR)
        self.timeout = timeout or Config.PI_TIMEOUT_SECONDS

    def build_command(self, system_prompt: str) -> list[str]:
        return [
            self.node_cli,
            self.cli_path,
            "--mode",
            "json",
            "--provider",
            "deepseek",
            "--model",
            Config.DEEPSEEK_MODEL,
            "--thinking",
            Config.PI_THINKING_LEVEL,
            *PI_SECURITY_FLAGS,
            "--system-prompt",
            system_prompt,
        ]

    def agent_turn_json(
        self,
        agent_id: str,
        system_prompt: str,
        user_prompt: str,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        start = time.monotonic()
        command = self.build_command(system_prompt)
        try:
            process = subprocess.run(
                command,
                input=user_prompt,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                encoding="utf-8",
                errors="replace",
                cwd=str(PROJECT_ROOT),
                env=self._environment(),
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "exit_code": -1,
                "raw": _as_text(exc.stdout),
                "stderr": _as_text(exc.stderr),
                "elapsed_s": round(time.monotonic() - start, 2),
                "error": f"Pi agent turn timed out after {timeout or self.timeout}s",
                "agent_id": agent_id,
                "policy": self.command_policy(),
            }
        except OSError as exc:
            return {
                "ok": False,
                "exit_code": -1,
                "raw": "",
                "stderr": str(exc),
                "elapsed_s": round(time.monotonic() - start, 2),
                "error": str(exc),
                "agent_id": agent_id,
                "policy": self.command_policy(),
            }

        elapsed = round(time.monotonic() - start, 2)
        stdout = process.stdout or ""
        stderr = process.stderr or ""
        if process.returncode != 0:
            return {
                "ok": False,
                "exit_code": process.returncode,
                "raw": stdout,
                "stderr": stderr,
                "elapsed_s": elapsed,
                "error": f"Pi exited with code {process.returncode}: {stderr[:500]}",
                "agent_id": agent_id,
                "policy": self.command_policy(),
            }

        try:
            events = parse_pi_jsonl(stdout)
            final_event = final_assistant_message(events)
            session = next(
                (event for event in events if event.get("type") == "session"), {}
            )
            message = final_event["message"]
            provider = str(message.get("provider", ""))
            model = str(message.get("model", ""))
            if provider.lower() != "deepseek":
                raise PiRuntimeError(
                    f"Pi used unexpected provider {provider or 'unknown'}"
                )
            if model != Config.DEEPSEEK_MODEL:
                raise PiRuntimeError(
                    f"Pi used unexpected model {model or 'unknown'}; "
                    f"expected {Config.DEEPSEEK_MODEL}"
                )
            if message.get("stopReason") != "stop":
                raise PiRuntimeError(
                    "Pi final message did not stop cleanly: "
                    + str(message.get("stopReason", "unknown"))
                )
            if _contains_tool_activity(events):
                raise PiRuntimeError("Pi emitted tool activity despite --no-tools")
            result_text = _message_text(message)
            parsed = extract_json_object(result_text)
            if parsed is None:
                raise PiRuntimeError("Pi final assistant message is not a JSON object")
            return {
                "ok": True,
                "exit_code": 0,
                "raw": stdout,
                "stderr": stderr,
                "elapsed_s": elapsed,
                "result_text": result_text,
                "parsed": parsed,
                "session_id": str(session.get("id", "")),
                "provider": provider,
                "model": model,
                "usage": message.get("usage", {}),
                "stop_reason": message.get("stopReason", ""),
                "response_id": message.get("responseId", ""),
                "agent_id": agent_id,
                "event_count": len(events),
                "policy": self.command_policy(),
            }
        except (KeyError, PiRuntimeError, ValueError) as exc:
            return {
                "ok": False,
                "exit_code": process.returncode,
                "raw": stdout,
                "stderr": stderr,
                "elapsed_s": elapsed,
                "error": str(exc),
                "agent_id": agent_id,
                "policy": self.command_policy(),
            }

    def ping(self) -> dict[str, Any]:
        return self.agent_turn_json(
            "quant-research-pi-health",
            "You are a runtime health-check agent. Return exactly one JSON object.",
            '{"requested_status":"pong","runtime":"pi"}',
            timeout=Config.PI_PING_TIMEOUT_SECONDS,
        )

    def inspect_runtime(self, list_models: bool = True) -> dict[str, Any]:
        errors = []
        node_path = shutil.which(self.node_cli)
        if not node_path:
            errors.append(f"Node executable not found: {self.node_cli}")
        if not os.path.isfile(self.cli_path):
            errors.append(
                "Pinned Pi CLI is not installed; run .\\install_pi_runtime.ps1"
            )

        node_version = ""
        if node_path:
            result = self._run_metadata([self.node_cli, "--version"])
            node_version = (result.get("stdout") or "").strip().lstrip("v")
            parsed_version = _parse_version(node_version)
            if parsed_version is None or parsed_version < MINIMUM_NODE_VERSION:
                errors.append("Pi 0.84.2 requires Node >= 22.19.0")

        package_version = ""
        if os.path.isfile(self.cli_path):
            package_path = Path(self.cli_path).parent.parent / "package.json"
            try:
                package = json.loads(package_path.read_text(encoding="utf-8"))
                package_version = str(package.get("version", ""))
                if package.get("name") != Config.PI_PACKAGE_NAME:
                    errors.append("Installed Pi package name is unexpected")
            except (OSError, json.JSONDecodeError):
                errors.append("Cannot read the installed Pi package metadata")
            if package_version != Config.PI_VERSION:
                errors.append(
                    f"Installed Pi version is {package_version or 'unknown'}; "
                    f"expected {Config.PI_VERSION}"
                )

        lock_result = verify_runtime_lock()
        errors.extend(lock_result["errors"])
        model_available = False
        model_output = ""
        if list_models and not errors:
            result = self._run_metadata(
                [
                    self.node_cli,
                    self.cli_path,
                    "--list-models",
                    "deepseek",
                    "--offline",
                ]
            )
            model_output = result.get("stdout", "")
            model_available = bool(
                re.search(
                    rf"(?m)^deepseek\s+{re.escape(Config.DEEPSEEK_MODEL)}\s+",
                    model_output,
                )
            )
            if result.get("exit_code") != 0:
                errors.append(
                    "Pi model catalog check failed: "
                    + str(result.get("stderr", ""))[:500]
                )
            elif not model_available:
                errors.append(
                    f"Pi model catalog does not contain deepseek/{Config.DEEPSEEK_MODEL}"
                )

        return {
            "ok": not errors,
            "errors": errors,
            "node_path": node_path or "",
            "node_version": node_version,
            "pi_cli_path": self.cli_path,
            "pi_package": Config.PI_PACKAGE_NAME,
            "pi_version": package_version,
            "expected_pi_version": Config.PI_VERSION,
            "provider": "deepseek",
            "model": Config.DEEPSEEK_MODEL,
            "model_available": model_available,
            "runtime_lock_sha256": lock_result.get("sha256", ""),
            "policy": self.command_policy(),
        }

    @staticmethod
    def command_policy() -> dict[str, Any]:
        return {
            "mode": "json",
            "session": "ephemeral",
            "all_tools_disabled": True,
            "extensions_disabled": True,
            "skills_disabled": True,
            "prompt_templates_disabled": True,
            "themes_disabled": True,
            "context_files_disabled": True,
            "project_resources_ignored": True,
            "startup_network_disabled": True,
            "provider_network_required": True,
            "flags": list(PI_SECURITY_FLAGS),
        }

    def _environment(self) -> dict[str, str]:
        os.makedirs(self.state_dir, exist_ok=True)
        environment = {
            name: os.environ[name]
            for name in PI_CHILD_ENV_ALLOWLIST
            if name in os.environ
        }
        environment["PI_CODING_AGENT_DIR"] = self.state_dir
        environment["PI_OFFLINE"] = "1"
        environment["PI_TELEMETRY"] = "0"
        return environment

    def _run_metadata(self, command: list[str]) -> dict[str, Any]:
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=Config.PI_METADATA_TIMEOUT_SECONDS,
                encoding="utf-8",
                errors="replace",
                cwd=str(PROJECT_ROOT),
                env=self._environment(),
            )
            return {
                "exit_code": process.returncode,
                "stdout": process.stdout or "",
                "stderr": process.stderr or "",
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"exit_code": -1, "stdout": "", "stderr": str(exc)}


def parse_pi_jsonl(text: str) -> list[dict[str, Any]]:
    events = []
    invalid_lines = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines.append(line_number)
            continue
        if isinstance(value, dict):
            events.append(value)
    if invalid_lines:
        raise PiRuntimeError(
            "Pi JSON mode emitted non-JSON lines: "
            + ", ".join(str(number) for number in invalid_lines[:10])
        )
    if not events:
        raise PiRuntimeError("Pi JSON mode returned no events")
    return events


def final_assistant_message(events: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        event
        for event in events
        if event.get("type") == "message_end"
        and isinstance(event.get("message"), dict)
        and event["message"].get("role") == "assistant"
    ]
    if not candidates:
        raise PiRuntimeError("Pi did not emit an assistant message_end event")
    return candidates[-1]


def extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = "\n".join(
            line for line in candidate.splitlines() if not line.strip().startswith("```")
        ).strip()
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, character in enumerate(candidate):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(candidate[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def verify_runtime_lock() -> dict[str, Any]:
    lock_path = PROJECT_ROOT / "pi_runtime" / "package-lock.json"
    errors = []
    try:
        content = lock_path.read_bytes()
        lock = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"Pi runtime lock is unreadable: {exc}"], "sha256": ""}
    package = lock.get("packages", {}).get(
        "node_modules/@earendil-works/pi-coding-agent", {}
    )
    if package.get("version") != Config.PI_VERSION:
        errors.append("Pi runtime lock has an unexpected package version")
    if package.get("integrity") != Config.PI_PACKAGE_INTEGRITY:
        errors.append("Pi runtime lock has an unexpected package integrity")
    root_dependency = lock.get("packages", {}).get("", {}).get("dependencies", {}).get(
        Config.PI_PACKAGE_NAME
    )
    if root_dependency != Config.PI_VERSION:
        errors.append("Pi runtime lock does not pin the exact approved version")
    return {
        "ok": not errors,
        "errors": errors,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", [])
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(item.get("text", ""))
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ).strip()


def _contains_tool_activity(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if str(event.get("type", "")).startswith("tool_"):
            return True
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        for item in message.get("content", []):
            if isinstance(item, dict) and str(item.get("type", "")).lower() in {
                "toolcall",
                "tool_call",
                "toolresult",
                "tool_result",
            }:
                return True
    return False


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _as_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")
