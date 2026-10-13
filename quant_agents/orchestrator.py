from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from .agents import (
    ResearchLeadAgent,
    DataAgent,
    StrategyAgent,
    BacktestAgent,
    RiskAgent,
    VisualizationAgent,
    ReviewAgent,
)
from .base_agent import save_agent_json, AGENT_ROLE_MAP
from .config import Config
from .data_client import DataClient
from .input_validation import validate_research_input
from .market_rules import build_policy_snapshot
from .pi_client import PiClient
from .python_runtime import inspect_python_runtime
from .audit import (
    build_file_manifest,
    canonical_json_sha256,
    collect_source_provenance,
    write_json_atomic,
)
from .governance import build_business_controls, evaluate_data_license
from .execution_cost_governance import evaluate_execution_cost_evidence
from .research_protocol import evaluate_research_protocol
from .experiment_registry import (
    ExperimentRegistryError,
    evaluate_experiment_registry,
    finalize_experiment,
    reserve_experiment,
)
from .operations import (
    ConcurrentRunError,
    DuplicateRequestError,
    RunLock,
    aggregate_model_usage,
    append_event,
    enforce_request_idempotency,
    evaluate_budget_gate,
    is_current_model_pricing,
    write_operational_artifacts,
)
from .release import write_integrity_report
from .secret_scan import evaluate_secret_scan_receipt
from .source_review import evaluate_source_review_decision


AGENT_PIPELINE = [
    ResearchLeadAgent,
    DataAgent,
    StrategyAgent,
    BacktestAgent,
    RiskAgent,
    VisualizationAgent,
    ReviewAgent,
]
RUN_SCHEMA_VERSION = 7
AGENT_DEPENDENCIES = {
    "research_lead": [],
    "data_agent": [],
    "strategy_agent": ["data_agent"],
    "backtest_agent": ["data_agent", "strategy_agent"],
    "risk_agent": ["research_lead", "data_agent", "strategy_agent", "backtest_agent"],
    "visualization_agent": ["strategy_agent", "backtest_agent", "risk_agent"],
    "review_agent": [
        "research_lead",
        "data_agent",
        "strategy_agent",
        "backtest_agent",
        "risk_agent",
        "visualization_agent",
    ],
}


class PipelinePreflightError(RuntimeError):
    def __init__(self, message: str, preflight: dict[str, Any]):
        super().__init__(message)
        self.preflight = preflight


def run_pipeline(
    input_data: dict,
    output_dir: str,
    mock: bool = False,
    runtime: str = "pi",
    request_id: str | None = None,
    retry_of: str | None = None,
) -> dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    validate_research_input(input_data)
    write_json_atomic(os.path.join(output_dir, "input.json"), input_data)
    source_provenance = collect_source_provenance()
    run_id = os.path.basename(os.path.abspath(output_dir))
    runs_root = os.path.dirname(os.path.abspath(output_dir))
    lock = RunLock(runs_root=runs_root, run_id=run_id, output_dir=output_dir)
    try:
        with lock:
            enforce_request_idempotency(runs_root, request_id, retry_of)
            append_event(
                output_dir,
                "pipeline_started",
                {
                    "run_id": run_id,
                    "runtime": "mock" if mock else runtime,
                    "request_id": request_id,
                    "retry_of": retry_of,
                },
            )
            return _run_pipeline_locked(
                input_data=input_data,
                output_dir=output_dir,
                mock=mock,
                runtime=runtime,
                request_id=request_id,
                retry_of=retry_of,
                lock=lock,
                source_provenance=source_provenance,
            )
    except (ConcurrentRunError, DuplicateRequestError) as exc:
        _write_preflight_failure(
            input_data=input_data,
            output_dir=output_dir,
            runtime="mock" if mock else runtime,
            error=f"operational gate failed: {exc}",
            mock=mock,
            request_id=None,
            retry_of=retry_of,
            source_provenance=source_provenance,
        )
        raise RuntimeError(str(exc)) from exc


def _run_pipeline_locked(
    input_data: dict,
    output_dir: str,
    mock: bool,
    runtime: str,
    request_id: str | None,
    retry_of: str | None,
    lock: RunLock,
    source_provenance: dict[str, Any],
) -> dict[str, Any]:
    pipeline_started = time.monotonic()

    python_runtime = inspect_python_runtime()
    python_runtime_check = {
        "name": "python_runtime_contract",
        "status": "ok" if python_runtime.get("ok") else "failed",
        "detail": python_runtime,
    }
    preflight = {
        "mode": "MOCK" if mock else runtime,
        "status": "passed" if python_runtime.get("ok") else "failed",
        "checks": [python_runtime_check],
    }
    if not python_runtime.get("ok"):
        error = "Python runtime contract failed: " + "; ".join(
            python_runtime.get("errors", ["unknown runtime error"])
        )
        preflight["error"] = error
        _write_preflight_failure(
            input_data=input_data,
            output_dir=output_dir,
            runtime="mock" if mock else runtime,
            error=error,
            mock=mock,
            request_id=request_id,
            retry_of=retry_of,
            source_provenance=source_provenance,
            preflight=preflight,
        )
        raise PipelinePreflightError(error, preflight)
    if not mock:
        try:
            lock.heartbeat("preflight")
            if source_provenance.get("release_ready") is not True:
                raise RuntimeError(
                    "Source revision preflight failed: "
                    + str(source_provenance.get("reason", "source provenance missing"))
                )
            preflight = _preflight_dependencies(
                runtime,
                input_data,
                run_id=os.path.basename(os.path.abspath(output_dir)),
                run_dir=output_dir,
                source_provenance=source_provenance,
                request_id=request_id,
                retry_of=retry_of,
                python_runtime_report=python_runtime,
            )
            append_event(output_dir, "preflight_passed", {"checks": [row["name"] for row in preflight["checks"]]})
        except (OSError, RuntimeError, ValueError) as exc:
            failure_preflight = getattr(exc, "preflight", preflight)
            _write_preflight_failure(
                input_data=input_data,
                output_dir=output_dir,
                runtime=runtime,
                error=str(exc),
                mock=False,
                request_id=request_id,
                retry_of=retry_of,
                source_provenance=source_provenance,
                preflight=failure_preflight,
            )
            raise

    date_range = input_data.get("date_range", {})
    state: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": os.path.basename(os.path.abspath(output_dir)),
        "input_fingerprint": canonical_json_sha256(input_data),
        "request_id": request_id,
        "retry_of": retry_of,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "mock": mock,
        "runtime": "mock" if mock else runtime,
        "pi_runtime": _pi_runtime_from_preflight(preflight) if not mock else None,
        "preflight": preflight,
        "input": input_data,
        "date_range": date_range,
        "output_dir": output_dir,
        "agent_outputs": {},
        "agent_results": [],
        "errors": [],
        "config": Config.snapshot(),
        "source_provenance": source_provenance,
        "run_lock": {
            key: lock.metadata.get(key)
            for key in ("pid", "hostname", "nonce", "acquired_at")
        },
        "business_controls": build_business_controls(
            input_data=input_data,
            mock=mock,
            license_gate=_license_gate_from_preflight(preflight),
            execution_cost_gate=_execution_cost_gate_from_preflight(preflight),
            research_protocol_gate=_research_protocol_gate_from_preflight(
                preflight
            ),
            experiment_registry_gate=_experiment_registry_gate_from_preflight(
                preflight
            ),
        ),
    }
    state["model_usage"] = aggregate_model_usage([], preflight)
    state["budget_gate"] = evaluate_budget_gate(
        [], preflight, time.monotonic() - pipeline_started
    )
    _checkpoint_state(state, output_dir)

    for AgentCls in AGENT_PIPELINE:
        agent = AgentCls(mock=mock, runtime=runtime)
        lock.heartbeat(f"agent:{agent.name}")
        append_event(output_dir, "agent_started", {"agent": agent.name})
        blocked_by = [
            dependency
            for dependency in AGENT_DEPENDENCIES.get(agent.name, [])
            if not _agent_succeeded(state, dependency)
        ]
        if state.get("budget_gate", {}).get("status") == "failed":
            blocked_by.append("operational_budget_gate")
        if blocked_by:
            error = f"blocked by failed dependencies: {', '.join(blocked_by)}"
            data = (
                _build_failure_review(state, blocked_by)
                if agent.name == "review_agent"
                else {"error": error, "blocked_by": blocked_by}
            )
            if agent.name == "review_agent":
                save_agent_json(output_dir, agent.name, data)
            result = {
                "agent": agent.name,
                "pi_agent_role": agent.pi_agent_role,
                "runtime": "mock" if mock else runtime,
                "status": "blocked",
                "elapsed_s": 0.0,
                "model": "mock" if mock else Config.DEEPSEEK_MODEL,
                "provider": "mock" if mock else "",
                "prompt_version": agent.prompt_version,
                "prompt_sha256": "",
                "usage": {},
                "error": error,
                "data": data,
            }
        else:
            context = {
                "input": input_data,
                "date_range": date_range,
                "output_dir": output_dir,
                "agent_outputs": state["agent_outputs"],
                "prev_findings": state["agent_outputs"].get("research_lead", {}).get("research_priorities", []),
                "pipeline_errors": state["errors"],
            }
            result = agent.run(context)
            if agent.name == "review_agent" and result["status"] != "ok":
                result["data"] = _build_failure_review(state, ["review_agent"])
                save_agent_json(output_dir, agent.name, result["data"])

        state["agent_results"].append({
            "agent": agent.name,
            "pi_agent_role": agent.pi_agent_role,
            "runtime": result.get("runtime", runtime),
            "status": result["status"],
            "elapsed_s": result["elapsed_s"],
            "model": result.get("model", ""),
            "provider": result.get("provider", ""),
            "session_id": result.get("session_id", ""),
            "response_id": result.get("response_id", ""),
            "pi_version": result.get("pi_version", ""),
            "runtime_policy": result.get("runtime_policy", {}),
            "prompt_version": result.get("prompt_version", agent.prompt_version),
            "prompt_sha256": result.get("prompt_sha256", ""),
            "usage": result.get("usage", {}),
            "error": result.get("error"),
        })
        if result["status"] == "ok":
            state["agent_outputs"][agent.name] = result["data"]
        else:
            state["agent_outputs"][agent.name] = {"error": result.get("error", "unknown")}
            if agent.name == "review_agent" and result.get("data"):
                state["agent_outputs"][agent.name] = result["data"]
            state["errors"].append(f"{agent.name}: {result.get('error', 'unknown')}")
        state["model_usage"] = aggregate_model_usage(state["agent_results"], preflight)
        prior_breaches = set(state.get("budget_gate", {}).get("breaches", []))
        state["budget_gate"] = evaluate_budget_gate(
            state["agent_results"],
            preflight,
            time.monotonic() - pipeline_started,
        )
        for breach in state["budget_gate"]["breaches"]:
            if breach not in prior_breaches:
                state["errors"].append(f"budget_gate: {breach}")
        append_event(
            output_dir,
            "agent_finished",
            {
                "agent": agent.name,
                "status": result["status"],
                "elapsed_s": result["elapsed_s"],
                "total_tokens_so_far": state["model_usage"]["total_tokens"],
            },
        )
        _checkpoint_state(state, output_dir)

    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["total_agents"] = len(AGENT_PIPELINE)
    state["success_count"] = sum(1 for r in state["agent_results"] if r["status"] == "ok")
    state["agent_error_count"] = state["total_agents"] - state["success_count"]
    data_output = state["agent_outputs"].get("data_agent", {})
    backtest_output = state["agent_outputs"].get("backtest_agent", {})
    state["data_mode"] = data_output.get("data_mode", "MOCK" if mock else "UNKNOWN")
    state["metrics_source"] = (
        "MOCK" if mock else backtest_output.get("data_mode", "UNAVAILABLE")
    )
    state["backtest_assurance"] = backtest_output.get(
        "backtest_assurance",
        {
            "decision": "NOT_APPLICABLE_MOCK" if mock else "UNAVAILABLE",
            "release_gate_passed": False,
        },
    )
    state["robustness_validation"] = backtest_output.get(
        "robustness_validation",
        {
            "decision": "NOT_APPLICABLE_MOCK" if mock else "UNAVAILABLE",
            "failed_checks": ["real_tushare_metrics"],
        },
    )
    state["model_usage"] = aggregate_model_usage(state["agent_results"], preflight)
    state["budget_gate"] = evaluate_budget_gate(
        state["agent_results"], preflight, time.monotonic() - pipeline_started
    )
    for breach in state["budget_gate"]["breaches"]:
        message = f"budget_gate: {breach}"
        if message not in state["errors"]:
            state["errors"].append(message)
    assurance_failed = (
        not mock
        and state["backtest_assurance"].get("decision")
        != "PASSED_FOR_INTERNAL_RESEARCH"
    )
    if assurance_failed:
        state["errors"].append(
            "backtest_assurance: deterministic internal-research assurance did not pass"
        )
    state["operational_error_count"] = sum(
        (
            state["budget_gate"]["status"] == "failed",
            assurance_failed,
        )
    )
    state["error_count"] = state["agent_error_count"] + state["operational_error_count"]
    state["status"] = "completed" if state["error_count"] == 0 else "completed_with_errors"
    state["artifact_manifest"] = "run_manifest.json"

    if not mock:
        try:
            registry_gate = finalize_experiment(state)
            state["business_controls"]["experiment_registry_gate"] = registry_gate
        except (ExperimentRegistryError, OSError, ValueError) as exc:
            state["business_controls"]["experiment_registry_gate"] = {
                **state["business_controls"].get("experiment_registry_gate", {}),
                "status": "finalization_failed",
                "ledger_integrity_ok": False,
                "error": str(exc),
                "live_execution_authorized": False,
                "external_distribution_authorized": False,
                "broker_connection_enabled": False,
            }
            state["errors"].append(f"experiment_registry: {exc}")
            state["operational_error_count"] += 1
            state["error_count"] += 1
            state["status"] = "completed_with_errors"

    append_event(
        output_dir,
        "pipeline_finished",
        {
            "status": state["status"],
            "success_count": state["success_count"],
            "error_count": state["error_count"],
        },
    )
    write_json_atomic(os.path.join(output_dir, "state.json"), state)

    _generate_summary(state, output_dir)
    write_operational_artifacts(state, output_dir)
    _write_run_manifest(state, output_dir)
    write_integrity_report(output_dir)
    lock.heartbeat("finalized")
    return state


def _write_preflight_failure(
    input_data: dict[str, Any],
    output_dir: str,
    runtime: str,
    error: str,
    mock: bool,
    request_id: str | None,
    retry_of: str | None,
    source_provenance: dict[str, Any],
    preflight: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    license_gate = _license_gate_from_preflight(preflight or {})
    research_protocol_gate = _research_protocol_gate_from_preflight(
        preflight or {}
    )
    experiment_registry_gate = _experiment_registry_gate_from_preflight(
        preflight or {}
    )
    execution_cost_gate = _execution_cost_gate_from_preflight(preflight or {})
    if not mock and preflight is None:
        try:
            license_gate = evaluate_data_license(input_data)
        except (OSError, RuntimeError, ValueError) as exc:
            license_gate = {
                "status": "failed",
                "commercial_use_permitted": False,
                "external_distribution_permitted": False,
                "error": str(exc),
            }
        try:
            research_protocol_gate = evaluate_research_protocol(input_data)
        except (OSError, RuntimeError, ValueError) as exc:
            research_protocol_gate = {
                "status": "failed",
                "live_execution_authorized": False,
                "external_distribution_authorized": False,
                "error": str(exc),
            }
        try:
            execution_cost_gate = evaluate_execution_cost_evidence(input_data)
        except (OSError, RuntimeError, ValueError) as exc:
            execution_cost_gate = {
                "status": "failed",
                "live_execution_ready": False,
                "error": str(exc),
            }
    preflight_document = dict(preflight or {"mode": runtime, "checks": []})
    preflight_document.update({"status": "failed", "error": error})
    state: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": os.path.basename(os.path.abspath(output_dir)),
        "input_fingerprint": canonical_json_sha256(input_data),
        "request_id": request_id,
        "retry_of": retry_of,
        "started_at": now,
        "finished_at": now,
        "status": "preflight_failed",
        "mock": mock,
        "runtime": runtime,
        "pi_runtime": None,
        "preflight": preflight_document,
        "input": input_data,
        "output_dir": output_dir,
        "agent_outputs": {},
        "agent_results": [],
        "errors": [f"preflight: {error}"],
        "total_agents": len(AGENT_PIPELINE),
        "success_count": 0,
        "error_count": len(AGENT_PIPELINE),
        "data_mode": "UNAVAILABLE",
        "metrics_source": "UNAVAILABLE",
        "backtest_assurance": {
            "decision": "UNAVAILABLE",
            "release_gate_passed": False,
        },
        "robustness_validation": {
            "decision": "UNAVAILABLE",
            "failed_checks": ["real_tushare_metrics"],
        },
        "config": Config.snapshot(),
        "source_provenance": source_provenance,
        "model_usage": aggregate_model_usage([], preflight_document),
        "budget_gate": {
            **evaluate_budget_gate([], preflight_document, 0.0),
            "status": "not_evaluated_preflight_failure",
        },
        "artifact_manifest": "run_manifest.json",
        "business_controls": build_business_controls(
            input_data=input_data,
            mock=mock,
            license_gate=license_gate,
            execution_cost_gate=execution_cost_gate,
            research_protocol_gate=research_protocol_gate,
            experiment_registry_gate=experiment_registry_gate,
        ),
    }
    if not mock and experiment_registry_gate and experiment_registry_gate.get(
        "status"
    ) == "reserved":
        try:
            state["business_controls"]["experiment_registry_gate"] = (
                finalize_experiment(state, experiment_registry_gate)
            )
        except (ExperimentRegistryError, OSError, ValueError) as exc:
            state["business_controls"]["experiment_registry_gate"] = {
                **experiment_registry_gate,
                "status": "finalization_failed",
                "ledger_integrity_ok": False,
                "error": str(exc),
                "live_execution_authorized": False,
                "external_distribution_authorized": False,
                "broker_connection_enabled": False,
            }
            state["errors"].append(f"experiment_registry: {exc}")
    append_event(output_dir, "preflight_failed", {"error": error, "runtime": runtime})
    write_json_atomic(os.path.join(output_dir, "state.json"), state)
    _generate_summary(state, output_dir)
    write_operational_artifacts(state, output_dir)
    _write_run_manifest(state, output_dir)
    write_integrity_report(output_dir)


def _checkpoint_state(state: dict[str, Any], output_dir: str) -> None:
    checkpoint = dict(state)
    checkpoint["total_agents"] = len(AGENT_PIPELINE)
    checkpoint["success_count"] = sum(
        1 for result in state.get("agent_results", []) if result.get("status") == "ok"
    )
    checkpoint["error_count"] = sum(
        1 for result in state.get("agent_results", []) if result.get("status") != "ok"
    )
    checkpoint["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(os.path.join(output_dir, "state.json"), checkpoint)


def _agent_succeeded(state: dict[str, Any], agent_name: str) -> bool:
    return any(
        result.get("agent") == agent_name and result.get("status") == "ok"
        for result in state.get("agent_results", [])
    )


def _build_failure_review(
    state: dict[str, Any],
    blocked_by: list[str],
) -> dict[str, Any]:
    errors = list(state.get("errors", []))
    return {
        "conclusion": "上游研究环节未全部通过，本轮仅保留失败审计记录，不形成市场或策略结论。",
        "trigger_level": "CRITICAL",
        "key_risks": errors or [f"未完成依赖: {', '.join(blocked_by)}"],
        "human_confirmation_needed": [
            "确认失败根因、数据快照和运行日志已由责任人复核",
            "确认修复后重新执行完整离线研究流程",
        ],
        "next_actions": [
            "修复失败的上游依赖",
            "重新运行并比较新的输入指纹、快照哈希和 Agent 审计记录",
        ],
        "overall_confidence": 0.0,
        "data_quality_score": 0.0,
        "strategy_quality_score": 0.0,
        "disclaimer": "本记录仅用于内部失败审计，不构成任何真实资金买卖建议。",
        "deterministic_fallback": True,
        "blocked_by": blocked_by,
    }


def _write_run_manifest(state: dict[str, Any], output_dir: str) -> None:
    relative_paths = []
    for root, _, filenames in os.walk(output_dir):
        for filename in filenames:
            absolute_path = os.path.join(root, filename)
            relative_path = os.path.relpath(absolute_path, output_dir)
            normalized = relative_path.replace("\\", "/")
            if normalized in {
                "run_manifest.json",
                "operations/integrity_verification.json",
            } or normalized.startswith("release/"):
                continue
            relative_paths.append(relative_path)
    data_output = state.get("agent_outputs", {}).get("data_agent", {})
    backtest_output = state.get("agent_outputs", {}).get("backtest_agent", {})
    license_gate = state.get("business_controls", {}).get("data_license_gate", {})
    research_protocol_gate = state.get("business_controls", {}).get(
        "research_protocol_gate", {}
    )
    experiment_registry_gate = state.get("business_controls", {}).get(
        "experiment_registry_gate", {}
    )
    execution_cost_gate = state.get("business_controls", {}).get(
        "execution_cost_gate", {}
    )
    manifest = build_file_manifest(
        output_dir,
        relative_paths,
        metadata={
            "run_id": state.get("run_id"),
            "run_schema_version": state.get("schema_version"),
            "input_fingerprint": state.get("input_fingerprint"),
            "runtime": state.get("runtime"),
            "pi_runtime": state.get("pi_runtime"),
            "market_snapshot_id": data_output.get("snapshot_id"),
            "market_rulebook_sha256": backtest_output.get(
                "execution_policy_snapshot", {}
            ).get("rulebook_sha256"),
            "backtest_assurance_decision": state.get("backtest_assurance", {}).get(
                "decision"
            ),
            "robustness_validation_decision": state.get(
                "robustness_validation", {}
            ).get("decision"),
            "robustness_contract_fingerprint": state.get(
                "robustness_validation", {}
            ).get("contract_fingerprint"),
            "model_usage": state.get("model_usage", {}),
            "request_id": state.get("request_id"),
            "source_provenance": state.get("source_provenance", {}),
            "data_license_status": license_gate.get("status"),
            "data_license_schema_version": license_gate.get("schema_version"),
            "data_license_evidence_sha256": license_gate.get("evidence_file_sha256"),
            "research_protocol_status": research_protocol_gate.get("status"),
            "research_protocol_id": research_protocol_gate.get("protocol_id"),
            "research_protocol_version": research_protocol_gate.get(
                "protocol_version"
            ),
            "research_protocol_model_contract_sha256": research_protocol_gate.get(
                "model_contract_sha256"
            ),
            "research_protocol_evidence_sha256": research_protocol_gate.get(
                "evidence_file_sha256"
            ),
            "experiment_registry_status": experiment_registry_gate.get("status"),
            "experiment_registry_id": experiment_registry_gate.get("registry_id"),
            "experiment_registry_metadata_sha256": experiment_registry_gate.get(
                "registry_metadata_sha256"
            ),
            "experiment_reservation_entry_hash": experiment_registry_gate.get(
                "reservation_entry_hash"
            ),
            "experiment_finalization_entry_hash": experiment_registry_gate.get(
                "finalization_entry_hash"
            ),
            "experiment_state_contract_sha256": experiment_registry_gate.get(
                "state_contract_sha256"
            ),
            "execution_cost_status": execution_cost_gate.get("status"),
            "execution_cost_model_fingerprint": execution_cost_gate.get(
                "cost_model_fingerprint"
            ),
            "execution_cost_evidence_sha256": execution_cost_gate.get(
                "evidence_file_sha256"
            ),
            "model_pricing_current": is_current_model_pricing(state),
        },
    )
    write_json_atomic(os.path.join(output_dir, "run_manifest.json"), manifest)


def finalize_recovered_run(output_dir: str, state: dict[str, Any]) -> None:
    state.setdefault("schema_version", RUN_SCHEMA_VERSION)
    state.setdefault("model_usage", aggregate_model_usage(state.get("agent_results", []), state.get("preflight")))
    state.setdefault("budget_gate", evaluate_budget_gate(state.get("agent_results", []), state.get("preflight"), 0.0))
    state.setdefault(
        "business_controls",
        build_business_controls(state.get("input", {}), bool(state.get("mock"))),
    )
    state["business_controls"].setdefault(
        "experiment_registry_gate",
        {
            "status": "not_evaluated_mock" if state.get("mock") else "unavailable",
            "ledger_integrity_ok": False,
            "live_execution_authorized": False,
            "external_distribution_authorized": False,
            "broker_connection_enabled": False,
        },
    )
    state.setdefault(
        "source_provenance",
        {
            "schema_version": 1,
            "release_ready": False,
            "reason": "source provenance missing from original interrupted run",
        },
    )
    state["artifact_manifest"] = "run_manifest.json"
    registry_gate = state["business_controls"].get("experiment_registry_gate", {})
    if not state.get("mock") and registry_gate.get("status") == "reserved":
        try:
            state["business_controls"]["experiment_registry_gate"] = (
                finalize_experiment(state, registry_gate)
            )
        except (ExperimentRegistryError, OSError, ValueError) as exc:
            state["business_controls"]["experiment_registry_gate"] = {
                **registry_gate,
                "status": "finalization_failed",
                "ledger_integrity_ok": False,
                "error": str(exc),
                "live_execution_authorized": False,
                "external_distribution_authorized": False,
                "broker_connection_enabled": False,
            }
            state.setdefault("errors", []).append(f"experiment_registry: {exc}")
    write_json_atomic(os.path.join(output_dir, "state.json"), state)
    _generate_summary(state, output_dir)
    write_operational_artifacts(state, output_dir)
    _write_run_manifest(state, output_dir)
    write_integrity_report(output_dir)


def _preflight_dependencies(
    runtime: str,
    input_data: dict[str, Any],
    run_id: str | None = None,
    run_dir: str | None = None,
    source_provenance: dict[str, Any] | None = None,
    request_id: str | None = None,
    retry_of: str | None = None,
    python_runtime_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if runtime != "pi":
        raise RuntimeError("only runtime=pi is supported")
    checks: list[dict[str, Any]] = []
    try:
        python_runtime = python_runtime_report or inspect_python_runtime()
        checks.append(
            {
                "name": "python_runtime_contract",
                "status": "ok" if python_runtime.get("ok") else "failed",
                "detail": python_runtime,
            }
        )
        if not python_runtime.get("ok"):
            raise RuntimeError(
                "Python runtime contract failed: "
                + "; ".join(
                    python_runtime.get("errors", ["unknown runtime error"])
                )
            )
        secret_scan_gate = evaluate_secret_scan_receipt()
        if not secret_scan_gate.get("ok"):
            raise RuntimeError(
                "Secret scan gate failed: "
                + "; ".join(secret_scan_gate.get("errors", []))
            )
        checks.append(
            {
                "name": "secret_scan",
                "status": "ok",
                "detail": secret_scan_gate.get("receipt_summary", {}),
            }
        )
        source_review_gate = evaluate_source_review_decision()
        source_review_check = {
            "name": "source_review_decision",
            "status": "ok" if source_review_gate.get("review_claim_valid") is True else "failed",
            "detail": source_review_gate,
        }
        checks.append(source_review_check)
        if source_review_gate.get("review_claim_valid") is not True:
            raise RuntimeError(
                "Source review decision gate failed: "
                + "; ".join(source_review_gate.get("errors", []))
            )
        license_gate = evaluate_data_license(input_data)
        checks.append(
            {
                "name": "data_license",
                "status": "ok",
                "detail": license_gate,
            }
        )
        research_protocol_gate = evaluate_research_protocol(input_data)
        checks.append(
            {
                "name": "research_protocol_registration",
                "status": "ok",
                "detail": research_protocol_gate,
            }
        )
        if run_id or run_dir or source_provenance:
            if not (run_id and run_dir and source_provenance):
                raise RuntimeError(
                    "experiment reservation requires run_id, run_dir, and source provenance"
                )
            experiment_registry_gate = reserve_experiment(
                Config.EXPERIMENT_REGISTRY_PATH,
                run_id=run_id,
                run_dir=run_dir,
                input_data=input_data,
                source_provenance=source_provenance,
                protocol_gate=research_protocol_gate,
                request_id=request_id,
                retry_of=retry_of,
            )
        else:
            experiment_registry_gate = evaluate_experiment_registry(
                input_data,
                research_protocol_gate,
            )
        checks.append(
            {
                "name": "experiment_registry_reservation",
                "status": "ok",
                "detail": experiment_registry_gate,
            }
        )
        date_range = input_data.get("date_range", {})
        execution_controls = input_data.get("execution_controls", {})
        market_rules = build_policy_snapshot(
            str(date_range.get("since", "")).replace("-", ""),
            str(date_range.get("until", "")).replace("-", ""),
            execution_controls.get("cost_model", {}),
        )
        checks.append(
            {
                "name": "a_share_market_rules",
                "status": "ok",
                "detail": market_rules,
            }
        )
        execution_cost_gate = evaluate_execution_cost_evidence(input_data)
        checks.append(
            {
                "name": "execution_cost_calibration",
                "status": "ok",
                "detail": execution_cost_gate,
            }
        )
        errors = Config.validate(
            require_deepseek=True,
            require_tushare=True,
        )
        if errors:
            raise RuntimeError(
                "Preflight configuration failed: " + "; ".join(errors)
            )

        data_health = DataClient().health()
        if not data_health.get("ok"):
            raise RuntimeError(
                "Tushare preflight failed: "
                + str(data_health.get("error", data_health))
            )
        checks.append({"name": "tushare", "status": "ok", "detail": data_health})
        checks.extend(_preflight_pi())
        return {"mode": runtime, "status": "passed", "checks": checks}
    except (OSError, RuntimeError, ValueError) as exc:
        raise PipelinePreflightError(
            str(exc),
            {
                "mode": runtime,
                "status": "failed",
                "error": str(exc),
                "checks": checks,
            },
        ) from exc


def _preflight_pi() -> list[dict[str, Any]]:
    client = PiClient()
    runtime = client.inspect_runtime(list_models=True)
    if not runtime.get("ok"):
        raise RuntimeError(
            "Pi runtime preflight failed: " + "; ".join(runtime.get("errors", []))
        )
    policy = runtime.get("policy", {})
    required_policy = {
        "all_tools_disabled",
        "extensions_disabled",
        "skills_disabled",
        "prompt_templates_disabled",
        "themes_disabled",
        "context_files_disabled",
        "project_resources_ignored",
        "startup_network_disabled",
    }
    disabled_controls = sorted(
        control for control in required_policy if policy.get(control) is not True
    )
    if disabled_controls:
        raise RuntimeError(
            "Pi security policy is incomplete: " + ", ".join(disabled_controls)
        )
    ping = client.ping()
    if not ping.get("ok"):
        raise RuntimeError(
            "Pi DeepSeek model-auth ping failed: " + str(ping.get("error", "unknown"))
        )
    ping_data = ping.get("parsed", {})
    if str(ping_data.get("runtime", "")).lower() != "pi":
        raise RuntimeError("Pi health response did not identify runtime=pi")
    return [
        {
            "name": "pi_runtime_integrity",
            "status": "ok",
            "package": runtime.get("pi_package"),
            "version": runtime.get("pi_version"),
            "node_version": runtime.get("node_version"),
            "runtime_lock_sha256": runtime.get("runtime_lock_sha256"),
        },
        {
            "name": "pi_security_policy",
            "status": "ok",
            **policy,
        },
        {
            "name": "pi_model_catalog",
            "status": "ok",
            "provider": runtime.get("provider", ""),
            "model": runtime.get("model", ""),
            "available": runtime.get("model_available", False),
        },
        {
            "name": "pi_llm_ping",
            "status": "ok",
            "provider": ping.get("provider", ""),
            "model": ping.get("model", ""),
            "session_id": ping.get("session_id", ""),
            "response_id": ping.get("response_id", ""),
            "usage": ping.get("usage", {}),
        },
    ]


def _pi_runtime_from_preflight(preflight: dict[str, Any]) -> dict[str, Any]:
    runtime = next(
        (
            check
            for check in preflight.get("checks", [])
            if check.get("name") == "pi_runtime_integrity"
        ),
        {},
    )
    model = next(
        (
            check
            for check in preflight.get("checks", [])
            if check.get("name") == "pi_model_catalog"
        ),
        {},
    )
    return {
        "package": runtime.get("package"),
        "version": runtime.get("version"),
        "node_version": runtime.get("node_version"),
        "runtime_lock_sha256": runtime.get("runtime_lock_sha256"),
        "provider": model.get("provider"),
        "model": model.get("model"),
    }


def _find_preflight_check(
    state: dict[str, Any], name: str
) -> dict[str, Any]:
    for check in state.get("preflight", {}).get("checks", []):
        if check.get("name") == name:
            return check
    return {}


def _license_gate_from_preflight(preflight: dict[str, Any]) -> dict[str, Any] | None:
    for check in preflight.get("checks", []):
        if check.get("name") == "data_license":
            detail = check.get("detail")
            return detail if isinstance(detail, dict) else None
    return None


def _execution_cost_gate_from_preflight(
    preflight: dict[str, Any],
) -> dict[str, Any] | None:
    for check in preflight.get("checks", []):
        if check.get("name") == "execution_cost_calibration":
            detail = check.get("detail")
            return detail if isinstance(detail, dict) else None
    return None


def _research_protocol_gate_from_preflight(
    preflight: dict[str, Any],
) -> dict[str, Any] | None:
    for check in preflight.get("checks", []):
        if check.get("name") == "research_protocol_registration":
            detail = check.get("detail")
            return detail if isinstance(detail, dict) else None
    return None


def _experiment_registry_gate_from_preflight(
    preflight: dict[str, Any],
) -> dict[str, Any] | None:
    for check in preflight.get("checks", []):
        if check.get("name") == "experiment_registry_reservation":
            detail = check.get("detail")
            return detail if isinstance(detail, dict) else None
    return None


def _generate_summary(state: dict, output_dir: str):
    review = state["agent_outputs"].get("review_agent", {})
    risk = state["agent_outputs"].get("risk_agent", {})
    strategy = state["agent_outputs"].get("strategy_agent", {})
    backtest = state["agent_outputs"].get("backtest_agent", {})
    research = state["agent_outputs"].get("research_lead", {})
    data = state["agent_outputs"].get("data_agent", {})
    controls = state.get("business_controls", {})
    license_gate = controls.get("data_license_gate", {})
    research_protocol_gate = controls.get("research_protocol_gate", {})
    experiment_registry_gate = controls.get("experiment_registry_gate", {})
    execution_cost_gate = controls.get("execution_cost_gate", {})
    source_provenance = state.get("source_provenance", {})
    source_review_preflight = _find_preflight_check(
        state, "source_review_decision"
    )
    source_review_detail = source_review_preflight.get("detail", {})
    source_review_status = source_review_detail.get(
        "status", "NOT_EVALUATED_IN_MOCK_OR_PRECHECK"
    )
    config_snapshot = state.get("config", {})
    assurance = state.get("backtest_assurance", {})
    robustness = state.get("robustness_validation", {})

    trigger = review.get("trigger_level", risk.get("overall_risk_level", "UNKNOWN"))
    conclusion = review.get("conclusion", "N/A")
    key_risks = review.get("key_risks", risk.get("warnings", []))
    if not isinstance(key_risks, list):
        key_risks = [str(key_risks)] if key_risks else []
    human_items = review.get("human_confirmation_needed", [])
    if not isinstance(human_items, list):
        human_items = [str(human_items)] if human_items else []
    next_actions = review.get("next_actions", [])
    if not isinstance(next_actions, list):
        next_actions = [str(next_actions)] if next_actions else []
    disclaimer = review.get("disclaimer", "本报告仅供研究参考，不构成任何真实资金买卖建议。")

    if not state.get("mock") and assurance.get("decision") != "PASSED_FOR_INTERNAL_RESEARCH":
        trigger = "CRITICAL"
        conclusion = "回测执行与成本验收未通过，本轮结果只能保留审计，不得进入内部发布审批。"
        key_risks = list(key_risks) + [
            "回测验收失败项: " + ", ".join(assurance.get("failed_checks", ["UNAVAILABLE"]))
        ]
    assurance_human = assurance.get("human_confirmation_required", [])
    if isinstance(assurance_human, list):
        human_items = list(human_items) + assurance_human
    if (
        license_gate.get("status") == "approved"
        and license_gate.get("identity_assurance")
        == "document_hash_only_not_signature_authenticated"
    ):
        human_items = list(human_items) + [
            "法务/合规通过组织身份或合同系统复核服务商签署人、授权原件和当前有效性；文件哈希本身不认证身份"
        ]
    if (
        research_protocol_gate.get("status") == "approved_for_backtest"
        and research_protocol_gate.get("identity_and_timestamp_assurance")
        == "external_record_claim_bound_by_hash_not_cryptographically_authenticated"
    ):
        human_items = list(human_items) + [
            "独立模型验证人与合规负责人在组织研究登记系统复核协议登记时间、批准人身份和不可变更记录；本机哈希不能认证外部身份或时间戳"
        ]
    if (
        experiment_registry_gate.get("status") == "finalized"
        and experiment_registry_gate.get("identity_and_timestamp_assurance")
        == "external_record_claim_bound_by_hash_not_cryptographically_authenticated"
    ):
        human_items = list(human_items) + [
            "平台负责人和合规负责人对照组织实验登记系统复核 Registry ID、批准人身份、时间戳和留存策略；本地哈希链可发现修改，但不是 WORM 或数字签名"
        ]
    if (
        execution_cost_gate.get("status") == "approved_for_internal_research"
        and execution_cost_gate.get("identity_assurance")
        == "document_hash_only_not_approver_identity_authenticated"
    ):
        human_items = list(human_items) + [
            "量化负责人和合规负责人通过组织身份系统复核成本校准批准人及独立复核人；本机文件哈希不认证人员身份"
        ]

    if state.get("errors"):
        trigger = "CRITICAL"
        conclusion = "研究流水线存在未完成或不合规的 Agent 输出，本轮结果不得进入后续验证或任何资金决策。"
        key_risks = list(key_risks) + [f"流水线错误: {item}" for item in state["errors"]]
        if not state.get("mock") and license_gate.get("status") != "approved":
            key_risks += ["数据商业内部研究授权未通过，不能调用生产数据接口"]
        if (
            not state.get("mock")
            and research_protocol_gate.get("status") != "approved_for_backtest"
        ):
            key_risks += ["研究假设、参数、样本区间和前向观察阈值没有外部预注册证据"]
        if (
            not state.get("mock")
            and experiment_registry_gate.get("status") != "finalized"
        ):
            key_risks += [
                "实验未在仓库外追加式账本完成预登记和终态登记，失败实验可能被选择性遗漏"
            ]
        if (
            not state.get("mock")
            and execution_cost_gate.get("status")
            != "approved_for_internal_research"
        ):
            key_risks += ["执行成本参数没有外部材料、独立复核和当前规则簿绑定证据"]
        if not state.get("mock") and not config_snapshot.get("tushare_token_set"):
            key_risks += ["未配置获准组织账户的 Tushare Token，无法形成真实数据快照"]
        human_items = list(human_items) + [
            "平台负责人为 operations/alerts.json 中每个 CRITICAL 门禁指定责任人和证据编号"
        ]
        next_actions = ["保留本轮失败 Run；禁止切换 Mock 或复用旧快照冒充真实数据"]
        if not state.get("mock") and license_gate.get("status") != "approved":
            human_items += [
                "数据负责人和法务取得服务商 v2 书面组织授权，覆盖商业内部研究、七个接口、自动API、缓存、衍生分析、DeepSeek、留存和终止处置"
            ]
            next_actions += [
                "取得已签授权文件，生成 APPROVED 证据 JSON，并在本机用 DATA_LICENSE_EVIDENCE_PATH 引用；合同和证据不得提交仓库"
            ]
        if (
            not state.get("mock")
            and research_protocol_gate.get("status") != "approved_for_backtest"
        ):
            human_items += [
                "量化负责人、独立模型验证人和合规负责人在组织系统预注册假设、精确输入指纹、冻结模型契约及前向观察升降级阈值"
            ]
            next_actions += [
                "在仓库外导出研究登记回执和原件哈希，填写 v1 协议证据并通过 RESEARCH_PROTOCOL_EVIDENCE_PATH 引用"
            ]
        if (
            not state.get("mock")
            and experiment_registry_gate.get("status") != "finalized"
        ):
            human_items += [
                "量化负责人、独立模型验证人、平台负责人和合规负责人批准独立实验 Registry，并确认所有成功、失败和中断 Run 均只能追加、不得删除"
            ]
            next_actions += [
                "在仓库外初始化实验 Registry，设置 EXPERIMENT_REGISTRY_PATH；清理遗留预登记只能追加恢复终态，禁止修改 experiments.jsonl 历史行"
            ]
        if (
            not state.get("mock")
            and execution_cost_gate.get("status")
            != "approved_for_internal_research"
        ):
            human_items += [
                "量化负责人、独立复核人和合规负责人确认券商费率口径、滑点、冲击、模拟资金规模、参与率和流动性下限"
            ]
            next_actions += [
                "在仓库外完成成本校准材料和 SHA-256 绑定，填写 v1 证据并通过 EXECUTION_COST_EVIDENCE_PATH 引用"
            ]
        if not state.get("mock") and not config_snapshot.get("tushare_token_set"):
            human_items += [
                "数据负责人确认 Tushare 账户权限、积分、频率和组织使用权覆盖本项目"
            ]
            next_actions += [
                "许可证据通过后，在受控 Secret/环境中配置 TUSHARE_TOKEN；不得写入代码、日志或审批 JSON"
            ]

    source_provenance = state.get("source_provenance", {})
    if source_provenance.get("release_ready") is not True:
        trigger = "CRITICAL"
        if not state.get("errors"):
            conclusion = "研究执行已完成，但源码没有形成可审计的 clean commit，本轮结果只能用于开发验证，不能进入内部发布审批。"
        key_risks = [
            f"源码版本门禁未通过: {source_provenance.get('reason', 'source provenance missing')}"
        ] + list(key_risks)
        human_items = [
            "由平台负责人复核源码和凭据扫描结果，纳入受控私有版本库并形成 clean commit/tag"
        ] + list(human_items)
        source_action = (
            "先生成并校验 source review packet 和外部 decision record，由 Platform/Security 两个不同组织身份逐文件复核；"
            "机器校验通过后仍须人工授权，再建立最小权限私有 Git clean commit/tag"
        )
        next_actions = [source_action] + [
            action for action in next_actions if action != source_action
        ]

    if state.get("mock"):
        source_actions = []
        if source_provenance.get("release_ready") is not True:
            source_actions = [source_action]
        next_actions = source_actions + [
            "任命 GM、Quant、Validator、Data、Platform、Model、Compliance、Ops、Finance 九个治理角色并批准试运行预算",
            "在仓库外完成数据授权、研究预注册、实验 Registry 和执行成本四类证据，并由相互独立的责任人复核",
            "重跑 project-readiness；只有全部前置项通过后，才由 Gate Owner 记录明确的 G1 GO/NO-GO",
            "G1 GO 前不得配置或调用真实 Tushare/付费 Pi；G1 GO 后才可在受控 Secret 中配置凭据并执行供应商 acceptance",
            "付费 Pi/Tushare acceptance 通过后，以新 Run ID 执行首个真实 7/7 baseline，并独立复验数据快照、成本和稳健性",
        ]
        human_items = [
            "Platform 与 Security 是否已在外部组织系统完成候选清单全部文件的逐文件审查、解决全部 review flags，并提交可校验的 decision record",
            "Gate Owner/Platform Owner 是否在 decision record 校验通过后单独授权建立 private baseline；机器校验不等于 Git 授权",
            "九个治理角色是否已任命，试运行预算是否已由 Finance/Gate Owner 批准",
            "数据授权、研究协议、实验 Registry、执行成本四类仓库外证据是否均由对应责任人和独立复核人批准",
            "Gate Owner 是否在全部前置项通过后记录了明确的 G1 GO；机器 READY 不能替代该决定",
        ] + list(human_items)

    if state.get("errors"):
        next_actions += [
            "先执行 .\\check_pi.ps1，再运行 .\\run_quant_agents.ps1",
            "真实 Run 达到 7/7 后复验 manifest/事件链，完成五方审批、外部归档和监控接入；此前不得安装生产调度",
        ]

    runtime_str = state.get("runtime", "unknown")
    pi_runtime = state.get("pi_runtime") or {}
    usage = state.get("model_usage", {})
    budget_gate = state.get("budget_gate", {})

    md = f"""# CSI 500 量化策略研究报告

**生成时间**: {state.get('finished_at', 'N/A')}
**Run ID**: {state.get('run_id', 'N/A')}
**输入指纹**: {state.get('input_fingerprint', 'N/A')}
**源码提交**: {source_provenance.get('head_commit') or 'UNVERSIONED'}
**源码发布门禁**: {'passed' if source_provenance.get('release_ready') is True else 'failed'}
**源码双人审查证据**: {source_review_status}
**运行时**: {runtime_str}
**Pi Runtime**: {pi_runtime.get('package', 'N/A')}@{pi_runtime.get('version', 'N/A')}
**Pi Provider / 模型**: {pi_runtime.get('provider', 'N/A')} / {pi_runtime.get('model', 'N/A')}
**模式**: {'MOCK (模拟)' if state.get('mock') else ('REAL (已调用真实LLM)' if usage.get('calls_with_usage', 0) else 'REAL REQUEST (真实LLM未调用)')}
**数据模式**: {state.get('data_mode', 'UNKNOWN')}
**指标来源**: {state.get('metrics_source', 'UNKNOWN')}
**回测验收**: {assurance.get('decision', 'UNAVAILABLE')}
**稳健性矩阵**: {robustness.get('decision', 'UNAVAILABLE')}
**数据质量**: {data.get('data_quality', 'UNKNOWN')}
**数据快照**: {data.get('snapshot_id', 'N/A')}
**成功Agent**: {state.get('success_count', 0)}/{state.get('total_agents', 0)}
**模型Token**: input={usage.get('input_tokens', 0)}, cache_read={usage.get('cache_read_tokens', 0)}, cache_write={usage.get('cache_write_tokens', 0)}, output={usage.get('output_tokens', 0)}, total={usage.get('total_tokens', 0)}
**缓存未命中计费Token**: {usage.get('cache_miss_billable_tokens', 0)}
**模型估算成本(USD)**: {usage.get('estimated_cost_usd', 0)}
**模型高峰包络估算成本(USD)**: {usage.get('contingency_estimated_cost_usd', 0)}
**模型供应商计费回报(USD)**: {usage.get('provider_reported_cost_usd', 0)}
**预算门禁采用成本(USD)**: {usage.get('budget_cost_usd', 0)}
**DeepSeek 价格基线/复核日/高峰倍数**: {usage.get('pricing', {}).get('baseline_id', 'N/A')} / {usage.get('pricing', {}).get('reviewed_at', 'N/A')} / {usage.get('pricing', {}).get('budget_contingency_multiplier', 'N/A')}
**成本与时限门禁**: {budget_gate.get('status', 'UNKNOWN')}
**预期用途**: {controls.get('intended_use', 'unknown')}
**数据许可门禁**: {license_gate.get('status', 'unknown')}
**许可证据 Schema**: {license_gate.get('schema_version', 'N/A')}
**许可证据 SHA-256**: {license_gate.get('evidence_file_sha256', 'N/A')}
**许可身份保证**: {license_gate.get('identity_assurance', 'N/A')}
**研究协议门禁**: {research_protocol_gate.get('status', 'unknown')}
**研究协议 ID/版本**: {research_protocol_gate.get('protocol_id', 'N/A')} / {research_protocol_gate.get('protocol_version', 'N/A')}
**协议绑定模式**: {research_protocol_gate.get('binding_mode', 'N/A')}
**冻结模型契约 SHA-256**: {research_protocol_gate.get('model_contract_sha256', 'N/A')}
**协议证据 SHA-256**: {research_protocol_gate.get('evidence_file_sha256', 'N/A')}
**实验登记门禁**: {experiment_registry_gate.get('status', 'unknown')}
**实验 Registry ID**: {experiment_registry_gate.get('registry_id', 'N/A')}
**实验预登记事件 SHA-256**: {experiment_registry_gate.get('reservation_entry_hash', 'N/A')}
**实验终态事件 SHA-256**: {experiment_registry_gate.get('finalization_entry_hash', 'N/A')}
**实验结果契约 SHA-256**: {experiment_registry_gate.get('state_contract_sha256', 'N/A')}
**实验账本保障**: {experiment_registry_gate.get('storage_enforcement', 'N/A')}
**执行成本校准门禁**: {execution_cost_gate.get('status', 'unknown')}
**成本模型指纹**: {execution_cost_gate.get('cost_model_fingerprint', 'N/A')}
**成本校准证据 SHA-256**: {execution_cost_gate.get('evidence_file_sha256', 'N/A')}
**成本校准基准/临时性**: {execution_cost_gate.get('calibration_basis', 'N/A')} / {execution_cost_gate.get('provisional', 'N/A')}
**外部分发**: PROHIBITED

---

## 关键结论

{conclusion}

## 研究流程触发等级: **{trigger}**

## 主要风险

"""
    for r in key_risks:
        md += f"- {r}\n"

    md += "\n## 需要人工确认的问题\n\n"
    for h in human_items:
        md += f"- [ ] {h}\n"

    md += "\n## 下一步动作\n\n"
    for n in next_actions:
        md += f"- {n}\n"

    md += f"""
## 策略概要

- **策略名称**: {strategy.get('strategy_name', 'N/A')}
- **策略类型**: {strategy.get('strategy_type', 'N/A')}
- **信号数量**: {len(strategy.get('signals', []))}
- **再平衡频率**: {strategy.get('rebalance_frequency', 'N/A')}

## 回测摘要

- **总收益**: {backtest.get('total_return', 'N/A')}
- **年化收益**: {backtest.get('annualized_return', 'N/A')}
- **夏普比率**: {backtest.get('sharpe_ratio', 'N/A')}
- **最大回撤**: {backtest.get('max_drawdown', 'N/A')}
- **胜率**: {backtest.get('win_rate', 'N/A')}
- **执行订单数**: {backtest.get('trade_count', 'N/A')}
- **再平衡次数**: {backtest.get('rebalance_count', 'N/A')}
- **模型总成本(CNY)**: {backtest.get('cost_summary', {}).get('total_cost_cny', 'N/A')}
- **成本模型**: {backtest.get('cost_summary', {}).get('model_id', 'N/A')}
- **有效规则策略**: {', '.join(backtest.get('execution_policy_snapshot', {}).get('policy_ids', [])) or 'N/A'}
- **样本外区间**: {backtest.get('robustness_validation', {}).get('chronological_split', {}).get('holdout_start', 'N/A')} ~ {backtest.get('robustness_validation', {}).get('chronological_split', {}).get('holdout_end', 'N/A')}
- **压力场景数**: {backtest.get('robustness_validation', {}).get('scenario_count', 'N/A')}
- **滚动样本外验证**: {backtest.get('robustness_validation', {}).get('walk_forward', {}).get('decision', 'N/A')} ({backtest.get('robustness_validation', {}).get('walk_forward', {}).get('passing_fold_count', 'N/A')}/{backtest.get('robustness_validation', {}).get('walk_forward', {}).get('fold_count', 'N/A')} folds)

## Agent 执行状态

| Agent | Pi Role | Runtime | 状态 | 耗时(s) | Provider / 模型 |
|-------|---------|---------|------|---------|-------------------|
"""
    for r in state.get("agent_results", []):
        md += f"| {r['agent']} | {r.get('pi_agent_role', '')} | {r.get('runtime', '')} | {r['status']} | {r['elapsed_s']} | {r.get('provider', '')} / {r.get('model', '')} |\n"

    md += f"""
---

## ⚠️ 免责声明

{disclaimer}

> 本报告由 AI Agent 自动生成，所有数据和分析仅供研究参考。
> 不构成任何真实资金买卖建议。请勿据此进行真实交易。
> 系统未接入券商、订单路由或真实资金账户；LLM 不负责计算回测指标。
"""

    with open(os.path.join(output_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(md)
