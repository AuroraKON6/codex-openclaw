---
name: quant-backtest-assurance
description: Review or design deterministic CSI 500 backtests for point-in-time correctness, A-share execution realism, bias control, costs, robustness, and auditable research conclusions. Use when changing strategy logic, backtest code, factor definitions, execution assumptions, or release evidence.
metadata:
  author: quant-research-project
  version: "1.0.0"
---

# Quant Backtest Assurance

This is an interactive Pi operator skill. Production Agent turns run with `--no-skills`, and Python owns all calculations.

Treat a backtest as a falsifiable research experiment, not as evidence of future returns.

1. Freeze the hypothesis, point-in-time universe rule, factor definitions, dates, rebalance rule, benchmark, execution timestamp, cost schedule, exclusions, acceptance thresholds, and forward pause criteria before execution. Bind the exact input and stable model contract to an external organization research-registry record; an input declaration is not preregistration evidence.
2. Verify that every input was available at the simulated decision time. Require historical CSI 500 membership, effective-dated security attributes, corporate-action handling, trade calendars, suspensions, price limits, risk-warning status, listing state, and source snapshot hashes.
3. Enforce the signal-to-fill boundary. Daily close-derived signals cannot receive the same close. Use the next eligible execution event, preserve unfilled orders, and model A-share sellability and board-specific rules by effective date.
4. Use an effective-dated cost and execution model. Include applicable commission, taxes, transfer fees, spread/slippage, market impact, lot/tick constraints, liquidity participation, and rejected or partial fills. Never insert an unsourced current fee rate.
5. Separate chronological development, validation, and untouched test periods. Record every parameter search, control repeated selection, and use walk-forward or regime tests where the hypothesis requires them. Do not optimize against the final test period.
6. Report coverage, turnover, exposures, concentration, capacity assumptions, missing-data behavior, delisting treatment, drawdown duration, tail outcomes, benchmark-relative results, and sensitivity to costs and timing. A Sharpe ratio alone is insufficient.
7. Reproduce the result from immutable inputs and deterministic code. Python calculates all metrics; the LLM may explain evidence but must not invent figures or overwrite failed gates.
8. After an approved baseline, require fixed-origin forward observation from the registered cutoff. Verify the append-only path hash, reject rewritten overlap, preserve predeclared minimum days/rebalances and pause thresholds, and cap any positive outcome at eligibility for independent validation.
9. Return `PASS`, `CONDITIONAL`, or `BLOCKED` with exact evidence, unresolved assumptions, affected metrics, responsible reviewer, and the next validation action.

Read [references/a-share-execution-gates.md](references/a-share-execution-gates.md) whenever execution, costs, fills, board rules, or effective dates are in scope.

For this workspace, return exactly one valid JSON object in the requested schema, with no preface, markdown fence, or trailing commentary. Validate parseability before responding.

Do not produce security-level real-capital actions, brokerage instructions, or claims of production readiness from backtest results.
