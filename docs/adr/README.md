# 架构决策记录（ADR）索引

本目录按 `PROJECT_GM_STRATEGY_BLUEPRINT.md` 第 27 节建立，记录项目最核心、最长周期的架构决策。每条 ADR 一旦"已接受"即视为对后续所有工程与经营选择的约束；推翻一条 ADR 必须写新 ADR 并显式标注取代关系，不允许静默偏离。

## 索引

| ADR | 决策 | Owner | 状态 |
|---|---|---|---|
| [ADR-0001](ADR-0001-python-remains-authoritative.md) | Python 保持唯一业务权威层 | 项目总经理 | 已接受 |
| [ADR-0002](ADR-0002-pi-production-no-tools.md) | 生产 Pi turn 永久 no-tools 隔离 | 模型/平台负责人 | 已接受 |
| [ADR-0003](ADR-0003-no-automatic-fallback.md) | 不做自动 provider/model/数据回退 | 平台/模型负责人 | 已接受 |
| [ADR-0004](ADR-0004-evidence-stays-outside-repository.md) | 商业证据与凭据永不入库 | 合规/平台负责人 | 已接受 |
| [ADR-0005](ADR-0005-local-jsonl-until-service-threshold.md) | Registry 与事件账本先用本地 JSONL | 平台负责人 | 已接受 |
| [ADR-0006](ADR-0006-no-broker-or-live-execution.md) | 永不在本项目建立券商/订单/真实资金能力 | 项目总经理/合规 | 已接受 |
| [ADR-0007](ADR-0007-data-provider-abstraction-deferred.md) | 数据供应商抽象化推迟到研究工厂阶段 | 数据负责人 | 已接受 |
| [ADR-0008](ADR-0008-mock-never-releaseable.md) | Mock 永不可发布 | 平台/量化负责人 | 已接受 |
| [ADR-0009](ADR-0009-operator-plugins-never-production.md) | operator 插件永不进入生产 turn | 平台/模型负责人 | 已接受 |
| [ADR-0010](ADR-0010-identity-and-worm-are-external-services.md) | 身份认证与不可变存储是外部组织服务 | 合规/平台负责人 | 已接受 |
| [ADR-0011](ADR-0011-model-changes-require-eval-and-approval.md) | 模型/提示词变更必须走评估与审批 | 模型负责人 | 已接受 |
| [ADR-0012](ADR-0012-failed-experiments-are-retained.md) | 失败实验永久保留 | 量化/合规负责人 | 已接受 |

## 书写规则

- 每条 ADR 必须包含：背景、决策、替代方案、后果、Owner、日期、复审触发。
- 措辞必须可执行：写"系统必须/必须不做"，不写"建议考虑"。
- 与代码冲突时以代码为准并立即修订 ADR 或开新 ADR；两者矛盾超过一个回归周期视为流程失败。
- 引用代码时只写到模块/常量级（如 `quant_agents/pi_client.py` 的 `PI_CHILD_ENV_ALLOWLIST`），不写行号，避免漂移。

## 建立记录

- 2026-09-06：按蓝图第 27 节清单一次性建立 ADR-0001 至 ADR-0012，全部标记"已接受"，依据为当时已落地的代码与测试证据（172 项单测通过）。
