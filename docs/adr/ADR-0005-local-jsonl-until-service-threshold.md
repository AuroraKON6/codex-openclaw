# ADR-0005：Registry 与事件账本先用本地 JSONL，达阈值再服务化

- 状态：已接受
- 日期：2026-09-06
- Owner：平台负责人
- 复审触发：出现第二个并发写者；run 总量接近 1000；组织要求集中审计导出或 IAM 集成
- 关联：`quant_agents/experiment_registry.py`、`operations.py`、蓝图 §13.4

## 背景

单机、单写者、单项目阶段引入数据库或 MLflow 属于过度建设；但并发写入、跨项目共享或组织审计需求出现时，本地 JSONL 会成为冲突点。需要预先写明升级条件，避免既过早建设又临时仓促迁移。

## 决策

实验 Registry 采用仓库外 `registry.json` + `experiments.jsonl` + 应用层哈希链 + append lock；run 事件链采用 `operations/events.jsonl`。此形态服务至出现下列任一条件：多 operator 并发写、跨项目共享、组织 IAM 审批需求、run 总量超过 1000 或审计查询困难、需要集中备份/WORM。达到阈值后建设 Registry 服务（append-only event API、幂等并发控制、数据库审计日志、签名身份）。在此之前不引入 MLflow 等作为真相源，只允许学习其概念模型。

## 替代方案

- 立即上数据库——否决：单机无并发收益，凭空增加运维面。
- 立即上 MLflow——否决：真相源必须等 IAM 与存储边界清楚后做 build-vs-buy。

## 后果

- 正面：零额外依赖、可 diff、易备份，审计面与代码同构。
- 负面：哈希链不是 WORM 或可信时间戳（见 ADR-0010）；大规模查询低效。
- 中性：schema 升级走 run schema 版本化（当前为 7），Registry 结构变化同样版本化推进。

## 合规检查

`tests/test_experiment_registry.py`、`tests/test_operations.py` 锁定追加、幂等与篡改检测行为。
