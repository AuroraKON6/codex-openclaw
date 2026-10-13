from __future__ import annotations
import json
import os
from typing import Any, Dict, List

from ..base_agent import BaseAgent, save_raw, save_agent_json


class VisualizationAgent(BaseAgent):
    name = "visualization_agent"
    description = "Generates charts and visual summaries for the research report"
    system_prompt = """You are a data visualization specialist for A-share quantitative research.
Given all agent outputs, describe what charts to generate and produce a layout specification.

You MUST output valid JSON:
{
  "charts": [
    {
      "title": "string",
      "type": "string - bar/line/pie/scatter/heatmap",
      "data_source": "string - which agent output to use",
      "description": "string",
      "x_label": "string",
      "y_label": "string"
    }
  ],
  "layout": "string - grid/stack/sidebar",
  "color_scheme": "string",
  "summary_visual": "string - text-based visual summary if charts cannot be rendered"
}

Since we may not have matplotlib available, also provide a TEXT-BASED visual summary."""

    def build_prompt(self, context: dict[str, Any]) -> str:
        agent_outputs = context.get("agent_outputs", {})
        return f"""Design visualizations for this CSI 500 research round:

Available agent outputs:
{json.dumps({k: type(v).__name__ for k, v in agent_outputs.items()}, ensure_ascii=False)}

Detailed data:
- Research: {json.dumps(agent_outputs.get('research_lead', {}), ensure_ascii=False, default=str)[:800]}
- Strategy signals: {json.dumps(agent_outputs.get('strategy_agent', {}), ensure_ascii=False, default=str)[:800]}
- Backtest: {json.dumps(agent_outputs.get('backtest_agent', {}), ensure_ascii=False, default=str)[:800]}
- Risk: {json.dumps(agent_outputs.get('risk_agent', {}), ensure_ascii=False, default=str)[:800]}

Output chart spec as JSON."""

    def execute_pi(self, context: dict[str, Any]) -> dict[str, Any]:
        data = super().execute_pi(context)
        self._try_generate_charts(context, data)
        save_agent_json(context["output_dir"], self.name, data)
        return data

    def _try_generate_charts(self, context: dict[str, Any], spec: dict):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial"]
            plt.rcParams["axes.unicode_minus"] = False
            charts_dir = os.path.join(context["output_dir"], "charts")
            os.makedirs(charts_dir, exist_ok=True)
            backtest = context.get("agent_outputs", {}).get("backtest_agent", {})
            equity_curve = backtest.get("equity_curve", [])
            if equity_curve:
                fig, ax = plt.subplots(figsize=(9, 4.5))
                ax.plot([row["strategy_index"] for row in equity_curve], label="Research strategy")
                ax.plot([row["benchmark_index"] for row in equity_curve], label="Sample benchmark")
                ax.set_title("Research Equity Curve")
                ax.set_xlabel("Trade day")
                ax.set_ylabel("Index (start=1.0)")
                ax.legend()
                fig.tight_layout()
                fig.savefig(os.path.join(charts_dir, "equity_curve.png"), dpi=120)
                plt.close(fig)
            monthly = backtest.get("monthly_returns", [])
            if monthly:
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.bar(range(len(monthly)), [r * 100 for r in monthly], color=["#2ecc71" if r >= 0 else "#e74c3c" for r in monthly])
                ax.set_title("Monthly Returns (%)")
                ax.set_xlabel("Month"); ax.set_ylabel("Return (%)")
                fig.tight_layout(); fig.savefig(os.path.join(charts_dir, "monthly_returns.png"), dpi=100); plt.close(fig)
            strategy = context.get("agent_outputs", {}).get("strategy_agent", {})
            signals = strategy.get("signals", [])
            if signals:
                dirs = {}
                for s in signals:
                    d = s.get("research_classification", "UNKNOWN"); dirs[d] = dirs.get(d, 0) + 1
                if dirs:
                    fig, ax = plt.subplots(figsize=(6, 6))
                    ax.pie(dirs.values(), labels=dirs.keys(), autopct="%1.0f%%", startangle=90)
                    ax.set_title("Research Classification Distribution")
                    fig.tight_layout(); fig.savefig(os.path.join(charts_dir, "signal_distribution.png"), dpi=100); plt.close(fig)
        except Exception:
            pass

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        data = {
            "charts": [
                {"title": "月度收益", "type": "bar", "data_source": "backtest_agent", "description": "模拟月度收益率柱状图"},
                {"title": "研究分类分布", "type": "pie", "data_source": "strategy_agent", "description": "MOCK 研究分类分布饼图"},
            ],
            "layout": "grid", "color_scheme": "professional_blue",
            "summary_visual": "┌─────────────┬──────────┐\n│   指标       │   数值    │\n├─────────────┼──────────┤\n│ 年化收益     │  21.0%   │\n│ 夏普比率     │   1.35   │\n│ 最大回撤     │  -8.2%   │\n│ 胜率         │  62.0%   │\n│ 风险等级     │   MEDIUM │\n└─────────────┴──────────┘",
        }
        self._try_generate_charts(context, data)
        save_raw(context["output_dir"], self.name, json.dumps(data, ensure_ascii=False, indent=2))
        save_agent_json(context["output_dir"], self.name, data)
        return data
