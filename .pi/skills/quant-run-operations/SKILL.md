---
name: quant-run-operations
description: Operate, diagnose, and verify the isolated Pi-based CSI 500 multi-Agent research pipeline. Use for Pi installation and health checks, mock regression, real-run preflight, run recovery, manifests, event chains, budgets, incident evidence, weekly reports, or scheduler-readiness decisions.
---

# Quant Run Operations

Preserve the production sequence and never silently fall back.

1. Run `./install_pi_runtime.ps1`, then `./check_pi.ps1`. Confirm the pinned Pi version, Node version, `deepseek/deepseek-v4-pro`, a real paid ping, ephemeral sessions, and all tools/resources disabled.
2. Run `./verify_quant_pipeline.ps1` for deterministic tests and explicit mock acceptance. Label every resulting artifact as mock.
3. Before a real run, execute full health checks. Require a clean source baseline, approved data-license evidence, an externally registered exact research protocol, execution-cost evidence, Tushare access, and Pi runtime health before spending on seven Agent turns.
4. Run `./run_quant_agents.ps1` only after hard gates pass. Never add `-Mock` to conceal a real-mode failure.
5. Inspect `state.json`, `summary.md`, `operations/alerts.json`, `operations/events.jsonl`, `run_manifest.json`, `pi_meta/`, data snapshot records, protocol identity, and integrity verification. For scheduled observation use `ops-status --campaign`; production status must ignore newer mock runs and require the latest real run in the external ledger.
6. Treat partial runs as failed evidence. Recover stale runs as interrupted and start a new run ID; never resume in place or reuse old outputs as current.
7. Back up with `backup_quant_runs.ps1`, independently verify the ZIP and restored run, then generate a plan-only legal-hold-aware retention report. Never delete automatically.
8. Initialize an external forward campaign only from the exact registered baseline after five-role internal-review approval. Freeze source, Pi/model, license, cost, rulebook, protocol, baseline cutoff, and thresholds; never store the campaign in Git.
9. Install scheduling only after campaign verification. Bind the hidden-window task to the approved run, approval hash, source commit, campaign metadata hash, and expiring deployment authorization. Treat a completed run whose ledger append failed as an operational failure.
10. Pause on path rewrites or threshold breaches. Close or retire only with external evidence and distinct model, compliance, and platform approvers. Never call independent-validation eligibility a trading approval.
11. When retiring OpenClaw, disable only the three exact legacy tasks and verify ports 18789/18790; never kill all Node processes or alter unrelated scheduled tasks.

Do not start any legacy gateway runtime, connect a broker, route orders, publish externally, or provide real-capital instructions.
