from __future__ import annotations
import json
from typing import Any, Dict, List

from ..base_agent import BaseAgent, save_raw, save_agent_json


class ReviewAgent(BaseAgent):
    name = "review_agent"
    description = "Reviews all outputs and produces final summary with conclusions"
    system_prompt = """You are a senior quantitative research reviewer.
Review all agent outputs for a CSI 500 research round and produce a final comprehensive summary.

You MUST output valid JSON:
{
  "conclusion": "string - key conclusion in 2-3 sentences",
  "trigger_level": "string - LOW/MEDIUM/HIGH/CRITICAL",
  "key_risks": ["string"],
  "human_confirmation_needed": ["string - items that need human review"],
  "next_actions": ["string - recommended next steps"],
  "overall_confidence": 0.0-1.0,
  "data_quality_score": 0.0-1.0,
  "strategy_quality_score": 0.0-1.0,
  "disclaimer": "string - must include that this is NOT real trading advice"
}

Be concise but thorough. Flag inconsistencies and distinguish measured facts from LLM interpretation.
next_actions may contain only data checks, model validation, stress tests, documentation, or human approval tasks.
Order gated actions as: reviewed private source baseline; named roles and approved budget; external data/protocol/registry/cost evidence; explicit human G1 decision; only then protected credentials and paid provider acceptance; then the first real baseline.
Never recommend configuring credentials, calling real data, or making paid model calls before their prerequisite human gate is approved.
Never recommend buying, selling, exposure changes, positions, stops, hedges, or real trading."""

    def build_prompt(self, context: dict[str, Any]) -> str:
        agent_outputs = context.get("agent_outputs", {})
        input_data = context.get("input", {})
        review_parts = []
        for name, output in agent_outputs.items():
            review_parts.append(f"=== {name} ===\n{json.dumps(output, ensure_ascii=False, default=str)[:1000]}")
        return f"""Review this CSI 500 research round:

Input theme: {input_data.get('theme', 'N/A')}
Date range: {context.get('date_range', {})}

Agent outputs:
{chr(10).join(review_parts)}

Return the completed final review JSON now. If any upstream agent failed, set trigger_level HIGH or CRITICAL and require human review."""

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        data = {
            "conclusion": "MOCK 流水线 7 个 Agent 已完成结构化输出验收。所有行情、信号和绩效均为合成数据，不得解释为真实市场结论。",
            "trigger_level": "CRITICAL",
            "key_risks": ["未使用真实 Tushare 数据", "未调用真实 Pi LLM", "合成回测指标不可用于研究判断"],
            "human_confirmation_needed": ["数据覆盖率是否满足研究准入标准", "回测偏差与成本假设是否已独立复核", "是否批准进入下一轮离线验证"],
            "next_actions": [
                "先由 Platform/Security 逐文件复核源码候选，批准后建立最小权限私有 Git clean commit/tag",
                "任命九个治理角色并批准试运行预算",
                "在仓库外完成数据授权、研究预注册、实验 Registry 和执行成本四类证据",
                "全部前置项通过后由 Gate Owner 记录 G1 GO/NO-GO；G1 批准前不得配置或调用真实 Tushare/付费 Pi",
                "仅在 G1 GO 后通过受控 Secret 配置凭据并执行付费 Pi/Tushare acceptance，再生成首个真实 7/7 baseline",
            ],
            "overall_confidence": 0.72, "data_quality_score": 0.8, "strategy_quality_score": 0.75,
            "disclaimer": "本报告仅供研究参考，不构成任何真实资金买卖建议。所有数据为模拟数据，不代表真实市场表现。",
        }
        save_raw(context["output_dir"], self.name, json.dumps(data, ensure_ascii=False, indent=2))
        save_agent_json(context["output_dir"], self.name, data)
        return data
