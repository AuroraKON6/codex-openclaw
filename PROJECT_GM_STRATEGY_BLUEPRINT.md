# 项目总经理战略与未来架构蓝图

> 文档定位：从项目总经理、产品负责人和经营责任人的视角，定义项目未来的目的、定位、发展走势、目标架构、组织框架、预期效果、经营指标、风险边界、改进组合和落地路线。
>
> 项目路径：`E:\闲鱼\codex openclaw`  
> 战略评审日期：2026-09-15（Asia/Shanghai）  
> 当前事实基线：`PROJECT_MASTER_PLAN.md` 与 `governance/project_execution_status.json` 的 2026-09-15 离线复验证据  
> 全项目执行规划：`PROJECT_MASTER_PLAN.md`  
> 当前运行基座：Pi Agent + DeepSeek V4 Pro + Python deterministic control plane  
> 当前业务状态：软件候选可用，真实商业研究 **BLOCKED**  
> 永久安全边界：内部研究，不接券商、不路由订单、不管理真实资金、不得生成真实资金交易建议

---

## 0. 2026-09-05 当前复核快照

本轮在不调用付费模型、不请求真实市场数据的前提下重新核验：

- `.\.venv\Scripts\python.exe -m unittest discover -s tests`：**172/172 通过**；
- `.\quant.ps1 python-runtime --require-ready`：项目 Windows CPython `3.11.9`、32 个 hash-locked 包、user-site 隔离通过，0 版本偏差、0 额外运行包；
- `.\quant.ps1 source-candidate --require-reviewable`：140 个候选文件、0 机器阻断、9 项人工 review flag；`source-review-packet` 已把精确身份、CSV 清单、审查说明和文件哈希打包，`source-review-verify` 检查篡改和双角色控制弱化；应用 hash 不是签名，只允许 Platform/Security 人工逐文件复核，不授权 Git 写入或真实运行；
- `.\quant.ps1 project-readiness --input .\strategy_round.example.json`：严格离线汇总 13 项门禁，4 PASS、9 BLOCKED，且明确 `g1_authorized=false`、`real_run_authorized=false`；
- 完整回归的最新明确 **MOCK** run `20260905_105154_540` 为 7/7、27 文件、16 事件、完整性通过，release 因 17 项真实门禁按设计 BLOCKED；
- `check_pi.ps1 -NoPing`：Pi `0.84.2`、Node `24.16.0`、`deepseek-v4-pro` 模型目录、全工具禁用、5 个 operator-only skills 和 1 个只读 operator extension 的锁定审计通过；生产 turn 继续禁用 skills/extensions；
- 真实 Pi/DeepSeek ping 被显式跳过，因此本轮不构成新的真实模型供应商证据；
- `TUSHARE_TOKEN` 与四类外部商业证据路径均未配置；
- Git 仍无 HEAD、tracked file 和 remote，尚无可发布源码基线；
- 3 个 OpenClaw 计划任务均为 `Disabled`，18789/18790 无监听；
- 本轮没有生成市场结论，也没有改变任何商业门禁状态。

这组复核只证明当前本地软件与 Pi 隔离契约仍可用，不证明真实研究、组织授权、市场有效性或商业 READY。

---

## 1. 总经理结论

## 1.1 重新定义项目

这个项目未来不应被定义为：

- 多 Agent 炒股机器人；
- 自动选股工具；
- 由 LLM 决定策略和绩效的系统；
- 自动交易系统；
- 靠增加 Agent 和插件数量体现价值的技术展示。

建议把项目正式定义为：

> **Governed Quant Research OS（受治理的量化研究操作系统）**

它的核心工作不是“给出一个看起来聪明的结论”，而是把内部量化研究变成一条有授权、有版本、有预注册、有失败记录、有独立复核、有成本约束、有完整审计和有前向生命周期的生产流程。

“Pi 多 Agent”只是系统中的认知解释层，不是产品本体。产品本体由以下五个能力组成：

1. **权利可信**：证明数据、模型和处理方式有权使用；
2. **研究可信**：证明假设、参数、样本和阈值是在结果之前冻结；
3. **计算可信**：证明数据、信号、执行和绩效来自可复现的确定性引擎；
4. **流程可信**：证明成功、失败和中断实验都被登记，没有静默降级；
5. **生命周期可信**：证明发布、归档、前向观察、暂停和退役都有责任人和证据。

## 1.2 最重要的经营判断

项目当前最大的瓶颈不是 Agent 数量、模型智力或图表，而是：

- 没有受控源码基线；
- 没有组织数据授权；
- 没有真实外部研究预注册；
- 没有真实 Experiment Registry；
- 没有真实执行成本材料；
- 没有真实 Tushare 快照和当前 schema 7 的真实 7/7；
- 没有组织身份审批和外部不可变证据存储。

因此未来投入顺序必须是：

```text
权利与源码 > 科学验证 > 执行真实性 > 身份与审计 > 运营稳定性 > 产品界面 > Agent 扩张 > 插件扩张
```

如果反过来先增加因子、Agent、插件、网页和自动调参，项目会变得更复杂，却不会更真实。

## 1.3 总经理的首要决策

1. 保留 Python 作为唯一业务权威层；
2. 保留 Pi 生产 turn 的 no-tools/no-skills/no-extensions；
3. 不再扩张 OpenClaw，旧任务继续 Disabled；
4. 不建立任何真实交易能力；
5. 先完成一个受授权、可复现的单策略 baseline，再谈多策略；
6. 先把 Experiment Registry、身份审批和归档做成组织能力，再谈自动候选生成；
7. 先证明 Agent 相比纯 deterministic 报告确实提高审查质量，再决定是否增加 Agent；
8. 把所有经营指标设计成“可信研究效率”和“风险控制”，不设计收益承诺。

---

## 2. 项目的目的

## 2.1 业务目的

为内部量化研究团队提供一套标准化研究生产线，让每个研究候选都能被快速、重复、独立地回答以下问题：

- 研究为什么发起？
- 谁提出假设？
- 假设何时冻结？
- 使用了哪个源码版本？
- 数据来源和使用权是什么？
- 使用了哪个点时数据快照？
- 研究 universe 是否与宣称一致？
- 采用了什么执行、费用、滑点、容量和 A 股规则？
- 做过多少次候选试验？
- holdout、walk-forward 和前向表现如何？
- LLM 的贡献是什么，是否改变了权威指标？
- 哪些门禁失败？
- 谁批准进入下一阶段？
- 证据能否被恢复和复验？

## 2.2 管理目的

- 减少“代码能跑但业务不能用”的伪完成；
- 减少结果导向的参数调整和选择性汇报；
- 减少同一策略由不同人员运行得到不同结果；
- 降低数据权限、模型成本、Secret 和供应链风险；
- 缩短审计、复现、问题定位和归档准备时间；
- 让管理层看见真实的研究漏斗，而不是只看成功案例；
- 为未来多策略内部研究建立统一控制面。

## 2.3 不以什么作为目的

- 不以回测收益最大化为项目 KPI；
- 不以 Agent 输出篇幅为质量；
- 不以模型数量、插件数量或调用次数为成果；
- 不以“本轮触发等级”为市场方向；
- 不以 Mock 成功率替代真实数据成功率；
- 不保证 alpha、收益、Sharpe 或资金结果；
- 不用自动化绕过人工和组织责任。

---

## 3. 服务对象与价值主张

## 3.1 核心内部用户

| 用户 | 主要问题 | 系统价值 |
|---|---|---|
| 量化研究员 | 实验散落、口径不一、失败结果丢失 | 冻结契约、标准执行、完整实验谱系 |
| 独立模型验证人 | 无法知道尝试次数、数据版本和参数历史 | Registry、trial count、可复现 snapshot、challenge pack |
| 数据负责人 | 不清楚哪些数据被谁、何时、发给哪个处理者 | 数据许可、请求日志、snapshot、处理边界 |
| 模型/AI 负责人 | 模型和 prompt 漂移难追踪 | model/prompt registry、eval、canary、rollback |
| 平台/SRE | 失败难恢复、调度重复、成本不透明 | lock、idempotency、事件链、SLO、预算、恢复 |
| 合规/法务 | example 和真实授权混淆，身份不可核 | 外部证据、角色分离、不可变归档、审批绑定 |
| 管理层 | 只看到“好结果”，看不到研究漏斗和风险 | 研究组合、失败率、成本、阻断、生命周期看板 |

## 3.2 核心价值主张

### 对研究团队

“少花时间拼接证据，多花时间提出可检验假设；失败实验被保留，重复实验可以比较。”

### 对独立验证

“每个结论都有精确数据、源码、参数、试验次数、执行假设和前向路径，不需要依赖作者口头说明。”

### 对管理层

“可以看到研究从提出、登记、验证、失败、批准到退役的完整漏斗，不把软件成功误判成商业成功。”

### 对合规与平台

“未授权、未登记、未批准或发生漂移时，系统在外部调用前硬失败，并留下可审计失败证据。”

---

## 4. 产品边界

## 4.1 产品内能力

- 内部研究输入和协议；
- 数据许可和供应商证据；
- 数据 adapter、point-in-time snapshot 和质量；
- 因子、策略和研究候选；
- 确定性回测和现实执行模型；
- 实验登记、运行、失败和恢复；
- LLM 解释、反证、风险和 review；
- 模型/prompt/eval 管理；
- 发布、审批、归档和前向观察；
- 运维监控、成本和审计。

## 4.2 永久产品外能力

- 券商接入；
- 下单和撤单；
- 账户和资金；
- 持仓建议；
- 对外投资顾问；
- 面向客户的市场信号分发；
- 未授权新闻、网页、社交媒体和 MCP 数据；
- Agent 自主修改生产代码；
- Agent 自主批准模型或策略。

如果未来真的要研究真实交易执行，应另立独立项目、独立代码库、独立数据许可、独立监管与风控，不在本项目上增量打开。

---

## 5. 当前成熟度判断

## 5.1 成熟度模型

| 等级 | 名称 | 定义 | 当前状态 |
|---|---|---|---|
| M0 | Demo | 能生成结果，但无可靠控制和证据 | 已超越 |
| M1 | Controlled Software | 有门禁、Mock、测试、审计和失败产物 | **当前所在** |
| M2 | Authorized Research | 有真实授权、真实数据、真实 Agent 和可复现 baseline | 未达到 |
| M3 | Repeatable Research Factory | 多次真实 run、统一数据/实验/模型生命周期 | 未达到 |
| M4 | Managed Portfolio Research | 多策略组合、前向监控、组织 SLO 和风险资本分配 | 未达到 |
| M5 | Optimized Internal Platform | 多团队、身份/WORM、可观测、持续优化 | 长期目标，不含交易 |

## 5.2 当前优势

- 已经明确 Python 权威、Pi 解释的边界；
- 真实模式不允许自动 fallback；
- 有 source/license/protocol/registry/cost 等硬门禁；
- 有点时数据、A 股规则和确定性回测框架；
- 有 holdout、walk-forward 和 stress；
- 有 run lock、幂等、事件链、manifest 和恢复；
- 有 release、archive、retention 和 forward lifecycle；
- 有 166 个测试、离线 readiness 汇总和完整 Mock E2E；
- 有 operator-only skills/extension 供应链控制；
- 已禁用旧 OpenClaw 自启动和端口。

## 5.3 当前核心缺陷

> 2026-08-30 Zcode 接管复核更正：下列前四条工程缺陷已在代码中修复并复核（见 `ZCODE_PROJECT_HANDOFF.md` 第 0 节），保留原文字为历史记录。

- 没有 committed source；
- ~~没有自动 Secret scan 证据~~ **已修复**：`quant_agents/secret_scan.py` + 回执 + 测试，已接入 source/release gate；
- ~~schedule authorization schema 2/3 漂移~~ **已修复**：installer/checker/runner 一致 schema 3，`test_schedule_contract.py` 约束；
- ~~Pi child process 继承父进程全部环境~~ **已修复**：`PI_CHILD_ENV_ALLOWLIST` 显式白名单；
- 数据、协议、Registry、成本四类真实证据缺失；
- Tushare 公开协议仍是个人、不可转让、非商业用途，不能直接覆盖组织内部商业研究；
- 当前 top-40 高权重样本不能代表完整 CSI 500；
- 示例研究区间和阈值偏软件验收；
- execution fill/impact 仍缺逐订单差分基准；
- 本地 JSON/hash 不认证真实身份、时间戳和 WORM；
- 当前 Agent 的增量价值没有与纯 Python 报告做 A/B 证明；
- ~~文档存在旧 test count 和旧 run 证据~~ **已修复**：`docs/DEPLOYMENT_ACCEPTANCE.md` 已更新至 166 测试与最新明确 Mock run，旧节标注为历史快照。

---

## 6. 未来发展走势

## 6.1 总体走势

项目应沿以下方向演进：

```text
单机受控流水线
    ↓
首个授权真实 baseline
    ↓
重复可复现的研究工厂
    ↓
组织级实验、模型和数据控制平面
    ↓
多策略内部研究组合与前向生命周期
```

不应沿以下方向演进：

```text
更多 Agent → 更多插件 → 自动调参 → 自动选股 → 自动交易
```

## 6.2 四个发展阶段

### 阶段 S1：可信基础

目标：把当前 M1 软件候选变成可提交、可授权、可做首个真实 baseline 的系统。

重点：

- 修 P0 代码缺口；
- 建私有 Git baseline；
- 完成真实组织证据；
- 完成当前 paid Pi acceptance；
- 完成一个预注册 momentum baseline；
- 不增加策略、不增加 Agent。

### 阶段 S2：研究工厂

目标：让第二个、第三个研究候选不需要复制整套流程。

重点：

- 数据 adapter 和 snapshot catalog；
- Parquet/DuckDB point-in-time 数据层；
- strategy protocol template；
- 统一 experiment/prompt/model registry；
- execution differential tests；
- statistical multiple-testing controls；
- read-only research status dashboard。

### 阶段 S3：组织平台

目标：支持多人、独立角色、组织身份、不可变归档和可观测运行。

重点：

- SSO/RBAC；
- 外部 approval system；
- trusted timestamp/signature；
- WORM/object lock；
- Registry service；
- independent validation workspace；
- OpenTelemetry-compatible metrics/traces/logs；
- vendor-neutral data adapters。

### 阶段 S4：多策略生命周期

目标：管理多个研究候选和前向 campaign，而不是自动交易。

重点：

- 受治理 candidate queue；
- trial budget 和 multiple testing；
- strategy/model cards；
- 多策略相关性、重叠风险和容量研究；
- shadow model/Agent eval；
- 暂停、独立验证、退役和复盘。

---

## 7. 未来目标架构总图

```text
┌──────────────────────────────────────────────────────────────┐
│  1. Management & User Plane                                 │
│  Research Brief | Portfolio | Review Workbench | Read-only  │
│  Dashboard | Decision Log                                   │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────v──────────────────────────────────┐
│  2. Governance & Evidence Plane                             │
│  Source | License | Protocol | Registry | Cost | Identity   │
│  Approval | WORM | Retention | Legal Hold | Audit           │
└───────────────────────────┬──────────────────────────────────┘
                            │ hard gates
┌───────────────────────────v──────────────────────────────────┐
│  3. Orchestration & Operations Plane                        │
│  Run Lock | Idempotency | DAG | Budget | Timeout | Events   │
│  Manifest | Alerts | Recovery | Schedule | Observability    │
└───────────────┬────────────────────────────┬─────────────────┘
                │                            │
┌───────────────v────────────────┐  ┌────────v─────────────────┐
│  4. Data & Research Plane      │  │  5. Pi Agent Plane       │
│  Vendor Adapters               │  │  7 no-tools JSON turns   │
│  Raw/Normalized/PIT Snapshots  │  │  Prompt/Model Registry   │
│  Feature/Universe Registry     │  │  Eval/Canary/Rollback    │
│  Deterministic Backtest        │  │  Explain/Challenge/Review│
│  Validation/Execution Models   │  │  No metric authority     │
└───────────────┬────────────────┘  └────────┬─────────────────┘
                │                            │
                └──────────────┬─────────────┘
                               v
┌──────────────────────────────────────────────────────────────┐
│  6. Artifact & Lifecycle Plane                              │
│  Run Artifacts | Experiment Ledger | Release | Archive      │
│  Restore | Forward Campaign | Observation | Retire          │
└──────────────────────────────────────────────────────────────┘
```

六个平面必须相互独立：

- 用户界面不能绕过治理；
- Agent 不能绕过 deterministic engine；
- deterministic engine 不能绕过数据权利；
- release 不能只信 run 内状态，必须复验外部证据；
- dashboard 只读，不成为第二套编排器；
- forward campaign 不能自动升级为交易。

---

## 8. 环境架构

## 8.1 三环境模型

### Development

- 无生产 Secret；
- Mock、合成和脱敏 fixture；
- 可使用 operator skills；
- 可运行静态分析、单测和差分测试；
- 不写真实 Registry；
- 不访问真实市场数据。

### Validation

- 使用批准的历史 snapshot 副本；
- 独立验证账户和目录；
- 只读源码 tag；
- 可做 replay、backtest 和 Agent eval；
- 不允许修改 baseline artifact；
- 不允许创建生产 release approval。

### Production Research

- 只运行 clean signed/tagged source；
- 独立 service account；
- Secret allowlist；
- 出站网络 allowlist；
- 外部 Registry、approval 和 WORM；
- 生产 Pi turn 永远 no-tools；
- 任务隐藏、非提升权限、IgnoreNew；
- 只产出内部研究 artifact。

## 8.2 环境隔离原则

- 三个环境不能共享 writable run root；
- 三个环境不能共享同一 API Token；
- Mock 和 real 使用不同 storage namespace；
- validation 不得写 production Registry；
- production 不自动加载 project-local extension/skill；
- 生产 host 不允许浏览器、MCP 和通用搜索进入 Agent turn；
- 生产网络只允许批准 provider、数据源和组织控制系统；
- 环境 identity、source tag 和 evidence root 写入 manifest。

---

## 9. 数据架构

## 9.1 数据供应商策略

Tushare 只能被视为一个 adapter，不应成为不可替换的产品架构。

目标接口：

```text
MarketDataProvider
├── calendar()
├── universe_history()
├── daily_prices()
├── adjustment_factors()
├── price_limits()
├── suspensions()
├── fundamentals_snapshot()
└── provider_evidence()
```

每个 provider 必须有：

- 组织授权；
- endpoint 和字段契约；
- 频率和配额；
- 数据更新时间；
- 缓存和衍生权；
- LLM 处理权；
- 保留和终止处置；
- quality profile；
- provider version 和 terms hash。

## 9.2 数据分区

```text
Raw Licensed Zone
    ↓ immutable provider response
Normalized PIT Zone
    ↓ schema, dates, corporate actions, universe
Feature Zone
    ↓ deterministic features with lineage
Research Snapshot Zone
    ↓ frozen dataset ID for one experiment
Derived Artifact Zone
    ↓ signals, orders, metrics, charts
```

## 9.3 近期存储选择

单机阶段不需要立刻建设大型数据湖。建议：

- 原始响应：压缩 JSON/CSV，仅保存合同允许内容；
- 标准化行情和成分：Parquet；
- 本地点时查询和统计：DuckDB；
- catalog/manifest：JSON + SQLite/DuckDB metadata；
- run artifact：当前目录结构继续保留；
- release/archive：仓库外 object storage；
- metadata 和 artifact 分离。

只有满足以下任一条件后，才升级成共享服务：

- 超过一个并发 operator；
- 单机 catalog 成为冲突点；
- 累计实验规模达到需要跨 run 查询；
- 审计要求组织 IAM 和集中保留；
- 多数据供应商和多团队同时使用。

## 9.4 必须新增的数据控制

- schema registry；
- dataset ID 和 dataset fingerprint；
- row count、coverage、null、duplicate、date continuity；
- universe membership point-in-time test；
- delisting、ST、IPO、停牌、公司行动策略；
- provider-to-normalized reconciliation；
- data freshness SLI；
- data drift report；
- licensed field allowlist；
- LLM prompt data minimization；
- retention expiry and deletion authorization。

---

## 10. 确定性研究架构

## 10.1 未来研究对象模型

```text
ResearchThesis
  └── ProtocolVersion
       ├── DatasetSnapshot
       ├── UniverseDefinition
       ├── FeatureDefinition
       ├── StrategyDefinition
       ├── ExecutionModelVersion
       ├── ValidationPlan
       ├── TrialBudget
       └── ForwardPlan

Experiment
  └── Run
       ├── DeterministicResults
       ├── AgentInterpretations
       ├── ChallengeResults
       ├── ReleaseDecision
       └── ForwardObservations
```

## 10.2 研究层必须拆分

### Universe

- 完整 CSI 500；
- 分层抽样；
- top-weight sample；
- 行业/规模中性样本。

这些必须是不同 protocol，不能混称。

### Feature

- feature formula；
- input fields；
- lag；
- missing treatment；
- winsorization/normalization；
- effective date；
- version/hash；
- leakage tests。

### Strategy

- ranking；
- selection；
- rebalance；
- weight；
- constraints；
- benchmark；
- turnover/capacity。

### Execution

- order timing；
- fill；
- price limits；
- suspension；
- lot sizes；
- T+1；
- fees；
- slippage；
- impact；
- partial fills；
- cancellation；
- cash/settlement。

### Validation

- development；
- holdout；
- anchored walk-forward；
- purging/embargo where labels overlap；
- stress；
- multiple testing；
- independent replay；
- forward observation。

## 10.3 当前 momentum baseline 应如何定位

首个真实 baseline 的目的不是证明动量能赚钱，而是证明完整研究流程可以运行。

必须明确：

- 当前 top-40 是高权重子样本；
- 当前 2025-01 至 2025-05 区间过短，不足以覆盖市场状态；
- 当前阈值用于软件流程，不足以单独证明研究质量；
- 当前 fill 和 impact 是研究假设；
- current outcome 不允许用于真实资金；
- 任何扩展区间、universe 或阈值都要新 protocol。

## 10.4 未来科学控制

建议逐步增加：

- benchmark-relative metrics；
- factor IC、Rank IC、ICIR；
- turnover and capacity；
- sector/size exposure；
- crowding/proxy concentration；
- minimum track record length；
- Deflated Sharpe Ratio；
- Probability of Backtest Overfitting；
- trial count from Registry；
- bootstrap confidence interval；
- regime stability；
- data perturbation；
- parameter neighborhood stability；
- independent implementation differential；
- deterministic seed protocol；
- candidate family-level multiple testing budget。

这些控制必须在候选生成体系稳定后按协议引入，不能看到结果后选择性使用。

---

## 11. 执行真实性架构

## 11.1 管理原则

回测最容易产生虚假确定性的地方不是 Agent，而是执行模型。

未来必须把 execution model 视为一等版本化产品：

```text
ExecutionModel
├── MarketRuleVersion
├── FeeModel
├── SlippageModel
├── ImpactModel
├── FillModel
├── LiquidityModel
├── SettlementModel
└── CapacityModel
```

## 11.2 LEAN 风格差分测试

借鉴 LEAN 的 fill/slippage/fee/capacity 可插拔思想，但不接其 live/brokerage 层。

建立冻结订单流 fixture，逐单比较：

- expected order；
- actual fill；
- blocked reason；
- quantity adjustment；
- fee components；
- slippage；
- impact；
- cash；
- positions；
- cost ledger；
- NAV change；
- rule source/version。

重点场景：

- 主板/创业板/科创板申报数量；
- odd-lot exit；
- T+1；
- 涨跌停；
- 停牌；
- partial fill；
- no volume；
- high participation；
- minimum commission；
- stamp duty sell-only；
- all-in commission double-count prevention；
- rebalance cash shortage；
- corporate actions；
- stale price；
- cancelled DAY order。

验收不能只比较最终收益，必须逐订单解释差异。

---

## 12. Pi Agent 未来架构

## 12.1 保留现有七 Agent，不立即扩张

当前七个角色已经覆盖：

- hypothesis；
- data narrative；
- strategy explanation；
- backtest interpretation；
- risk challenge；
- visualization spec；
- final review。

现阶段没有证据表明增加更多 Agent 会提高质量。增加 Agent 会同时增加：

- token cost；
- failure points；
- context duplication；
- prompt maintenance；
- contradictory outputs；
- 审计复杂度。

因此下一步不是增加 Agent，而是建立 Agent effectiveness evaluation。

## 12.2 Agent 价值评估

每个 Agent 必须回答：

1. 它发现了 Python deterministic report 没发现的什么？
2. 它是否减少了人工 review 时间？
3. 它是否增加了错误、幻觉或无依据叙述？
4. 它是否稳定满足 JSON contract？
5. 它每次运行的增量成本是多少？
6. 没有它时 release decision 是否变化？

建立三组对照：

- deterministic-only；
- current 7-Agent；
- 7-Agent + shadow challenger。

只有通过盲评和固定 eval set 后，才考虑调整 Agent 结构。

## 12.3 未来可选的 shadow challenger

不是立即增加第八个生产 Agent，而是建立 evaluation-only challenger：

- 使用已批准、脱敏或固定 snapshot；
- 不写 production review；
- 不参与 release；
- 只比较遗漏风险、引用准确性、JSON contract 和成本；
- 达到预注册改进阈值后，走 model/prompt change review。

## 12.4 Prompt/Model Registry

未来每个 Agent 需要：

- role ID；
- prompt version；
- system/user template hash；
- input schema；
- output schema；
- model/provider/version；
- thinking mode；
- security flags；
- eval suite version；
- known limitations；
- owner；
- approval status；
- canary status；
- rollback version。

## 12.5 Model change 流程

```text
Model/Prompt Candidate
  → offline contract eval
  → hallucination/unsupported-claim eval
  → trading-language safety eval
  → fixed-snapshot regression
  → cost/latency eval
  → shadow canary
  → independent approval
  → tagged rollout
  → monitored production
  → rollback if breached
```

不得因 provider 自动更新或目录出现新模型就直接切换。

## 12.6 Skills、extensions 和插件

生产 Agent：

- no tools；
- no skills；
- no extensions；
- no project context files；
- no MCP/web/browser。

Operator profile：

- 可以有固定 hash 的只读 status extension；
- 可以有项目自有 runbook skills；
- 第三方 package 一次只评估一个；
- 必须固定 version/commit、审查 lifecycle scripts、网络、写入、Secret 和 telemetry；
- 不能自动加载；
- 不能创建后台自启动。

Pi 官方安全模型明确说明 Pi 本身不是沙箱，并把本地用户、workspace、skills 和 extensions 视为信任边界的一部分。因此 no-tools 和 operator-only 隔离是架构要求，不是临时限制。

---

## 13. 治理与证据架构

## 13.1 四条证据链

### 权利链

```text
Vendor Terms → Organization Agreement → Evidence Hash → Dataset Snapshot → Retention/Termination
```

### 研究链

```text
Thesis → Protocol → Model Contract → Experiment Reservation → Run → Finalization
```

### 计算链

```text
Source Commit → Dependency Lock → Data Snapshot → Deterministic Results → Manifest
```

### 决策链

```text
Challenge → Release Candidate → Identity Approval → Archive → Forward → Pause/Retire
```

## 13.2 近期证据架构

当前外部 JSON + supporting document + hash 可以继续用于单机 pilot，但必须明确：

- hash 证明内容一致，不证明签署人；
- local timestamp 不可信；
- append-only application logic 不是 WORM；
- Windows file permissions 不等于组织审批；
- 本地 approval JSON 不等于电子签名。

## 13.3 组织级目标架构

```text
Organization IAM / SSO
        ↓ identity and role
Approval / Ticket System
        ↓ signed decision
Experiment Registry Service
        ↓ append-only metadata
Object Storage with Retention Lock
        ↓ immutable artifacts
Audit Export / Trusted Timestamp
```

## 13.4 Experiment Registry 演进

当前阶段：

- 外部目录；
- `registry.json`；
- `experiments.jsonl`；
- application hash chain；
- one writer lock。

升级条件：

- 多 operator；
- 并发写入；
- 跨项目共享；
- IAM 审批；
- 超过 1,000 runs 或审计查询困难；
- 需要集中备份/WORM。

目标服务：

- append-only event API；
- optimistic concurrency/idempotency；
- database audit log；
- signed actor identity；
- artifact URI + hash；
- immutable export；
- no delete API for research events；
- retention/legal hold。

不建议现在立刻引入 MLflow 作为生产真相源。可以学习其 experiment/run/parameter/metric/artifact 模型，等组织 IAM 和存储边界清楚后再做 build-vs-buy 评估。

---

## 14. 平台、安全与 SRE 架构

## 14.1 近期 P0

> 2026-08-30 Zcode 接管复核更正：第 1、3、4、6 项已在代码中完成并复核（schema 3 契约测试、child env allowlist、secret scan 回执、acceptance 文档更新）；第 5 项 private Git baseline 是当前最高优先级开放项；第 2 项由 `test_schedule_contract.py` 部分覆盖；第 7—10 项仍开放。

1. ~~修 `check_quant_schedule.ps1` schema 2/3~~ **已完成**；
2. authorization contract single source of truth（部分：跨脚本 schema 一致性已有 8 项契约测试约束）；
3. ~~Pi child env allowlist~~ **已完成**；
4. ~~Secret scan and evidence~~ **已完成**；
5. **private Git baseline（当前最优先开放项）**；
6. ~~current acceptance docs~~ **已完成**；
7. PowerShell contract tests（已完成核心部分：`test_schedule_contract.py` 8 项）；
8. ~~no paid call by default in CI~~ **已完成（2026-09-06）**：`.github/workflows/ci.yml` 只运行零付费 `verify_quant_pipeline.ps1`，由 `test_ops_contract.py` 锁定；
9. separate dev/validation/prod paths（开放）；
10. ~~exact task and port checks~~ **已完成（2026-09-06）**：`test_ops_contract.py` 锁定 disable_legacy 精确任务/端口与 ops console 无自启动。

## 14.2 Secret 架构

原则：

- Secret 不写 `.env` 作为长期生产方案；
- Secret 不写 Markdown、state、manifest、approval；
- Pi 只收到 DeepSeek 所需变量；
- Tushare Token 只存在于 Python data process；
- Registry/evidence paths 可进入 orchestrator，不进入模型 child；
- 每个环境和服务账户使用不同 Secret；
- rotation 有明确 owner；
- 日志只记录 set/not-set、length class 或 hash，不记录值。

近期单机可以使用组织批准的 Windows protected credential store；长期使用组织 Secret Manager。

## 14.3 网络架构

Production Research 出站 allowlist：

- DeepSeek API；
- 获准市场数据 provider；
- 组织 IAM/approval/registry/observability；
- 必要的时间同步和证书服务。

禁止：

- 通用网页搜索；
- 未批准 MCP；
- 任意 URL；
- plugin auto-update；
- package install during run；
- public callback/webhook；
- broker endpoint。

## 14.4 可观测性

当前事件链和 metrics 是良好起点。未来应增加统一 `run_id`/`request_id`/`experiment_id` correlation：

- traces：preflight、data endpoint、Agent turn、backtest、finalization；
- metrics：latency、error、tokens、cost、data coverage、gate status；
- logs：structured events，不含 Secret；
- artifacts：snapshot、manifest、approval、archive；
- alerts：severity、owner、deadline、evidence link。

OpenTelemetry 可作为未来 vendor-neutral instrumentation 标准，但不是近期必须引入的 backend。先定义稳定字段，再决定 exporter。

## 14.5 SLI/SLO

首个真实 baseline 前不承诺生产 SLO。先收集至少 20 个授权 real runs，再冻结 p50/p95/p99。

管理目标：

| 指标 | 初始目标 |
|---|---|
| 未授权外部调用 | 0 |
| 未登记真实 run | 0 |
| Mock 被识别为 real | 0 |
| release artifact integrity | 100% |
| approved candidate 可独立恢复 | 100% |
| Secret 日志泄露 | 0 |
| stale reservation 未响应 | 0 超过 SLA |
| budget breach 自动发布 | 0 |
| source drift 后继续运行 | 0 |
| authorized scheduled run | 受 2400 秒 hard timeout 约束，20 次后定 p95 |

## 14.6 RTO/RPO 建议目标

| 对象 | RPO | RTO |
|---|---|---|
| Experiment ledger | 0 个已确认 event 丢失 | 4 个业务小时内恢复写入/判定 BLOCKED |
| Released artifacts | 0 个批准 artifact 丢失 | 1 个业务日内恢复并复验 |
| Raw licensed snapshot | 按合同和 snapshot policy | 1 个业务日或从 provider 重建，前提是许可允许 |
| Schedule | 可错过一次，不自动补跑 | 当日人工复核后恢复 |
| Pi provider | 不做自动 provider fallback | 恢复后新 Run ID；无 RTO 承诺 |

## 14.7 降级原则

- DeepSeek 失败：run 失败并 finalize，不自动换模型；
- Tushare 失败：run 失败并 finalize，不用旧快照冒充；
- Registry 失败：外部调用前阻断；
- WORM/approval 失败：release 阻断；
- schedule 失败：不自动重跑，operator 明确 `retry_of`；
- dashboard 失败：不影响 CLI/control plane；
- observability backend 失败：如果审计 event 无法保存，生产 run 阻断。

---

## 15. 产品界面与用户体验

## 15.1 近期界面

继续以 CLI + Markdown + JSON 为权威：

- 容易审计；
- 易于版本化；
- 不引入第二套状态；
- 不需要新的账号和网络；
- 适合当前单 operator。

## 15.2 未来只读控制台

在至少三个授权 real runs 后，可以建设 read-only dashboard：

- 当前 source/evidence/runtime 状态；
- real 和 mock 分栏；
- research funnel；
- experiment reservations/finalizations；
- data quality；
- Agent cost/latency/contract errors；
- release blockers；
- forward campaign；
- incidents and owner。

禁止在 dashboard 中加入：

- 一键绕过；
- 手工改指标；
- 删除失败实验；
- 真实资金动作；
- 对外分享；
- 直接编辑 external ledger。

## 15.3 Research Workbench

组织平台阶段可以增加：

- protocol drafting；
- evidence checklist；
- experiment compare；
- run artifact explorer；
- challenge/review queue；
- approval deep links；
- archive/restore receipts；
- model/strategy cards。

真正的审批仍在组织 IAM/approval 系统完成。

---

## 16. 组织框架

## 16.1 最小团队

| 角色 | 核心责任 |
|---|---|
| 项目总经理/Product Owner | 价值、范围、资源、优先级、Go/No-Go |
| Quant Owner | 研究 thesis、protocol、策略、结果解释 |
| Independent Model Validator | 独立复现、统计控制、challenge、退役建议 |
| Data Owner | vendor、权限、质量、snapshot、数据事故 |
| Platform/SRE Owner | source、runtime、Secret、schedule、recovery、SLO |
| Model/AI Owner | Pi/model/prompt/eval/cost/drift |
| Compliance/Legal Owner | 数据用途、身份、发布、保留、外部分发边界 |

开发阶段一个人可以承担多个实现任务，但审批职责必须分离；量化负责人不能自任独立验证人。

## 16.2 决策会议

### 每周 Delivery Review

- P0/P1 状态；
- test/Mock；
- blocker owner；
- cost；
- incident；
- next acceptance。

### 每个 Experiment Review

- protocol；
- trial budget；
- data rights；
- execution model；
- success/failure；
- next action。

### 每月 Model Risk Review

- model/prompt drift；
- Agent eval；
- unsupported claims；
- cost/latency；
- forward status；
- candidate retirements。

### 每季度 Steering Review

- internal user value；
- research funnel；
- operating cost；
- vendor and license；
- maturity stage；
- continue/pause/kill decisions。

## 16.3 RACI 摘要

| 事项 | A | R | C | I |
|---|---|---|---|---|
| Source baseline | Platform | Engineering | Security/Quant | GM |
| Data license | Compliance | Data Owner | Legal/Platform | GM/Quant |
| Protocol | Quant | Quant | Validator/Compliance | GM |
| Registry | Platform | Platform | Validator/Compliance/Quant | GM |
| Cost evidence | Quant | Cost Reviewer | Compliance/Data | GM |
| Pi model change | Model Owner | AI Engineering | Platform/Validator | GM/Quant |
| Real run | Quant | Platform | Data/Model | Compliance/GM |
| Release | GM/Committee | Five owners | Audit | Internal users |
| Forward | Model Owner | Platform | Validator/Compliance | GM |
| Incident | Platform or Data | Assigned owner | Compliance/Model | GM |

---

## 17. 经营指标与预期效果

## 17.1 北极星指标

建议北极星指标：

> **可独立复现且证据完整的内部研究候选比例**

计算口径：

```text
在规定周期内，满足 source、rights、protocol、registry、cost、data、deterministic validation、Agent contract、integrity 和 approval 的候选数
÷
进入正式验证阶段的候选总数
```

不把未进入正式验证的 brainstorming 计入；不按收益方向过滤失败候选。

## 17.2 控制指标

- registered real experiments = 100%；
- failed/interrupted experiments retained = 100%；
- unauthorized external calls = 0；
- Mock/real misclassification = 0；
- released artifact integrity = 100%；
- independent role separation = 100%；
- unapproved external distribution = 0；
- broker connectivity = 0；
- secret exposure = 0。

## 17.3 研究质量指标

- point-in-time coverage；
- data quality GOOD rate；
- dataset reproducibility；
- protocol exact match；
- holdout and walk-forward completion；
- trial count completeness；
- execution ledger reconciliation；
- independent replay pass rate；
- forward observation completeness；
- strategy retirement discipline。

不能把所有候选通过率设为越高越好。过高通过率可能说明门槛过低；应关注证据完整性和失败是否被正确保留。

## 17.4 Agent 指标

- JSON contract pass rate；
- unsupported claim rate；
- forbidden-language rate；
- risk issue precision/recall on fixed eval；
- incremental review findings；
- human review time saved；
- cost per accepted finding；
- p50/p95 latency；
- repair-turn rate；
- model/prompt drift incidents。

## 17.5 运营与成本指标

- cost per real run；
- cost per valid candidate；
- tokens by Agent；
- provider cost vs estimate；
- cache hit ratio；
- data request volume/retry；
- pipeline p50/p95；
- mean time to detect；
- mean time to resolve；
- archive restore time；
- manual evidence assembly time。

## 17.6 预期效果

以下是未来管理目标，不是当前已经实现的收益：

| 效果 | 目标 |
|---|---|
| 研究可追溯 | 每个正式候选 100% 有完整 lineage |
| 失败透明 | 失败/中断候选 100% 保留和登记 |
| 复现效率 | release candidate 在 1 个业务日内可独立恢复复验 |
| 审批效率 | 证据包自动生成，人工只做责任判断 |
| 运营透明 | 管理层可看研究漏斗、成本、阻断和 owner |
| 风险降低 | 未授权数据/模型/发布在外部调用或发布前硬阻断 |
| Agent 价值 | 用固定 eval 证明增量价值，不以主观观感判断 |
| 人工时间 | 先测现状，稳定 3 个周期后再设减少 50% 的证据整理目标 |

项目不设“预计收益率”“预计 Sharpe”或“资金回报”作为交付承诺。

---

## 18. FinOps 与资源配置

## 18.1 成本结构

真正的成本通常按重要性排序为：

1. 数据授权和供应商；
2. 独立量化验证和合规人员；
3. 平台、安全、身份和不可变存储；
4. 研究工程和维护；
5. LLM API；
6. dashboard 和插件。

不要因为 LLM token 价格可见，就忽略更大的数据权利和人员成本。

## 18.2 DeepSeek 当前成本基线

截至 2026-08-30，DeepSeek 官方页面列出的 V4 Pro off-peak 单价与项目当前 baseline 一致：

- cache hit：0.022 USD / 1M tokens；
- cache miss：0.66 USD / 1M tokens；
- output：1.98 USD / 1M tokens；
- peak 价格为上述两倍。

项目使用 off-peak estimate + 2x peak envelope 的思路合理。由于供应商明确保留调整价格的权利，必须继续执行 30 天复核和 provider-reported cost 取高值门禁。

## 18.3 成本决策

- 当前每 run 2 USD 是预算上限，不是保证成本；
- 先测七 Agent 的增量价值，再分配 token；
- 没有价值的 Agent 应合并或移除；
- repair turn 单独计费；
- 不为提高“智能感”开启默认 thinking；
- 不做自动 provider fallback；
- shadow eval 使用独立预算；
- dashboard/MLflow/OTel 不应早于真实 baseline 投资。

---

## 19. 最重要的改进组合

## 19.1 P0：首个真实 baseline 前

> 2026-08-30 Zcode 接管复核更正：下表前 5 行工程项已在代码中完成并复核（工程部分）；Git baseline 待人工建仓；第 6—10 行外部证据与付费验收项全部开放。

| 改进 | 价值 | 验收 | 状态 |
|---|---|---|---|
| 修 schedule schema 2/3 | 防止安装后 checker 永久误报 | installer/checker/runner contract test | **代码已完成** |
| Pi child env allowlist | 防止 Tushare/其他 Secret 进入模型进程 | 测试 key 名不存在且不回显值 | **代码已完成** |
| 自动 Secret scan | source gate 不再只靠口头 | 固定 scanner/version/hash + pass receipt | **代码已完成** |
| 私有 Git baseline | 让真实 run 有可追溯源码 | clean HEAD/tag/remote | **开放（人工/平台）** |
| 更新 acceptance | 防止旧 102/旧 run 冒充当前 | current date/run/test count | **已完成** |
| 外部数据授权 | 合法调用和处理数据 | 独立组织原件和 hash | **开放** |
| 外部 protocol | 防止结果后改参数 | exact input/model contract binding | **开放** |
| 真实 Registry | 保留全部 trial | RESERVED/FINALIZED/reconcile | **开放** |
| 执行成本证据 | 防止成本后调 | external material + independent review | **开放** |
| current paid acceptance | 证明当前 provider/model/no-tools | ping + Agent contract + usage | **开放（需预算批准）** |

## 19.2 P1：研究工厂

| 改进 | 价值 |
|---|---|
| Provider adapter | 避免 Tushare lock-in |
| Parquet + DuckDB PIT layer | 提高 point-in-time 查询和复现 |
| Full/stratified CSI500 protocols | 消除 top-40 宣称偏差 |
| Longer multi-regime baseline | 提高研究覆盖 |
| Execution differential suite | 提高 fill/cost/limit/T+1 真实性 |
| Trial-budget + DSR/PBO | 控制多重检验和过拟合 |
| Prompt/model registry | 管理 Agent 变更和 rollback |
| Agent A/B eval | 证明 LLM 增量价值 |
| Identity/WORM integration | 从本地哈希升级组织证据 |
| Unified observability fields | run/experiment/provider 关联 |

## 19.3 P2：组织平台

- read-only dashboard；
- approval deep links；
- Registry service；
- centralized artifact catalog；
- independent validation workspace；
- shadow challenger；
- governed candidate queue；
- optional operator safety plugin；
- cross-strategy exposure/capacity research；
- disaster recovery exercise。

---

## 20. 不建议做的改进

1. 不建议现在增加更多生产 Agent；
2. 不建议现在安装 Qlib、MLflow 和多个插件；
3. 不建议用 subagent plugin 替换 Python DAG；
4. 不建议把 Web/MCP/news 接入生产；
5. 不建议把 current top-40 结果扩称 CSI500 全市场；
6. 不建议自动调参和自动候选晋级；
7. 不建议把 dashboard 当成第二套状态源；
8. 不建议为了“可用”绕过 source/license/protocol；
9. 不建议自动切换 provider/model；
10. 不建议建立真实交易或外部分发。

---

## 21. 风险登记册

| 风险 | 影响 | 当前控制 | 未来控制 |
|---|---|---|---|
| 数据用途不匹配 | 合同/业务中断 | license gate | organization agreement + periodic review |
| Source 无版本 | 无法复现 | hard block | private Git + signed tag + scan |
| Secret 泄露 | 账户/数据风险 | 不回显 | allowlist + manager + rotation |
| Top-40 代表性偏差 | 结论误称 | handoff disclosure | protocol-specific universe catalog |
| Backtest overfitting | 虚假研究结论 | prereg/no search | trial budget + DSR/PBO + forward |
| Execution 偏乐观 | 绩效高估 | costs/limits/T+1 | differential fill/capacity suite |
| LLM unsupported claim | 错误解释 | JSON/contracts | fixed eval + citation/evidence binding |
| Model drift | 结果不可比 | exact model | registry/canary/rollback |
| Plugin supply chain | 代码执行/Secret | production disabled | operator isolation + source review |
| Local hash 被误称 WORM | 审计误判 | explicit disclaimer | object lock + trusted identity/time |
| 调度重复/弹窗 | 运营干扰 | hidden/IgnoreNew | contract test + task monitor |
| Vendor outage | run 中断 | hard failure | explicit retry, no silent fallback |
| 人员角色不独立 | 自我批准 | distinct fields | IAM and committee |
| 平台过度建设 | 成本和延迟 | staged roadmap | architecture thresholds |
| Agent 无增量价值 | 浪费成本 | 未评估 | A/B eval and removal criteria |

---

## 22. Kill Criteria

管理层必须预先定义停止、暂停或缩小项目的条件。

## 22.1 项目级暂停

- 无法取得与内部用途兼容的数据授权；
- 无法建立独立审批角色；
- 无法建立 clean source 和 Secret 安全；
- 真实 baseline 连续出现不可复现；
- 组织不愿承担 WORM、IAM 和保留责任；
- 没有明确内部用户愿意使用 research artifact；
- 运营成本持续高于批准预算且没有可测价值。

## 22.2 Strategy 候选退役

- 预注册门槛未通过；
- independent replay 失败；
- forward threshold 失败；
- data/feature lineage 无法恢复；
- execution capacity 不成立；
- trial budget 超限；
- 需要结果后修改阈值才能存活。

退役不等于删除，全部证据继续保留。

## 22.3 Agent 移除条件

- 固定 eval 不优于 deterministic-only；
- unsupported claim 持续高于阈值；
- repair-turn 率过高；
- 成本高于增量审查价值；
- 结果与其他 Agent 重复；
- 经常造成 review 冲突而不增加有效风险发现。

---

## 23. Build / Buy / Adopt 决策

| 能力 | 决策 | 原因 |
|---|---|---|
| Deterministic A-share engine | Build | 规则和审计是核心差异 |
| Python orchestration/gates | Build | 必须掌握业务真相源 |
| Pi Agent runtime | Adopt pinned | 不自建 LLM runtime |
| Experiment concepts | Adopt Qlib concepts | 不直接复制其数据/live 层 |
| Execution tests | Adopt LEAN concepts | 自建 A 股规则和 fixtures |
| Candidate loop | Defer RD-Agent concepts | 先完成真实治理和 forward |
| Experiment UI | Evaluate MLflow later | 当前 JSONL 足够，先解决 IAM/WORM |
| Data | Buy/license | 不自称拥有第三方数据权 |
| Identity/approval | Buy/use organization system | 本地 JSON 不能认证身份 |
| WORM/object lock | Buy/platform service | 不应自造法律不可变存储 |
| Observability | Adopt OTel semantics later | 先稳定 run fields |
| Broker/trading | Do not build | 永久在产品边界外 |

---

## 24. 路线图

时间窗口从外部责任人和预算正式到位时开始计算，不是无条件交付承诺。

## 24.1 0—30 天：可信基础

### 工程

- schedule schema；
- child env；
- Secret scan；
- PowerShell contract tests；
- acceptance docs；
- private Git candidate；
- full regression。

### 组织

- 指定 GM、Quant、Validator、Data、Platform、Model、Compliance；
- 明确 RACI；
- 选择组织审批和 Secret 系统；
- 启动数据授权和成本材料。

### 退出标准

- clean source；
- P0 engineering closed；
- no secret exposure；
- 172 tests/Mock；
- external evidence owner/deadline；
- no production schedule。

## 24.2 31—90 天：首个真实 baseline

- 完成四类外部证据；
- current Pi paid acceptance；
- Tushare data acceptance；
- one frozen momentum protocol；
- real Registry reserve/finalize；
- real 7/7；
- deterministic backtest；
- release/approval/archive；
- forward campaign；
- 不增加策略。

退出标准：一个可独立恢复的真实内部研究 baseline，不以表现好坏为条件。

## 24.3 3—6 个月：研究工厂

- provider adapter；
- Parquet/DuckDB；
- dataset catalog；
- execution differential suite；
- statistical controls；
- prompt/model registry；
- Agent A/B eval；
- three authorized research cycles；
- read-only status dashboard discovery。

退出标准：第二、第三个候选可以复用平台，不复制治理代码。

## 24.4 6—12 个月：组织化

- IAM/RBAC；
- Registry service；
- WORM/object lock；
- approval integration；
- independent validation workspace；
- observability export；
- DR exercise；
- multiple strategy protocols；
- candidate queue pilot。

退出标准：多用户、多策略仍保持 100% 注册、证据和角色分离。

---

## 25. 工作包与验收顺序

| WP | 工作包 | Owner | 依赖 | 主要产物 | Exit Evidence |
|---|---|---|---|---|---|
| WP-01 | P0 code hardening | Platform | 无 | schema/env/scan/tests | full regression |
| WP-02 | Source baseline | Platform/Security | WP-01 | private Git/tag | clean provenance |
| WP-03 | Data rights | Data/Compliance | 无 | agreement/evidence | approved v2 |
| WP-04 | Protocol | Quant/Validator | strategy freeze | external record | exact binding |
| WP-05 | Registry | Platform/Compliance | IAM/storage | registry/evidence | healthy ledger |
| WP-06 | Cost evidence | Quant/Reviewer | execution contract | materials/evidence | approved v1 |
| WP-07 | Runtime acceptance | Model/Platform | WP-02—06 | ping/contract | current real proof |
| WP-08 | Real baseline | Quant/Platform | WP-07 | run artifacts | 7/7 + integrity |
| WP-09 | Release/archive | Five roles | WP-08 | approval/archive | restore pass |
| WP-10 | Forward | Model/Validator | WP-09 | campaign | append-only status |
| WP-11 | Research factory | Architecture | three cycles | data/registry/eval | reusable platform |
| WP-12 | Organization scale | GM/Platform | WP-11 | IAM/WORM/dashboard | multi-user acceptance |

---

## 26. Go / No-Go 关口

## G0：继续开发

需要：P0 backlog 明确、内部用户和 owner 存在。  
当前：GO。

## G1：调用真实数据和模型

需要：clean source、四类 evidence、Secret isolation、预算。  
当前：NO-GO。

## G2：形成真实 baseline

需要：current health、real Registry、Tushare、Pi 7/7、deterministic validation。  
当前：NO-GO。

## G3：内部 release

需要：integrity、five-role identity approval、archive。  
当前：NO-GO。

## G4：forward schedule

需要：approved baseline、campaign、schema 3 checker、hidden task。  
当前：NO-GO。

## G5：扩大策略和 Agent

需要：至少三个授权周期、Agent A/B、multiple testing、组织控制。  
当前：NO-GO。

---

## 27. 架构决策原则

`docs/adr/` 已于 2026-09-06 建立，以下 12 条决策全部落为正式 ADR（索引与正文见 `docs/adr/README.md`），并由 `tests/test_ops_contract.py` 锁定索引完整性：

1. Python remains authoritative；
2. Pi production no-tools；
3. no automatic provider/model fallback；
4. evidence stays outside repository；
5. local JSONL until service threshold；
6. no broker/live execution；
7. data provider abstraction；
8. Mock never releaseable；
9. operator plugins never production；
10. identity/WORM are external organization services；
11. model/prompt changes require eval and approval；
12. failed experiments are retained。

每个 ADR 必须包含：背景、决策、替代方案、后果、owner、日期、review trigger。推翻任一 ADR 必须写新 ADR 并显式标注取代关系。

---

## 28. 外部设计依据

以下资料在 2026-08-30 复核，只作为架构和管理依据，不构成法律、投资或供应商授权意见：

1. [Pi Security Policy](https://github.com/earendil-works/pi/security)：Pi 是本地高权限 coding agent，不提供内建沙箱；skills/extensions 和 workspace 属于用户信任边界。
2. [Microsoft Qlib Recorder](https://github.com/microsoft/qlib/blob/main/docs/component/recorder.rst)：ExperimentManager—Experiment—Recorder 的实验分层和 run/metric/artifact 管理概念。
3. [QuantConnect LEAN Reality Modeling](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts)：fill、slippage、fee、capacity 等现实模型应可独立配置和验证。
4. [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent/blob/main/README.md)：hypothesis—implementation—experiment—feedback 的自动研究循环；本项目只在治理成熟后采用候选队列概念。
5. [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)：experiment、run、parameter、metric、dataset 和 artifact 的管理模型；是否引入需后续 build-vs-buy。
6. [NIST AI RMF Playbook](https://www.nist.gov/itl/ai-risk-management-framework/nist-ai-rmf-playbook)：Govern、Map、Measure、Manage 的全生命周期风险治理结构。
7. [OpenTelemetry Observability Primer](https://opentelemetry.io/docs/concepts/observability-primer/)：logs、metrics、traces、SLI 和 SLO 的统一观测思想。
8. [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)：V4 Pro 当前 off-peak/peak 价格和动态调整说明。
9. [Tushare 数据服务协议](https://tushare.pro/document/1?doc_id=405)：公开协议当前明确个人、不可转让、非商业用途，组织内部商业研究必须另取独立书面授权。
10. [Deflated Sharpe Ratio paper](https://doi.org/10.2139/ssrn.2460551)：selection bias、multiple testing、非正态和 backtest overfitting 的统计修正依据。

---

## 29. 评审方法与限制

- 本蓝图基于当前代码、测试、run、`ZCODE_PROJECT_HANDOFF.md` 和官方一手资料；
- 原计划使用五个子代理分别做总经理、量化、数据合规、平台 SRE 和 Pi 架构独立评审；
- 五个子代理均因账户 usage limit 直接失败，没有产生任何可用内容；
- 本文没有把“发起子代理”冒充为“完成独立评审”；
- 关键商业、数据授权、法律、身份、真实模型和真实数据判断仍必须由相应组织责任人确认；
- 时间窗口是管理规划，不是无条件工期承诺；
- 预期效果是运营目标，不是当前实现结果；
- 本文不构成真实资金交易建议。

---

## 30. 最终总经理决策

### 继续做什么

- 继续建设受治理研究 OS；
- 继续保持 Python 权威和 Pi no-tools；
- 继续完善 source、rights、protocol、registry、cost、execution、identity、archive 和 forward；
- 先交付一个真实、可复现、可退役的 baseline；
- 用研究质量、证据和运营指标管理项目。

### 暂停做什么

- 暂停新增生产 Agent；
- 暂停批量插件；
- 暂停自动因子/参数搜索；
- 暂停 dashboard 大建设；
- 暂停多策略扩张；
- 暂停任何真实数据 run，直到所有 G1 门禁通过。

### 永远不做什么

- 不在本项目接券商、订单和真实资金；
- 不自动给出真实资金操作建议；
- 不把 Mock、ping、配置或本地 hash 称为商业完成；
- 不绕过数据权利和独立审批；
- 不让 Agent 成为权威计算和发布决策者。

本项目最合理的长期形态不是“替人做投资决定的 Agent”，而是“让内部量化研究过程更真实、更可复现、更可审计、更容易被独立否证和及时退役的操作系统”。

这就是未来所有架构和投入选择的最高判断标准。

## 31. 2026-09-15 架构推进判断

本轮的战略重点不是增加模型、Agent 或插件，而是把源码可信链补成可落地的组织顺序：

`candidate manifest → hash-bound packet → external dual review → owner Git authorization → clean clone → G1 evidence review → paid/data acceptance → real baseline`

其中 `source-review-decision-verify` 只做结构、哈希、时效和字段完整性检查，不做身份认证，也不产生任何 Git、G1 或真实运行授权。这个边界必须在产品、运维、审计和管理层界面中保持一致。

从经营角度，本轮新增的价值有三点：

1. 将“有人说审过了”转化为可绑定精确候选的组织记录接口，同时保留身份认证在外部系统；
2. 将模板、机器校验、人工授权和真实运行拆成独立状态，减少误把准备工作当成商业完成的风险；
3. 将坏输入、损坏 packet 和自定义 receipt 环境错误转为可解释阻断，而不是静默降级或异常退出。

未来投入仍遵循 `权利与源码 > 科学验证 > 执行真实性 > 身份与审计 > 运营稳定性 > 界面 > Agent/插件扩张`。在 G1 前，不新增生产 Agent、不启用生产插件、不安装调度、不接入真实交易能力。
