# Pi Skills governance

## Objective

The current milestone is a controlled skills supply chain for interactive operators, plus project-native backtest assurance and real-Agent evaluation workflows. Production research turns continue to use `--no-skills`, `--no-tools`, ephemeral sessions, and deterministic Python calculations.

## GitHub review on 2026-08-23

| Candidate | Pinned review revision | Decision | Commercial reason |
|---|---|---|---|
| `earendil-works/pi` skills documentation | `c49906ec77788625aacbdc53ebca6fbe65bd20f5` | Format/runtime basis | Pi discovers `.pi/skills`, supports progressive disclosure, and warns that skills may contain executable instructions. |
| `agentskills/agentskills` specification | `69ef37e9424c0a7ea9dd2293b559e43ec8176379` | Format/validation basis | Defines required frontmatter, bounded metadata, resource layout, and progressive disclosure. |
| `wshobson/agents` `backtesting-frameworks` | `367cb6a4a182cf7e9b0a17c9429f7411ddd9cf35` | Adapted, not vendored | Bias, chronological split, walk-forward, cost, and capacity checks are useful; generic worked code does not model CSI 500 membership or effective-dated A-share execution and is therefore not safe to install unchanged. |
| `arjunprabhulal/agent-skills` `agent-evaluation` | `42dd24080fce6d731d00e2a1134f398c3da4171b` | Adapted, not vendored | Baselines, deterministic graders, repeated runs, holdouts, regression reporting, and calibrated judges fit real Pi Agent acceptance. |
| `badlogic/pi-skills` `brave-search` | `90bb51cae36515a648515b633a81c0c6efc8c74d` | Rejected for this project | Requires a new API credential, npm dependencies, executable JavaScript, arbitrary URL retrieval, and produces unlicensed/unfrozen web content outside the production evidence chain. |
| `anthropics/financial-services` idea-generation workflows | `33a3d8a9d6e5c3d4861731933a8857cc5e03315d` | Rejected unchanged | Primarily US-oriented security idea generation and long/short screening conflict with the CSI 500 scope and no-real-capital-advice boundary. |
| `LLMQuant/skills` | `1918237467c2dff4cc97a18ebc0892dfd46e8129` | Rejected unchanged | Workflows are coupled to a separate LLMQuant Data/MCP evidence contract rather than the licensed Tushare snapshots owned by this project. |
| `HKUDS/Vibe-Trading` | reviewed from GitHub main on 2026-08-23 | Rejected unchanged | Broad market-data fallbacks, MCP tools, broker connectors, and trading workflow surface conflict with the isolated no-tools research runtime. |

No third-party executable code was copied into `.pi/skills`. The two new skills are project-authored adaptations of reviewed methods and include A-share, data-license, audit, and no-advice boundaries.

## Installed operator skills

- `quant-data-governance`: data rights, point-in-time inputs, provenance, and quality.
- `quant-backtest-assurance`: research pre-registration, A-share execution realism, bias, costs, robustness, and reproducibility.
- `quant-agent-evaluation`: baseline and regression evidence for the seven real Pi Agents.
- `quant-run-operations`: runtime, recovery, integrity, drill, and scheduling operations.
- `quant-release-review`: five-role internal research release review.

## Supply-chain gate

`governance/pi_skills.lock.json` pins every installed skill resource by SHA-256 and records upstream review references. `python -m quant_agents skills-audit` fails when a skill is added without review, a locked file changes, a symlink/reparse point appears, an executable resource is present, or the production `--no-skills` boundary is removed.

`check_pi.ps1` runs the skills audit before Pi runtime health. `invoke_pi_skills_acceptance.ps1` then performs repeated real DeepSeek V4 Pro trials with only the `read` tool, explicit hash-locked skill paths, strict JSON/type checks, raw JSONL hashes, token/cost evidence, and a clear contract-only scope. This acceptance mode is not the production business-Agent runtime.

Updating a skill requires review, deterministic validation, hash-lock refresh, tests, and a documented source decision. Never use a branch name or an unpinned URL as supply-chain evidence.

## Pi extensions

Extensions are a separate, higher-risk supply chain because they execute arbitrary code at load time. `governance/pi_extensions.lock.json` currently permits only the project-authored `quant-ops-readonly` command extension. It has no network, subprocess, write, provider, or LLM-tool capability and is loaded only by `open_pi_ops_console.ps1` after `python -m quant_agents extensions-audit` passes.

Production business-Agent turns continue to pass `--no-extensions`; no operator extension can participate in research inference. The GitHub architecture and plugin review, exact commits, rejected candidates, and third-party package intake sequence are documented in `docs/OPEN_SOURCE_ECOSYSTEM_REVIEW.md` and `governance/upstream_references.json`.
