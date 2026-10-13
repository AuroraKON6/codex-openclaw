from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from .config import Config
from .audit import collect_source_provenance, write_json_atomic
from .governance import evaluate_data_license
from .execution_cost_governance import evaluate_execution_cost_evidence
from .research_protocol import evaluate_research_protocol
from .experiment_registry import (
    evaluate_experiment_registry,
    initialize_experiment_registry,
    registry_status,
)
from .operations import latest_run_status, recover_incomplete_runs
from .orchestrator import finalize_recovered_run, run_pipeline
from .release import (
    archive_run,
    build_retention_plan,
    prepare_release_candidate,
    verify_archive,
    verify_release_approval,
    write_integrity_report,
)
from .scheduling import build_scheduled_input
from .secret_scan import build_secret_scan_receipt, evaluate_secret_scan_receipt
from .source_baseline import build_source_candidate_manifest
from .source_review import (
    build_source_review_decision_template,
    build_source_review_packet,
    evaluate_source_review_decision,
    verify_source_review_packet,
)
from .readiness import build_project_readiness
from .python_runtime import inspect_python_runtime
from .skill_governance import audit_project_skills
from .extension_governance import audit_project_extensions
from .weekly import generate_weekly_report
from .forward_observation import (
    campaign_status,
    close_campaign,
    initialize_campaign,
    record_observation,
)


def cmd_health(args):
    print("=== Quant Agents Health Check ===\n")
    print(f"Pi package: {Config.PI_PACKAGE_NAME}@{Config.PI_VERSION}")
    print(f"Pi CLI: {Config.PI_CLI_PATH}")
    print(f"Model: {Config.DEEPSEEK_MODEL}")
    print(f"API Key set: {bool(Config.DEEPSEEK_API_KEY)}")
    print(f"Tushare Token set: {bool(Config.TUSHARE_TOKEN)}")
    print(f"Data license evidence path set: {bool(Config.DATA_LICENSE_EVIDENCE_PATH)}")
    print(
        "Research protocol evidence path set: "
        f"{bool(Config.RESEARCH_PROTOCOL_EVIDENCE_PATH)}"
    )
    print(
        "Execution cost evidence path set: "
        f"{bool(Config.EXECUTION_COST_EVIDENCE_PATH)}"
    )
    print(f"Experiment registry path set: {bool(Config.EXPERIMENT_REGISTRY_PATH)}")
    print()

    def failed(errors):
        print("\nHealth check FAILED:")
        for error in dict.fromkeys(errors):
            print(f"  - {error}")
        return 1

    python_runtime = inspect_python_runtime()
    print("--- Python Runtime Contract ---")
    print(f"Target: {python_runtime['target']}")
    print(f"Executable: {python_runtime['executable']}")
    print(f"Python: {python_runtime['implementation']} {python_runtime['python_version']}")
    print(f"Requirements lock: {python_runtime.get('requirements_lock_sha256') or 'MISSING'}")
    print(f"Locked packages: {python_runtime['locked_package_count']}")
    if not python_runtime.get("ok"):
        return failed(
            [
                f"Python runtime contract failed: {error}"
                for error in python_runtime.get("errors", ["unknown runtime error"])
            ]
        )
    print("Python runtime contract passed.\n")

    if args.mock:
        errors = Config.validate(require_deepseek=False, require_tushare=False)
        if errors:
            return failed(errors)
        print("Mock configuration check passed; no external services were called.")
        return 0

    if not args.runtime_only:
        source = collect_source_provenance()
        print(
            "Source revision gate: "
            f"{'passed' if source['release_ready'] else 'FAILED'} "
            f"({source.get('head_commit') or source['reason']})"
        )
        if not source["release_ready"]:
            return failed([f"Source revision gate failed: {source['reason']}"])
        print()

        scan = evaluate_secret_scan_receipt()
        print(
            "Secret scan gate: "
            f"{'passed' if scan['ok'] else 'FAILED'} "
            f"({scan.get('receipt_summary', {}).get('scanned_at', 'no receipt')})"
        )
        if not scan["ok"]:
            return failed(
                [f"Secret scan gate failed: {error}" for error in scan["errors"]]
            )
        print()

        source_review = evaluate_source_review_decision()
        print(
            "Source review decision gate: "
            f"{'passed' if source_review.get('review_claim_valid') else 'FAILED'} "
            f"({source_review.get('status', 'no decision')})"
        )
        if not source_review.get("review_claim_valid"):
            return failed(
                [
                    "Source review decision gate failed: " + error
                    for error in source_review.get(
                        "errors", ["external dual-review evidence is unavailable"]
                    )
                ]
            )
        print()

        try:
            with open(args.input, "r", encoding="utf-8") as file:
                health_input = json.load(file)
            license_result = evaluate_data_license(health_input)
            print(f"Data license gate: {license_result['status']}")
        except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
            print(f"Data license gate: FAILED ({exc})")
            return failed([f"Data license gate failed: {exc}"])
        print()

        try:
            protocol_result = evaluate_research_protocol(health_input)
            print(
                "Research protocol gate: "
                f"{protocol_result['status']} "
                f"({protocol_result['protocol_id']} v{protocol_result['protocol_version']})"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Research protocol gate: FAILED ({exc})")
            return failed([f"Research protocol gate failed: {exc}"])
        print()

        try:
            registry_result = evaluate_experiment_registry(
                health_input, protocol_result
            )
            print(
                "Experiment registry gate: "
                f"{registry_result['status']} ({registry_result['registry_id']})"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Experiment registry gate: FAILED ({exc})")
            return failed([f"Experiment registry gate failed: {exc}"])
        print()

        try:
            cost_result = evaluate_execution_cost_evidence(health_input)
            print(
                "Execution cost calibration gate: "
                f"{cost_result['status']} ({cost_result['cost_model_id']})"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Execution cost calibration gate: FAILED ({exc})")
            return failed([f"Execution cost calibration gate failed: {exc}"])
        print()

    errors = Config.validate(
        require_deepseek=True,
        require_tushare=not args.no_tushare and not args.runtime_only,
    )
    if errors:
        return failed(errors)

    if not args.no_tushare and not args.runtime_only and not args.mock:
        from .data_client import DataClient

        health = DataClient().health()
        print(f"Tushare API reachable: {health.get('ok', False)}")
        if not health.get("ok"):
            print(f"  Error: {health.get('error', 'unknown')}")
            return failed(["Tushare API is not reachable"])
        print()

    print("--- Pi Runtime Check ---")
    from .pi_client import PiClient

    client = PiClient()
    runtime = client.inspect_runtime(list_models=True)
    print(f"Installed version: {runtime.get('pi_version') or 'MISSING'}")
    print(f"Node version: {runtime.get('node_version') or 'MISSING'}")
    print(f"Model available: {runtime.get('model_available', False)}")
    print(f"All tools disabled: {runtime.get('policy', {}).get('all_tools_disabled', False)}")
    if not runtime.get("ok"):
        return failed(runtime.get("errors", ["Pi runtime check failed"]))
    if args.no_ping:
        print("Real Pi / DeepSeek ping: skipped explicitly")
    else:
        ping = client.ping()
        print(f"Real Pi / DeepSeek ping: {ping.get('ok', False)}")
        if not ping.get("ok"):
            return failed(
                ["Pi DeepSeek ping failed: " + str(ping.get("error", "unknown"))]
            )
        print(f"  Provider / model: {ping.get('provider')} / {ping.get('model')}")
        print(f"  Session: {ping.get('session_id')}")
        print(f"  Tokens: {ping.get('usage', {}).get('totalTokens', 0)}")
    print()

    print("All checks passed.")
    if args.no_tushare and not args.runtime_only:
        print("Tushare check was explicitly skipped; real pipeline runs will still require TUSHARE_TOKEN.")
    return 0


def cmd_run(args):
    with open(args.input, "r", encoding="utf-8") as f:
        input_data = json.load(f)

    runtime = args.runtime
    mock = args.mock
    if mock:
        runtime = "mock"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    output_dir = os.path.join("runs", timestamp)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Running pipeline -> {output_dir}")
    print(f"Runtime: {runtime}")
    print(f"Mode: {'MOCK' if mock else 'REAL'}")
    if runtime == "pi":
        print(f"Pi Runtime: {Config.PI_PACKAGE_NAME}@{Config.PI_VERSION}")
    print(f"Model: {Config.DEEPSEEK_MODEL}")
    print()

    try:
        state = run_pipeline(
            input_data,
            output_dir,
            mock=mock,
            runtime=runtime,
            request_id=args.request_id
            or input_data.get("schedule_context", {}).get("request_id"),
            retry_of=args.retry_of,
        )
    except (RuntimeError, ValueError) as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        return 2

    print(f"\nCompleted: {state.get('success_count', 0)}/{state.get('total_agents', 0)} agents")
    print(f"Runtime: {state.get('runtime', 'unknown')}")
    if state.get("errors"):
        print("Errors:")
        for e in state["errors"]:
            try:
                print(f"  - {e}")
            except UnicodeEncodeError:
                print(f"  - [unicode error - see state.json]")

    summary_path = os.path.join(output_dir, "summary.md")
    if os.path.exists(summary_path):
        print(f"\nSummary: {summary_path}")

    return 0 if state.get("error_count", 0) == 0 else 1


def cmd_verify_run(args):
    result = write_integrity_report(args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_release_prepare(args):
    result = prepare_release_candidate(args.run_dir, target=args.target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "BLOCKED" else 3


def cmd_release_verify(args):
    result = verify_release_approval(args.run_dir, args.approval)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "APPROVED_FOR_INTERNAL_REVIEW" else 3


def cmd_archive_run(args):
    result = archive_run(args.run_dir, args.archive_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_verify_archive(args):
    result = verify_archive(
        args.archive,
        expected_sha256=args.expected_sha256,
        expected_run_id=args.expected_run_id,
        expected_manifest_snapshot_id=args.expected_manifest_snapshot_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_retention_plan(args):
    result = build_retention_plan(
        runs_root=args.runs_root,
        archive_root=args.archive_root,
        retention_days=args.retention_days,
    )
    if args.output:
        write_json_atomic(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_make_scheduled_input(args):
    result = build_scheduled_input(
        template_path=args.template,
        output_path=args.output,
        as_of=args.as_of,
        campaign_path=args.campaign,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_forward_init(args):
    try:
        result = initialize_campaign(
            baseline_run_dir=args.baseline_run,
            approval_path=args.approval,
            campaign_root=args.root,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_forward_record(args):
    try:
        result = record_observation(
            campaign_dir=args.campaign,
            run_dir=args.run_dir,
            expected_campaign_sha256=args.expected_campaign_sha256,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_forward_status(args):
    try:
        result = campaign_status(
            campaign_dir=args.campaign,
            expected_campaign_sha256=args.expected_campaign_sha256,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ledger_integrity_ok") else 1


def cmd_forward_close(args):
    try:
        result = close_campaign(
            campaign_dir=args.campaign,
            decision_path=args.decision,
            expected_campaign_sha256=args.expected_campaign_sha256,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_experiment_init(args):
    try:
        result = initialize_experiment_registry(
            evidence_path=args.evidence,
            registry_root=args.root,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_experiment_status(args):
    try:
        result = registry_status(
            registry_dir=args.registry,
            runs_root=args.runs_root,
            stale_hours=args.stale_hours,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_recover(args):
    recovered = recover_incomplete_runs(args.runs_root, args.stale_seconds)
    for run_dir, state in recovered:
        finalize_recovered_run(run_dir, state)
    print(
        json.dumps(
            {
                "recovered_count": len(recovered),
                "runs": [state.get("run_id") for _, state in recovered],
                "policy": "mark_interrupted_no_in_place_resume",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_ops_status(args):
    result = latest_run_status(
        args.runs_root,
        include_mock=args.include_mock,
        max_age_hours=args.max_age_hours,
        campaign_dir=args.campaign,
        expected_campaign_sha256=args.expected_campaign_sha256,
        experiment_registry_dir=args.experiment_registry,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_pi_acceptance(args):
    from .agents import ResearchLeadAgent
    from .pi_client import PiClient

    errors = Config.validate(require_deepseek=True, require_tushare=False)
    if errors:
        print(json.dumps({"status": "failed", "errors": errors}, indent=2))
        return 2
    runtime = PiClient().inspect_runtime(list_models=True)
    if not runtime.get("ok"):
        print(json.dumps({"status": "failed", "runtime": runtime}, indent=2))
        return 2

    output_dir = args.output or os.path.join(
        "drill_reports",
        "pi_runtime_acceptance_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3],
    )
    os.makedirs(output_dir, exist_ok=True)
    acceptance_input = {
        "theme": "Pi runtime contract validation only; do not make current market claims",
        "scope": "CSI500",
        "acceptance_scope": "runtime_contract_only_not_market_research",
    }
    write_json_atomic(os.path.join(output_dir, "input.json"), acceptance_input)
    result = ResearchLeadAgent(mock=False, runtime="pi").run(
        {
            "input": acceptance_input,
            "date_range": {"since": "20250101", "until": "20250530"},
            "output_dir": output_dir,
            "agent_outputs": {},
            "prev_findings": [],
            "pipeline_errors": [],
        }
    )
    policy = result.get("runtime_policy", {})
    passed = (
        result.get("status") == "ok"
        and result.get("provider") == "deepseek"
        and result.get("model") == Config.DEEPSEEK_MODEL
        and result.get("pi_version") == Config.PI_VERSION
        and result.get("usage", {}).get("totalTokens", 0) > 0
        and policy.get("all_tools_disabled") is True
        and policy.get("context_files_disabled") is True
        and policy.get("project_resources_ignored") is True
    )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "acceptance_scope": "runtime_contract_only_not_market_research",
        "runtime": "pi",
        "pi_package": Config.PI_PACKAGE_NAME,
        "pi_version": result.get("pi_version"),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "session_id": result.get("session_id"),
        "response_id": result.get("response_id"),
        "usage": result.get("usage", {}),
        "runtime_policy": policy,
        "agent_status": result.get("status"),
        "agent_error": result.get("error"),
        "output_dir": output_dir,
        "disclaimer": "Runtime contract evidence only; not market research or real trading advice.",
    }
    write_json_atomic(os.path.join(output_dir, "acceptance_report.json"), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def cmd_skills_audit(args):
    result = audit_project_skills()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


def cmd_extensions_audit(args):
    result = audit_project_extensions()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


def cmd_secret_scan(args):
    receipt = build_secret_scan_receipt(output_path=args.output)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if receipt.get("status") != "passed":
        print(
            "\nSecret scan FAILED. Review the reported file and line locations, "
            "remove the secret or adjust the versioned scan rules, then re-run.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_source_candidate(args):
    result = build_source_candidate_manifest(
        output_path=args.output,
        receipt_path=args.secret_receipt,
        max_file_bytes=args.max_file_bytes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if (
        args.require_reviewable
        and result.get("status") != "READY_FOR_HUMAN_FILE_REVIEW_NOT_AUTHORIZED"
    ):
        return 3
    return 0


def cmd_python_runtime(args):
    result = inspect_python_runtime()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_ready and not result.get("ok"):
        return 3
    return 0


def cmd_source_review_packet(args):
    try:
        result = build_source_review_packet(
            output_root=args.output_root,
            receipt_path=args.secret_receipt,
            max_file_bytes=args.max_file_bytes,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        result = {
            "schema_version": 1,
            "report_type": "SOURCE_REVIEW_PACKET",
            "status": "ERROR",
            "packet_created": False,
            "source_baseline_authorized": False,
            "git_actions_performed": False,
            "errors": [str(exc)],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if result.get("status") == "BLOCKED" else 0


def cmd_source_review_verify(args):
    result = verify_source_review_packet(args.packet_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 3


def cmd_source_review_decision_template(args):
    try:
        result = build_source_review_decision_template(
            packet_dir=args.packet_dir,
            output_path=args.output,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        result = {
            "schema_version": 1,
            "report_type": "SOURCE_REVIEW_DECISION_TEMPLATE",
            "status": "ERROR",
            "template_created": False,
            "source_baseline_authorized": False,
            "git_actions_performed": False,
            "errors": [str(exc)],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("template_created") else 3


def cmd_source_review_decision_verify(args):
    result = evaluate_source_review_decision(
        packet_dir=args.packet_dir,
        decision_path=args.decision,
        secret_receipt_path=args.secret_receipt,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("review_claim_valid") else 3


def cmd_project_readiness(args):
    result = build_project_readiness(
        input_path=args.input,
        runs_root=args.runs_root,
        acceptance_root=args.acceptance_root,
        planning_status_path=args.planning_status,
        inspect_pi=not args.skip_pi_inspect,
        acceptance_max_age_days=args.acceptance_max_age_days,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if (
        args.require_ready
        and result.get("status") != "READY_FOR_HUMAN_G1_REVIEW_NOT_AUTHORIZED"
    ):
        return 3
    return 0


def cmd_weekly(args):
    runtime = args.runtime
    mock = args.mock
    if mock:
        runtime = "mock"

    output_dir = os.path.join("runs", f"weekly_{args.since}_{args.until}")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating weekly report: {args.since} ~ {args.until}")
    print(f"Runtime: {runtime}")
    print(f"Output: {output_dir}")
    print()

    try:
        report_path = generate_weekly_report(
            since=args.since,
            until=args.until,
            output_dir=output_dir,
            mock=mock,
            runtime=runtime,
        )
    except RuntimeError as e:
        print(f"\nFATAL: {e}", file=sys.stderr)
        return 2

    print(f"\nWeekly report: {report_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="quant_agents",
        description="A-share CSI 500 Quantitative Research Multi-Agent System",
    )
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no real LLM calls)")
    parser.add_argument("--runtime", choices=["pi"], default="pi",
                        help="Runtime: pi")
    sub = parser.add_subparsers(dest="command")

    p_health = sub.add_parser("health", help="Check system health")
    p_health.add_argument("--no-tushare", action="store_true", help="Skip Tushare check")
    p_health.add_argument("--runtime", choices=["pi"], default="pi")
    p_health.add_argument("--mock", action="store_true")
    p_health.add_argument("--runtime-only", action="store_true", help="Check Pi without source, license, or Tushare gates")
    p_health.add_argument("--no-ping", action="store_true", help="Skip the paid Pi/DeepSeek ping")
    p_health.add_argument("--input", default="strategy_round.example.json")

    p_run = sub.add_parser("run", help="Run a research round")
    p_run.add_argument("--input", required=True, help="Input JSON file path")
    p_run.add_argument("--mock", action="store_true", help="Run in mock mode")
    p_run.add_argument("--runtime", choices=["pi"], default="pi",
                        help="Runtime: pi")
    p_run.add_argument("--request-id", help="Idempotency key for scheduled/automated runs")
    p_run.add_argument("--retry-of", help="Prior failed/interrupted run ID for an explicit retry")

    p_weekly = sub.add_parser("weekly", help="Generate weekly report")
    p_weekly.add_argument("--since", required=True, help="Start date (YYYYMMDD)")
    p_weekly.add_argument("--until", required=True, help="End date (YYYYMMDD)")
    p_weekly.add_argument("--mock", action="store_true", help="Run in mock mode")
    p_weekly.add_argument("--runtime", choices=["pi"], default="pi",
                          help="Runtime: pi")

    p_verify = sub.add_parser("verify-run", help="Verify run manifest and event hash chain")
    p_verify.add_argument("--run-dir", required=True)

    p_release_prepare = sub.add_parser("release-prepare", help="Prepare internal-review approval package")
    p_release_prepare.add_argument("--run-dir", required=True)
    p_release_prepare.add_argument("--target", default="internal_research_review")

    p_release_verify = sub.add_parser("release-verify", help="Verify completed human approvals")
    p_release_verify.add_argument("--run-dir", required=True)
    p_release_verify.add_argument("--approval", required=True)

    p_archive = sub.add_parser("archive-run", help="Integrity-check and archive one run")
    p_archive.add_argument("--run-dir", required=True)
    p_archive.add_argument("--archive-root", required=True)

    p_verify_archive = sub.add_parser(
        "verify-archive", help="Verify archive hash, inventory, safe extraction, and restored run"
    )
    p_verify_archive.add_argument("--archive", required=True)
    p_verify_archive.add_argument("--expected-sha256")
    p_verify_archive.add_argument("--expected-run-id")
    p_verify_archive.add_argument("--expected-manifest-snapshot-id")

    p_retention = sub.add_parser(
        "retention-plan", help="Build a legal-hold-aware retention plan without deletion"
    )
    p_retention.add_argument("--runs-root", default="runs")
    p_retention.add_argument("--archive-root", required=True)
    p_retention.add_argument("--retention-days", type=int, default=Config.RUN_RETENTION_DAYS)
    p_retention.add_argument("--output")

    p_schedule = sub.add_parser("make-scheduled-input", help="Resolve latest trade date and create rolling input")
    p_schedule.add_argument("--template", default="strategy_round.example.json")
    p_schedule.add_argument("--output", required=True)
    p_schedule.add_argument("--as-of")
    p_schedule.add_argument("--campaign")

    p_forward_init = sub.add_parser(
        "forward-init", help="Initialize an external append-only forward campaign"
    )
    p_forward_init.add_argument("--baseline-run", required=True)
    p_forward_init.add_argument("--approval", required=True)
    p_forward_init.add_argument("--root", required=True)

    p_forward_record = sub.add_parser(
        "forward-record", help="Append one verified real forward observation"
    )
    p_forward_record.add_argument("--campaign", required=True)
    p_forward_record.add_argument("--run-dir", required=True)
    p_forward_record.add_argument("--expected-campaign-sha256")

    p_forward_status = sub.add_parser(
        "forward-status", help="Verify and report a forward campaign"
    )
    p_forward_status.add_argument("--campaign", required=True)
    p_forward_status.add_argument("--expected-campaign-sha256")

    p_forward_close = sub.add_parser(
        "forward-close", help="Retire or close a forward campaign"
    )
    p_forward_close.add_argument("--campaign", required=True)
    p_forward_close.add_argument("--decision", required=True)
    p_forward_close.add_argument("--expected-campaign-sha256")

    p_experiment_init = sub.add_parser(
        "experiment-init",
        help="Initialize an external append-only experiment registry",
    )
    p_experiment_init.add_argument("--evidence", required=True)
    p_experiment_init.add_argument("--root", required=True)

    p_experiment_status = sub.add_parser(
        "experiment-status",
        help="Verify the external experiment registry and unresolved reservations",
    )
    p_experiment_status.add_argument(
        "--registry", default=Config.EXPERIMENT_REGISTRY_PATH, required=not bool(Config.EXPERIMENT_REGISTRY_PATH)
    )
    p_experiment_status.add_argument("--runs-root", default="runs")
    p_experiment_status.add_argument("--stale-hours", type=float, default=4.0)

    p_recover = sub.add_parser("recover", help="Mark stale in-progress runs as interrupted")
    p_recover.add_argument("--runs-root", default="runs")
    p_recover.add_argument("--stale-seconds", type=int, default=Config.RUN_LOCK_STALE_SECONDS)

    p_status = sub.add_parser("ops-status", help="Emit latest run status as JSON")
    p_status.add_argument("--runs-root", default="runs")
    p_status.add_argument("--include-mock", action="store_true")
    p_status.add_argument("--max-age-hours", type=float, default=36.0)
    p_status.add_argument("--campaign")
    p_status.add_argument("--expected-campaign-sha256")
    p_status.add_argument("--experiment-registry", default=Config.EXPERIMENT_REGISTRY_PATH)

    p_pi_acceptance = sub.add_parser(
        "pi-acceptance", help="Run one real no-tools Pi Agent contract acceptance"
    )
    p_pi_acceptance.add_argument("--output")

    sub.add_parser(
        "skills-audit",
        help="Verify project Pi skills hashes and production isolation",
    )
    sub.add_parser(
        "extensions-audit",
        help="Verify operator Pi extension hashes and production isolation",
    )

    p_secret_scan = sub.add_parser(
        "secret-scan",
        help="Scan commit candidates for secrets and write a verifiable receipt",
    )
    p_secret_scan.add_argument("--output", help="Receipt output path")

    p_source_candidate = sub.add_parser(
        "source-candidate",
        help="Build a pre-commit source inventory without staging or committing",
    )
    p_source_candidate.add_argument(
        "--output",
        help="Ignored or external manifest path",
    )
    p_source_candidate.add_argument("--secret-receipt")
    p_source_candidate.add_argument(
        "--max-file-bytes",
        type=int,
        default=1024 * 1024,
    )
    p_source_candidate.add_argument(
        "--require-reviewable",
        action="store_true",
        help="Exit 3 while machine blockers prevent human per-file review",
    )

    p_python_runtime = sub.add_parser(
        "python-runtime",
        help="Inspect the Windows CPython 3.11 project-venv contract offline",
    )
    p_python_runtime.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 3 when the project Python runtime contract is not satisfied",
    )

    p_source_review = sub.add_parser(
        "source-review-packet",
        help="Generate a non-authorizing per-file review handoff packet",
    )
    p_source_review.add_argument(
        "--output-root",
        help="Ignored or external directory that will contain a new immutable packet",
    )
    p_source_review.add_argument("--secret-receipt")
    p_source_review.add_argument(
        "--max-file-bytes",
        type=int,
        default=1024 * 1024,
    )
    p_source_review_verify = sub.add_parser(
        "source-review-verify",
        help="Verify a source review packet without granting authorization",
    )
    p_source_review_verify.add_argument("--packet-dir", required=True)

    p_source_review_decision_template = sub.add_parser(
        "source-review-decision-template",
        help="Create a blank external-review decision template bound to a packet",
    )
    p_source_review_decision_template.add_argument("--packet-dir", required=True)
    p_source_review_decision_template.add_argument(
        "--output",
        help="Ignored or external output path for the blank template",
    )
    p_source_review_decision_verify = sub.add_parser(
        "source-review-decision-verify",
        help="Verify completed external dual-review evidence without authorization",
    )
    p_source_review_decision_verify.add_argument("--packet-dir", required=True)
    p_source_review_decision_verify.add_argument("--decision", required=True)
    p_source_review_decision_verify.add_argument(
        "--secret-receipt",
        help="Secret-scan receipt used when the reviewed packet was generated",
    )

    p_readiness = sub.add_parser(
        "project-readiness",
        help="Report all local and external blockers without network or paid calls",
    )
    p_readiness.add_argument("--input", default="strategy_round.example.json")
    p_readiness.add_argument("--runs-root", default="runs")
    p_readiness.add_argument("--acceptance-root", default="drill_reports")
    p_readiness.add_argument("--planning-status")
    p_readiness.add_argument(
        "--acceptance-max-age-days",
        type=int,
        default=7,
    )
    p_readiness.add_argument("--skip-pi-inspect", action="store_true")
    p_readiness.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 3 while the project is not ready for a human G1 review",
    )

    args = parser.parse_args()

    if args.command == "health":
        sys.exit(cmd_health(args))
    elif args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "weekly":
        sys.exit(cmd_weekly(args))
    elif args.command == "verify-run":
        sys.exit(cmd_verify_run(args))
    elif args.command == "release-prepare":
        sys.exit(cmd_release_prepare(args))
    elif args.command == "release-verify":
        sys.exit(cmd_release_verify(args))
    elif args.command == "archive-run":
        sys.exit(cmd_archive_run(args))
    elif args.command == "verify-archive":
        sys.exit(cmd_verify_archive(args))
    elif args.command == "retention-plan":
        sys.exit(cmd_retention_plan(args))
    elif args.command == "make-scheduled-input":
        sys.exit(cmd_make_scheduled_input(args))
    elif args.command == "forward-init":
        sys.exit(cmd_forward_init(args))
    elif args.command == "forward-record":
        sys.exit(cmd_forward_record(args))
    elif args.command == "forward-status":
        sys.exit(cmd_forward_status(args))
    elif args.command == "forward-close":
        sys.exit(cmd_forward_close(args))
    elif args.command == "experiment-init":
        sys.exit(cmd_experiment_init(args))
    elif args.command == "experiment-status":
        sys.exit(cmd_experiment_status(args))
    elif args.command == "recover":
        sys.exit(cmd_recover(args))
    elif args.command == "ops-status":
        sys.exit(cmd_ops_status(args))
    elif args.command == "pi-acceptance":
        sys.exit(cmd_pi_acceptance(args))
    elif args.command == "skills-audit":
        sys.exit(cmd_skills_audit(args))
    elif args.command == "extensions-audit":
        sys.exit(cmd_extensions_audit(args))
    elif args.command == "secret-scan":
        sys.exit(cmd_secret_scan(args))
    elif args.command == "source-candidate":
        sys.exit(cmd_source_candidate(args))
    elif args.command == "python-runtime":
        sys.exit(cmd_python_runtime(args))
    elif args.command == "source-review-packet":
        sys.exit(cmd_source_review_packet(args))
    elif args.command == "source-review-verify":
        sys.exit(cmd_source_review_verify(args))
    elif args.command == "source-review-decision-template":
        sys.exit(cmd_source_review_decision_template(args))
    elif args.command == "source-review-decision-verify":
        sys.exit(cmd_source_review_decision_verify(args))
    elif args.command == "project-readiness":
        sys.exit(cmd_project_readiness(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
