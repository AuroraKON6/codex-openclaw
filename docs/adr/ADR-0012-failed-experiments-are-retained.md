# ADR-0012：失败实验永久保留

- 状态：已接受
- 日期：2026-09-06
- Owner：量化负责人 + 合规负责人
- 复审触发：任何清理/归档策略变更；retention 期限调整；组织 legal hold 变化
- 关联：`quant_agents/orchestrator.py`、`operations.py`、`experiment_registry.py`、`release.py`、蓝图 §22.2

## 背景

选择性保留成功结果是量化研究最大的隐偏；Experiment Registry 与 trial count 的全部价值都建立在"失败也入账"之上。看结果后修改阈值并复用实验 ID 是项目明令禁止的行为，其前提是失败证据不可被抹除。

## 决策

- 失败与中断 run 的目录永不删除、永不原地改写；orchestrator 为失败 run 落盘完整失败审计（state、summary、alerts、manifest、事件链）。
- recover 只把 stale run 标记为 `interrupted`，不原地续跑；修复后的重试必须新 Run ID 并以 `retry_of` 指向旧失败。
- 外部 Registry 对成功、失败、中断一律追加 `FINALIZED`；Registry 历史行永不删除；硬崩溃且无可信 running state 备份时只能 BLOCKED 并升级事件，不允许人工伪造终态。
- retention（默认 365 天）只生成候选计划：删除需同时满足有效归档、恢复复验、期限届满、无 legal hold、人工授权五条件，代码不自动删除。
- 策略候选退役不等于删除：预注册门槛未过、独立复现失败、forward 失败、trial budget 超限等退役路径的证据全部保留（蓝图 §22.2）。

## 替代方案

- 只保留成功 run + 失败摘要——否决：摘要无法支撑独立复现与 trial count 审计。
- 定期清理失败 run——否决：破坏 Registry reconcile 与多重检验控制的数据基础。

## 后果

- 正面：trial count 可信，DSR/PBO 等多重检验控制有数据基础；"谁在何时试过什么"可完整回答。
- 负面：磁盘随 run 数量线性增长——由归档与 retention 计划承担，不以删证据换取空间。
- 中性：`ops-status` 的 CRITICAL 时效告警依赖最新真实 run 存在，与保留策略互不冲突。

## 合规检查

`tests/test_operations.py`、`tests/test_experiment_registry.py`、`tests/test_release.py` 锁定失败产物、终态追加与 retention 候选行为。
