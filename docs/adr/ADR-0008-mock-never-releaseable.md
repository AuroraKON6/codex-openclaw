# ADR-0008：Mock 永不可发布

- 状态：已接受
- 日期：2026-09-06
- Owner：平台负责人 + 量化负责人
- 复审触发：任何把 Mock 用作演示、对外材料或"临时发布"的请求（直接否决）
- 关联：`quant_agents/release.py`、`orchestrator.py`、`verify_quant_pipeline.ps1`、蓝图 §3.3

## 背景

Mock run 证明控制流与产物完整性，极易被误叙述为市场证据。项目最高判断标准要求任何"完成"必须写明 real/mock；需要以机器可验证的方式让 Mock 永远不可能进入发布通道。

## 决策

- `release.py` 对 mock run 硬阻断（退出码 3），blockers 明确列出 "mock runs are never releaseable"。
- state、manifest 携带显式 `MOCK` 与 `NOT_APPLICABLE_MOCK` 语义字段；回测 assurance、稳健性、三类商业门禁在 Mock 下均为显式 not-applicable，而非留空。
- `verify_quant_pipeline.ps1` 断言上述语义字段与阻断存在，Mock release 阻断是验收的一部分。
- `ops-status` 默认忽略 Mock，生产监控不把 Mock 计入时效。
- forward campaign 只能从批准的真实 baseline 创建；Mock 或失败 run 不得建 campaign。
- 禁止资金动作语言检查对 Mock run 同样生效，防止 Mock 产物成为语言越界的出口。

## 替代方案

- Mock 可发布 + 加水印——否决：水印可删，且语义污染审计面。
- 禁止 Mock——否决：无外部调用的全链路回归是阶段 A 验收与脚本契约测试的基础。

## 后果

- 正面："Mock 7/7"在任何场合都不能被叙述成研究结果；审计语义永远显式。
- 负面：无实质性负面。
- 中性：Mock run 同样保留完整审计产物，作为软件回归证据长期留存。

## 合规检查

`verify_quant_pipeline.ps1` 中 `release gate must block with exit code 3` 断言；`tests/test_release.py` 锁定阻断逻辑。
