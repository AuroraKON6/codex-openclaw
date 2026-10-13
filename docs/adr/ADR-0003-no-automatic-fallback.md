# ADR-0003：不做自动 provider/model/数据回退

- 状态：已接受
- 日期：2026-09-06
- Owner：平台负责人 + 模型负责人
- 复审触发：组织级多 provider 冗余方案出现；operator 开始系统性绕过失败流程的迹象
- 关联：`run_quant_agents.ps1`、`run_daily_research.ps1`、`quant_agents/pi_client.py`、`data_client.py`、蓝图 §14.7

## 背景

供应商故障时"自动换模型""用旧快照顶上""失败后自动重跑"会造成不可比结果并掩盖事故。研究可信度要求每一次失败都被显式处置并留证。

## 决策

- DeepSeek 不可用：run 失败并 finalize，不自动更换 provider 或模型。
- Tushare 不可用：run 失败并 finalize，不用旧快照冒充新数据；研究输入要求 freshness lag 为 0。
- 调度失败：不自动重跑；operator 必须显式传 `-RetryOf`，且必须指向同一 request 的最新失败 run（`run_daily_research.ps1` 强校验）。
- Mock 永不自动顶替真实：真实模式无 fallback，Mock 必须显式 `-Mock`。
- 修复后的重试一律新 Run ID，经 `request_id`/`retry_of` 关联，失败目录永不复用。

## 替代方案

- 自动 fallback + 事后告警——否决：告警可被忽略，回退本身不可追溯且破坏结果可比性。
- 半自动"一键重试"工具——允许：operator 复盘后显式操作，每步留证；不改变"无自动重试"的边界。

## 后果

- 正面：失败可归因、跨 run 可比、事故不被静默吞掉。
- 负面：可用性下降，恢复依赖人工响应；运营必须接受错过的调度窗口不被自动补跑。
- 中性：DeepSeek 定价 30 天复核与预算门禁独立于本决策继续生效。

## 合规检查

`tests/test_schedule_contract.py` 锁定 runner 不接受隐式重试；`verify_quant_pipeline.ps1` 断言 Mock 必须显式。
