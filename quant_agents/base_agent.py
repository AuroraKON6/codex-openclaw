from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from .contracts import OutputContractError, validate_agent_output
from .config import Config
from .audit import canonical_json_sha256
from .pi_client import PiClient


AGENT_ROLE_MAP = {
    "research_lead": "quant-research-lead",
    "data_agent": "quant-data-agent",
    "strategy_agent": "quant-strategy-agent",
    "backtest_agent": "quant-backtest-agent",
    "risk_agent": "quant-risk-agent",
    "visualization_agent": "quant-visualization-agent",
    "review_agent": "quant-review-agent",
}


class BaseAgent:
    name: str = "base"
    description: str = ""
    system_prompt: str = "You are a quantitative research assistant."
    prompt_version: str = "2026-08-18.1"

    def __init__(self, mock: bool = False, runtime: str = "pi"):
        self.mock = mock
        self.runtime = runtime
        self.pi_agent_role = AGENT_ROLE_MAP.get(self.name, f"quant-{self.name}")
        self.pi = PiClient()
        self.runtime_meta: dict[str, Any] = {}

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        start = time.time()
        result: dict[str, Any] = {
            "agent": self.name,
            "pi_agent_role": self.pi_agent_role,
            "runtime": self.runtime,
            "status": "pending",
            "model": "mock" if self.mock else Config.DEEPSEEK_MODEL,
            "provider": "mock" if self.mock else "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "prompt_version": self.prompt_version,
        }
        try:
            if self.mock:
                result["data"] = self.mock_execute(context)
                result["runtime"] = "mock"
            elif self.runtime == "pi":
                result["data"] = self.execute_pi(context)
            else:
                raise RuntimeError(f"unsupported runtime: {self.runtime}")
            validate_agent_output(self.name, result["data"])
            if self.runtime_meta.get("model"):
                result["model"] = self.runtime_meta["model"]
            if self.runtime_meta.get("provider"):
                result["provider"] = self.runtime_meta["provider"]
            result["session_id"] = self.runtime_meta.get("session_id", "")
            result["response_id"] = self.runtime_meta.get("response_id", "")
            result["pi_version"] = self.runtime_meta.get("pi_version", "")
            result["runtime_policy"] = self.runtime_meta.get("runtime_policy", {})
            result["prompt_sha256"] = self.runtime_meta.get("prompt_sha256", "")
            result["usage"] = self.runtime_meta.get("usage", {})
            result["status"] = "ok"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            result["data"] = {}
        result["elapsed_s"] = round(time.time() - start, 2)
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        return result

    def execute_pi(self, context: dict[str, Any]) -> dict[str, Any]:
        user_prompt = self.build_prompt(context)
        contract_prompt = (
            "Complete the requested task now. Return exactly one final JSON object. "
            "Do not answer with ready, pong, awaiting_task, or a description of what you could do. "
            "Do not invent missing market facts or performance numbers. "
            "Do not provide buy/sell, position, stop-loss, or other real-capital instructions."
        )
        full_message = f"{contract_prompt}\n\n---\n\n{user_prompt}"
        prompt_sha256 = canonical_json_sha256(
            {
                "agent": self.name,
                "prompt_version": self.prompt_version,
                "system_prompt": self.system_prompt,
                "user_prompt": full_message,
            }
        )
        pi_result = self.pi.agent_turn_json(
            self.pi_agent_role,
            self.system_prompt,
            full_message,
        )

        if not pi_result["ok"]:
            save_raw(context["output_dir"], self.name, pi_result.get("raw", ""))
            _save_pi_meta(
                context["output_dir"],
                self.name,
                self.pi_agent_role,
                pi_result,
                self.prompt_version,
                prompt_sha256,
            )
            raise RuntimeError(pi_result.get("error", "Pi agent turn failed"))

        data = pi_result.get("parsed")

        validation_error = None
        try:
            validate_agent_output(self.name, data)
        except OutputContractError as exc:
            validation_error = str(exc)

        raw_outputs = [pi_result.get("raw", "")]
        attempts = [pi_result]
        if validation_error:
            repair_message = (
                f"{full_message}\n\nThe previous response was:\n"
                f"{pi_result.get('result_text', '')[:12000]}\n\n"
                f"It violated the output contract: {validation_error}. "
                "Return the corrected final JSON object now."
            )
            repaired = self.pi.agent_turn_json(
                self.pi_agent_role,
                self.system_prompt,
                repair_message,
            )
            raw_outputs.append(repaired.get("raw", ""))
            attempts.append(repaired)
            if not repaired.get("ok"):
                save_raw(
                    context["output_dir"],
                    self.name,
                    "\n\n--- RETRY ---\n\n".join(raw_outputs),
                )
                repaired["usage"] = _merge_pi_usage(attempts)
                repaired["attempt_count"] = len(attempts)
                _save_pi_meta(
                    context["output_dir"],
                    self.name,
                    self.pi_agent_role,
                    repaired,
                    self.prompt_version,
                    prompt_sha256,
                )
                raise RuntimeError(repaired.get("error", "Pi contract repair failed"))
            data = repaired.get("parsed")
            try:
                validate_agent_output(self.name, data)
            except OutputContractError:
                save_raw(
                    context["output_dir"],
                    self.name,
                    "\n\n--- RETRY ---\n\n".join(raw_outputs),
                )
                repaired["usage"] = _merge_pi_usage(attempts)
                repaired["attempt_count"] = len(attempts)
                _save_pi_meta(
                    context["output_dir"],
                    self.name,
                    self.pi_agent_role,
                    repaired,
                    self.prompt_version,
                    prompt_sha256,
                )
                raise
            pi_result = repaired

        pi_result["usage"] = _merge_pi_usage(attempts)
        pi_result["attempt_count"] = len(attempts)

        self.runtime_meta = {
            "session_id": pi_result.get("session_id", ""),
            "response_id": pi_result.get("response_id", ""),
            "provider": pi_result.get("provider", ""),
            "model": pi_result.get("model", ""),
            "usage": pi_result.get("usage", {}),
            "prompt_sha256": prompt_sha256,
            "pi_version": Config.PI_VERSION,
            "runtime_policy": pi_result.get("policy", {}),
        }
        save_raw(context["output_dir"], self.name, "\n\n--- RETRY ---\n\n".join(raw_outputs))
        _save_pi_meta(
            context["output_dir"],
            self.name,
            self.pi_agent_role,
            pi_result,
            self.prompt_version,
            prompt_sha256,
        )

        save_agent_json(context["output_dir"], self.name, data)
        return data

    def build_prompt(self, context: dict[str, Any]) -> str:
        return f"Agent: {self.name}\nContext: {json.dumps(context.get('input', {}), ensure_ascii=False)[:2000]}"

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        return {"mock": True, "agent": self.name, "note": "mock mode placeholder"}

def save_raw(output_dir: str, agent_name: str, raw_text: str):
    d = os.path.join(output_dir, "raw_outputs")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{agent_name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw_text)


def save_agent_json(output_dir: str, agent_name: str, data: dict):
    d = os.path.join(output_dir, "agent_outputs")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{agent_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _save_pi_meta(
    output_dir: str,
    agent_name: str,
    pi_agent_role: str,
    pi_result: dict,
    prompt_version: str,
    prompt_sha256: str,
):
    d = os.path.join(output_dir, "pi_meta")
    os.makedirs(d, exist_ok=True)
    meta = {
        "agent": agent_name,
        "pi_agent_role": pi_agent_role,
        "pi_package": Config.PI_PACKAGE_NAME,
        "pi_version": Config.PI_VERSION,
        "session_id": pi_result.get("session_id", ""),
        "response_id": pi_result.get("response_id", ""),
        "provider": pi_result.get("provider", ""),
        "model": pi_result.get("model", ""),
        "exit_code": pi_result.get("exit_code"),
        "elapsed_s": pi_result.get("elapsed_s"),
        "ok": pi_result.get("ok"),
        "error": pi_result.get("error"),
        "usage": pi_result.get("usage", {}),
        "stop_reason": pi_result.get("stop_reason", ""),
        "event_count": pi_result.get("event_count", 0),
        "attempt_count": pi_result.get("attempt_count", 1),
        "runtime_policy": pi_result.get("policy", {}),
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
    }
    path = os.path.join(d, f"{agent_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _merge_pi_usage(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "reasoning": 0,
        "totalTokens": 0,
        "cost": {
            "input": 0.0,
            "output": 0.0,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": 0.0,
        },
    }
    for attempt in attempts:
        usage = attempt.get("usage", {})
        if not isinstance(usage, dict):
            continue
        for key in ("input", "output", "cacheRead", "cacheWrite", "reasoning", "totalTokens"):
            value = usage.get(key, 0)
            if isinstance(value, (int, float)):
                totals[key] += value
        cost = usage.get("cost", {})
        if isinstance(cost, dict):
            for key in totals["cost"]:
                value = cost.get(key, 0)
                if isinstance(value, (int, float)):
                    totals["cost"][key] += value
    return totals
