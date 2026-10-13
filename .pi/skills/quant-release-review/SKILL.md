---
name: quant-release-review
description: Review Pi-based CSI 500 research runs for controlled internal release readiness. Use when preparing or verifying release candidates, checking five-role approvals, validating no-trading boundaries, archiving accepted runs, or deciding whether a report remains blocked.
---

# Quant Release Review

Review the immutable candidate, not an informal summary.

1. Verify schema version 6, file manifest hashes, event hash chain, input fingerprint, source revision, and absence of unmanifested material changes.
2. Require `runtime=pi`, pinned Pi integrity, no-tools policy, a real DeepSeek V4 Pro ping, seven successful Agent records, and recorded model usage.
3. Require `REAL_TUSHARE`, deterministic metrics, approved license evidence, external protocol registration bound to the exact input and model contract, approved execution-cost evidence, fresh covered data, and a passed operational budget gate.
4. Scan summaries and Agent outputs for prohibited real-capital actions. Keep broker connectivity and external distribution disabled.
5. Prepare the candidate with `python -m quant_agents release-prepare --run-dir <run>`. Do not alter artifacts after candidate creation.
6. Require distinct approvals from data owner, quant owner, model owner, platform owner, and compliance owner. Never invent names, timestamps, evidence, or decisions. Treat local approval files as unauthenticated unless an external identity system supplies evidence.
7. Verify approval and archive only after all gates pass. Verify sidecar, receipt, complete member inventory, safe temporary extraction, restored manifest, event chain, and externally retained SHA-256. An existing ZIP is not trusted automatically.
8. Internal-review approval may initialize a forward campaign but cannot bypass its minimum observation, path-integrity, pause, independent-validation, or closure controls.
9. Retention is plan-only: require elapsed policy period, a verified restorable archive, no legal hold, and separate human deletion authorization. Otherwise return `BLOCKED` with exact blockers, owners, evidence needed, and the next review action.

Approval permits internal research review only. It never authorizes external publication, brokerage integration, orders, or real trading advice.
