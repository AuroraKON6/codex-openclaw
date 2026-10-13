---
name: quant-data-governance
description: Validate CSI 500 quant-research data licensing, provenance, point-in-time coverage, freshness, and quality gates. Use when reviewing DATA_LICENSE_EVIDENCE_PATH, Tushare inputs, saved market snapshots, governance failures, or whether data may enter an internal research run.
---

# Quant Data Governance

Apply gates in this order and stop at the first failed hard gate.

1. Read the run input and identify `intended_use`, organization, date range, required interfaces, retention, and external-distribution setting.
2. Validate the referenced license evidence without printing credentials or copying confidential contracts into the repository.
3. Require signed evidence whose SHA-256, validity dates, legal entity, internal-use right, derivative-data right, caching/retention terms, and required Tushare interfaces match the run.
4. Require `TUSHARE_TOKEN` only from the process environment or approved secret store. Never place it in code, logs, summaries, manifests, or approval files.
5. Verify point-in-time CSI 500 membership, saved raw responses, request logs, data cutoff, freshness lag, coverage ratios, limit/suspension data, and snapshot hashes.
6. Report `APPROVED` only when every hard gate has machine-verifiable evidence. Otherwise report `BLOCKED`, list missing evidence, responsible role, and the next lawful action.

Do not substitute mock data, cached historical outputs, web search, or LLM assertions for licensed source data. Do not generate real-capital actions or trading recommendations.
