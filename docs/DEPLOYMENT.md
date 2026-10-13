# Pi 部署与迁移

## 隔离布局

- 源码：`E:\闲鱼\codex openclaw`
- 依赖：`pi_runtime/node_modules/`
- 锁文件：`pi_runtime/package-lock.json`
- Pi 可写状态：`.cache/pi-agent/`
- 交互式 skills：`.pi/skills/`
- 研究产物：`runs/`

Pi 采用每次 Agent turn 启动一次本地进程的方式，不需要 Gateway、常驻服务或端口。生产调用显式忽略用户全局 Pi 配置和项目资源，避免与机器上其他 Pi 项目冲突。

## 安装

```powershell
cd "E:\闲鱼\codex openclaw"
.\bootstrap_python.ps1
.\install_pi_runtime.ps1
```

安装使用 `npm ci --ignore-scripts` 和项目锁，只接受 `@earendil-works/pi-coding-agent@0.84.2`、Node `>=22.19.0` 和 `deepseek-v4-pro`。安装回执写入忽略版本控制的 `.cache/pi-agent/install_receipt.json`。

## 配置

从 `.env.example` 创建本机 `.env`，或由 Secret 管理器注入环境变量。关键变量：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL=deepseek-v4-pro`
- `TUSHARE_TOKEN`
- `DATA_LICENSE_EVIDENCE_PATH`
- `RESEARCH_PROTOCOL_EVIDENCE_PATH`
- `EXECUTION_COST_EVIDENCE_PATH`
- `EXPERIMENT_REGISTRY_PATH`（仓库外目录，包含受批准的 `registry.json` 与 `experiments.jsonl`）
- `DEEPSEEK_PRICING_REVIEWED_DATE`、价格费率、预算缓冲倍数、token、Agent/Pipeline 时限和数据新鲜度参数

不要设置 `PI_CLI_PATH` 或 `PI_STATE_DIR`，除非部署系统明确提供受控的测试覆盖。不得用全局 `pi` 替代项目锁定 CLI。

## 验证

```powershell
.\check_pi.ps1 -NoPing
.\check_pi.ps1
.\invoke_pi_acceptance.ps1
.\verify_quant_pipeline.ps1
.\quant.ps1 health --runtime pi --input .\strategy_round.example.json
```

`check_pi.ps1` 的默认调用会产生一次极小的真实 DeepSeek 费用。完整 health 还要求 source、数据许可、外部研究预注册、实验 Registry、执行成本校准和 Tushare；缺失时应失败。价格基线复核超过 30 天也会在真实外部调用前失败。

离线模型目录检查在 Windows 上使用独立的 `PI_METADATA_TIMEOUT_SECONDS=60`；偶发超时先按原命令串行重试并保留失败记录，不得通过跳过模型目录检查进入真实 run。

## 旧运行时退出

先完成 Pi 安装、真实 ping 和 Mock 全回归，再运行：

```powershell
.\disable_legacy_openclaw.ps1 -WhatIf
.\disable_legacy_openclaw.ps1
```

脚本只处理两个精确命名的旧计划任务，不删除 profile、不杀死全部 Node 进程。若 18790 仍被监听，脚本报告人工阻断；必须核对进程所有者和命令行后单独处理。

保留外部 profile 作为短期只读回滚证据，不再从本仓库启动。观察期结束后，由平台负责人按组织变更单清理外部状态和密钥。

## 调度

只有真实 7/7、完整性、缓冲后预算、数据许可、外部预注册、实验 Registry 终态复验、执行成本校准、clean source 和五方审批全部通过，并已创建仓库外前向 campaign 后，才能预览并安装：

```powershell
.\install_quant_schedule.ps1 -ApprovedRunDir <run> -ApprovalPath <approval.json> -ForwardCampaignPath <campaign> -ExperimentRegistryPath $env:EXPERIMENT_REGISTRY_PATH -WhatIf
.\install_quant_schedule.ps1 -ApprovedRunDir <run> -ApprovalPath <approval.json> -ForwardCampaignPath <campaign> -ExperimentRegistryPath $env:EXPERIMENT_REGISTRY_PATH
.\check_quant_schedule.ps1
```

调度使用独立 request ID、`IgnoreNew`、隐藏窗口和显式失败；不允许 Mock fallback。authorization 固定真实批准 run、candidate、审批文件哈希、源码 commit、Pi/V4 Pro、实验 Registry 路径/身份/元数据哈希、campaign 身份/元数据哈希和失效时间；任何漂移都在外部 API 前阻断。每日 run 的实验预登记/终态或前向账本追加失败时任务仍失败，禁止漏记。

## 备份与保留

```powershell
.\backup_quant_runs.ps1 -RunDir <run> -ArchiveRoot <controlled-path>
.\quant.ps1 verify-archive --archive <zip> --expected-sha256 <sha256>
.\plan_quant_retention.ps1 -ArchiveRoot <controlled-path>
```

每次备份都生成 SHA-256 sidecar 和结构化 receipt，并实际解压到安全临时目录复验 run manifest、事件链和全部成员清单。已存在 ZIP 也必须重新验证。保留计划默认 365 天、识别 `operations/legal_hold.json` 或 `release/legal_hold.json`，且永不自动删除。

## 回滚

代码回滚必须恢复对应 Git tag、`package-lock.json` 和模型批准记录，并用新的 Run ID 完整重验。不要混用新代码、旧 Pi 依赖或旧研究产物。旧 Gateway 仅可在明确批准的回滚变更中恢复，不能与 Pi 生产调度并行。
