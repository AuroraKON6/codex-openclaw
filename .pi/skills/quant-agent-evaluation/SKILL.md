---
name: quant-agent-evaluation
description: Build and review regression evaluations for this project's seven Pi and DeepSeek quant-research Agents. Use before changing prompts, schemas, model/runtime settings, orchestration, safety rules, or claiming that real LLM Agents work reliably.
metadata:
  author: quant-research-project
  version: "1.0.0"
---

# Quant Agent Evaluation

This is an interactive Pi operator skill. Evaluate the production no-tools and `--no-skills` contract rather than enabling skills inside business Agent turns.

Measure behavior against an explicit baseline. A successful ping, one valid response, Mock run, or local schema test is not business-Agent reliability evidence.

1. Define the exact change, affected Agent contracts, baseline revision, provider/model, prompt hashes, runtime flags, dataset cutoff, sample size, repeats, cost ceiling, and release threshold before running evaluations. Change one independent variable at a time.
2. Build cases from real run traces, recorded failures, each JSON contract, ambiguous or unavailable-data conditions, prompt-injection attempts inside supplied context, and prohibited real-capital requests. Keep an untouched holdout set.
3. Grade deterministically first: authoritative Pi event, provider/model identity, no tool activity, JSON-only output, schema and type validity, required fields, bounded tokens/time, no secret leakage, no fabricated evidence, and no prohibited trading action.
4. Use a separately identified LLM judge only for semantic criteria that cannot be checked programmatically. Give it an anchored rubric, retain its raw result and usage, and compare it with a human-labeled calibration sample before trusting it.
5. Run enough repeated trials to expose stochastic failures. Report numerator, denominator, repeats, variance or confidence interval, per-case regressions, failure clusters, latency, tokens, cost, and anything not covered. Never present an aggregate score without its configuration.
6. Compare with the committed baseline and list every formerly passing case that regressed. Do not tune on the holdout set or erase failed runs.
7. Require Mock regression plus real Pi contract cases for runtime changes. Require licensed real data separately for claims involving market facts; do not let an LLM evaluation bypass data, compliance, or approval gates.
8. Return `PASS`, `CONDITIONAL`, or `BLOCKED` against predeclared thresholds, with evidence paths and the next corrective experiment. Human review remains required for semantic safety and release approval.

Read [references/evaluation-contract.md](references/evaluation-contract.md) when defining cases, graders, artifacts, or the acceptance report.

For this workspace, return exactly one valid JSON object in the requested schema, with no preface, markdown fence, or trailing commentary. Validate parseability before responding.

Do not enable broker tools, place orders, convert research output into real-capital advice, or call a non-production tool-enabled Agent configuration equivalent to production.
