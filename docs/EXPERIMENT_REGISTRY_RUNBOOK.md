# 实验登记账本运行手册

## 目的与边界

本项目借鉴 Microsoft Qlib 的 Experiment/Recorder 分层：一个组织 Registry 管理多个研究实验，每个 `run_id` 对应一条预登记和一条终态记录。实现不引入 Qlib、MLflow 或在线交易模块，而是在仓库外保存 `registry.json` 与 `experiments.jsonl`，把成功、失败和中断实验统一纳入审计。

账本采用应用层追加写、进程互斥、逐行 SHA-256 和前序哈希链。它能发现历史行被修改、删除、插入、重排或跨 Registry 混用，但不是 WORM 介质、可信时间戳、数字签名或组织身份认证。生产组织仍需在自己的记录系统和受控归档中保存原件。

本账本只覆盖内部研究实验，不连接券商、不授权真实交易、不允许外部分发，也不提供真实资金买卖建议。

## 商业责任顺序

1. 量化负责人确认实验分类只包含 `development_backtest` 与 `forward_observation_refresh`。
2. 独立模型验证人确认失败、中断、无显著结果和阈值未通过的实验同样必须登记。
3. 平台负责人确定仓库外受控目录、备份、365 天以上留存、访问控制和恢复流程。
4. 合规负责人确认 Registry 仅限内部研究，`live_execution_authorized=false`、`external_distribution_authorized=false`。
5. 四名不同责任人在组织系统批准，导出记录和支持原件；不得在仓库示例中填写虚构人员或批准。
6. 平台负责人初始化本地投影并记录 `registry.json` SHA-256；初始化后不得用编辑器修改账本历史。

## 初始化

先在仓库外准备支持原件和证据 JSON。可将 `governance/experiment_registry_evidence.example.json` 复制到受控目录后填写；仓库内示例本身永远不是批准证据。

```powershell
$document = 'D:\controlled\quant\registry\organization-registry-export.pdf'
(Get-FileHash -LiteralPath $document -Algorithm SHA256).Hash.ToLowerInvariant()

python -m quant_agents experiment-init `
  --evidence D:\controlled\quant\registry\experiment-registry-evidence-v1.json `
  --root D:\controlled\quant\experiment-registry

$env:EXPERIMENT_REGISTRY_PATH = 'D:\controlled\quant\experiment-registry'
python -m quant_agents experiment-status `
  --registry $env:EXPERIMENT_REGISTRY_PATH `
  --runs-root .\runs
```

初始化硬校验：证据和支持原件均在仓库外、日期当前有效、留存期不短于项目策略、四个角色由不同人员批准、批准引用不同、文件哈希一致、安全边界全部为 `false`。已有 Registry 只能用同一证据幂等读取，不能覆盖成另一身份。

## 真实运行顺序

真实流水线固定为：

1. clean source revision；
2. 数据许可；
3. 精确输入/模型契约绑定的研究协议；
4. 向外部实验账本追加 `RESERVED`；
5. A 股规则和执行成本证据；
6. 配置、Tushare health、Pi runtime 与真实 DeepSeek ping；
7. 七 Agent 与确定性回测；
8. 向同一账本追加 `FINALIZED`；
9. 写入 state、summary、operations、manifest 和完整性报告。

因此，成本、凭据、数据、Pi 或 Agent 后续失败不会消失：只要预登记已经成功，失败收尾也会进入账本。Mock 不读写 Registry，并继续禁止发布。

每个 `RESERVED` 绑定：`run_id`、run 目录、request/retry、输入指纹、模型契约、协议、run class、源码提交、用途和前一事件哈希。每个 `FINALIZED` 绑定：流水线状态、Agent 成功/错误数、数据/指标来源、快照、回测与稳健性结论、预算、模型用量、安全边界和结果契约哈希。

## 日常检查

```powershell
python -m quant_agents experiment-status `
  --registry $env:EXPERIMENT_REGISTRY_PATH `
  --runs-root .\runs `
  --stale-hours 4

python -m quant_agents ops-status `
  --runs-root .\runs `
  --experiment-registry $env:EXPERIMENT_REGISTRY_PATH `
  --campaign <仓库外campaign目录> `
  --max-age-hours 36
```

必须检查：`ledger_integrity_ok=true`、没有 `stale_reservation_run_ids`、没有 `unregistered_external_run_ids`，最新真实 run 的 `experiment_registry_gate.status=finalized`，预登记/终态哈希与账本一致。

只读 Pi operator 控制台只显示 run 内保存的 Registry 状态，不会读取仓库外目录，也不能替代 `experiment-status` 的外部账本复验。

## 故障与恢复

| 故障 | 自动行为 | 人工动作 |
|---|---|---|
| Registry 缺失、过期或哈希变化 | 在 Tushare/Pi 前硬失败 | 复核组织记录和受控文件；不得新建临时 Registry 绕过 |
| 预登记后普通门禁失败 | 追加失败终态并生成失败 run | 修复根因后使用新 Run ID；原记录保留 |
| 进程中断且存在 stale state | `recover` 标记 `interrupted` 并追加终态 | 核对进程、锁和最后事件；不得原地续跑 |
| 硬崩溃只留下预登记 | `experiment-status` 标记 stale reservation | 优先从受控备份恢复原始 running state，再由 `recover` 追加中断终态；没有可信 state 备份时保持 **BLOCKED** 并升级平台/合规事件，当前工具不会允许人工伪造终态 |
| `.append.lock` 遗留 | 所有追加拒绝 | 先确认原 PID/主机已退出并保存锁证据，再按变更单移除；系统不会自动抢锁 |
| 历史行修改/删除/重排 | 哈希或序号链失败，发布/监控阻断 | 隔离介质、从受控备份恢复、开展审计；不得重新计算哈希掩盖事件 |

## 发布与调度

`release-prepare`、`release-verify`、前向 `record` 和生产 `ops-status` 都会重新读取 `EXPERIMENT_REGISTRY_PATH`，而不是只相信 run 内状态。调度 authorization 额外绑定 Registry 绝对路径、Registry ID 和 `registry.json` SHA-256；任何漂移都会在 Tushare/Pi 前失败。

```powershell
.\install_quant_schedule.ps1 `
  -ApprovedRunDir <真实已批准run> `
  -ApprovalPath <approval.json> `
  -ForwardCampaignPath <仓库外campaign目录> `
  -ExperimentRegistryPath $env:EXPERIMENT_REGISTRY_PATH `
  -WhatIf
```

参考实现来源：[Microsoft Qlib Recorder 官方文档](https://github.com/microsoft/qlib/blob/main/docs/component/recorder.rst)。本项目只采用实验管理概念，未复制其代码、数据或交易实现。
