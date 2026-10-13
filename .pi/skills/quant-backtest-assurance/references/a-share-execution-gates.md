# A-share execution gates

Use this checklist for CSI 500 daily-equity research. Reverify the effective rule text before each controlled release; links are evidence pointers, not a permanent rule database.

## Required rule snapshot

Record these fields in the research configuration or source snapshot:

- exchange, board, security status, rule identifier, effective-from date, retrieved-at time, source URL, and content SHA-256;
- permitted session and price source used for the simulated fill;
- buy and sell quantity increments, tick size, daily price-limit regime, first-listing/relisting exceptions, and risk-warning treatment;
- same-day resale or settlement restriction applicable to the security type;
- suspension, no-quote, limit-locked, partial-fill, and order-expiry behavior;
- effective-dated commission, tax, transfer-fee, slippage, impact, and liquidity-participation assumptions.

## Current primary references

- Shanghai Stock Exchange, Trading Rules (2026 revision, effective 2026-07-06): https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml
- Shanghai Stock Exchange explanation of the 2026 changes: https://star.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml
- Shenzhen Stock Exchange, notice publishing the 2026 trading rules (effective 2026-07-06): https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html
- Shenzhen Stock Exchange, 2026 trading-rules PDF: https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf

The current SSE rule text requires auction-trading A-share purchases in lots of 100 shares or integral multiples, permits a residual sub-100-share sale as one order, sets the A-share tick at RMB 0.01, and defines price-limit rules and exceptions. It also states that securities bought before settlement may not be sold unless the instrument is eligible for turnaround trading. Do not generalize those values to every board, instrument, date, or session without checking the applicable rule snapshot.

## Daily-bar minimum model

For a close-derived signal, the earliest default fill is the next eligible bar, never the signal bar's close. A fill must be rejected or deferred when the security is suspended, has no executable quote, is locked at the relevant limit, violates lot/tick constraints, exceeds the predeclared liquidity cap, or cannot legally be sold. Persist the attempted order and reason; silently dropping an unfilled order biases results.

If the data cannot distinguish an executable fill from a touched daily high/low, use a conservative documented rule or block the claim. Never infer queue priority or full liquidity from OHLCV alone.
