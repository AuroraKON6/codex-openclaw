# CSI 500 Pi 多 Agent 研究流水线

项目路径：`E:\闲鱼\codex openclaw`。

这是一个面向 A 股中证 500 **内部离线研究** 的可审计流水线。Pi Agent 执行真实 DeepSeek V4 Pro 推理，Tushare 提供获准的市场数据，Python 负责业务顺序、点时数据、确定性信号与回测、预算、审计和发布门禁。

系统没有券商、订单路由或真实资金账户接口，不生成真实资金买卖建议。Mock 只用于软件回归，绝不自动替代真实失败。

## 架构边界

| 层 | 职责 |
|---|---|
| Python orchestrator | 锁、幂等、依赖顺序、数据许可、外部研究预注册、追加式实验登记、执行成本校准、数据采集、确定性计算、预算、manifest、事件链、审批阻断 |
| Pi `0.84.2` | 7 个独立一次性 Agent 推理；只解释、归纳、审查，不计算权威指标 |
| DeepSeek | 固定 `deepseek/deepseek-v4-pro`，API Key 仅从环境读取 |
| Tushare | 获准的 CSI 500 点时成分、行情、估值、涨跌停、停牌和复权数据 |
| 人工治理 | 数据、量化、模型、平台、合规五方审批；外部分发始终关闭 |

生产 Pi turn 使用 JSON mode、stdin、临时会话，并关闭 tools、extensions、skills、prompt templates、themes、context files、项目授权、启动更新和遥测。项目 skills 仅供交互式运维，不会进入生产 Agent turn。

## 环境要求

- Windows PowerShell 5.1+。
- Windows CPython 3.11.x；项目命令只使用隔离的 `.venv`，不使用 PATH 中的全局 Python。
- Node.js `>=22.19.0` 和 npm。
- DeepSeek API Key。
- Tushare Token 及覆盖本项目用途的有效授权证据。
- 与本轮资金规模、参与率、流动性下限和规则簿绑定的执行成本校准证据。
- 在组织系统预先登记且与精确输入、冻结模型契约和前向阈值绑定的研究协议原件。
- 仓库外受控实验 Registry，以及量化、独立模型验证、平台、合规四方批准证据。
- 受控私有 Git 仓库中的 clean commit/tag。

```powershell
cd "E:\闲鱼\codex openclaw"
.\bootstrap_python.ps1
.\install_pi_runtime.ps1
Copy-Item .\.env.example .\.env
```

`requirements.in` 固定三项直依赖，`requirements.txt` 固定 32 个 Windows CPython 3.11 wheel 及 SHA-256；bootstrap 强制 `--require-hashes --only-binary`，执行 `pip check`、程序内 runtime contract 和测试。程序内门禁要求当前解释器必须是项目 `.venv` 中的 Windows CPython 3.11、禁用 user site、全部锁定版本一致且不存在 pip/setuptools/wheel 以外的额外分发包。重新解析依赖先运行 `.\lock_python_dependencies.ps1` 生成忽略目录中的候选，独立复核后才允许显式 `-Apply`。在 `.env` 或受控进程环境配置凭据，不得提交 `.env`、许可证原件或密钥。

## 运行顺序

1. 冻结候选树，重跑 Secret scan、source-candidate 和 source-review packet。
2. Platform 与 Security 在外部组织系统对每个候选文件逐行/逐文件复核，解决全部机器 review flags，并形成两名不同身份的 decision record。
3. 用 `source-review-decision-verify` 校验 decision record；机器通过仍不代表身份认证、Git 授权或 G1 GO。由 Gate Owner/Platform Owner 单独授权后，才创建最小 private clean commit/tag/remote。
4. 数据负责人及法务取得服务商独立书面组织授权，确认商业内部研究、自动 API、缓存、衍生分析、DeepSeek 处理、365 天留存和终止处置，生成 v2 哈希绑定证据。
5. 量化负责人冻结假设、样本、参数、执行与验证阈值；量化、独立模型验证、合规三方在组织系统登记，生成与精确输入和模型契约绑定的 v1 外部预注册证据。
6. 量化、独立模型验证、平台、合规四方批准仓库外实验 Registry；初始化追加式哈希链，要求成功、失败和中断实验全部登记。
7. 量化、独立复核和合规负责人校准佣金、滑点和冲击，绑定规则簿、资金规模、参与率、流动性下限和外部材料哈希，生成 v1 执行成本证据。
8. 在 Secret/进程环境配置四类外部证据路径，再配置 `TUSHARE_TOKEN` 和 `DEEPSEEK_API_KEY`；证据与密钥均不提交仓库。
9. 安装并检查锁定 Pi runtime；在预算和 G1 授权后执行一次真实 DeepSeek V4 Pro ping。
10. 执行完整健康检查，硬顺序为项目 Python runtime → clean source → Secret 回执 → 外部 source-review decision → 数据许可 → 外部研究预注册 → 实验 Registry 检查 → 有效期 A 股规则簿 → 执行成本校准 → 价格/预算配置 → Tushare → Pi runtime/model/ping。
11. 真实 run 在任何 Tushare/Pi 调用前追加实验预登记，执行 7 Agent 后追加终态，再校验 holdout、三折滚动样本外、成本/时滞压力、预算、manifest、事件链和禁止资金动作语言。
12. 准备内部评审候选并完成五方审批；再从精确基线创建仓库外前向 campaign。每日调度只推进冻结截止日并追加防重写账本，不得自动转为真实交易。

## Python 运行时门禁

```powershell
.\quant.ps1 python-runtime --require-ready
```

该命令不访问网络、不修改工作区，输出解释器、`.venv`、user site、锁文件 SHA-256、32 个锁定分发包、版本偏差和额外分发包。`health`、真实 run、Mock run、离线 readiness 和 release candidate 都复用该合同；因此直接调用 PATH 中的 Anaconda/其他 Python 不能生成合格证据。

## 离线项目就绪总览

在任何真实凭据、Tushare 或付费 Pi 调用前，先聚合检查 Python runtime、源码、Secret 回执、四类外部证据、组织角色、预算、provider 配置和最近 Pi 验收：

```powershell
.\quant.ps1 project-readiness --input .\strategy_round.example.json
.\quant.ps1 project-readiness --input .\strategy_round.example.json --require-ready
```

该命令严格离线，不访问网络、不调用数据服务商或付费模型、不执行 Pi ping，也不修改工作区。报告模式始终输出全部检查；`--require-ready` 在尚未具备人工 G1 评审前置条件时返回退出码 3。即使所有机器检查通过，它也只表示“可以提交人工 G1 评审”，不能批准真实 run、发布、交易或真实资金动作。

## 源码候选审查

在任何 `git add` 或 commit 前，先重签 Secret 回执并生成忽略目录中的逐文件候选 manifest：

```powershell
.\quant.ps1 secret-scan
.\quant.ps1 source-candidate --require-reviewable
$packet = .\quant.ps1 source-review-packet | ConvertFrom-Json
.\quant.ps1 source-review-verify --packet-dir $packet.packet_dir
```

候选清单绑定每个文件的路径、类型、大小和 SHA-256，拒绝运行产物、凭据/归档/数据库/可执行文件、二进制、大于 1 MiB 文件、链接/reparse、跨平台路径碰撞、缺失源码和未加哈希的 Python 依赖。`source-review-packet` 只在清单和 Secret 回执身份一致时生成新的不可覆盖审查目录，包含原始 manifest、机器 review request、公式注入防护 CSV、审查说明及逐文件 hash manifest；默认位于忽略目录 `.cache/source-baseline/review-packets/`。`source-review-verify` 会复核固定文件集合、链接/reparse、四个 artifact hash、候选身份、双角色职责分离控制和空白人工决定字段，篡改时退出码为 3。该校验只是应用层哈希一致性，不是数字签名，也不认证审查人。机器通过、packet 生成或校验通过都只表示可以开始 Platform/Security 逐文件人工审查；均不构成 stage、commit、tag、remote 或源码基线授权。

### 外部双人 decision record

packet 之后必须在仓库外完成逐文件 decision record；模板只是空白工作件，不是审批证据：

```powershell
$packet = .\quant.ps1 source-review-packet | ConvertFrom-Json
.\quant.ps1 source-review-decision-template `
  --packet-dir $packet.packet_dir `
  --output D:\controlled\quant\source-review-decision-template.json
```

组织系统或受控副本必须为每个候选文件填写 Platform/Security 两个决定、各自证据编号和备注，并为每个机器 review flag 填写 `RESOLVED`、理由和证据编号。顶层必须绑定 packet ID、candidate manifest SHA-256、candidate files SHA-256、文件数量和完成时间；必须包含恰好 `PLATFORM_REVIEWER` 与 `SECURITY_REVIEWER` 两个不同 `reviewer_subject_id`，两人都声明完整文件数量且决定为 `APPROVED`。所有约束确认项必须为 true，`rejected_files`/`unresolved_files` 必须为空；任何 `REPLACE_`、`TODO`、未来时间、过期记录、哈希不一致或模板状态都会失败。

将完成记录放在仓库外并配置路径后校验：

```powershell
$env:SOURCE_REVIEW_PACKET_DIR = $packet.packet_dir
$env:SOURCE_REVIEW_DECISION_PATH = 'D:\controlled\quant\source-review-decision-v1.json'
.\quant.ps1 source-review-decision-verify `
  --packet-dir $env:SOURCE_REVIEW_PACKET_DIR `
  --decision $env:SOURCE_REVIEW_DECISION_PATH `
  --secret-receipt .\.cache\secret-scan\receipt.json
```

退出码 `0` 只表示当前候选与外部记录结构一致；空白模板或任何不完整记录必须以退出码 `3` 阻断。校验结果明确返回 `organization_identity_verified=false`、`private_baseline_execution_authorized=false`、`source_baseline_authorized=false`。因此仍需人工 Gate Owner/Platform Owner 授权并执行受控 Git 建仓，之后重新生成 source provenance、clean-clone 和全部验收证据。decision 文件不得放入项目目录、`.cache`、run 或源码提交；应用哈希不能替代组织系统签名或身份认证。

## 健康检查

对全部提交候选执行固定规则密钥扫描并生成可复验回执（真实 run preflight 与发布门禁都要求回执有效）：

```powershell
.\quant.ps1 secret-scan
```

发现只记录文件、行号和规则，不回显命中值；确认为测试样例的行可加 `quant-secret-scan-allow` 行内标记并人工复核，回执保留全部命中记录。源码任何变化都会使回执失效并要求重扫。

仅验证 Pi，并执行真实付费 ping：

```powershell
.\check_pi.ps1
```

验证一个真实、无工具的业务 Agent 输出契约（不属于市场研究 run）：

```powershell
.\invoke_pi_acceptance.ps1
```

仅做本地安装和模型目录检查，不调用 LLM：

```powershell
.\check_pi.ps1 -NoPing
```

包含源码、许可、研究协议、实验 Registry、Tushare 和 Pi 的完整门禁：

```powershell
.\quant.ps1 health --runtime pi --input .\strategy_round.example.json
```

## 执行研究

真实模式，不允许自动 fallback：

```powershell
.\run_quant_agents.ps1
```

显式 Mock 软件回归：

```powershell
.\run_quant_agents.ps1 -Mock
```

完整回归和 Mock 验收：

```powershell
.\verify_quant_pipeline.ps1
```

真实前置门禁失败时命令返回非零，并生成失败 `state.json`、`summary.md`、alerts、manifest 和完整性报告。不得把一次 Pi ping、Mock 7/7 或配置存在称为真实研究完成。

## Agent 顺序

1. `research_lead`：只基于输入形成待验证研究假设。
2. `data_agent`：采集和固化获准 Tushare 数据与快照。
3. `strategy_agent`：解释 Python 生成的研究分类信号。
4. `backtest_agent`：解释 Python 确定性模拟回测。
5. `risk_agent`：识别模型、数据、流动性和制度风险。
6. `visualization_agent`：生成图表规范和本地图表。
7. `review_agent`：形成关键结论、触发等级、风险、人工问题和下一步。

依赖失败会阻断下游；失败 run 不原地续跑。修复后使用新的 Run ID，并通过显式 `request_id/retry_of` 记录重试关系。

## 产物

每个 `runs/<run-id>/` 至少包含：

- `input.json`、`state.json`、`summary.md`。
- `agent_outputs/`、`raw_outputs/`、`pi_meta/`。
- `market_data/`、`backtest/`、`charts/`。
- `backtest/cost_ledger.json`、`execution_policy.json`、`robustness_validation.json`、`backtest_assurance.json`。
- `operations/events.jsonl`、`metrics.json`、`alerts.json`、完整性报告。
- `run_manifest.json`，绑定输入指纹、源码、Pi runtime、模型用量和数据快照。
- `release/`，仅由发布命令生成，且不属于原始 run manifest。
- 实验 `registry.json` 和 `experiments.jsonl` 必须位于仓库外；每个真实 run 先追加 `RESERVED`，再追加成功、失败或中断的 `FINALIZED`，哈希写入 state/manifest。
- 前向 `campaign.json` 和 `observations.jsonl` 必须位于仓库外受控目录，不属于单个 run；账本记录 run manifest、源码、数据快照、协议和前向路径哈希链。

## 发布与归档

发布命令要求当前进程设置与 run 一致的 `EXPERIMENT_REGISTRY_PATH`，并重新读取外部账本验证预登记、终态和结果契约。

```powershell
.\quant.ps1 verify-run --run-dir .\runs\<run-id>
.\quant.ps1 release-prepare --run-dir .\runs\<run-id>
.\quant.ps1 release-verify --run-dir .\runs\<run-id> --approval .\runs\<run-id>\release\approval_request.json
.\quant.ps1 archive-run --run-dir .\runs\<run-id> --archive-root <受控归档目录>
.\quant.ps1 verify-archive --archive <zip> --expected-sha256 <外部保存的SHA-256>
.\plan_quant_retention.ps1 -ArchiveRoot <受控归档目录>
```

创建批准后的前向 campaign：

```powershell
.\quant.ps1 forward-init --baseline-run .\runs\<run-id> --approval .\runs\<run-id>\release\approval_request.json --root D:\controlled\quant\forward-campaigns
.\quant.ps1 forward-status --campaign <仓库外campaign目录>
```

归档回执绑定 ZIP 哈希、全部成员哈希、run manifest snapshot 和保留期限；验证命令使用安全临时目录做恢复及 run 完整性复验。保留计划只列出候选，不自动删除；任何删除仍要求有效归档、恢复复验、期限届满、无 legal hold 和人工授权。本地审批文件不具备身份认证能力；生产需接入组织审批系统并保存签名证据。批准范围只限内部研究评审，`external_distribution_approved=false`。

## 监控与调度

```powershell
.\quant.ps1 experiment-status --registry $env:EXPERIMENT_REGISTRY_PATH --runs-root .\runs
.\quant.ps1 ops-status --runs-root .\runs --experiment-registry $env:EXPERIMENT_REGISTRY_PATH --campaign <仓库外campaign目录> --max-age-hours 36
.\install_quant_schedule.ps1 -ApprovedRunDir <真实已批准run> -ApprovalPath <approval.json> -ForwardCampaignPath <仓库外campaign目录> -ExperimentRegistryPath $env:EXPERIMENT_REGISTRY_PATH -WhatIf
.\install_quant_schedule.ps1 -ApprovedRunDir <真实已批准run> -ApprovalPath <approval.json> -ForwardCampaignPath <仓库外campaign目录> -ExperimentRegistryPath $env:EXPERIMENT_REGISTRY_PATH
.\check_quant_schedule.ps1
```

生产监控默认忽略 Mock；只有真实 Pi、7/7、`REAL_TUSHARE`、数据许可、研究预注册、实验预登记/终态、执行成本校准、回测、模型预算、源码、alerts、完整性、时效及最新 run 已进入前向账本才返回健康。计划任务绑定已批准 run、源码 commit、审批文件哈希、实验 Registry ID/元数据哈希、campaign 元数据哈希及有期限的 deployment authorization；漂移或过期会在调用数据和 LLM 前失败。计划任务使用隐藏窗口，不应弹出交互终端。

许可证据填写、文件哈希、30 天条款复核及失败处置见 `docs/DATA_LICENSE_RUNBOOK.md`。公开 Tushare 条款不能直接作为组织商业研究授权。

执行成本证据的责任顺序、两种校准基础、90 天复核、材料哈希和失败处置见 `docs/EXECUTION_COST_RUNBOOK.md`。输入里的 `cost_assumption_source` 文本不能替代证据。

研究协议外部登记、精确输入/模型契约指纹、修订控制见 `docs/RESEARCH_PROTOCOL_RUNBOOK.md`；前向账本、路径防重写、暂停/独立验证/退役状态见 `docs/FORWARD_OBSERVATION_RUNBOOK.md`。

实验 Registry 的四方批准、初始化、预登记/终态、哈希链、未收尾实验和故障恢复见 `docs/EXPERIMENT_REGISTRY_RUNBOOK.md`。

## 关闭旧自启动

```powershell
.\disable_legacy_openclaw.ps1
```

脚本仅停止并禁用三个精确命名的 OpenClaw 任务并检查 `18789/18790`，不会终止所有 Node 进程，也不会改动其他项目计划任务。

## Pi Skills

- `.pi/skills/quant-data-governance`：许可证、来源、点时和质量门禁。
- `.pi/skills/quant-backtest-assurance`：A 股回测偏差、执行、成本和稳健性验收。
- `.pi/skills/quant-agent-evaluation`：真实 Pi Agent 基线、回归、成本和安全评测。
- `.pi/skills/quant-run-operations`：安装、健康、执行、恢复和证据检查。
- `.pi/skills/quant-release-review`：五方审批和内部发布检查。

运行 `.\quant.ps1 skills-audit` 校验全部 skill 的 SHA-256 锁、来源和生产隔离。GitHub 候选审查与固定 revision 见 `docs/SKILLS_GOVERNANCE.md`。

运行 `powershell -ExecutionPolicy Bypass -File .\invoke_pi_skills_acceptance.ps1`，使用真实 DeepSeek V4 Pro 对新增 operator skills 各做三次严格 JSON 加载验收；该命令只临时开放目标 skill 内的 `read`，不代表生产市场研究验收。

不安装通用浏览器/搜索 skill 到无人值守运行时。宏观或新闻数据必须先建立独立的数据许可、来源白名单、时间戳和快照审计链。

## Pi Operator Extension

项目没有批量安装第三方 Pi package。当前只提供项目自有、无网络/子进程/写入能力的只读 `/quant-status` 命令：

```powershell
.\quant.ps1 extensions-audit
.\open_pi_ops_console.ps1
```

进入控制台后输入 `/quant-status`。该视图分别显示最新 REAL 和明确标记的 `[MOCK]` 运行状态，不展示策略结论。脚本仅在当前终端手工运行，不创建自启动或计划任务。生产七 Agent turn 仍强制 `--no-extensions --no-tools`。

相似开源量化项目、精确 Git commit、可借鉴设计、许可证风险和 Pi 插件推荐见 `docs/OPEN_SOURCE_ECOSYSTEM_REVIEW.md`；机器可读决策在 `governance/upstream_references.json`。

## 文档

- `docs/PI_RUNTIME_CONTRACT.md`：Pi 运行契约和安全边界。
- `docs/OPERATIONS.md`：日常运行、故障和证据流程。
- `docs/COMMERCIAL_READINESS.md`：商业准入门禁。
- `docs/BACKTEST_EXECUTION.md`：有效期交易规则、成本账本、执行顺序和限制。
- `docs/EXECUTION_COST_RUNBOOK.md`：执行成本校准、证据和复核流程。
- `docs/RESEARCH_PROTOCOL_RUNBOOK.md`：外部预注册、输入绑定和变更控制。
- `docs/EXPERIMENT_REGISTRY_RUNBOOK.md`：跨 run 实验预登记、终态、哈希链和恢复。
- `docs/FORWARD_OBSERVATION_RUNBOOK.md`：连续前向观察、哈希链和生命周期状态。
- `docs/DEPLOYMENT.md`：部署与回滚。
- `docs/INCIDENT_DRILL.md`：Pi/API/数据故障演练。
- `docs/DEPLOYMENT_ACCEPTANCE.md`：逐项部署候选验收与外部阻断证据。
- `docs/OPEN_SOURCE_ECOSYSTEM_REVIEW.md`：Qlib、RD-Agent、LEAN、TradingAgents、RQAlpha 与 Pi 插件采用评审。
- `docs/adr/`：12 条核心架构决策记录（Python 权威、Pi no-tools、无自动回退、证据外置、Mock 不可发布等），索引见 `docs/adr/README.md`。

参考：[当前 Pi fork](https://github.com/earendil-works/pi)、[Pi coding agent](https://github.com/earendil-works/pi/tree/main/packages/coding-agent)、[Pi package 目录](https://pi.dev/packages)、[DeepSeek 模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)、[Tushare 服务条款](https://tushare.pro/document/1?doc_id=405)。
