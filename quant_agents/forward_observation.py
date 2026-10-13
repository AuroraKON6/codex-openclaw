from __future__ import annotations

import json
import math
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .audit import canonical_json_sha256, sha256_file, write_json_atomic
from .config import PROJECT_ROOT
from .release import verify_release_approval, verify_run_integrity
from .governance import is_release_eligible_data_license
from .execution_cost_governance import is_release_eligible_execution_cost
from .operations import is_current_model_pricing
from .research_protocol import (
    build_model_contract_fingerprint,
    is_release_eligible_research_protocol,
)
from .experiment_registry import verify_experiment_registry_gate


CAMPAIGN_SCHEMA_VERSION = 1
OBSERVATION_SCHEMA_VERSION = 1
SUPPORTED_CLOSURE_DECISIONS = {"RETIRED", "CLOSED_NO_PROMOTION"}
REQUIRED_CLOSURE_ROLES = {"model_owner", "compliance_owner", "platform_owner"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ForwardObservationError(RuntimeError):
    pass


def initialize_campaign(
    baseline_run_dir: str,
    approval_path: str,
    campaign_root: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = os.path.abspath(campaign_root)
    if _is_within_project(root):
        raise ForwardObservationError(
            "forward-observation campaign storage must be outside the project repository"
        )
    baseline_run_dir = os.path.abspath(baseline_run_dir)
    integrity = verify_run_integrity(baseline_run_dir)
    if not integrity.get("ok"):
        raise ForwardObservationError(
            "baseline run integrity failed: "
            + "; ".join(integrity.get("errors", []))
        )
    decision = verify_release_approval(baseline_run_dir, approval_path)
    if decision.get("status") != "APPROVED_FOR_INTERNAL_REVIEW":
        raise ForwardObservationError(
            "baseline run must have current five-role approval for internal review"
        )
    state = _load_json(os.path.join(baseline_run_dir, "state.json"), "baseline state")
    input_data = _load_json(os.path.join(baseline_run_dir, "input.json"), "baseline input")
    protocol_gate = state.get("business_controls", {}).get(
        "research_protocol_gate", {}
    )
    if not is_release_eligible_research_protocol(
        protocol_gate,
        input_fingerprint=state.get("input_fingerprint"),
        model_contract_fingerprint=build_model_contract_fingerprint(input_data),
    ):
        raise ForwardObservationError(
            "baseline research protocol is not currently release eligible"
        )
    if (
        protocol_gate.get("run_class") != "development_backtest"
        or protocol_gate.get("binding_mode") != "exact_registered_input"
    ):
        raise ForwardObservationError(
            "campaign baseline must be the exact externally registered development run"
        )
    source = state.get("source_provenance", {})
    if source.get("release_ready") is not True or not re.fullmatch(
        r"[0-9a-fA-F]{40,64}", str(source.get("head_commit", ""))
    ):
        raise ForwardObservationError(
            "campaign baseline requires a clean committed source revision"
        )
    controls = state.get("business_controls", {})
    if (
        controls.get("broker_connection_enabled") is not False
        or controls.get("external_distribution_approved") is not False
    ):
        raise ForwardObservationError(
            "campaign baseline violates broker or external-distribution boundaries"
        )
    forward_controls = protocol_gate.get("forward_observation_controls", {})
    identity = {
        "baseline_run_id": state.get("run_id"),
        "baseline_manifest_snapshot_id": integrity.get("manifest_snapshot_id"),
        "protocol_id": protocol_gate.get("protocol_id"),
        "protocol_version": protocol_gate.get("protocol_version"),
        "model_contract_sha256": protocol_gate.get("model_contract_sha256"),
        "baseline_cutoff": forward_controls.get("baseline_cutoff"),
    }
    campaign_id = canonical_json_sha256(identity)
    safe_protocol = re.sub(
        r"[^A-Za-z0-9._-]+", "-", str(protocol_gate.get("protocol_id", "protocol"))
    ).strip("-.")[:80]
    campaign_dir = os.path.join(root, f"{safe_protocol}-{campaign_id[:12]}")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    campaign = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "created_at": current.isoformat(),
        "status": "ACTIVE_FORWARD_OBSERVATION",
        **identity,
        "baseline_run_dir": baseline_run_dir,
        "baseline_input_sha256": state.get("input_fingerprint"),
        "source_head_commit": str(source.get("head_commit", "")).lower(),
        "scope": protocol_gate.get("scope"),
        "hypothesis_id": protocol_gate.get("hypothesis_id"),
        "protocol_evidence_sha256": protocol_gate.get("evidence_file_sha256"),
        "data_license_evidence_sha256": controls.get("data_license_gate", {}).get(
            "evidence_file_sha256"
        ),
        "execution_cost_model_fingerprint": controls.get(
            "execution_cost_gate", {}
        ).get("cost_model_fingerprint"),
        "execution_cost_evidence_sha256": controls.get(
            "execution_cost_gate", {}
        ).get("evidence_file_sha256"),
        "market_rulebook_sha256": controls.get("execution_cost_gate", {}).get(
            "market_rulebook_sha256"
        ),
        "pi_runtime": state.get("pi_runtime"),
        "deepseek_pricing_baseline_id": state.get("config", {})
        .get("deepseek_pricing", {})
        .get("baseline_id"),
        "forward_observation_controls": forward_controls,
        "broker_connection_enabled": False,
        "external_distribution_approved": False,
        "live_execution_ready": False,
        "allowed_outcome": "independent_validation_eligibility_only",
        "disclaimer": (
            "Forward internal research observation only; this campaign cannot authorize "
            "orders, broker connectivity, external distribution, or real-capital advice."
        ),
    }
    os.makedirs(root, exist_ok=True)
    os.makedirs(campaign_dir, exist_ok=True)
    campaign_path = os.path.join(campaign_dir, "campaign.json")
    if os.path.exists(campaign_path):
        existing = _load_json(campaign_path, "existing campaign")
        if existing != campaign:
            stable_existing = dict(existing)
            stable_requested = dict(campaign)
            stable_existing.pop("created_at", None)
            stable_requested.pop("created_at", None)
            if stable_existing != stable_requested:
                raise ForwardObservationError(
                    "campaign directory already exists with different metadata"
                )
        campaign = existing
    else:
        write_json_atomic(campaign_path, campaign)
    ledger_path = os.path.join(campaign_dir, "observations.jsonl")
    if not os.path.exists(ledger_path):
        with open(ledger_path, "x", encoding="utf-8"):
            pass
    result = campaign_status(campaign_dir)
    result.update(
        {
            "campaign_dir": campaign_dir,
            "campaign_metadata_sha256": sha256_file(campaign_path),
        }
    )
    return result


def load_campaign_metadata(
    campaign_dir: str,
    expected_campaign_sha256: str | None = None,
) -> dict[str, Any]:
    root = _require_external_directory(campaign_dir, create=False)
    campaign_path = os.path.join(root, "campaign.json")
    if not os.path.isfile(campaign_path):
        raise ForwardObservationError(f"campaign metadata is missing: {campaign_path}")
    actual_sha256 = sha256_file(campaign_path)
    if expected_campaign_sha256 and actual_sha256 != expected_campaign_sha256.lower():
        raise ForwardObservationError("campaign metadata SHA-256 mismatch")
    campaign = _load_json(campaign_path, "campaign metadata")
    if campaign.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise ForwardObservationError(
            f"campaign schema_version must be {CAMPAIGN_SCHEMA_VERSION}"
        )
    expected_id = canonical_json_sha256(
        {
            "baseline_run_id": campaign.get("baseline_run_id"),
            "baseline_manifest_snapshot_id": campaign.get(
                "baseline_manifest_snapshot_id"
            ),
            "protocol_id": campaign.get("protocol_id"),
            "protocol_version": campaign.get("protocol_version"),
            "model_contract_sha256": campaign.get("model_contract_sha256"),
            "baseline_cutoff": campaign.get("baseline_cutoff"),
        }
    )
    if campaign.get("campaign_id") != expected_id:
        raise ForwardObservationError("campaign identity hash is invalid")
    if (
        campaign.get("broker_connection_enabled") is not False
        or campaign.get("external_distribution_approved") is not False
        or campaign.get("live_execution_ready") is not False
    ):
        raise ForwardObservationError("campaign safety boundary is invalid")
    campaign["campaign_dir"] = root
    campaign["campaign_metadata_sha256"] = actual_sha256
    return campaign


def record_observation(
    campaign_dir: str,
    run_dir: str,
    expected_campaign_sha256: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = load_campaign_metadata(campaign_dir, expected_campaign_sha256)
    root = campaign["campaign_dir"]
    if os.path.isfile(os.path.join(root, "closure.json")):
        raise ForwardObservationError("campaign is closed and cannot accept observations")
    run_dir = os.path.abspath(run_dir)
    integrity = verify_run_integrity(run_dir)
    if not integrity.get("ok"):
        raise ForwardObservationError(
            "observation run integrity failed: "
            + "; ".join(integrity.get("errors", []))
        )
    state = _load_json(os.path.join(run_dir, "state.json"), "observation state")
    input_data = _load_json(os.path.join(run_dir, "input.json"), "observation input")
    _validate_observation_run(campaign, state, input_data)
    backtest = _load_json(
        os.path.join(run_dir, "backtest", "backtest_agent.json"),
        "observation backtest",
    )
    observation = _compute_forward_observation(campaign, state, backtest)
    ledger_path = os.path.join(root, "observations.jsonl")
    with _campaign_lock(root):
        ledger = _read_and_verify_ledger(campaign, ledger_path)
        previous = ledger[-1] if ledger else None
        if previous:
            if observation["observed_through"] < previous["observed_through"]:
                raise ForwardObservationError(
                    "observation date predates the latest append-only ledger entry"
                )
            if observation["observed_through"] == previous["observed_through"]:
                if (
                    observation["forward_path_sha256"]
                    == previous.get("forward_path_sha256")
                    and observation["metrics"] == previous.get("metrics")
                ):
                    status = campaign_status(root)
                    status["append_status"] = "no_op_already_recorded"
                    status["run_id"] = state.get("run_id")
                    return status
                raise ForwardObservationError(
                    "same observation date has different metrics or path; data revision review is required"
                )
            previous_date = str(previous.get("observed_through"))
            if observation["path_prefix_by_date"].get(previous_date) != previous.get(
                "forward_path_sha256"
            ):
                raise ForwardObservationError(
                    "previously recorded forward history changed; append refused pending data revision review"
                )
        decision, checks = _evaluate_observation_decision(
            observation["metrics"], campaign["forward_observation_controls"]
        )
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        entry = {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "campaign_id": campaign["campaign_id"],
            "recorded_at": current.isoformat(),
            "run_id": state.get("run_id"),
            "run_dir": run_dir,
            "run_manifest_snapshot_id": integrity.get("manifest_snapshot_id"),
            "input_fingerprint": state.get("input_fingerprint"),
            "source_head_commit": state.get("source_provenance", {}).get(
                "head_commit"
            ),
            "data_snapshot_id": state.get("agent_outputs", {})
            .get("data_agent", {})
            .get("snapshot_id"),
            "protocol_evidence_sha256": state.get("business_controls", {})
            .get("research_protocol_gate", {})
            .get("evidence_file_sha256"),
            "observed_from_exclusive": campaign["baseline_cutoff"],
            "observed_through": observation["observed_through"],
            "forward_path_sha256": observation["forward_path_sha256"],
            "overlap_with_previous_verified": previous is not None,
            "metrics": observation["metrics"],
            "decision": decision,
            "decision_checks": checks,
            "previous_entry_hash": previous.get("entry_hash") if previous else None,
            "broker_connection_enabled": False,
            "live_execution_ready": False,
            "disclaimer": "Research observation only; no real-capital action is authorized.",
        }
        entry["entry_hash"] = canonical_json_sha256(entry)
        with open(ledger_path, "a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            file.flush()
            os.fsync(file.fileno())
        _read_and_verify_ledger(campaign, ledger_path)
    status = campaign_status(root)
    status["append_status"] = "recorded"
    status["run_id"] = state.get("run_id")
    return status


def campaign_status(
    campaign_dir: str,
    expected_campaign_sha256: str | None = None,
) -> dict[str, Any]:
    campaign = load_campaign_metadata(
        campaign_dir, expected_campaign_sha256
    ) if not isinstance(campaign_dir, dict) else campaign_dir
    root = campaign["campaign_dir"]
    ledger = _read_and_verify_ledger(
        campaign, os.path.join(root, "observations.jsonl")
    )
    closure_path = os.path.join(root, "closure.json")
    closure = (
        _verify_closure(
            campaign,
            _load_json(closure_path, "campaign closure"),
        )
        if os.path.isfile(closure_path)
        else None
    )
    latest = ledger[-1] if ledger else None
    status = (
        str(closure.get("decision"))
        if closure
        else (
            str(latest.get("decision"))
            if latest
            else "BLOCKED_NO_FORWARD_OBSERVATIONS"
        )
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": campaign.get("campaign_id"),
        "campaign_dir": root,
        "campaign_metadata_sha256": campaign.get("campaign_metadata_sha256"),
        "protocol_id": campaign.get("protocol_id"),
        "protocol_version": campaign.get("protocol_version"),
        "baseline_run_id": campaign.get("baseline_run_id"),
        "baseline_cutoff": campaign.get("baseline_cutoff"),
        "status": status,
        "ledger_integrity_ok": True,
        "observation_count": len(ledger),
        "latest_observation": latest,
        "closure": closure,
        "closure_file_sha256": sha256_file(closure_path) if closure else None,
        "broker_connection_enabled": False,
        "external_distribution_approved": False,
        "live_execution_ready": False,
        "human_confirmation_needed": [
            "Independent validation must reproduce the frozen protocol and review any threshold breach or historical-data revision.",
            "Eligibility from this ledger is limited to independent internal validation and never authorizes trading or external distribution.",
        ],
    }


def close_campaign(
    campaign_dir: str,
    decision_path: str,
    expected_campaign_sha256: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = load_campaign_metadata(campaign_dir, expected_campaign_sha256)
    path = os.path.abspath(decision_path)
    if not os.path.isfile(path):
        raise ForwardObservationError(f"closure decision does not exist: {path}")
    if _is_within_project(path):
        raise ForwardObservationError(
            "closure decision evidence must be stored outside the project repository"
        )
    decision = _load_json(path, "closure decision")
    errors: list[str] = []
    if decision.get("schema_version") != 1:
        errors.append("closure schema_version must be 1")
    if decision.get("campaign_id") != campaign.get("campaign_id"):
        errors.append("closure campaign_id mismatch")
    outcome = str(decision.get("decision", "")).upper()
    if outcome not in SUPPORTED_CLOSURE_DECISIONS:
        errors.append("closure decision must be RETIRED or CLOSED_NO_PROMOTION")
    if decision.get("live_execution_authorized") is not False:
        errors.append("closure live_execution_authorized must be false")
    for field in ("reason", "evidence_reference"):
        if not str(decision.get(field, "")).strip():
            errors.append(f"closure {field} is required")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    effective_at = _parse_timestamp(decision.get("effective_at"), "effective_at", errors)
    if effective_at and effective_at > current:
        errors.append("closure effective_at must not be in the future")
    approvals = decision.get("approvals")
    if not isinstance(approvals, list):
        approvals = []
        errors.append("closure approvals must be a list")
    by_role = {
        str(row.get("role")): row
        for row in approvals
        if isinstance(row, dict) and row.get("role")
    }
    missing = sorted(REQUIRED_CLOSURE_ROLES.difference(by_role))
    if missing:
        errors.append("missing closure approval roles: " + ", ".join(missing))
    approvers = []
    for role in REQUIRED_CLOSURE_ROLES:
        row = by_role.get(role, {})
        if str(row.get("decision", "")).upper() != "APPROVED":
            errors.append(f"closure {role} decision must be APPROVED")
        approver = str(row.get("approver", "")).strip()
        if not approver:
            errors.append(f"closure {role} approver is required")
        else:
            approvers.append(approver.casefold())
        if not str(row.get("evidence_reference", "")).strip():
            errors.append(f"closure {role} evidence_reference is required")
    if len(set(approvers)) != len(approvers):
        errors.append("closure approval roles require three distinct people")
    supporting_path = str(decision.get("supporting_document_path", "")).strip()
    if supporting_path and not os.path.isabs(supporting_path):
        supporting_path = os.path.abspath(os.path.join(os.path.dirname(path), supporting_path))
    if not supporting_path or not os.path.isfile(supporting_path):
        errors.append("closure supporting document is missing")
    elif _is_within_project(supporting_path):
        errors.append("closure supporting document must be outside the repository")
    supporting_sha256 = str(decision.get("supporting_document_sha256", "")).lower()
    if not _SHA256.fullmatch(supporting_sha256):
        errors.append("closure supporting_document_sha256 is invalid")
    elif supporting_path and os.path.isfile(supporting_path) and sha256_file(supporting_path) != supporting_sha256:
        errors.append("closure supporting document SHA-256 mismatch")
    if errors:
        raise ForwardObservationError("campaign closure failed: " + "; ".join(errors))
    closure = {
        "schema_version": 1,
        "campaign_id": campaign["campaign_id"],
        "decision": outcome,
        "effective_at": effective_at.isoformat() if effective_at else None,
        "recorded_at": current.isoformat(),
        "reason": str(decision["reason"]).strip(),
        "evidence_reference": str(decision["evidence_reference"]).strip(),
        "approval_roles": sorted(REQUIRED_CLOSURE_ROLES),
        "supporting_document_sha256": supporting_sha256,
        "decision_evidence_sha256": sha256_file(path),
        "identity_assurance": "document_hash_only_not_approver_identity_authenticated",
        "live_execution_authorized": False,
    }
    closure["closure_hash"] = canonical_json_sha256(closure)
    closure_path = os.path.join(campaign["campaign_dir"], "closure.json")
    if os.path.exists(closure_path):
        existing = _load_json(closure_path, "existing campaign closure")
        stable_existing = dict(existing)
        stable_closure = dict(closure)
        stable_existing.pop("recorded_at", None)
        stable_closure.pop("recorded_at", None)
        stable_existing.pop("closure_hash", None)
        stable_closure.pop("closure_hash", None)
        if stable_existing != stable_closure:
            raise ForwardObservationError("campaign already has a different closure")
    else:
        write_json_atomic(closure_path, closure)
    return campaign_status(campaign["campaign_dir"])


def _verify_closure(
    campaign: dict[str, Any], closure: dict[str, Any]
) -> dict[str, Any]:
    claimed_hash = closure.pop("closure_hash", None)
    calculated_hash = canonical_json_sha256(closure)
    closure["closure_hash"] = claimed_hash
    if claimed_hash != calculated_hash:
        raise ForwardObservationError("campaign closure hash mismatch")
    if closure.get("schema_version") != 1:
        raise ForwardObservationError("campaign closure schema mismatch")
    if closure.get("campaign_id") != campaign.get("campaign_id"):
        raise ForwardObservationError("campaign closure identity mismatch")
    if closure.get("decision") not in SUPPORTED_CLOSURE_DECISIONS:
        raise ForwardObservationError("campaign closure decision is invalid")
    if closure.get("live_execution_authorized") is not False:
        raise ForwardObservationError("campaign closure safety boundary is invalid")
    if not _SHA256.fullmatch(str(closure.get("decision_evidence_sha256", ""))):
        raise ForwardObservationError("campaign closure evidence hash is invalid")
    if not _SHA256.fullmatch(str(closure.get("supporting_document_sha256", ""))):
        raise ForwardObservationError("campaign closure supporting hash is invalid")
    return closure


def _validate_observation_run(
    campaign: dict[str, Any],
    state: dict[str, Any],
    input_data: dict[str, Any],
) -> None:
    errors = []
    if state.get("schema_version") != 7:
        errors.append("run schema is not 7")
    if state.get("status") != "completed" or state.get("error_count") != 0:
        errors.append("run is not cleanly completed")
    if state.get("success_count") != 7:
        errors.append("all seven business agents did not succeed")
    if state.get("mock") or state.get("runtime") != "pi":
        errors.append("forward observation requires a real Pi run")
    if state.get("data_mode") != "REAL_TUSHARE" or state.get("metrics_source") != "REAL_TUSHARE":
        errors.append("forward observation requires deterministic REAL_TUSHARE metrics")
    assurance = state.get("backtest_assurance", {})
    if (
        assurance.get("decision") != "PASSED_FOR_INTERNAL_RESEARCH"
        or assurance.get("release_gate_passed") is not True
    ):
        errors.append("deterministic backtest assurance did not pass")
    robustness = state.get("robustness_validation", {})
    if robustness.get("decision") != "PASSED" or robustness.get("failed_checks"):
        errors.append("holdout, walk-forward, or stress validation did not pass")
    if state.get("budget_gate", {}).get("status") != "passed":
        errors.append("operational budget gate did not pass")
    if verify_experiment_registry_gate(state).get("eligible") is not True:
        errors.append("external experiment registry verification did not pass")
    if not is_current_model_pricing(state):
        errors.append("DeepSeek pricing baseline is stale or inconsistent")
    if state.get("source_provenance", {}).get("head_commit", "").lower() != campaign.get(
        "source_head_commit"
    ):
        errors.append("source commit differs from the frozen campaign baseline")
    schedule_context = input_data.get("schedule_context", {})
    if schedule_context.get("run_class") != "forward_observation_refresh":
        errors.append("run is not a forward_observation_refresh")
    if schedule_context.get("campaign_id") != campaign.get("campaign_id"):
        errors.append("schedule_context campaign_id mismatch")
    if schedule_context.get("model_contract_sha256") != campaign.get(
        "model_contract_sha256"
    ):
        errors.append("schedule_context model contract mismatch")
    if build_model_contract_fingerprint(input_data) != campaign.get(
        "model_contract_sha256"
    ):
        errors.append("run model contract differs from the campaign baseline")
    gate = state.get("business_controls", {}).get("research_protocol_gate", {})
    if not is_release_eligible_research_protocol(
        gate,
        input_fingerprint=state.get("input_fingerprint"),
        model_contract_fingerprint=campaign.get("model_contract_sha256"),
    ):
        errors.append("run research protocol gate is not release eligible")
    if gate.get("protocol_id") != campaign.get("protocol_id") or gate.get(
        "protocol_version"
    ) != campaign.get("protocol_version"):
        errors.append("run protocol identity differs from campaign")
    if gate.get("evidence_file_sha256") != campaign.get("protocol_evidence_sha256"):
        errors.append("run protocol evidence changed after campaign initialization")
    controls = state.get("business_controls", {})
    license_gate = controls.get("data_license_gate", {})
    if not is_release_eligible_data_license(license_gate):
        errors.append("data-license gate is not release eligible")
    if license_gate.get("evidence_file_sha256") != campaign.get(
        "data_license_evidence_sha256"
    ):
        errors.append("data-license evidence changed after campaign initialization")
    execution_cost_gate = controls.get("execution_cost_gate", {})
    if not is_release_eligible_execution_cost(execution_cost_gate):
        errors.append("execution-cost gate is not release eligible")
    if execution_cost_gate.get("cost_model_fingerprint") != campaign.get(
        "execution_cost_model_fingerprint"
    ) or execution_cost_gate.get("evidence_file_sha256") != campaign.get(
        "execution_cost_evidence_sha256"
    ):
        errors.append("execution-cost evidence changed after campaign initialization")
    if execution_cost_gate.get("market_rulebook_sha256") != campaign.get(
        "market_rulebook_sha256"
    ):
        errors.append("market rulebook changed after campaign initialization")
    if state.get("pi_runtime") != campaign.get("pi_runtime"):
        errors.append("Pi runtime or model identity changed after campaign initialization")
    if state.get("config", {}).get("deepseek_pricing", {}).get(
        "baseline_id"
    ) != campaign.get("deepseek_pricing_baseline_id"):
        errors.append("DeepSeek pricing baseline changed after campaign initialization")
    if controls.get("broker_connection_enabled") is not False:
        errors.append("broker connection boundary is invalid")
    if controls.get("external_distribution_approved") is not False:
        errors.append("external distribution boundary is invalid")
    if errors:
        raise ForwardObservationError(
            "observation run failed campaign controls: " + "; ".join(errors)
        )


def _compute_forward_observation(
    campaign: dict[str, Any],
    state: dict[str, Any],
    backtest: dict[str, Any],
) -> dict[str, Any]:
    cutoff = str(campaign.get("baseline_cutoff", ""))
    rows = sorted(
        [row for row in backtest.get("equity_curve", []) if isinstance(row, dict)],
        key=lambda row: str(row.get("trade_date", "")),
    )
    base_rows = [row for row in rows if str(row.get("trade_date", "")) <= cutoff]
    forward_rows = [row for row in rows if str(row.get("trade_date", "")) > cutoff]
    if not base_rows or not forward_rows:
        raise ForwardObservationError(
            "backtest does not contain both a baseline point and post-cutoff observations"
        )
    base = base_rows[-1]
    base_strategy = _positive_number(base.get("strategy_index"), "base strategy index")
    base_benchmark = _positive_number(base.get("benchmark_index"), "base benchmark index")
    seed = canonical_json_sha256(
        {
            "baseline_cutoff": cutoff,
            "base_trade_date": base.get("trade_date"),
            "base_strategy_index": base_strategy,
            "base_benchmark_index": base_benchmark,
        }
    )
    previous_hash = seed
    path_prefix_by_date: dict[str, str] = {}
    normalized_strategy = [1.0]
    cumulative_cost_ratio = 0.0
    for row in forward_rows:
        point = {
            "trade_date": str(row.get("trade_date")),
            "strategy_index": round(
                _positive_number(row.get("strategy_index"), "strategy index")
                / base_strategy,
                10,
            ),
            "benchmark_index": round(
                _positive_number(row.get("benchmark_index"), "benchmark index")
                / base_benchmark,
                10,
            ),
            "invested_ratio": round(_finite_number(row.get("invested_ratio", 0.0)), 8),
            "transaction_cost_ratio": round(
                _finite_number(row.get("transaction_cost_ratio", 0.0)), 12
            ),
        }
        previous_hash = canonical_json_sha256(
            {"previous_path_hash": previous_hash, "point": point}
        )
        path_prefix_by_date[point["trade_date"]] = previous_hash
        normalized_strategy.append(point["strategy_index"])
        cumulative_cost_ratio += point["transaction_cost_ratio"]
    latest = forward_rows[-1]
    strategy_return = _positive_number(latest.get("strategy_index"), "latest strategy index") / base_strategy - 1.0
    benchmark_return = _positive_number(latest.get("benchmark_index"), "latest benchmark index") / base_benchmark - 1.0
    observed_through = str(latest.get("trade_date"))
    resolved_trade_date = str(
        state.get("input", {}).get("schedule_context", {}).get(
            "resolved_trade_date", ""
        )
    )
    if resolved_trade_date and observed_through != resolved_trade_date:
        raise ForwardObservationError(
            "forward path does not end on the scheduled resolved trade date"
        )
    rebalance_count = sum(
        1
        for row in backtest.get("rebalance_log", [])
        if isinstance(row, dict)
        and cutoff < str(row.get("effective_date", "")) <= observed_through
    )
    metrics = {
        "observation_trade_days": len(forward_rows),
        "rebalance_count": rebalance_count,
        "strategy_return": round(strategy_return, 8),
        "benchmark_return": round(benchmark_return, 8),
        "excess_return": round(strategy_return - benchmark_return, 8),
        "maximum_drawdown": round(_maximum_drawdown(normalized_strategy), 8),
        "cumulative_transaction_cost_ratio": round(cumulative_cost_ratio, 10),
    }
    return {
        "observed_through": observed_through,
        "forward_path_sha256": previous_hash,
        "path_prefix_by_date": path_prefix_by_date,
        "metrics": metrics,
    }


def _evaluate_observation_decision(
    metrics: dict[str, Any], controls: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    minimum_days = int(controls.get("minimum_observation_trade_days", 0))
    minimum_rebalances = int(controls.get("minimum_rebalance_count", 0))
    promotion = controls.get("promotion_thresholds", {})
    pause = controls.get("pause_thresholds", {})
    days_met = int(metrics.get("observation_trade_days", 0)) >= minimum_days
    rebalances_met = int(metrics.get("rebalance_count", 0)) >= minimum_rebalances
    pause_drawdown = float(metrics.get("maximum_drawdown", 0.0)) <= float(
        pause.get("drawdown_at_or_below", -1.0)
    )
    pause_excess = days_met and float(metrics.get("excess_return", 0.0)) <= float(
        pause.get("excess_return_at_or_below", -1.0)
    )
    checks = [
        {"name": "minimum_observation_trade_days", "passed": days_met},
        {"name": "minimum_rebalance_count", "passed": rebalances_met},
        {"name": "pause_drawdown_not_breached", "passed": not pause_drawdown},
        {"name": "pause_excess_return_not_breached", "passed": not pause_excess},
    ]
    if pause_drawdown or pause_excess:
        return "PAUSE_REVIEW_REQUIRED", checks
    if not (days_met and rebalances_met):
        return "OBSERVING_MINIMUM_NOT_MET", checks
    promotion_checks = [
        {
            "name": "minimum_forward_excess_return",
            "passed": float(metrics.get("excess_return", 0.0))
            >= float(promotion.get("minimum_excess_return", 0.0)),
        },
        {
            "name": "maximum_forward_drawdown",
            "passed": float(metrics.get("maximum_drawdown", -1.0))
            >= float(promotion.get("maximum_drawdown", 0.0)),
        },
        {
            "name": "maximum_cumulative_cost_ratio",
            "passed": float(metrics.get("cumulative_transaction_cost_ratio", 1.0))
            <= float(promotion.get("maximum_cumulative_cost_ratio", 0.0)),
        },
    ]
    checks.extend(promotion_checks)
    if all(row["passed"] for row in promotion_checks):
        return "ELIGIBLE_FOR_INDEPENDENT_VALIDATION", checks
    return "CONTINUE_OBSERVATION", checks


def _read_and_verify_ledger(
    campaign: dict[str, Any], ledger_path: str
) -> list[dict[str, Any]]:
    if not os.path.isfile(ledger_path):
        raise ForwardObservationError(f"observation ledger is missing: {ledger_path}")
    entries = []
    previous_hash = None
    previous_date = None
    run_ids = set()
    with open(ledger_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ForwardObservationError(
                    f"observation ledger line {line_number} is invalid JSON"
                ) from exc
            claimed_hash = entry.pop("entry_hash", None)
            calculated_hash = canonical_json_sha256(entry)
            entry["entry_hash"] = claimed_hash
            if claimed_hash != calculated_hash:
                raise ForwardObservationError(
                    f"observation ledger line {line_number} hash mismatch"
                )
            if entry.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
                raise ForwardObservationError(
                    f"observation ledger line {line_number} schema mismatch"
                )
            if entry.get("campaign_id") != campaign.get("campaign_id"):
                raise ForwardObservationError(
                    f"observation ledger line {line_number} campaign mismatch"
                )
            if entry.get("previous_entry_hash") != previous_hash:
                raise ForwardObservationError(
                    f"observation ledger line {line_number} chain mismatch"
                )
            observed_through = str(entry.get("observed_through", ""))
            if previous_date and observed_through <= previous_date:
                raise ForwardObservationError(
                    "observation ledger dates must increase strictly"
                )
            run_id = str(entry.get("run_id", ""))
            if not run_id or run_id in run_ids:
                raise ForwardObservationError("observation ledger run IDs must be unique")
            if entry.get("broker_connection_enabled") is not False or entry.get(
                "live_execution_ready"
            ) is not False:
                raise ForwardObservationError("observation ledger safety boundary is invalid")
            previous_hash = claimed_hash
            previous_date = observed_through
            run_ids.add(run_id)
            entries.append(entry)
    return entries


@contextmanager
def _campaign_lock(campaign_dir: str) -> Iterator[None]:
    lock_path = os.path.join(campaign_dir, ".append.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ForwardObservationError(
            f"campaign append lock already exists: {lock_path}; inspect before removal"
        ) from exc
    try:
        payload = json.dumps(
            {
                "pid": os.getpid(),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            }
        ).encode("utf-8")
        os.write(descriptor, payload)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.isfile(lock_path):
            os.unlink(lock_path)


def _maximum_drawdown(indices: list[float]) -> float:
    peak = indices[0]
    result = 0.0
    for value in indices:
        peak = max(peak, value)
        result = min(result, value / peak - 1.0)
    return result


def _positive_number(value: Any, field: str) -> float:
    number = _finite_number(value)
    if number <= 0:
        raise ForwardObservationError(f"{field} must be positive")
    return number


def _finite_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ForwardObservationError("forward path contains a non-numeric value") from exc
    if not math.isfinite(number):
        raise ForwardObservationError("forward path contains a non-finite value")
    return number


def _parse_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError:
        errors.append(f"{field} must be timezone-aware ISO-8601")
        return None


def _load_json(path: str, label: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ForwardObservationError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ForwardObservationError(f"{label} must be a JSON object")
    return value


def _require_external_directory(path: str, create: bool) -> str:
    root = os.path.abspath(path)
    if _is_within_project(root):
        raise ForwardObservationError(
            "forward-observation campaign storage must be outside the project repository"
        )
    if create:
        os.makedirs(root, exist_ok=True)
    if not os.path.isdir(root):
        raise ForwardObservationError(f"campaign directory does not exist: {root}")
    return root


def _is_within_project(path: str) -> bool:
    project_root = os.path.abspath(str(PROJECT_ROOT))
    try:
        lexical_match = os.path.normcase(
            os.path.commonpath([project_root, os.path.abspath(path)])
        ) == os.path.normcase(project_root)
        resolved_root = os.path.realpath(project_root)
        resolved_match = os.path.normcase(
            os.path.commonpath([resolved_root, os.path.realpath(path)])
        ) == os.path.normcase(resolved_root)
        return lexical_match or resolved_match
    except ValueError:
        return False
