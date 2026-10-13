# Evaluation contract

## Case record

Each case needs a stable ID, Agent ID, purpose, source category, input fixture hash, expected structural assertions, semantic rubric if required, prohibited outcomes, timeout, and cost cap. Mark whether it belongs to development or untouched holdout data.

## Required case families

- one normal contract case for every Agent role;
- missing, stale, conflicting, and explicitly unavailable evidence;
- malformed or oversized context at the Python boundary;
- prompt injection embedded in purported source material;
- requests for security-level buying, selling, sizing, timing, brokerage, or guaranteed returns;
- provider, model, tool, JSON, timeout, and partial-run drift;
- repeated identical inputs to measure nondeterminism and contract stability.

## Grading order

1. Reject incomplete Pi JSONL or a non-authoritative final assistant event.
2. Reject provider/model mismatch, tool activity, non-ephemeral state, or missing usage identity.
3. Parse exactly one JSON object and validate the role schema and types.
4. Apply deterministic safety, evidence, token, latency, and cost checks.
5. Apply calibrated semantic grading only to the remaining open criteria.
6. Preserve all raw inputs, events, outputs, grader versions, decisions, and hashes.

## Acceptance report

The report must identify the source revision, Pi package/integrity, DeepSeek model, prompt and schema hashes, data class (`MOCK`, `CONTRACT_ONLY`, or `LICENSED_MARKET_DATA`), case count, repeats, pass rate, uncertainty, baseline delta, regressions, failure clusters, spend, not-covered scope, and decision. A real model with mock data remains Mock research; a contract-only run does not prove market analysis quality.
