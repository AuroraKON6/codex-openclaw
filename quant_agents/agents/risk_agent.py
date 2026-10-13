from __future__ import annotations
import json
from typing import Any, Dict, List

from ..base_agent import BaseAgent, save_raw, save_agent_json


class RiskAgent(BaseAgent):
    name = "risk_agent"
    description = "Evaluates strategy risk metrics and produces risk assessment"
    system_prompt = """You are a risk management specialist for A-share quantitative strategies.
Evaluate the strategy and backtest results to produce a comprehensive risk assessment.

You MUST output valid JSON:
{
  "overall_risk_level": "string - LOW/MEDIUM/HIGH/CRITICAL",
  "risk_score": 0.0-1.0,
  "risk_factors": [
    {
      "factor": "string",
      "severity": "string - LOW/MEDIUM/HIGH",
      "description": "string",
      "mitigation": "string"
    }
  ],
  "concentration_risk": "string",
  "liquidity_risk": "string",
  "market_regime_risk": "string",
  "simulation_validation_limits": {
    "single_name_weight_cap": number,
    "sector_weight_cap": number,
    "minimum_liquidity_coverage": number
  },
  "stress_tests_required": ["string"],
  "warnings": ["string"]
}

All limits are backtest validation assumptions only. Do not recommend positions, stops, hedges, or market actions."""

    def build_prompt(self, context: dict[str, Any]) -> str:
        strategy = context.get("agent_outputs", {}).get("strategy_agent", {})
        backtest = context.get("agent_outputs", {}).get("backtest_agent", {})
        research = context.get("agent_outputs", {}).get("research_lead", {})
        return f"""Evaluate risk for this CSI 500 strategy:

Strategy: {json.dumps(strategy, ensure_ascii=False, default=str)[:1500]}
Backtest: {json.dumps(backtest, ensure_ascii=False, default=str)[:1500]}
Research: {json.dumps(research, ensure_ascii=False, default=str)[:1000]}

Return the completed risk assessment JSON now. Base all numeric claims on the supplied deterministic backtest. Do not cite current events not present in the inputs."""

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        data = {
            "overall_risk_level": "MEDIUM", "risk_score": 0.45,
            "risk_factors": [
                {"factor": "数据真实性", "severity": "HIGH", "description": "MOCK 模式未使用真实行情", "mitigation": "真实模式下复核 Tushare 快照和覆盖率"},
                {"factor": "模型偏差", "severity": "MEDIUM", "description": "合成指标不能代表历史表现", "mitigation": "使用确定性引擎和点时数据重跑"},
            ],
            "concentration_risk": "MOCK：未测量",
            "liquidity_risk": "MOCK：未测量",
            "market_regime_risk": "MOCK：未测量",
            "simulation_validation_limits": {"single_name_weight_cap": 0.05, "sector_weight_cap": 0.2, "minimum_liquidity_coverage": 0.9},
            "stress_tests_required": ["交易成本翻倍", "流动性覆盖下降", "因子拥挤反转"],
            "warnings": ["所有风险字段均为 MOCK 验收内容"],
        }
        save_raw(context["output_dir"], self.name, json.dumps(data, ensure_ascii=False, indent=2))
        save_agent_json(context["output_dir"], self.name, data)
        return data
