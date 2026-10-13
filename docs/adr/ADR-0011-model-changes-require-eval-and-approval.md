# ADR-0011：模型/提示词变更必须走评估与审批，禁止目录驱动升级

- 状态：已接受
- 日期：2026-09-06
- Owner：模型负责人
- 复审触发：Pi/DeepSeek 版本公告；repair-turn 率或 contract 失败率超阈值；安全语言命中异常
- 关联：`quant_agents/config.py`、`pi_client.py`、`pi_runtime/package-lock.json`、蓝图 §12.4、§12.5

## 背景

provider 目录出现新模型、或 Pi 发布新版本，都不构成升级理由。跨 run 可比性是研究可信度的前提：不可比的新结果比旧模型更危险。运行时已通过版本与 integrity 锁定强制这一点，需要以 ADR 固化变更流程。

## 决策

- 运行时锁定：`pi_runtime/package-lock.json` 固定 `@earendil-works/pi-coding-agent@0.84.2` 与 integrity；Config 精确校验包名、版本与 lock 哈希；模型精确匹配 `deepseek-v4-pro`；目录检查失败即硬失败。不得改成 `latest`。
- 任何模型/提示词变更必须走蓝图 §12.5 流程：离线 contract eval → unsupported-claim eval → 交易语言安全 eval → 固定快照回归 → 成本/时延 eval → shadow canary → 独立审批 → tagged rollout → 生产监控 → 越界即回滚。
- 变更后：`docs/DEPLOYMENT_ACCEPTANCE.md` 记录新证据，全量契约回归（含跨脚本契约测试）重跑通过。
- 未来建立 Prompt/Model Registry（蓝图 §12.4），每个 Agent 登记 prompt version、模板哈希、eval suite、canary 与 rollback 版本。

## 替代方案

- 跟随 provider 自动更新——否决：破坏历史 run 可比性与预算基线。
- 永不变更——不可持续：供应商终将下线旧版本；届时走同一流程换版，而非破例。

## 后果

- 正面：所有历史 run 可与模型版本对齐；成本基线稳定可审计。
- 负面：新模型能力引入滞后——有意为之。
- 中性：pricing 30 天复核（`DEEPSEEK_PRICING_REVIEWED_DATE`）独立于版本变更继续生效。

## 合规检查

`tests/test_pi_client.py` 锁定版本/模型/integrity 校验；`tests/test_config.py` 锁定 pricing 基线字段。
