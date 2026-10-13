from __future__ import annotations

import ctypes
import json
import math
import os
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from .audit import canonical_json_sha256, write_json_atomic
from .config import (
    APPROVED_DEEPSEEK_OFF_PEAK_RATES,
    APPROVED_DEEPSEEK_PRICING_BASELINE_ID,
    Config,
)
from .governance import is_release_eligible_data_license
from .execution_cost_governance import is_release_eligible_execution_cost
from .research_protocol import (
    build_model_contract_fingerprint,
    is_release_eligible_research_protocol,
)
from .experiment_registry import verify_experiment_registry_gate


PRICING_SOURCE_URL = "https://api-docs.deepseek.com/quick_start/pricing/"


class ConcurrentRunError(RuntimeError):
    pass


class DuplicateRequestError(RuntimeError):
    pass


@dataclass
class RunLock:
    runs_root: str
    run_id: str
    output_dir: str
    stale_seconds: int = Config.RUN_LOCK_STALE_SECONDS

    def __post_init__(self) -> None:
        operations_dir = os.path.join(os.path.abspath(self.runs_root), ".operations")
        self.lock_path = os.path.join(operations_dir, "pipeline.lock.json")
        self.stale_archive_dir = os.path.join(operations_dir, "stale_locks")
        self.nonce = uuid.uuid4().hex
        self.acquired = False
        self.metadata: dict[str, Any] = {}

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()

    def acquire(self) -> None:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        for _ in range(3):
            metadata = self._new_metadata("acquiring")
            try:
                descriptor = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                    json.dump(metadata, file, ensure_ascii=False, indent=2)
                    file.write("\n")
                    file.flush()
                    os.fsync(file.fileno())
                self.acquired = True
                self.metadata = metadata
                self.heartbeat("acquired")
                return
            except FileExistsError:
                existing = _read_json(self.lock_path)
                if not self._can_reclaim(existing):
                    raise ConcurrentRunError(_format_lock_error(existing))
                self._archive_stale_lock(existing)
        raise ConcurrentRunError("could not acquire pipeline lock after stale-lock recovery")

    def heartbeat(self, stage: str) -> None:
        if not self.acquired:
            return
        current = _read_json(self.lock_path)
        if current.get("nonce") != self.nonce:
            raise ConcurrentRunError("pipeline lock ownership changed unexpectedly")
        current["heartbeat_at"] = _utc_now()
        current["stage"] = stage
        write_json_atomic(self.lock_path, current)
        self.metadata = current

    def release(self) -> None:
        if not self.acquired:
            return
        current = _read_json(self.lock_path)
        if current.get("nonce") == self.nonce:
            try:
                os.unlink(self.lock_path)
            except FileNotFoundError:
                pass
        self.acquired = False

    def _new_metadata(self, stage: str) -> dict[str, Any]:
        now = _utc_now()
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "output_dir": os.path.abspath(self.output_dir),
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "nonce": self.nonce,
            "acquired_at": now,
            "heartbeat_at": now,
            "stage": stage,
        }

    def _can_reclaim(self, existing: dict[str, Any]) -> bool:
        if not existing:
            try:
                age = time.time() - os.path.getmtime(self.lock_path)
            except OSError:
                return True
            return age > self.stale_seconds
        heartbeat = _parse_timestamp(existing.get("heartbeat_at"))
        if existing.get("hostname") != socket.gethostname():
            if heartbeat is None:
                return False
            return (
                datetime.now(timezone.utc) - heartbeat
            ).total_seconds() >= self.stale_seconds
        pid = int(existing.get("pid") or 0)
        if _is_process_alive(pid):
            return False
        if heartbeat is None:
            return True
        return (datetime.now(timezone.utc) - heartbeat).total_seconds() >= 0

    def _archive_stale_lock(self, existing: dict[str, Any]) -> None:
        os.makedirs(self.stale_archive_dir, exist_ok=True)
        stale_run = str(existing.get("run_id", "unknown")).replace(os.sep, "_")
        destination = os.path.join(
            self.stale_archive_dir,
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{stale_run}_{uuid.uuid4().hex[:8]}.json",
        )
        try:
            os.replace(self.lock_path, destination)
        except FileNotFoundError:
            pass


def enforce_request_idempotency(
    runs_root: str,
    request_id: str | None,
    retry_of: str | None = None,
) -> None:
    if not request_id:
        return
    matches = [
        (path, state)
        for path, state in _iter_run_states(runs_root)
        if state.get("request_id") == request_id
    ]
    if not matches:
        return
    matches.sort(
        key=lambda item: (
            str(item[1].get("started_at") or item[1].get("finished_at") or ""),
            str(item[1].get("run_id") or os.path.basename(item[0])),
        )
    )
    latest_path, latest_state = matches[-1]
    latest_run_id = str(
        latest_state.get("run_id") or os.path.basename(latest_path)
    )
    retryable_statuses = {
        "preflight_failed",
        "completed_with_errors",
        "interrupted",
        "failed",
    }
    if retry_of == latest_run_id and latest_state.get("status") in retryable_statuses:
        return
    if retry_of and retry_of != latest_run_id:
        raise DuplicateRequestError(
            f"request_id {request_id!r} latest run is {latest_run_id}; "
            "--retry-of must reference that latest failed/interrupted run"
        )
    raise DuplicateRequestError(
        f"request_id {request_id!r} already belongs to run {latest_run_id} "
        f"with status {latest_state.get('status', 'unknown')}; "
        "use a new request_id, or --retry-of for the latest failed/interrupted run"
    )


def append_event(
    output_dir: str,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    operations_dir = os.path.join(output_dir, "operations")
    os.makedirs(operations_dir, exist_ok=True)
    path = os.path.join(operations_dir, "events.jsonl")
    previous = _last_json_line(path)
    event = {
        "sequence": int(previous.get("sequence", 0)) + 1,
        "timestamp": _utc_now(),
        "event_type": event_type,
        "details": details or {},
        "previous_hash": previous.get("event_hash", ""),
    }
    event["event_hash"] = canonical_json_sha256(event)
    with open(path, "a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        file.flush()
        os.fsync(file.fileno())
    return event


def verify_event_chain(path: str) -> dict[str, Any]:
    errors = []
    previous_hash = ""
    expected_sequence = 1
    count = 0
    if not os.path.isfile(path):
        return {"ok": False, "event_count": 0, "errors": ["event log is missing"]}
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"line {line_number}: invalid JSON")
                continue
            count += 1
            recorded_hash = event.pop("event_hash", "")
            if event.get("sequence") != expected_sequence:
                errors.append(f"line {line_number}: sequence mismatch")
            if event.get("previous_hash") != previous_hash:
                errors.append(f"line {line_number}: previous hash mismatch")
            actual_hash = canonical_json_sha256(event)
            if recorded_hash != actual_hash:
                errors.append(f"line {line_number}: event hash mismatch")
            previous_hash = recorded_hash
            expected_sequence += 1
    return {
        "ok": not errors,
        "event_count": count,
        "last_event_hash": previous_hash,
        "errors": errors,
    }


def aggregate_model_usage(
    agent_results: list[dict[str, Any]],
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for result in agent_results:
        usage = result.get("usage")
        if isinstance(usage, dict) and usage:
            rows.append((str(result.get("agent", "unknown")), usage))
    for check in (preflight or {}).get("checks", []):
        usage = check.get("usage")
        if isinstance(usage, dict) and usage:
            rows.append((str(check.get("name", "preflight")), usage))

    aggregate: dict[str, Any] = {
        "input_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "provider_reported_cost_usd": 0.0,
        "calls_with_usage": 0,
        "raw_by_call": {},
    }
    for name, usage in rows:
        input_tokens = _first_numeric(
            usage, ("input_tokens", "prompt_tokens", "inputTokens", "input")
        )
        cache_read = _first_numeric(
            usage,
            (
                "cache_read_tokens",
                "cacheReadTokens",
                "cache_read_input_tokens",
                "cacheRead",
            ),
        )
        cache_write = _first_numeric(
            usage,
            (
                "cache_write_tokens",
                "cacheWriteTokens",
                "cache_creation_input_tokens",
                "cacheWrite",
            ),
        )
        output_tokens = _first_numeric(
            usage,
            ("output_tokens", "completion_tokens", "outputTokens", "output"),
        )
        reasoning_tokens = _first_numeric(
            usage, ("reasoning_tokens", "reasoningTokens", "reasoning")
        )
        total_tokens = _first_numeric(
            usage, ("total_tokens", "totalTokens", "total")
        ) or input_tokens + cache_read + cache_write + output_tokens
        aggregate["input_tokens"] += int(input_tokens)
        aggregate["cache_read_tokens"] += int(cache_read)
        aggregate["cache_write_tokens"] += int(cache_write)
        aggregate["output_tokens"] += int(output_tokens)
        aggregate["reasoning_tokens"] += int(reasoning_tokens)
        aggregate["total_tokens"] += int(total_tokens)
        cost = usage.get("cost", {})
        if isinstance(cost, dict):
            aggregate["provider_reported_cost_usd"] += float(
                _first_numeric(cost, ("total", "total_cost", "totalCost"))
            )
        aggregate["calls_with_usage"] += 1
        aggregate["raw_by_call"][name] = usage
    aggregate["cache_miss_billable_tokens"] = (
        aggregate["input_tokens"] + aggregate["cache_write_tokens"]
    )
    aggregate["estimated_cost_usd"] = estimate_model_cost_usd(aggregate)
    aggregate["contingency_estimated_cost_usd"] = round(
        aggregate["estimated_cost_usd"]
        * Config.DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER,
        8,
    )
    aggregate["provider_reported_cost_usd"] = round(
        aggregate["provider_reported_cost_usd"], 8
    )
    aggregate["budget_cost_usd"] = max(
        aggregate["contingency_estimated_cost_usd"],
        aggregate["provider_reported_cost_usd"],
    )
    aggregate["pricing"] = {
        "source": PRICING_SOURCE_URL,
        "baseline_id": APPROVED_DEEPSEEK_PRICING_BASELINE_ID,
        "reviewed_at": Config.DEEPSEEK_PRICING_REVIEWED_DATE,
        "review_max_age_days": Config.DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS,
        "budget_contingency_multiplier": Config.DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER,
        "baseline_schedule": "deepseek_v4_pro_off_peak",
        "budget_schedule": "peak_rate_envelope",
        "input_cache_hit_usd_per_m": Config.DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M,
        "input_cache_miss_usd_per_m": Config.DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M,
        "output_usd_per_m": Config.DEEPSEEK_OUTPUT_USD_PER_M,
    }
    return aggregate


def estimate_model_cost_usd(usage: dict[str, Any]) -> float:
    input_tokens = float(usage.get("input_tokens", 0))
    cache_read_tokens = float(usage.get("cache_read_tokens", 0))
    cache_write_tokens = float(usage.get("cache_write_tokens", 0))
    cache_miss_billable_tokens = input_tokens + cache_write_tokens
    cost = (
        cache_miss_billable_tokens * Config.DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M
        + cache_read_tokens
        * Config.DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M
        + float(usage.get("output_tokens", 0)) * Config.DEEPSEEK_OUTPUT_USD_PER_M
    ) / 1_000_000
    return round(cost, 8)


def evaluate_budget_gate(
    agent_results: list[dict[str, Any]],
    preflight: dict[str, Any] | None,
    pipeline_elapsed_seconds: float,
) -> dict[str, Any]:
    usage = aggregate_model_usage(agent_results, preflight)
    breaches = []
    if usage["total_tokens"] > Config.MAX_LLM_TOTAL_TOKENS_PER_RUN:
        breaches.append(
            f"total tokens {usage['total_tokens']} exceed {Config.MAX_LLM_TOTAL_TOKENS_PER_RUN}"
        )
    if usage["budget_cost_usd"] > Config.MAX_LLM_COST_USD_PER_RUN:
        breaches.append(
            f"budget cost USD {usage['budget_cost_usd']} exceeds "
            f"{Config.MAX_LLM_COST_USD_PER_RUN}"
        )
    slow_agents = [
        str(result.get("agent"))
        for result in agent_results
        if float(result.get("elapsed_s", 0)) > Config.MAX_AGENT_RUNTIME_SECONDS
    ]
    if slow_agents:
        breaches.append("agent runtime limit exceeded: " + ", ".join(slow_agents))
    if pipeline_elapsed_seconds > Config.MAX_PIPELINE_RUNTIME_SECONDS:
        breaches.append(
            f"pipeline runtime {round(pipeline_elapsed_seconds, 2)}s exceeds "
            f"{Config.MAX_PIPELINE_RUNTIME_SECONDS}s"
        )
    return {
        "status": "failed" if breaches else "passed",
        "breaches": breaches,
        "observed": {
            "total_tokens": usage["total_tokens"],
            "cache_miss_billable_tokens": usage["cache_miss_billable_tokens"],
            "estimated_cost_usd": usage["estimated_cost_usd"],
            "contingency_estimated_cost_usd": usage[
                "contingency_estimated_cost_usd"
            ],
            "provider_reported_cost_usd": usage["provider_reported_cost_usd"],
            "budget_cost_usd": usage["budget_cost_usd"],
            "pipeline_elapsed_seconds": round(pipeline_elapsed_seconds, 2),
        },
        "limits": {
            "max_total_tokens": Config.MAX_LLM_TOTAL_TOKENS_PER_RUN,
            "max_estimated_cost_usd": Config.MAX_LLM_COST_USD_PER_RUN,
            "max_agent_runtime_seconds": Config.MAX_AGENT_RUNTIME_SECONDS,
            "max_pipeline_runtime_seconds": Config.MAX_PIPELINE_RUNTIME_SECONDS,
        },
    }


def is_current_model_pricing(
    state: dict[str, Any],
    today: date | None = None,
) -> bool:
    config_pricing = state.get("config", {}).get("deepseek_pricing", {})
    usage = state.get("model_usage", {})
    usage_pricing = usage.get("pricing", {})
    try:
        reviewed_at = datetime.strptime(
            str(config_pricing.get("reviewed_at", "")), "%Y-%m-%d"
        ).date()
        review_max_age_days = int(config_pricing.get("review_max_age_days", 0))
        multiplier = float(config_pricing.get("budget_contingency_multiplier", 0))
        estimated = float(usage.get("estimated_cost_usd", -1))
        contingency = float(usage.get("contingency_estimated_cost_usd", -1))
        provider_reported = float(usage.get("provider_reported_cost_usd", -1))
        budget_cost = float(usage.get("budget_cost_usd", -1))
        config_rates = {
            field: float(config_pricing.get(field, -1))
            for field in (
                "input_cache_hit_usd_per_m",
                "input_cache_miss_usd_per_m",
                "output_usd_per_m",
            )
        }
        usage_rates = {
            field: float(usage_pricing.get(field, -1))
            for field in (
                "input_cache_hit_usd_per_m",
                "input_cache_miss_usd_per_m",
                "output_usd_per_m",
            )
        }
    except (TypeError, ValueError):
        return False
    evaluation_date = today or date.today()
    rate_fields = (
        "input_cache_hit_usd_per_m",
        "input_cache_miss_usd_per_m",
        "output_usd_per_m",
    )
    expected_rates = APPROVED_DEEPSEEK_OFF_PEAK_RATES
    return (
        reviewed_at <= evaluation_date
        and (evaluation_date - reviewed_at).days <= review_max_age_days
        and review_max_age_days == Config.DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS
        and 2.0 <= multiplier <= 3.0
        and multiplier == Config.DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER
        and all(
            config_rates[field] == expected_rates[field]
            and usage_rates[field] == expected_rates[field]
            for field in rate_fields
        )
        and all(
            math.isfinite(value)
            for value in (
                estimated,
                contingency,
                provider_reported,
                budget_cost,
                *config_rates.values(),
                *usage_rates.values(),
            )
        )
        and usage_pricing.get("source") == PRICING_SOURCE_URL
        and config_pricing.get("baseline_id")
        == APPROVED_DEEPSEEK_PRICING_BASELINE_ID
        and usage_pricing.get("baseline_id")
        == APPROVED_DEEPSEEK_PRICING_BASELINE_ID
        and usage_pricing.get("reviewed_at") == config_pricing.get("reviewed_at")
        and usage_pricing.get("baseline_schedule") == "deepseek_v4_pro_off_peak"
        and usage_pricing.get("budget_schedule") == "peak_rate_envelope"
        and abs(contingency - round(estimated * multiplier, 8)) < 1e-9
        and abs(budget_cost - max(contingency, provider_reported)) < 1e-9
    )


def write_operational_artifacts(state: dict[str, Any], output_dir: str) -> None:
    operations_dir = os.path.join(output_dir, "operations")
    os.makedirs(operations_dir, exist_ok=True)
    usage = state.get("model_usage", {})
    budget = state.get("budget_gate", {})
    license_gate = state.get("business_controls", {}).get("data_license_gate", {})
    execution_cost_gate = state.get("business_controls", {}).get(
        "execution_cost_gate", {}
    )
    research_protocol_gate = state.get("business_controls", {}).get(
        "research_protocol_gate", {}
    )
    experiment_registry_gate = state.get("business_controls", {}).get(
        "experiment_registry_gate", {}
    )
    robustness = state.get("robustness_validation", {})
    metrics = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "runtime": state.get("runtime"),
        "mock": state.get("mock"),
        "success_count": state.get("success_count", 0),
        "error_count": state.get("error_count", 0),
        "model_usage": usage,
        "budget_gate": budget,
        "data_mode": state.get("data_mode"),
        "metrics_source": state.get("metrics_source"),
        "backtest_assurance_decision": state.get("backtest_assurance", {}).get(
            "decision"
        ),
        "market_rulebook_sha256": state.get("agent_outputs", {})
        .get("backtest_agent", {})
        .get("execution_policy_snapshot", {})
        .get("rulebook_sha256"),
        "backtest_assurance": state.get("backtest_assurance", {}),
        "robustness_validation": robustness,
        "walk_forward_decision": robustness.get("walk_forward", {}).get("decision"),
        "walk_forward_passing_folds": robustness.get("walk_forward", {}).get(
            "passing_fold_count"
        ),
        "data_snapshot_id": (
            state.get("agent_outputs", {}).get("data_agent", {}).get("snapshot_id")
        ),
        "freshness_lag_trade_days": state.get("agent_outputs", {})
        .get("data_agent", {})
        .get("freshness_lag_trade_days"),
        "trigger_level": state.get("agent_outputs", {})
        .get("review_agent", {})
        .get("trigger_level"),
        "data_license_status": license_gate.get("status"),
        "data_license_schema_version": license_gate.get("schema_version"),
        "data_license_evidence_sha256": license_gate.get("evidence_file_sha256"),
        "research_protocol_status": research_protocol_gate.get("status"),
        "research_protocol_id": research_protocol_gate.get("protocol_id"),
        "research_protocol_version": research_protocol_gate.get(
            "protocol_version"
        ),
        "research_protocol_binding_mode": research_protocol_gate.get(
            "binding_mode"
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
        "experiment_registry_storage_enforcement": experiment_registry_gate.get(
            "storage_enforcement"
        ),
        "execution_cost_status": execution_cost_gate.get("status"),
        "execution_cost_model_fingerprint": execution_cost_gate.get(
            "cost_model_fingerprint"
        ),
        "execution_cost_evidence_sha256": execution_cost_gate.get(
            "evidence_file_sha256"
        ),
        "execution_cost_provisional": execution_cost_gate.get("provisional"),
        "external_distribution_approved": False,
        "broker_connection_enabled": False,
        "source_release_ready": state.get("source_provenance", {}).get(
            "release_ready", False
        ),
        "model_pricing_current": is_current_model_pricing(state),
    }
    alerts = []
    if state.get("status") != "completed":
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "PIPELINE_NOT_COMPLETED",
                "message": f"pipeline status is {state.get('status')}",
            }
        )
    if state.get("mock"):
        alerts.append(
            {
                "severity": "INFO",
                "code": "MOCK_NOT_RELEASEABLE",
                "message": "mock output is synthetic and cannot be released",
            }
        )
    assurance = state.get("backtest_assurance", {})
    if (
        not state.get("mock")
        and (
            assurance.get("decision") != "PASSED_FOR_INTERNAL_RESEARCH"
            or assurance.get("release_gate_passed") is not True
        )
    ):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "BACKTEST_ASSURANCE_FAILED",
                "message": "deterministic backtest assurance did not pass",
            }
        )
    if not state.get("mock") and not is_current_model_pricing(state):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "MODEL_PRICING_BASELINE_INVALID",
                "message": (
                    "DeepSeek pricing snapshot is stale, inconsistent with the approved "
                    "runtime configuration, or missing the peak-rate budget envelope"
                ),
            }
        )
    if (
        not state.get("mock")
        and (
            robustness.get("decision") != "PASSED"
            or robustness.get("failed_checks")
        )
    ):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "ROBUSTNESS_VALIDATION_FAILED",
                "message": "holdout, walk-forward, or stress validation did not pass",
            }
        )
    for breach in budget.get("breaches", []):
        alerts.append(
            {"severity": "CRITICAL", "code": "BUDGET_GATE_FAILED", "message": breach}
        )
    cost_limit = float(budget.get("limits", {}).get("max_estimated_cost_usd", 0) or 0)
    observed_cost = float(budget.get("observed", {}).get("budget_cost_usd", 0) or 0)
    if cost_limit and observed_cost >= cost_limit * 0.8 and not budget.get("breaches"):
        alerts.append(
            {
                "severity": "WARNING",
                "code": "LLM_COST_NEAR_LIMIT",
                "message": f"estimated LLM cost reached {observed_cost / cost_limit:.1%} of the run limit",
            }
        )
    data_output = state.get("agent_outputs", {}).get("data_agent", {})
    allowed_lag = state.get("input", {}).get("data_controls", {}).get(
        "max_staleness_trade_days"
    )
    observed_lag = data_output.get("freshness_lag_trade_days")
    if (
        not state.get("mock")
        and isinstance(observed_lag, (int, float))
        and isinstance(allowed_lag, (int, float))
        and observed_lag > allowed_lag
    ):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "MARKET_DATA_STALE",
                "message": f"market data lag {observed_lag} exceeds allowed {allowed_lag} trade days",
            }
        )
    license_status = license_gate.get("status")
    if not state.get("mock") and not is_release_eligible_data_license(license_gate):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "DATA_LICENSE_NOT_APPROVED",
                "message": (
                    "data license is missing the current organizational, processing, "
                    f"retention, or evidence scope; status={license_status or 'missing'}"
                ),
            }
        )
    if (
        not state.get("mock")
        and not is_release_eligible_research_protocol(
            research_protocol_gate,
            input_fingerprint=state.get("input_fingerprint"),
            model_contract_fingerprint=(
                build_model_contract_fingerprint(state.get("input", {}))
                if isinstance(state.get("input"), dict)
                else None
            ),
        )
    ):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "RESEARCH_PROTOCOL_NOT_APPROVED",
                "message": (
                    "research protocol is missing, stale, not externally registered, "
                    "or mismatched to the frozen input/model contract"
                ),
            }
        )
    if (
        not state.get("mock")
        and not is_release_eligible_execution_cost(execution_cost_gate)
    ):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "EXECUTION_COST_CALIBRATION_FAILED",
                "message": (
                    "execution-cost evidence is missing, stale, mismatched, or not "
                    "approved for internal research"
                ),
            }
        )
    if not state.get("mock"):
        experiment_verification = verify_experiment_registry_gate(state)
        if experiment_verification.get("eligible") is not True:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "code": "EXPERIMENT_REGISTRY_NOT_RELEASE_ELIGIBLE",
                    "message": (
                        "external experiment reservation/finalization is missing, "
                        "inconsistent, or records a non-clean outcome"
                    ),
                }
            )
    preflight_cost = next(
        (
            row
            for row in state.get("preflight", {}).get("checks", [])
            if isinstance(row, dict)
            and row.get("name") == "execution_cost_calibration"
        ),
        {},
    )
    preflight_protocol = next(
        (
            row
            for row in state.get("preflight", {}).get("checks", [])
            if isinstance(row, dict)
            and row.get("name") == "research_protocol_registration"
        ),
        {},
    )
    if (
        not state.get("mock")
        and is_release_eligible_research_protocol(
            research_protocol_gate,
            input_fingerprint=state.get("input_fingerprint"),
            model_contract_fingerprint=(
                build_model_contract_fingerprint(state.get("input", {}))
                if isinstance(state.get("input"), dict)
                else None
            ),
        )
        and (
            preflight_protocol.get("status") != "ok"
            or preflight_protocol.get("detail", {}).get("evidence_file_sha256")
            != research_protocol_gate.get("evidence_file_sha256")
        )
    ):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "RESEARCH_PROTOCOL_PREFLIGHT_INCONSISTENT",
                "message": "research-protocol preflight and persisted business control disagree",
            }
        )
    if (
        not state.get("mock")
        and is_release_eligible_execution_cost(execution_cost_gate)
        and (
            preflight_cost.get("status") != "ok"
            or preflight_cost.get("detail", {}).get("cost_model_fingerprint")
            != execution_cost_gate.get("cost_model_fingerprint")
        )
    ):
        alerts.append(
            {
                "severity": "CRITICAL",
                "code": "EXECUTION_COST_PREFLIGHT_INCONSISTENT",
                "message": "execution-cost preflight and persisted business control disagree",
            }
        )
    source_provenance = state.get("source_provenance", {})
    if source_provenance.get("release_ready") is not True:
        alerts.append(
            {
                "severity": "WARNING" if state.get("mock") else "CRITICAL",
                "code": "SOURCE_PROVENANCE_NOT_RELEASEABLE",
                "message": source_provenance.get(
                    "reason", "source provenance is missing"
                ),
            }
        )
    write_json_atomic(os.path.join(operations_dir, "metrics.json"), metrics)
    write_json_atomic(
        os.path.join(operations_dir, "alerts.json"),
        {
            "schema_version": 1,
            "generated_at": _utc_now(),
            "run_id": state.get("run_id"),
            "alert_count": len(alerts),
            "alerts": alerts,
        },
    )


def latest_run_status(
    runs_root: str,
    include_mock: bool = False,
    max_age_hours: float = 36.0,
    campaign_dir: str | None = None,
    expected_campaign_sha256: str | None = None,
    experiment_registry_dir: str | None = None,
) -> dict[str, Any]:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    all_states = list(_iter_run_states(runs_root))
    states = all_states if include_mock else [row for row in all_states if not row[1].get("mock")]
    if not states:
        return {
            "schema_version": 1,
            "generated_at": _utc_now(),
            "ok": False,
            "severity": "CRITICAL",
            "scope": "all_runs" if include_mock else "production_real_only",
            "error": "no matching run state found",
            "run_count": len(all_states),
            "ignored_mock_count": sum(1 for _, state in all_states if state.get("mock")),
        }

    def sort_key(item: tuple[str, dict[str, Any]]) -> tuple[datetime, str]:
        parsed = _parse_timestamp(
            item[1].get("finished_at")
            or item[1].get("updated_at")
            or item[1].get("started_at")
        )
        return parsed or datetime.min.replace(tzinfo=timezone.utc), str(item[1].get("run_id", ""))

    path, state = max(states, key=sort_key)
    blockers: list[str] = []
    checks: dict[str, Any] = {}

    def require(name: str, passed: bool, failure: str) -> None:
        checks[name] = bool(passed)
        if not passed:
            blockers.append(failure)

    is_mock = bool(state.get("mock"))
    require("run_schema", state.get("schema_version") == 7, "run schema is not 7")
    require("real_run", not is_mock, "mock run is not production evidence")
    require(
        "pipeline_completed",
        state.get("status") == "completed" and int(state.get("error_count", 0)) == 0,
        "pipeline is not a clean completed run",
    )
    require(
        "seven_agents",
        int(state.get("success_count", 0)) == 7,
        "all seven business agents did not succeed",
    )
    require("runtime_pi", state.get("runtime") == "pi", "runtime is not pi")
    require(
        "budget",
        state.get("budget_gate", {}).get("status") == "passed",
        "budget gate did not pass",
    )
    require(
        "model_pricing",
        is_current_model_pricing(state),
        "DeepSeek pricing snapshot is stale or inconsistent",
    )
    require(
        "real_data",
        state.get("data_mode") == "REAL_TUSHARE"
        and state.get("metrics_source") == "REAL_TUSHARE",
        "data or deterministic metrics are not REAL_TUSHARE",
    )
    assurance = state.get("backtest_assurance", {})
    require(
        "backtest_assurance",
        assurance.get("decision") == "PASSED_FOR_INTERNAL_RESEARCH"
        and assurance.get("release_gate_passed") is True,
        "deterministic backtest assurance did not pass",
    )
    robustness = state.get("robustness_validation", {})
    require(
        "robustness_validation",
        robustness.get("decision") == "PASSED"
        and not robustness.get("failed_checks"),
        "holdout, walk-forward, or stress validation did not pass",
    )
    require(
        "source_baseline",
        state.get("source_provenance", {}).get("release_ready") is True,
        "source revision is not a clean committed baseline",
    )
    controls = state.get("business_controls", {})
    license_gate = controls.get("data_license_gate", {})
    require(
        "data_license",
        is_release_eligible_data_license(license_gate),
        "data-license gate is not approved for organizational processing and retention",
    )
    execution_cost_gate = controls.get("execution_cost_gate", {})
    require(
        "execution_cost_calibration",
        is_release_eligible_execution_cost(execution_cost_gate),
        "execution-cost calibration is not approved for internal research",
    )
    research_protocol_gate = controls.get("research_protocol_gate", {})
    require(
        "research_protocol",
        is_release_eligible_research_protocol(
            research_protocol_gate,
            input_fingerprint=state.get("input_fingerprint"),
            model_contract_fingerprint=(
                build_model_contract_fingerprint(state.get("input", {}))
                if isinstance(state.get("input"), dict)
                else None
            ),
        ),
        "research protocol is not externally registered or contract-bound",
    )
    experiment_registry_verification = verify_experiment_registry_gate(
        state, registry_dir=experiment_registry_dir
    )
    require(
        "experiment_registry",
        experiment_registry_verification.get("eligible") is True,
        "external experiment registry verification did not pass",
    )
    require(
        "broker_disabled",
        controls.get("broker_connection_enabled") is False,
        "broker connection boundary is invalid",
    )
    require(
        "external_distribution_disabled",
        controls.get("external_distribution_approved") is False,
        "external distribution boundary is invalid",
    )
    preflight_checks = {
        str(row.get("name")): row
        for row in state.get("preflight", {}).get("checks", [])
        if isinstance(row, dict)
    }
    pi_ping = preflight_checks.get("pi_llm_ping", {})
    market_rules = preflight_checks.get("a_share_market_rules", {})
    execution_cost_preflight = preflight_checks.get(
        "execution_cost_calibration", {}
    )
    research_protocol_preflight = preflight_checks.get(
        "research_protocol_registration", {}
    )
    market_rule_detail = market_rules.get("detail", {})
    require(
        "a_share_market_rules",
        market_rules.get("status") == "ok"
        and len(str(market_rule_detail.get("rulebook_sha256", ""))) == 64
        and bool(market_rule_detail.get("policy_ids")),
        "effective-dated A-share market-rule evidence is missing",
    )
    require(
        "execution_cost_preflight",
        execution_cost_preflight.get("status") == "ok"
        and execution_cost_preflight.get("detail", {}).get(
            "cost_model_fingerprint"
        )
        == execution_cost_gate.get("cost_model_fingerprint"),
        "execution-cost preflight evidence is missing or inconsistent",
    )
    require(
        "research_protocol_preflight",
        research_protocol_preflight.get("status") == "ok"
        and research_protocol_preflight.get("detail", {}).get(
            "evidence_file_sha256"
        )
        == research_protocol_gate.get("evidence_file_sha256")
        and research_protocol_preflight.get("detail", {}).get(
            "model_contract_sha256"
        )
        == research_protocol_gate.get("model_contract_sha256"),
        "research-protocol preflight evidence is missing or inconsistent",
    )
    require(
        "pi_live_ping",
        pi_ping.get("status") == "ok"
        and pi_ping.get("provider") == "deepseek"
        and pi_ping.get("model") == Config.DEEPSEEK_MODEL,
        "approved Pi DeepSeek live ping evidence is missing",
    )

    finished_at = _parse_timestamp(
        state.get("finished_at") or state.get("updated_at") or state.get("started_at")
    )
    age_hours = None
    if finished_at:
        age_hours = max(
            0.0,
            (datetime.now(timezone.utc) - finished_at).total_seconds() / 3600,
        )
    require(
        "fresh_run",
        age_hours is not None and age_hours <= max_age_hours,
        f"latest run is missing a valid timestamp or older than {max_age_hours:g} hours",
    )

    alerts_document = _read_json(os.path.join(path, "operations", "alerts.json"))
    alerts = alerts_document.get("alerts", []) if isinstance(alerts_document, dict) else []
    critical_alerts = [
        row
        for row in alerts
        if isinstance(row, dict) and str(row.get("severity", "")).upper() == "CRITICAL"
    ]
    require(
        "structured_alerts",
        bool(alerts_document) and not critical_alerts,
        "structured monitoring has missing or CRITICAL alerts",
    )
    try:
        from .release import verify_run_integrity

        integrity = verify_run_integrity(path)
    except (OSError, RuntimeError, ValueError) as exc:
        integrity = {"ok": False, "errors": [str(exc)]}
    require(
        "artifact_integrity",
        integrity.get("ok") is True,
        "run artifact integrity verification failed",
    )

    release_decision = _read_json(os.path.join(path, "release", "release_decision.json"))
    forward_campaign = None
    if campaign_dir:
        try:
            from .forward_observation import campaign_status

            forward_campaign = campaign_status(
                campaign_dir,
                expected_campaign_sha256=expected_campaign_sha256,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            require(
                "forward_campaign_integrity",
                False,
                f"forward campaign verification failed: {exc}",
            )
            forward_campaign = {"error": str(exc)}
        else:
            latest_observation = forward_campaign.get("latest_observation") or {}
            campaign_status_value = forward_campaign.get("status")
            require(
                "forward_campaign_integrity",
                forward_campaign.get("ledger_integrity_ok") is True,
                "forward campaign ledger integrity failed",
            )
            require(
                "forward_campaign_current_run",
                latest_observation.get("run_id") == state.get("run_id"),
                "latest real run is not recorded in the forward campaign ledger",
            )
            require(
                "forward_campaign_protocol",
                forward_campaign.get("protocol_id")
                == research_protocol_gate.get("protocol_id")
                and forward_campaign.get("protocol_version")
                == research_protocol_gate.get("protocol_version"),
                "forward campaign protocol differs from the latest run",
            )
            require(
                "forward_campaign_operating_state",
                campaign_status_value
                in {
                    "OBSERVING_MINIMUM_NOT_MET",
                    "CONTINUE_OBSERVATION",
                    "ELIGIBLE_FOR_INDEPENDENT_VALIDATION",
                },
                f"forward campaign requires intervention: {campaign_status_value}",
            )
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "ok": not blockers,
        "severity": "OK" if not blockers else ("INFO" if is_mock else "CRITICAL"),
        "scope": "all_runs" if include_mock else "production_real_only",
        "run_dir": path,
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "runtime": state.get("runtime"),
        "mock": is_mock,
        "finished_at": state.get("finished_at"),
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "max_age_hours": max_age_hours,
        "success_count": state.get("success_count", 0),
        "error_count": state.get("error_count", 0),
        "budget_status": state.get("budget_gate", {}).get("status", "unknown"),
        "model_pricing_current": is_current_model_pricing(state),
        "budget_cost_usd": state.get("budget_gate", {})
        .get("observed", {})
        .get("budget_cost_usd"),
        "data_mode": state.get("data_mode"),
        "metrics_source": state.get("metrics_source"),
        "backtest_assurance_decision": assurance.get("decision"),
        "robustness_validation_decision": robustness.get("decision"),
        "market_rulebook_sha256": market_rule_detail.get("rulebook_sha256"),
        "data_license_status": controls.get("data_license_gate", {}).get("status"),
        "research_protocol_status": research_protocol_gate.get("status"),
        "research_protocol_id": research_protocol_gate.get("protocol_id"),
        "research_protocol_version": research_protocol_gate.get(
            "protocol_version"
        ),
        "research_protocol_binding_mode": research_protocol_gate.get(
            "binding_mode"
        ),
        "experiment_registry_status": controls.get(
            "experiment_registry_gate", {}
        ).get("status"),
        "experiment_registry_id": controls.get(
            "experiment_registry_gate", {}
        ).get("registry_id"),
        "experiment_registry_verification": experiment_registry_verification,
        "execution_cost_status": execution_cost_gate.get("status"),
        "execution_cost_model_fingerprint": execution_cost_gate.get(
            "cost_model_fingerprint"
        ),
        "integrity": integrity,
        "critical_alert_count": len(critical_alerts),
        "release_status": release_decision.get("status", "NOT_VERIFIED"),
        "forward_campaign": forward_campaign,
        "checks": checks,
        "blockers": blockers,
        "run_count": len(all_states),
        "ignored_mock_count": sum(1 for _, row in all_states if row.get("mock")),
        "broker_connection_enabled": controls.get("broker_connection_enabled"),
        "external_distribution_approved": controls.get("external_distribution_approved"),
    }


def recover_incomplete_runs(
    runs_root: str,
    stale_seconds: int,
) -> list[tuple[str, dict[str, Any]]]:
    recovered = []
    now = datetime.now(timezone.utc)
    lock = _read_json(
        os.path.join(os.path.abspath(runs_root), ".operations", "pipeline.lock.json")
    )
    active_output = os.path.abspath(str(lock.get("output_dir", ""))) if lock else ""
    active_pid = int(lock.get("pid") or 0) if lock else 0
    active_host = lock.get("hostname") if lock else None
    for path, state in _iter_run_states(runs_root):
        if state.get("status") != "running":
            continue
        updated = _parse_timestamp(
            state.get("updated_at") or state.get("started_at")
        )
        if updated and (now - updated).total_seconds() < stale_seconds:
            continue
        if (
            active_output == os.path.abspath(path)
            and active_host == socket.gethostname()
            and _is_process_alive(active_pid)
        ):
            continue
        state["status"] = "interrupted"
        state["finished_at"] = _utc_now()
        state["updated_at"] = state["finished_at"]
        state.setdefault("errors", []).append(
            "operations: stale running state recovered as interrupted; a new run is required"
        )
        state["error_count"] = max(
            int(state.get("error_count", 0)),
            max(1, int(state.get("total_agents", 7)) - int(state.get("success_count", 0))),
        )
        state["recovery"] = {
            "recovered_at": state["finished_at"],
            "policy": "mark_interrupted_no_in_place_resume",
            "reason": "stale state without a live owning process",
        }
        write_json_atomic(os.path.join(path, "state.json"), state)
        append_event(path, "pipeline_recovered_as_interrupted", state["recovery"])
        recovered.append((path, state))
    return recovered


def _iter_run_states(runs_root: str):
    if not os.path.isdir(runs_root):
        return
    for entry in os.scandir(runs_root):
        if not entry.is_dir() or entry.name.startswith("weekly_") or entry.name.startswith("."):
            continue
        state_path = os.path.join(entry.path, "state.json")
        if not os.path.isfile(state_path):
            continue
        state = _read_json(state_path)
        if state:
            yield entry.path, state


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _format_lock_error(existing: dict[str, Any]) -> str:
    if not existing:
        return "another pipeline run holds an unreadable active lock"
    return (
        "another pipeline run is active: "
        f"run_id={existing.get('run_id')}, pid={existing.get('pid')}, "
        f"host={existing.get('hostname')}, stage={existing.get('stage')}, "
        f"heartbeat={existing.get('heartbeat_at')}"
    )


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _last_json_line(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    last = ""
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                last = line
    try:
        value = json.loads(last)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _first_numeric(value: dict[str, Any], keys: tuple[str, ...]) -> float:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, (int, float)):
            return float(candidate)
    return 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
