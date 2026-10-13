# Pi Runtime Contract

## Decision

Use pinned `@earendil-works/pi-coding-agent@0.84.2` as the only real LLM runtime. Python remains the system of record for orchestration, licensed data access, deterministic calculations, gates, artifacts, budgets, and release decisions.

Do not use Pi's subagent extension for the production pipeline. The Python dependency graph already owns ordering and recovery; a second orchestrator would add state, permissions, and failure modes without business value.

## Agent Turn

Each of the seven business roles receives a separate one-shot Pi process with:

- JSON event mode and stdin prompt transport.
- `deepseek/deepseek-v4-pro` only.
- Ephemeral session and isolated project state directory.
- No tools, extensions, skills, prompt templates, themes, context files, or project trust.
- Startup update and telemetry network disabled; only the selected DeepSeek provider call is allowed.
- Per-turn timeout, exact provider/model validation, tool-event rejection, output-contract validation, and at most one repair turn.

Only the final assistant `message_end` is authoritative. Persist its session ID, response ID, usage, provider, model, Pi version, security policy, prompt hash, raw JSONL, and validated final JSON.

## Production Order

1. Establish a clean, reviewed source revision.
2. Approve data-license evidence and secret handling.
3. Bind the exact input and frozen model contract to an externally registered research protocol with independent validation and compliance approval.
4. Bind effective-dated market rules and independently reviewed execution-cost evidence to the exact run contract.
5. Validate the reviewed model-pricing baseline and contingency budget, then Tushare access and source-data health.
6. Verify pinned Pi runtime, no-tools policy, model catalog, and real DeepSeek ping.
7. Execute seven roles in the Python dependency order.
8. Enforce token, cost, runtime, data, integrity, and no-trading gates.
9. Require five independent human approvals before internal review release; then use a separate append-only forward campaign for ongoing observation and retirement controls.
10. Keep external distribution, broker access, orders, and real funds disabled.

Mock mode is a software regression path only. It is never an automatic fallback and can never satisfy a release gate.

## Skills

Project skills under `.pi/skills/` support interactive operators. Production Agent turns always pass `--no-skills`; skills cannot alter calculations, inject external data, or bypass hard gates. Do not install broad browser/search skill packs into the unattended runtime.

## Extensions

Pi packages and extensions can execute arbitrary code. Production Agent turns always pass `--no-extensions` and reject tool activity. The only local extension is the hash-locked, command-only `quant-ops-readonly`, explicitly loaded by the manual operator console with tools, sessions, automatic resources, context files, startup networking, and project trust disabled. It reads operational JSON metadata and never enters the seven-Agent dependency graph.

Third-party extension candidates must be pinned, unpacked without lifecycle scripts, source-reviewed, tested in an external state directory, and independently approved. Installing a package into `.pi/settings.json` or the shared Pi profile is prohibited for this project. Decisions and upstream revisions are recorded in `docs/OPEN_SOURCE_ECOSYSTEM_REVIEW.md`.
