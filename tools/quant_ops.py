"""Cross-platform operations driver for macOS and Linux.

Windows keeps its PowerShell entry points unchanged; this driver mirrors the
operational scripts that are not bound to Windows facilities (scheduled tasks,
legacy OpenClaw teardown, the production daily runner) so the same
``quant_agents`` commands run from one reviewed implementation per platform:

- bootstrap_python.ps1         -> bootstrap
- lock_python_dependencies.ps1 -> lock
- install_pi_runtime.ps1       -> install-pi-runtime
- quant.ps1                    -> cli (and any unknown sub-command)
- check_pi.ps1                 -> check-pi
- run_quant_agents.ps1         -> run
- run_weekly_report.ps1        -> weekly
- verify_quant_pipeline.ps1    -> verify
- backup_quant_runs.ps1        -> backup
- plan_quant_retention.ps1     -> retention-plan
- invoke_quant_drill.ps1       -> drill
- open_pi_ops_console.ps1      -> ops-console
- invoke_pi_acceptance.ps1     -> pi-acceptance

The driver is standard-library only and Python 3.9 compatible because
``bootstrap`` runs before the project ``.venv`` exists. Every other command
resolves the project interpreter from the same locked contract the pipeline
enforces, and nothing here calls a provider, data service, or ledger on its
own: it only forwards to ``python -m quant_agents``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PI_RUNTIME_DIR = PROJECT_ROOT / "pi_runtime"
PI_CLI = (
    PI_RUNTIME_DIR
    / "node_modules"
    / "@earendil-works"
    / "pi-coding-agent"
    / "dist"
    / "cli.js"
)
PI_STATE_DIR = PROJECT_ROOT / ".cache" / "pi-agent"
PI_EXTENSION = PROJECT_ROOT / ".pi" / "extensions" / "quant-ops-readonly.mjs"
MINIMUM_NODE_VERSION = (22, 19, 0)
EXPECTED_PYTHON_VERSION = "0.84.2"
EXPECTED_PYTHON_MINOR = "3.11"
LOCK_COMPILER_VERSION = "pip-tools==7.6.1"
OPS_COMMANDS = (
    "bootstrap",
    "lock",
    "install-pi-runtime",
    "cli",
    "check-pi",
    "run",
    "weekly",
    "verify",
    "backup",
    "retention-plan",
    "drill",
    "ops-console",
    "pi-acceptance",
)
# Commands that trigger paid LLM usage, licensed data usage, production
# schedule installation, or forward-ledger writes. Never used by verify.
PAID_OR_PRIVILEGED_MARKERS = (
    "invoke_pi_acceptance",
    "invoke_pi_skills_acceptance",
    "install_quant_schedule",
    "run_daily_research",
    "forward-record",
    "check_pi",
)
DRILL_TEST_PATTERNS = (
    "test_operations.py",
    "test_release.py",
    "test_scheduling.py",
    "test_governance.py",
    "test_cli.py",
    "test_pi_client.py",
    "test_orchestrator.py",
)
DRILL_REPORTS = (
    "run_lock_contention_and_stale_reclaim",
    "request_idempotency_and_explicit_retry",
    "event_chain_tamper_detection",
    "stale_run_recovery",
    "production_monitor_excludes_mock_and_stale_runs",
    "archive_tamper_path_traversal_and_restore_verification",
    "retention_and_legal_hold_plan",
    "release_block_on_mock_or_tamper",
    "schedule_cutoff_and_stable_request_id",
    "data_license_evidence_validation",
    "pi_version_model_json_tool_and_timeout_failures",
    "source_preflight_dependency_and_budget_blocking",
)
FORBIDDEN_TRADING_TERMS = ("买入", "卖出", "加仓", "减仓", "止损", "止盈", "LONG", "SHORT")
REQUIRED_BACKTEST_ARTIFACTS = (
    "backtest/cost_ledger.json",
    "backtest/execution_policy.json",
    "backtest/robustness_validation.json",
    "backtest/backtest_assurance.json",
)
_ENV_LINE = re.compile(r"^\s*([^#][^=]+)=(.+)$")
_RUN_ID = re.compile(r"^\d{8}_\d{6}_\d{3}$")


class OpsError(RuntimeError):
    """Operator-facing failure; the message is the whole diagnostic."""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        return cmd_help([])
    command = argv[0]
    if command not in OPS_COMMANDS:
        # quant.ps1 equivalent: forward unknown sub-commands to quant_agents.
        return cmd_cli(argv)
    handler = globals()[f"cmd_{command.replace('-', '_')}"]
    try:
        return handler(argv[1:])
    except OpsError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


def cmd_help(_: list[str]) -> int:
    print(__doc__.strip())
    print("\nUsage: ./quant.sh <command> [options]   |   ./quant.sh <quant_agents sub-command> ...")
    return 0


# --- interpreters, environment, subprocesses ---------------------------------


def require_posix(command: str) -> None:
    if os.name == "nt":
        raise OpsError(
            f"{command}: use the PowerShell entry point on Windows; "
            "this driver is the macOS/Linux entry."
        )


def _python_minor(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "-c", "import sys, platform; print('%d.%d %s' % (sys.version_info[0], sys.version_info[1], platform.python_implementation()))"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    minor, _, implementation = result.stdout.strip().partition(" ")
    return minor if implementation == "CPython" else None


def find_base_python() -> str:
    """Locate a CPython 3.11.x interpreter for creating the venv."""

    candidates = [
        os.environ.get("QUANT_BASE_PYTHON"),
        shutil.which("python3.11"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) or candidate
        if _python_minor(resolved) == EXPECTED_PYTHON_MINOR:
            return str(Path(resolved).resolve())
    uv = shutil.which("uv")
    if uv:
        found = _capture([uv, "python", "find", "3.11"])
        if found.returncode == 0:
            resolved = found.stdout.strip().splitlines()[0].strip()
            if _python_minor(resolved) == EXPECTED_PYTHON_MINOR:
                return str(Path(resolved).resolve())
    raise OpsError(
        "CPython 3.11.x is required. Install it (for example `uv python install 3.11` "
        "or `brew install python@3.11`), or set QUANT_BASE_PYTHON to its path."
    )


def resolve_project_python() -> str:
    python = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not python.is_file():
        raise OpsError("Project Python environment is missing. Run ./quant.sh bootstrap first.")
    if _python_minor(str(python)) != EXPECTED_PYTHON_MINOR:
        raise OpsError(f"Project Python must be CPython 3.11.x; found another version at {python}.")
    return str(python)


def host_lock_file() -> Path:
    """Committed hash lock for the host platform, from the runtime contract.

    The driver only runs on POSIX hosts that have a lock (Darwin arm64, Linux
    arm64); an unsupported host fails the pipeline's own operating_system
    check instead of borrowing another platform's wheels.
    """

    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from quant_agents.python_runtime import current_runtime_contract

        return PROJECT_ROOT / current_runtime_contract().lock_file
    finally:
        sys.path.pop(0)


def load_env_file() -> bool:
    """Mirror of the PowerShell wrappers: fill unset variables from .env."""

    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return False
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        match = _ENV_LINE.match(line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip().strip('"').strip("'")
        if not os.environ.get(key):
            os.environ[key] = value
    return True


def _child_env() -> dict:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    return dict(os.environ)


def run_python(
    args: list[str], *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess:
    """Run ``python -m <args>`` in the project venv, streaming unless captured."""

    result = subprocess.run(
        [resolve_project_python(), *args],
        cwd=PROJECT_ROOT,
        env=_child_env(),
        **(
            {"capture_output": True, "text": True, "encoding": "utf-8"}
            if capture
            else {}
        ),
    )
    if check and result.returncode != 0:
        raise OpsError(f"python -m {' '.join(args)} failed with exit code {result.returncode}")
    return result


def run_json(args: list[str], *, check: bool = True) -> dict:
    """Parse a JSON command's stdout; ``check=False`` keeps a blocking exit code."""

    result = subprocess.run(
        [resolve_project_python(), *args],
        cwd=PROJECT_ROOT,
        env=_child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        if check:
            raise OpsError(f"python -m {' '.join(args)} failed with exit code {result.returncode}")
    return json.loads(result.stdout)


def _capture(args: list[str], *, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=cwd or PROJECT_ROOT,
        env=env or _child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_version(text: str) -> tuple[int, ...]:
    parts = text.strip().split(".")
    return tuple(int(part) for part in parts) if all(part.isdigit() for part in parts) else ()


def _latest_run() -> Path:
    runs_root = PROJECT_ROOT / "runs"
    candidates = [
        entry
        for entry in (runs_root.iterdir() if runs_root.is_dir() else [])
        if entry.is_dir() and _RUN_ID.match(entry.name)
    ]
    if not candidates:
        raise OpsError("No pipeline run directory was found under runs/.")
    return max(candidates, key=lambda entry: entry.stat().st_mtime)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise OpsError(message)


# --- bootstrap and lock ------------------------------------------------------


def cmd_bootstrap(args: list[str]) -> int:
    require_posix("bootstrap")
    parser = argparse.ArgumentParser(prog="quant.sh bootstrap")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--wheelhouse")
    options = parser.parse_args(args)

    base_python = find_base_python()
    venv_root = PROJECT_ROOT / ".venv"
    if not (venv_root / "bin" / "python").is_file():
        if subprocess.run([base_python, "-m", "venv", str(venv_root)]).returncode != 0:
            raise OpsError("Failed to create the project virtual environment.")
    python = resolve_project_python()
    install_args = [python, "-m", "pip", "install", "--require-hashes", "--only-binary=:all:"]
    if options.wheelhouse:
        install_args += ["--no-index", "--find-links", str(Path(options.wheelhouse).resolve())]
    install_args += ["-r", str(host_lock_file())]
    if subprocess.run(install_args, cwd=PROJECT_ROOT, env=_child_env()).returncode != 0:
        raise OpsError("Hash-locked dependency installation failed.")
    if subprocess.run([python, "-m", "pip", "check"], cwd=PROJECT_ROOT, env=_child_env()).returncode != 0:
        raise OpsError("The isolated dependency set is inconsistent.")
    run_python(["-m", "quant_agents", "python-runtime", "--require-ready"])
    if not options.skip_tests:
        run_python(["-m", "unittest", "discover", "-s", "tests"])
    print(f"Isolated CPython 3.11 environment is ready: {python}")
    return 0


def _lock_pins(text: str) -> list[tuple[str, str]]:
    return re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s\\]+)", text)


def cmd_lock(args: list[str]) -> int:
    """Regenerate the host platform's hash lock; nothing is applied by default."""

    require_posix("lock")
    parser = argparse.ArgumentParser(prog="quant.sh lock")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--index-url")
    options = parser.parse_args(args)

    base_python = find_base_python()
    lock_path = host_lock_file()
    build_root = PROJECT_ROOT / ".tmp" / f"python-lock-{uuid.uuid4().hex}"
    build_root.mkdir(parents=True)
    index_args = ["--index-url", options.index_url] if options.index_url else []
    steps = [
        ([base_python, "-m", "venv", str(build_root / "venv")], "Failed to create the isolated lock environment."),
        ([str(build_root / "venv" / "bin" / "python"), "-m", "pip", "install", *index_args, LOCK_COMPILER_VERSION], "Failed to install the pinned lock compiler."),
    ]
    python = str(build_root / "venv" / "bin" / "python")
    for command, failure in steps:
        if subprocess.run(command, cwd=PROJECT_ROOT, env=_child_env()).returncode != 0:
            raise OpsError(failure)
    resolved = build_root / "requirements.resolved.txt"
    compile_result = _capture(
        [
            python, "-m", "piptools", "compile",
            "--resolver=backtracking",
            "--no-header",
            "--no-emit-index-url",
            "--no-emit-trusted-host",
            "--strip-extras",
            f"--output-file={resolved}",
            *index_args,
            str(PROJECT_ROOT / "requirements.in"),
        ]
    )
    if compile_result.returncode != 0:
        sys.stderr.write(compile_result.stderr)
        raise OpsError("Dependency resolution failed.")
    wheelhouse = build_root / "wheelhouse"
    download_result = _capture(
        [python, "-m", "pip", "download", "--only-binary=:all:", "--dest", str(wheelhouse), *index_args, "-r", str(resolved)]
    )
    if download_result.returncode != 0:
        sys.stderr.write(download_result.stderr)
        raise OpsError("Wheel download failed.")
    candidate = build_root / lock_path.name
    build_result = _capture(
        [python, str(PROJECT_ROOT / "tools" / "build_python_lock.py"), "--resolved", str(resolved), "--wheelhouse", str(wheelhouse), "--output", str(candidate), "--platform-label", _platform_label(), "--origin-note", _ORIGIN_NOTE]
    )
    if build_result.returncode != 0:
        sys.stderr.write(build_result.stderr)
        raise OpsError("Hash-lock generation failed.")

    committed = _lock_pins(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else []
    proposed = _lock_pins(candidate.read_text(encoding="utf-8"))
    if proposed != committed:
        print(
            f"Resolved pins differ from the committed {lock_path.name}: "
            f"{len(committed)} committed, {len(proposed)} resolved. Review before applying.",
            file=sys.stderr,
        )
    if options.apply:
        shutil.copyfile(candidate, lock_path)
        print(f"Applied lock candidate to {lock_path.name}. Run bootstrap, tests, secret-scan, and source-candidate before review.")
    else:
        print(f"Lock candidate generated without modifying {lock_path.name}: {candidate}")
    return 0


_PLATFORM_LOCK_LABELS = {
    "Darwin": "macOS arm64 CPython 3.11",
    "Linux": "Linux arm64 CPython 3.11",
}


def _platform_label() -> str:
    import platform

    return _PLATFORM_LOCK_LABELS.get(platform.system(), "POSIX CPython 3.11")


def _origin_note() -> str:
    return (
        "Resolved with pip-tools 7.6.1 and verified from one selected "
        f"{_platform_label()} wheel per pin."
    )


def cmd_install_pi_runtime(_: list[str]) -> int:
    require_posix("install-pi-runtime")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise OpsError("Node.js >= 22.19.0 and npm are required to install the pinned Pi runtime")
    node_version = _capture([node, "--version"]).stdout.strip().lstrip("v")
    if _parse_version(node_version) < MINIMUM_NODE_VERSION:
        raise OpsError(f"Pi 0.84.2 requires Node >= 22.19.0; found {node_version}")
    env = _child_env()
    env["npm_config_cache"] = os.path.join(tempfile.gettempdir(), "quant-pi-npm-cache")
    result = subprocess.run(
        [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--registry=https://registry.npmjs.org"],
        cwd=PI_RUNTIME_DIR,
        env=env,
    )
    if result.returncode != 0:
        raise OpsError(f"npm ci failed with exit code {result.returncode}")
    _require(PI_CLI.is_file(), f"Pi CLI was not installed at {PI_CLI}")
    pi_version = _capture([node, str(PI_CLI), "--version"]).stdout.strip()
    _require(pi_version == EXPECTED_PYTHON_VERSION, f"Installed Pi version is '{pi_version}'; expected {EXPECTED_PYTHON_VERSION}")
    PI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    offline_env = dict(_child_env(), PI_CODING_AGENT_DIR=str(PI_STATE_DIR), PI_OFFLINE="1", PI_TELEMETRY="0")
    # Pi 0.84.2 serves its bundled catalog only for a configured provider. The
    # listing runs with --offline, so no request is made and nothing is
    # written to the isolated state directory; a non-secret placeholder keeps
    # the install step free of real credentials when none is configured.
    offline_env.setdefault("DEEPSEEK_API_KEY", "catalog-listing-placeholder-not-a-credential")
    models = _capture([node, str(PI_CLI), "--list-models", "deepseek", "--offline"], env=offline_env)
    _require(
        models.returncode == 0 and re.search(r"(?m)^deepseek\s+deepseek-v4-pro\s+", models.stdout),
        "Pinned Pi runtime does not expose deepseek/deepseek-v4-pro",
    )
    receipt = {
        "schema_version": 1,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "package": "@earendil-works/pi-coding-agent",
        "version": pi_version,
        "node_version": node_version,
        "package_lock_sha256": _sha256(PI_RUNTIME_DIR / "package-lock.json"),
        "cli_sha256": _sha256(PI_CLI),
        "install_scripts_disabled": True,
        "model": "deepseek-v4-pro",
    }
    receipt_path = PI_STATE_DIR / "install_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**receipt, "receipt_path": str(receipt_path)}, indent=2))
    return 0


# --- quant_agents forwarding -------------------------------------------------


def cmd_cli(args: list[str]) -> int:
    require_posix("cli")
    if not args:
        print("Usage: ./quant.sh <quant_agents sub-command> [options]")
        return 2
    return run_python(["-m", "quant_agents", *args], check=False).returncode


def cmd_check_pi(args: list[str]) -> int:
    require_posix("check-pi")
    parser = argparse.ArgumentParser(prog="quant.sh check-pi")
    parser.add_argument("--no-ping", action="store_true")
    options = parser.parse_args(args)
    load_env_file()
    for audit in ("extensions-audit", "skills-audit"):
        if run_python(["-m", "quant_agents", audit], check=False).returncode != 0:
            return 1
    health_args = ["-m", "quant_agents", "health", "--runtime", "pi", "--runtime-only"]
    if options.no_ping:
        health_args.append("--no-ping")
    return run_python(health_args, check=False).returncode


def cmd_run(args: list[str]) -> int:
    require_posix("run")
    parser = argparse.ArgumentParser(prog="quant.sh run")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--input", default="strategy_round.example.json")
    parser.add_argument("--runtime", choices=["pi"], default="pi")
    parser.add_argument("--request-id")
    parser.add_argument("--retry-of")
    options = parser.parse_args(args)
    print("=== CSI 500 Quant Research Agent System ===")
    print(f"Input: {options.input}")
    print(f"Runtime: {options.runtime}")
    print(f"Mode: {'MOCK' if options.mock else 'REAL'}")
    print("Fallback: disabled (Mock requires --mock)\n")
    if load_env_file():
        print("Loaded .env file")
    run_python(["-m", "quant_agents", "recover", "--runs-root", "runs"])
    run_args = ["-m", "quant_agents", "run", "--runtime", options.runtime, "--input", options.input]
    if options.mock:
        run_args.append("--mock")
    if options.request_id:
        run_args += ["--request-id", options.request_id]
    if options.retry_of:
        _require(options.request_id, "--retry-of requires --request-id")
        run_args += ["--retry-of", options.retry_of]
    exit_code = run_python(run_args, check=False).returncode
    print()
    if exit_code == 0:
        print("=== Done ===")
    elif exit_code == 2:
        print("=== FAILED: real-mode preflight did not pass ===")
        print("Run ./quant.sh check-pi and ./quant.sh health --runtime " + options.runtime)
    else:
        print(f"=== Done with errors (exit {exit_code}) ===")
    return exit_code


def cmd_weekly(args: list[str]) -> int:
    require_posix("weekly")
    parser = argparse.ArgumentParser(prog="quant.sh weekly")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    parser.add_argument("--runtime", choices=["pi"], default="pi")
    options = parser.parse_args(args)
    since = options.since or (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    until = options.until or datetime.now().strftime("%Y%m%d")
    print("=== CSI 500 Weekly Report ===")
    print(f"Period: {since} ~ {until}")
    print(f"Runtime: {options.runtime}")
    print(f"Mode: {'MOCK' if options.mock else 'REAL'}\n")
    load_env_file()
    weekly_args = ["-m", "quant_agents", "weekly", "--runtime", options.runtime, "--since", since, "--until", until]
    if options.mock:
        weekly_args.append("--mock")
    print(f"Running: python {' '.join(weekly_args)}")
    exit_code = run_python(weekly_args, check=False).returncode
    print()
    if exit_code == 0:
        print("=== Done ===")
    elif exit_code == 2:
        print("=== FAILED: weekly aggregation could not complete ===")
    else:
        print(f"=== Done with errors (exit {exit_code}) ===")
    return exit_code


def cmd_pi_acceptance(_: list[str]) -> int:
    """Paid call: a real DeepSeek turn. Forwarded only on explicit request."""

    require_posix("pi-acceptance")
    load_env_file()
    return run_python(["-m", "quant_agents", "pi-acceptance"], check=False).returncode


def cmd_ops_console(_: list[str]) -> int:
    require_posix("ops-console")
    os.environ["PI_OFFLINE"] = "1"
    os.environ["PI_TELEMETRY"] = "0"
    if run_python(["-m", "quant_agents", "extensions-audit"], check=False).returncode != 0:
        return 1
    node = shutil.which("node")
    _require(node is not None, "Node.js is required for the Pi operator console")
    os.environ["PI_CODING_AGENT_DIR"] = str(PI_STATE_DIR)
    print("Pi read-only operator console. Use /quant-status or /quant-status clear.")
    print("No tools, skills, automatic extensions, sessions, context files, or startup network are enabled.")
    return subprocess.run(
        [
            node,
            str(PI_CLI),
            "--provider", "deepseek",
            "--model", "deepseek-v4-pro",
            "--thinking", "off",
            "--no-session",
            "--no-tools",
            "--no-extensions",
            "--extension", str(PI_EXTENSION),
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-context-files",
            "--no-approve",
            "--offline",
            "--system-prompt", "You are a read-only quant operations console. Return JSON only. Do not provide market analysis or real-money trading advice.",
        ],
        cwd=PROJECT_ROOT,
    ).returncode


# --- offline verification ----------------------------------------------------


def cmd_verify(args: list[str]) -> int:
    require_posix("verify")
    parser = argparse.ArgumentParser(prog="quant.sh verify")
    parser.add_argument("--skip-mock", action="store_true")
    options = parser.parse_args(args)
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))

    run_python(["-m", "quant_agents", "python-runtime", "--require-ready"])
    python_files = sorted(str(path) for path in (PROJECT_ROOT / "quant_agents").rglob("*.py"))
    run_python(["-m", "py_compile", *python_files])

    run_python(["-m", "quant_agents", "secret-scan"])
    run_python(["-m", "quant_agents", "source-candidate", "--require-reviewable"])

    packet = run_json(["-m", "quant_agents", "source-review-packet"])
    _require(
        packet.get("packet_created") is True
        and packet.get("source_baseline_authorized") is False
        and Path(str(packet.get("packet_dir", ""))).is_dir(),
        "Source-review packet smoke test did not create a non-authorizing packet.",
    )
    verification = run_json(["-m", "quant_agents", "source-review-verify", "--packet-dir", packet["packet_dir"]])
    _require(
        verification.get("ok") is True
        and verification.get("organization_identity_verified") is False
        and verification.get("source_baseline_authorized") is False,
        "Source-review packet verification weakened a review or authorization boundary.",
    )
    template = run_json(["-m", "quant_agents", "source-review-decision-template", "--packet-dir", packet["packet_dir"]])
    _require(
        template.get("template_created") is True
        and template.get("human_fields_blank") is True
        and template.get("source_baseline_authorized") is False,
        "Source-review decision template smoke test did not preserve blank, non-authorizing controls.",
    )
    # A blank decision must block: the command still reports JSON with exit code 3.
    blank_exit = run_python(
        ["-m", "quant_agents", "source-review-decision-verify", "--packet-dir", packet["packet_dir"], "--decision", template["template_path"]],
        check=False,
        capture=True,
    )
    _require(blank_exit.returncode == 3, "Blank source-review decision must block with exit code 3.")
    blank = json.loads(blank_exit.stdout)
    _require(
        blank.get("review_claim_valid") is False
        and blank.get("source_baseline_authorized") is False
        and blank.get("g1_authorized") is False
        and blank.get("real_run_authorized") is False,
        "Blank source-review decision incorrectly passed a governance boundary.",
    )

    _verify_powershell_syntax()

    if run_python(["-m", "unittest", "discover", "-s", "tests", "-v"], check=False).returncode != 0:
        return 1

    if not options.skip_mock:
        exit_code = cmd_run(["--mock"])
        if exit_code != 0:
            return exit_code
        _verify_mock_run()
    print("Quant pipeline verification PASSED")
    return 0


def _verify_powershell_syntax() -> None:
    """Parse the retained Windows entry points when PowerShell exists here."""

    scripts = sorted(PROJECT_ROOT.glob("*.ps1"))
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        print(
            f"PowerShell syntax parse: SKIPPED on this platform (no pwsh); "
            f"{len(scripts)} retained Windows scripts are parsed by verify_quant_pipeline.ps1 "
            "and the windows-latest CI job."
        )
        return
    probe = PROJECT_ROOT / ".tmp" / "ps-parse.ps1"
    probe.parent.mkdir(exist_ok=True)
    probe.write_text(
        "$failed = 0\n"
        "foreach ($file in Get-ChildItem -LiteralPath $args[0] -Filter *.ps1 -File) {\n"
        "  $tokens = $null; $errors = $null\n"
        "  [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)\n"
        "  if ($errors -and $errors.Count -gt 0) { $failed = 1; Write-Host \"$($file.Name): $($errors[0].Message)\" }\n"
        "}\n"
        "Write-Host (\"PowerShell syntax parse: {0} scripts checked\" -f (Get-ChildItem -LiteralPath $args[0] -Filter *.ps1 -File).Count)\n"
        "exit $failed\n",
        encoding="utf-8",
    )
    _require(
        subprocess.run([pwsh, "-NoProfile", "-File", str(probe), str(PROJECT_ROOT)]).returncode == 0,
        "PowerShell parse error in a retained Windows script.",
    )
    probe.unlink()


def _verify_mock_run() -> None:
    latest = _latest_run()
    state = _read_json(latest / "state.json")
    _require(
        state.get("schema_version") == 7 and state.get("success_count") == 7 and state.get("error_count") == 0,
        f"Mock acceptance failed for {latest}",
    )
    runtime_checks = [
        check
        for check in state.get("preflight", {}).get("checks", [])
        if check.get("name") == "python_runtime_contract"
    ]
    expected_lock_sha256 = _sha256(host_lock_file())
    _require(
        len(runtime_checks) == 1
        and runtime_checks[0].get("status") == "ok"
        and runtime_checks[0].get("detail", {}).get("ok") is True
        and runtime_checks[0]["detail"].get("requirements_lock_sha256") == expected_lock_sha256,
        "Mock evidence is not bound to the current project Python runtime contract.",
    )
    _require(
        state.get("budget_gate", {}).get("status") == "passed"
        and state.get("business_controls", {}).get("broker_connection_enabled") is False,
        f"Operational or broker boundary gate failed for {latest}",
    )
    controls = state.get("business_controls", {})
    _require(
        controls.get("research_protocol_gate", {}).get("status") == "not_evaluated_mock"
        and controls["research_protocol_gate"].get("live_execution_authorized") is False,
        f"Mock research-protocol gate must remain explicitly non-applicable for {latest}",
    )
    _require(
        controls.get("execution_cost_gate", {}).get("status") == "not_evaluated_mock"
        and controls["execution_cost_gate"].get("live_execution_ready") is False,
        f"Mock execution-cost gate must remain explicitly non-applicable for {latest}",
    )
    _require(
        controls.get("experiment_registry_gate", {}).get("status") == "not_evaluated_mock"
        and controls["experiment_registry_gate"].get("ledger_integrity_ok") is False,
        f"Mock experiment-registry gate must remain explicitly non-applicable for {latest}",
    )
    _require(
        state.get("backtest_assurance", {}).get("decision") == "NOT_APPLICABLE_MOCK"
        and state.get("robustness_validation", {}).get("decision") == "NOT_APPLICABLE_MOCK"
        and state["robustness_validation"].get("walk_forward", {}).get("decision") == "NOT_APPLICABLE_MOCK",
        f"Mock backtest gates must remain explicitly non-applicable for {latest}",
    )
    for relative in REQUIRED_BACKTEST_ARTIFACTS:
        artifact = latest / relative
        _require(artifact.is_file(), f"Required backtest artifact is missing: {artifact}")
        json.loads(artifact.read_text(encoding="utf-8"))
    metadata = _read_json(latest / "run_manifest.json").get("metadata", {})
    _require(
        metadata.get("backtest_assurance_decision") == "NOT_APPLICABLE_MOCK"
        and metadata.get("robustness_validation_decision") == "NOT_APPLICABLE_MOCK",
        f"Run manifest is not bound to the mock assurance decisions for {latest}",
    )
    for key, expected in (
        ("execution_cost_status", "not_evaluated_mock"),
        ("research_protocol_status", "not_evaluated_mock"),
        ("experiment_registry_status", "not_evaluated_mock"),
    ):
        _require(metadata.get(key) == expected, f"Run manifest is not bound to the mock {key} for {latest}")
    summary = (latest / "summary.md").read_text(encoding="utf-8")
    hits = [term for term in FORBIDDEN_TRADING_TERMS if term in summary]
    _require(not hits, f"Forbidden trading terms in summary: {', '.join(hits)}")

    run_python(["-m", "quant_agents", "verify-run", "--run-dir", str(latest)])
    release_exit = run_python(["-m", "quant_agents", "release-prepare", "--run-dir", str(latest)], check=False).returncode
    _require(release_exit == 3, "Mock release gate must block with exit code 3")


# --- backup, retention, drill ------------------------------------------------


def cmd_backup(args: list[str]) -> int:
    require_posix("backup")
    parser = argparse.ArgumentParser(prog="quant.sh backup")
    parser.add_argument("--run-dir")
    parser.add_argument("--archive-root")
    parser.add_argument("--allow-mock", action="store_true")
    options = parser.parse_args(args)
    archive_root = options.archive_root or str(PROJECT_ROOT.parent / "quant-research-archives")
    load_env_file()

    run_dir = options.run_dir
    if not run_dir:
        candidates = []
        for directory in sorted((PROJECT_ROOT / "runs").iterdir()):
            state_path = directory / "state.json"
            if not directory.is_dir() or not state_path.is_file():
                continue
            try:
                state = _read_json(state_path)
            except (OSError, ValueError):
                continue
            if state.get("status") == "completed" and state.get("error_count") == 0 and (options.allow_mock or not state.get("mock")):
                candidates.append((str(state.get("finished_at", "")), directory))
        _require(candidates, "No clean completed run is available for backup")
        run_dir = str(max(candidates)[1])
    run_dir_path = Path(run_dir).resolve()
    state = _read_json(run_dir_path / "state.json")
    _require(not state.get("mock") or options.allow_mock, "Refusing to archive a mock run without --allow-mock")

    archive = run_json(["-m", "quant_agents", "archive-run", "--run-dir", str(run_dir_path), "--archive-root", archive_root])
    actual_hash = _sha256(Path(archive["archive"]))
    _require(actual_hash == str(archive["sha256"]).lower(), "Archive SHA-256 verification failed")
    verification = run_json(
        [
            "-m", "quant_agents", "verify-archive",
            "--archive", archive["archive"],
            "--expected-sha256", actual_hash,
            "--expected-run-id", archive["run_id"],
            "--expected-manifest-snapshot-id", archive["manifest_snapshot_id"],
        ]
    )
    _require(
        verification.get("ok") and verification.get("restore_tested") and verification.get("restored_integrity_ok"),
        "Archive did not pass the full restore and run-integrity test",
    )
    print(
        json.dumps(
            {
                "status": archive["status"],
                "run_id": archive["run_id"],
                "archive": archive["archive"],
                "sha256": actual_hash,
                "verified": True,
                "restore_tested": bool(verification["restore_tested"]),
                "restored_integrity_ok": bool(verification["restored_integrity_ok"]),
                "archive_content_id": archive["archive_content_id"],
                "receipt": archive["receipt"],
                "source_mock": bool(state.get("mock")),
                "retention_days": int(os.environ.get("RUN_RETENTION_DAYS", "365")),
                "deletion_performed": False,
            },
            indent=2,
        )
    )
    return 0


def cmd_retention_plan(args: list[str]) -> int:
    require_posix("retention-plan")
    parser = argparse.ArgumentParser(prog="quant.sh retention-plan")
    parser.add_argument("--runs-root", default="runs")
    parser.add_argument("--archive-root")
    parser.add_argument("--retention-days", type=int, default=0)
    parser.add_argument("--output")
    options = parser.parse_args(args)
    archive_root = options.archive_root or str(PROJECT_ROOT.parent / "quant-research-archives")
    retention_days = options.retention_days or int(os.environ.get("RUN_RETENTION_DAYS", "365"))
    output = options.output or str(PROJECT_ROOT / "drill_reports" / f"retention_plan_{_now_stamp()}.json")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    run_python(
        [
            "-m", "quant_agents", "retention-plan",
            "--runs-root", options.runs_root,
            "--archive-root", archive_root,
            "--retention-days", str(retention_days),
            "--output", output,
        ]
    )
    return 0


def cmd_drill(args: list[str]) -> int:
    require_posix("drill")
    parser = argparse.ArgumentParser(prog="quant.sh drill")
    parser.add_argument("--include-full-regression", action="store_true")
    options = parser.parse_args(args)
    report_dir = PROJECT_ROOT / "drill_reports" / f"operational_drill_{_now_stamp()}"
    report_dir.mkdir(parents=True, exist_ok=True)
    test_results = []
    status = "passed"
    failure = None
    for pattern in DRILL_TEST_PATTERNS:
        result = _capture(
            [resolve_project_python(), "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"]
        )
        sys.stdout.write(result.stdout + result.stderr)
        log_path = report_dir / pattern.replace(".py", ".log")
        log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
        test_results.append(
            {"pattern": pattern, "exit_code": result.returncode, "passed": result.returncode == 0, "log": str(log_path)}
        )
        if result.returncode != 0:
            status = "failed"
            failure = f"Fault drill failed for {pattern}"
            break
    full_regression = None
    if options.include_full_regression and status == "passed":
        log_path = report_dir / "full_regression.log"
        exit_code = cmd_verify([])
        log_path.write_text("exit_code=%d\n" % exit_code, encoding="utf-8")
        full_regression = {"exit_code": exit_code, "passed": exit_code == 0, "log": str(log_path)}
        if exit_code != 0:
            status = "failed"
            failure = "Full regression failed during drill"
    report = {
        "schema_version": 1,
        "status": status,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "runtime": "test_and_mock_only",
        "real_llm_called": False,
        "drills": list(DRILL_REPORTS),
        "test_results": test_results,
        "full_regression": full_regression,
        "failure": failure,
        "evidence_dir": str(report_dir),
        "production_files_modified": False,
        "disclaimer": "Operational drill only; not market research or real trading advice.",
    }
    report_path = report_dir / "drill_report.json"
    _write_report(report_path, report)
    print(json.dumps(report, indent=2))
    _require(status == "passed", failure or "Drill failed")
    return 0


def _write_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.exit(main())
