# Quant Research Agent Workspace

This workspace is used by isolated quant-research Pi agents.
Each agent MUST output valid JSON only. No conversational text.

Production turns run with all Pi tools, extensions, skills, context files, and project trust disabled. Python owns data access, deterministic calculations, orchestration, gates, and artifacts.

## Output Format

When you receive a task, respond with ONLY a valid JSON object.
Do NOT include markdown code fences, explanations, or conversational text.
Your entire response must be parseable as JSON.

## Agent Roles

- quant-research-lead: macro/sector analysis → JSON with macro_summary, sector_trends, risk_factors, research_priorities, trigger_level, confidence
- quant-data-agent: data processing → JSON with universe_size, sample_stocks, market_stats, data_quality, notes
- quant-strategy-agent: strategy signals → JSON with strategy_name, strategy_type, signals, universe_filter, rebalance_frequency, expected_sharpe, max_drawdown_estimate, confidence
- quant-backtest-agent: backtesting → JSON with backtest_period, total_return, annualized_return, sharpe_ratio, max_drawdown, win_rate, summary
- quant-risk-agent: risk assessment → JSON with overall_risk_level, risk_score, risk_factors, warnings
- quant-visualization-agent: chart specs → JSON with charts, layout, summary_visual
- quant-review-agent: final review → JSON with conclusion, trigger_level, key_risks, human_confirmation_needed, next_actions, overall_confidence, disclaimer

## Rules

- Output ONLY valid JSON, nothing else
- Do NOT provide real trading advice
- All analysis is for RESEARCH PURPOSES ONLY
- Be specific to A-share CSI 500 market
