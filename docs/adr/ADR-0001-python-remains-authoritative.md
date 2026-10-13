# ADR-0001：Python 保持唯一业务权威层

- 状态：已接受
- 日期：2026-09-06
- Owner：项目总经理（A）；量化负责人 + 平台负责人（R）
- 复审触发：任何把权威计算迁出 Python 的提案；Agent A/B 评估结论；`research_engine` 重大重构
- 关联：蓝图 §1.1、§5.2、§12.2；`quant_agents/orchestrator.py`、`research_engine.py`、`backtest_validation.py`、`contracts.py`

## 背景

项目使用 LLM Agent 生成研究叙述，但若数据质量、信号、绩效、门禁的最终判定由 LLM 给出，结果将不可复现且可被幻觉污染。交接文档与蓝图均已把"Python 权威、Pi 只解释"列为核心边界，需要以 ADR 固化，防止未来以"提升智能"为由侵蚀。

## 决策

数据请求与快照、点时成分、动量信号、回测订单与持仓、费用滑点冲击、绩效指标、数据质量、稳健性、预算与发布生命周期判定的最终权威在 Python 控制面。Pi/DeepSeek 只输出结构化解释、反证和终审 JSON；Agent 返回的指标字段不覆盖 Python 计算结果，输出契约由 `contracts.py` 校验并允许一次独立修复 turn。

## 替代方案

- LLM 直接计算指标——否决：不可复现，且无法审计计算过程。
- LLM 与 Python 双轨互相校验——否决：制造第二真相源，冲突时无仲裁规则。
- 纯 Python 无 LLM——保留为对照基线（蓝图 §12.2 的 deterministic-only 组），用于持续证明 Agent 增量价值；若 A/B 无差异应按 Kill Criteria 裁撤 Agent 而非保留。

## 后果

- 正面：每个指标可复现、可审计、失败可归因；审计链完整。
- 负面：LLM 的贡献被限制在解释层，其增量价值必须独立评估并承担被裁撤的风险。
- 中性：生产 Agent 数量冻结在 7 个；扩张需先通过 §12.2 评估流程。

## 合规检查

本 ADR 与 `verify_quant_pipeline.ps1` 的 Mock 验收断言一致：权威指标只来自 deterministic engine，Mock 的 `NOT_APPLICABLE_MOCK` 语义由 Python 侧写入 state/manifest。
