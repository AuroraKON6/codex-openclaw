# 运行手册

## 责任顺序

| 顺序 | 责任人 | 动作 | 通过证据 |
|---|---|---|---|
| 1 | 平台 | clean source、依赖锁、凭据扫描 | source provenance release-ready |
| 2 | 数据/合规 | v2 书面组织授权、自动处理/DeepSeek、接口、缓存、留存、终止处置 | license gate organizational scope approved |
| 3 | 量化/独立验证/合规 | 在组织系统冻结假设、精确输入、模型契约、前向阈值和三方批准 | research-protocol gate approved |
| 4 | 量化/独立验证/平台/合规 | 批准仓库外实验 Registry，所有成功/失败/中断 run 先预登记再记终态 | Registry ID、元数据哈希、两阶段账本事件 |
| 5 | 量化/合规 | 有效期交易规则、成本模型、资金规模、参与率和流动性范围 | rulebook hash 和 execution-cost evidence fingerprint |
| 6 | 量化/独立复核 | 冻结临时或历史成本校准基础、限制和复核日 | cost gate approved for internal research |
| 7 | 数据 | Tushare 权限、截止日、覆盖、新鲜度 | health 和 snapshot manifest |
| 8 | 模型/平台 | Pi 版本、Node、无工具策略、V4 Pro ping | Pi preflight checks |
| 9 | 系统 | 7 Agent 依赖顺序、确定性数据与回测 | 7/7、`REAL_TUSHARE`、backtest assurance passed |
| 10 | 平台/模型 | token、供应商回报成本、价格基线、当前高峰2倍预算包络、时限和 alerts | budget passed |
| 11 | 平台 | manifest、事件链、输入指纹 | integrity passed |
| 12 | 五方 | 内部评审审批 | release verified |
| 13 | 模型/平台/独立验证 | 创建前向 campaign、每日追加、防重写、暂停/关闭 | external forward ledger |

## 运行前离线总检

```powershell
cd "E:\闲鱼\codex openclaw"
.\quant.ps1 project-readiness --input .\strategy_round.example.json
.\quant.ps1 project-readiness --input .\strategy_round.example.json --require-ready
```

第一条一次列出全部未满足项，便于总经理和各责任人分派；第二条用于机器门禁，尚未满足人工 G1 评审前置条件时返回退出码 3。两条命令都不访问网络、不调用 Tushare/付费模型、不执行 Pi ping，也不会批准 G1。人工 G1 记录、真实 `health` 和运行前 preflight 仍然不可替代。

## 每次运行

```powershell
cd "E:\闲鱼\codex openclaw"
.\quant.ps1 project-readiness --input .\strategy_round.example.json --require-ready
.\check_pi.ps1
.\quant.ps1 health --runtime pi --input .\strategy_round.example.json
.\run_quant_agents.ps1 -RequestId <受控幂等键>
```

健康检查失败时停止。不得添加 `-Mock` 继续真实作业。需要重试时先审阅最新失败 run，再传同一 `RequestId` 和 `-RetryOf <latest-run-id>`。

## 结果检查

按顺序检查：

1. `state.json`：schema 7、runtime、7/7、data/metrics source、Pi identity、budget、数据许可、研究预注册、实验 Registry 和执行成本 business controls。
2. `operations/alerts.json`：每个 CRITICAL 有责任人和证据编号。
3. `pi_meta/*.json`：版本、provider/model、session/response、usage、attempt、no-tools policy、prompt hash。
4. `market_data/snapshot_manifest.json` 与请求日志：截止日、点时、覆盖、新鲜度和哈希。
5. `backtest/execution_policy.json`、`cost_ledger.json`、`robustness_validation.json`、`backtest_assurance.json`：规则有效期、费用不重复、账本对账、holdout、滚动样本外、压力矩阵和验收通过。
6. `run_manifest.json` 和 integrity report：无缺失、无篡改。
7. `summary.md`：关键结论、触发等级、风险、人工问题、下一步及无真实交易建议。

## 监控

至少监控：pipeline status、Agent success、preflight failures、Pi 的 input/cacheRead/cacheWrite/output token、provider-reported cost、非高峰基础估算、高峰预算包络、budget cost、价格基线复核日、运行时长、数据新鲜度、许可证据、协议 ID/版本/模型契约/证据哈希、实验 Registry ID/预登记/终态/结果契约/未收尾记录、成本模型指纹、滚动样本外通过折数、前向状态/最新 run/账本完整性、source gate、trigger level 和 integrity。`input` 与 `cacheWrite` 按缓存未命中费率、`cacheRead` 按命中费率计价，不得从 `input` 再减一次；成本预警按高峰包络预算的 80% 触发，供应商回报成本更高时始终采用更高值。

```powershell
.\quant.ps1 experiment-status --registry $env:EXPERIMENT_REGISTRY_PATH --runs-root .\runs
.\quant.ps1 ops-status --runs-root .\runs --experiment-registry $env:EXPERIMENT_REGISTRY_PATH --campaign <仓库外campaign目录> --max-age-hours 36
```

默认只选择最新真实 run，不能让更新的 Mock 覆盖生产故障。传入 campaign 后还要求账本完整、协议一致、最新真实 run 已追加且不处于暂停/关闭状态。返回码为 0 只代表研究运行健康；`ELIGIBLE_FOR_INDEPENDENT_VALIDATION` 也不代表上线或资金批准。

## 发布

候选必须同时满足：schema 7、clean source、真实 Pi V4 Pro、no-tools policy、7/7、`REAL_TUSHARE`、v2 组织处理许可、v1 外部预注册、仓库外实验 Registry 预登记和终态复验、v1 执行成本校准、`PASSED` holdout/滚动/压力矩阵、`PASSED_FOR_INTERNAL_RESEARCH` 回测验收、缓冲后预算 passed、完整性 passed、无资金动作语言。

```powershell
.\quant.ps1 verify-run --run-dir <run>
.\quant.ps1 release-prepare --run-dir <run>
.\quant.ps1 release-verify --run-dir <run> --approval <approval.json>
.\quant.ps1 archive-run --run-dir <run> --archive-root <controlled-path>
.\quant.ps1 verify-archive --archive <zip> --expected-sha256 <externally-recorded-sha256>
.\plan_quant_retention.ps1 -ArchiveRoot <controlled-path>
```

ZIP 已存在时不得直接信任：重复归档会重新核对 sidecar、回执、成员清单、CRC、安全路径、恢复后的 manifest 和事件链。保留计划不执行删除；只有期限届满、归档恢复通过、无 legal hold 且人工授权时才列为删除候选。本地 approval JSON 不能证明真实身份。生产审批必须由组织身份系统提供签名、时间和不可抵赖证据。

## 调度授权

```powershell
.\install_quant_schedule.ps1 `
  -ApprovedRunDir <真实已批准run> `
  -ApprovalPath <approval.json> `
  -ForwardCampaignPath <仓库外campaign目录> `
  -ExperimentRegistryPath $env:EXPERIMENT_REGISTRY_PATH `
  -WhatIf
.\check_quant_schedule.ps1
```

先按 `docs/FORWARD_OBSERVATION_RUNBOOK.md` 从批准基线创建 campaign。安装脚本重新验证 run、五方审批、实验 Registry 和 campaign 哈希链，并将任务绑定到源码 commit、candidate、approval SHA-256、Registry ID/元数据 SHA-256、campaign 元数据 SHA-256 和 90 天 authorization。每日 runner 在外部调用前复验全部身份，真实 run 先进入实验 Registry，完成后再追加前向账本；任务动作使用隐藏窗口，避免周期性终端弹出。

## Mock

```powershell
.\verify_quant_pipeline.ps1
```

Mock 验证代码结构、依赖阻断、产物和发布拒绝。它不验证 API、Tushare、市场结论或商业许可，所有 summary 必须明确标记 Mock。
