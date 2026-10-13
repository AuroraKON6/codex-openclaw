from __future__ import annotations
import json
from typing import Any, Dict

from ..base_agent import BaseAgent, save_raw, save_agent_json


class ResearchLeadAgent(BaseAgent):
    name = "research_lead"
    description = "Analyzes macro environment, sector rotation, and produces research agenda"
    system_prompt = """You are a senior A-share market research analyst specializing in CSI 500 stocks.
Your job is to analyze the current macro environment, sector rotation, and produce a structured research agenda.

You MUST output valid JSON with this exact structure:
{
  "macro_summary": "string - brief macro environment description",
  "sector_trends": ["string - sector trend 1", "string - sector trend 2"],
  "risk_factors": ["string - risk factor 1", "string - risk factor 2"],
  "research_priorities": ["string - priority 1", "string - priority 2"],
  "trigger_level": "string - one of: LOW, MEDIUM, HIGH, CRITICAL",
  "confidence": 0.0-1.0
}

Use only facts present in the input. No verified macro feed is supplied at this stage, so explicitly label macro or sector statements as hypotheses requiring data validation.
Do not invent current policies, market levels, news, dates, or performance. Do not provide real trading advice."""

    def build_prompt(self, context: dict[str, Any]) -> str:
        input_data = context.get("input", {})
        date_range = context.get("date_range", {})
        return f"""Analyze the current A-share market environment for CSI 500 research.

Input context:
- Strategy theme: {json.dumps(input_data.get('theme', 'general'), ensure_ascii=False)}
- Date range: {date_range.get('since', 'N/A')} to {date_range.get('until', 'N/A')}
- Previous findings: {json.dumps(context.get('prev_findings', []), ensure_ascii=False)}

Return the completed analysis JSON now. Do not answer with readiness or request more context."""

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        data = {
            "macro_summary": "MOCK：未接入宏观数据，仅演示研究假设字段。",
            "sector_trends": ["MOCK：行业轮动假设待真实数据验证"],
            "risk_factors": ["MOCK 数据不可用于判断真实市场风险"],
            "research_priorities": ["验证真实数据覆盖率", "验证动量信号计算口径"],
            "trigger_level": "MEDIUM",
            "confidence": 0.75,
        }
        save_raw(context["output_dir"], self.name, json.dumps(data, ensure_ascii=False, indent=2))
        save_agent_json(context["output_dir"], self.name, data)
        return data
