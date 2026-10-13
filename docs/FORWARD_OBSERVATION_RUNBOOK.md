# 前向观察与模型生命周期运行手册

## 边界

前向 campaign 是仓库外、追加式的内部研究账本。它从已批准的精确开发基线开始，只统计登记截止日之后的真实 Tushare 路径，不连接券商、不生成委托、不自动升格为实盘或投资建议。

最终状态最多为 `ELIGIBLE_FOR_INDEPENDENT_VALIDATION`。这只表示可以进入独立复现，不能表示策略有效、商业上线或真实资金获批。

## 启动顺序

1. 真实基线 run 必须满足 clean source、数据授权、外部预注册、实验 Registry 预登记/终态、规则簿、成本校准、真实 Tushare、真实 Pi 7/7、回测/压力、预算和完整性门禁。
2. 执行 `release-prepare`，由数据、量化、模型、平台、合规五方完成内部评审批准。
3. 在仓库外创建 campaign；命令会再次验证 run 完整性和批准文件。

```powershell
python -m quant_agents forward-init `
  --baseline-run .\runs\<baseline-run-id> `
  --approval .\runs\<baseline-run-id>\release\approval_request.json `
  --root D:\controlled\quant\forward-campaigns
```

保存输出中的 `campaign_dir` 和 `campaign_metadata_sha256`。`campaign.json` 是冻结元数据，`observations.jsonl` 是哈希链账本；两者都不得放入 Git。

## 每日前向运行

调度安装必须绑定 campaign：

```powershell
.\install_quant_schedule.ps1 `
  -ApprovedRunDir .\runs\<baseline-run-id> `
  -ApprovalPath .\runs\<baseline-run-id>\release\approval_request.json `
  -ForwardCampaignPath D:\controlled\quant\forward-campaigns\<campaign-dir> `
  -ExperimentRegistryPath $env:EXPERIMENT_REGISTRY_PATH `
  -WhatIf
```

复核 WhatIf 后移除 `-WhatIf`。任务以隐藏窗口、Limited 权限和 `IgnoreNew` 运行，避免交互终端弹出并防止并发重入。

每日 runner 在任何 Tushare/Pi 调用前复验：deployment authorization 哈希和有效期、clean commit、五方批准、实验 Registry 元数据/身份/哈希链、campaign 元数据哈希/身份/账本、外部协议及其他业务门禁。每个真实 run 先追加实验预登记并在收尾时追加终态，之后才执行 `forward-record`；任何账本追加失败都会使任务失败并要求人工处置。

手工命令：

```powershell
python -m quant_agents forward-record --campaign <campaign-dir> --run-dir .\runs\<real-forward-run>
python -m quant_agents forward-status --campaign <campaign-dir>
python -m quant_agents ops-status --runs-root .\runs --experiment-registry $env:EXPERIMENT_REGISTRY_PATH --campaign <campaign-dir> --max-age-hours 36
```

## 计算与防重写

- 每次运行从注册的固定 warm-up 起点重新执行同一确定性 Python 策略，截止日只能向前推进。
- 前向收益、基准、超额、最大回撤、成本和再平衡次数只使用 `baseline_cutoff` 之后的 `equity_curve`。
- 账本保存前向路径前缀哈希；新运行必须复现上一条记录的全部重叠历史。历史行情修订、基线变化或计算漂移会拒绝追加，先调查数据版本，不静默接受。
- 同一观察日、同一路径和指标重复提交为 no-op；同日不同结果硬失败。
- 每条记录绑定 run manifest、输入指纹、源码 commit、数据快照、协议哈希和前一条账本哈希。

## 状态与动作

| 状态 | 含义 | 必须动作 |
|---|---|---|
| `BLOCKED_NO_FORWARD_OBSERVATIONS` | campaign 已建但没有真实记录 | 不能声称完成前向验证 |
| `OBSERVING_MINIMUM_NOT_MET` | 尚未达到预注册交易日或再平衡数 | 继续采集，不改阈值 |
| `CONTINUE_OBSERVATION` | 最小样本达到但晋级阈值未全部通过 | 独立复核原因；继续观察或关闭 |
| `PAUSE_REVIEW_REQUIRED` | 回撤/超额暂停阈值触发 | 停止自动依赖，调查模型、数据、成本和制度变化 |
| `ELIGIBLE_FOR_INDEPENDENT_VALIDATION` | 冻结阈值通过 | 由独立团队从源码、原始数据和协议重新复现；仍不授权交易 |
| `RETIRED` / `CLOSED_NO_PROMOTION` | 三方外部关闭证据生效 | 禁止再追加，保留账本和归档 |

关闭命令要求仓库外决定文件、三名不同的模型/合规/平台批准人及支持原件哈希：

```powershell
python -m quant_agents forward-close --campaign <campaign-dir> --decision D:\controlled\quant\closure-v1.json
```

## 真实交易隔离

[证监会《证券市场程序化交易管理规定（试行）》](https://www.csrc.gov.cn/csrc/c100028/c7480577/content.shtml) 自 2024-10-08 实施，程序化交易涉及先报告后交易、证券公司客户管理、实时监控、风控和信息系统要求。本项目没有交易账户、券商接入或订单路由；未来若考虑真实程序化交易，必须新建独立受监管项目完成适用性法律意见、券商报告/接入、交易前风控、异常监控、灾备和授权，不能从本 campaign 直接切换。
