# 全项目主计划（Project Master Plan）

> 计划版本：v1.2  
> 编制与复核日期：2026-09-15（Asia/Shanghai）  
> 规划周期：12 个月，按门禁推进，不按日期强行放行  
> 项目定位：Governed Quant Research OS（受治理的量化研究操作系统）  
> 当前运行基座：Python deterministic control plane + Pi Agent `0.84.2` + DeepSeek V4 Pro  
> 当前总体状态：**G0 GO；G1—G5 NO-GO；真实商业研究 BLOCKED**  
> 永久边界：内部研究，不接券商、不路由订单、不管理真实资金、不得生成或执行真实资金交易建议

本文件是项目的执行与管理计划，不是实时运行状态源。真实状态必须由 Git、外部授权原件、Experiment Registry、run manifest、审批系统和归档证据共同证明。

关联文件：

- 战略与目标架构：`PROJECT_GM_STRATEGY_BLUEPRINT.md`；
- 接管与代码事实：`ZCODE_PROJECT_HANDOFF.md`；
- 商业门禁：`docs/COMMERCIAL_READINESS.md`；
- 部署验收：`docs/DEPLOYMENT_ACCEPTANCE.md`；
- 运行契约：`docs/PI_RUNTIME_CONTRACT.md`；
- 运维手册：`docs/OPERATIONS.md`；
- Phase A 激活包：`docs/PHASE_A_ACTIVATION_PACK.md`；
- Source baseline 准备：`docs/SOURCE_BASELINE_PREPARATION.md`；
- 机器可读规划状态：`governance/project_execution_status.json`。

---

## 1. 总经理执行摘要

### 1.1 总目标

在不建立真实交易能力的前提下，建设一套能把 A 股中证 500 内部量化研究变成以下标准流程的操作系统：

1. 数据和模型有权使用；
2. 源码、依赖、配置和输入可追溯；
3. 假设、样本、参数、试验预算和阈值在结果前冻结；
4. 每个真实实验先登记，再运行，再终态化；
5. 数据、信号、执行和绩效由 Python 确定性计算；
6. Pi Agent 只做解释、挑战、风险发现和终审，不改变权威指标；
7. 成功、失败、中断和退役实验全部留痕；
8. 发布必须通过独立验证、身份审批、完整性和恢复测试；
9. 发布后进入前向观察，不因回测表现自动升级；
10. 只有完成至少三个授权周期并证明平台可复用，才扩大策略和 Agent。

### 1.2 项目成功定义

项目成功不是“回测收益高”，而是：

> 一个内部研究候选能够在授权范围内，从预注册、真实数据、确定性计算、Pi 审查、独立复验、审批、归档到前向观察完整运行，并能由另一名合格人员在一个业务日内恢复和复验。

### 1.3 当前最短结论

- 软件候选和本地治理控制已具备较强基础；
- 当前没有可发布源码基线，没有组织级数据与证据授权；
- 任何真实 Tushare、真实 Pi 研究流水线和生产调度都必须继续硬阻断；
- 最快路径不是继续增加 Agent、策略或插件，而是并行完成源码基线和四类外部证据；
- 首个真实 baseline 完成前只维护单一冻结策略，不开展自动调参和候选扩张。

---

## 2. 2026-09-05 当前事实基线

### 2.1 本轮重新验证

| 项目 | 当前结果 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| `.\.venv\Scripts\python.exe -m unittest discover -s tests` | 172/172 PASS | 当前隔离环境中的单元和契约测试通过 | 不证明真实数据或商业 READY |
| `verify_quant_pipeline.ps1` | PASS；明确 **MOCK** 的 `20260905_105154_540` 为 7/7、27 文件、16 事件、完整性通过，release BLOCKED（17 项阻断） | 当前软件、Mock、完整性和阻断合同可用 | 不证明真实 Tushare、真实 Pi 研究或 release |
| `.\quant.ps1 python-runtime --require-ready` | PASS；Windows CPython 3.11.9；32 个锁定包；0 偏差、0 额外运行包 | 项目 `.venv`、user-site 隔离和当前 lock 绑定可用 | 不证明未来依赖安全、供应商可用或业务授权 |
| `.\quant.ps1 source-candidate --require-reviewable` | 140 文件、1,387,797 bytes、0 机器阻断、9 项人工 review flag | 候选可进入逐文件人工复核 | 不授权 stage、commit、tag、remote 或 release |
| `.\quant.ps1 source-review-packet` | PASS；生成 5 个 hash-bound 机器文件并拒绝覆盖 | Platform/Security 可按同一候选身份逐文件复核 | 不认证人员、不记录批准、不授权 Git |
| `.\quant.ps1 source-review-verify --packet-dir <DIR>` | PASS；检查固定文件、reparse、hash、候选身份和双角色控制 | 可发现 packet 与机器 manifest 不一致或控制弱化 | 应用 hash 不是签名，不认证人员或批准 baseline |
| `.\quant.ps1 project-readiness ...` | 13 项离线检查，4 PASS、9 BLOCKED；当前 G0/BLOCKED | 能一次列出 G1/Phase C 的全部源码、证据、组织和运行时前置项 | 不替代组织审批、真实 health 或付费验收 |
| `check_pi.ps1 -NoPing` | PASS | Pi `0.84.2`、Node `24.16.0`、模型目录和 no-tools 契约可用 | 本轮未付费 ping，不证明当前供应商调用 |
| Git HEAD | 不存在 | source gate 会正确阻断 | 无法形成可追溯真实 run |
| Git tracked files | 0 | 当前仍是提交候选集合 | 不构成源码基线 |
| Git remote | 0 | 未连接受控私有仓库 | 不具备备份、审查和来源链 |
| 工作树状态 | 37 个顶层未跟踪条目、140 个候选文件 | 项目内容仍在本地 | 未完成逐文件复核、纳管和最小提交审查 |
| Tushare Token | 未配置 | 不会误发真实数据请求 | 无真实 schema 7 数据验收 |
| 四类外部证据路径 | 未配置 | 商业门禁没有被绕过 | 无数据授权、预注册、Registry、成本原件 |
| OpenClaw 计划任务 | 3/3 Disabled | 旧 Gateway 不再自启动 | 不等于 Pi 真实研究完成 |
| 18789/18790 监听 | 0 | 旧 Gateway 端口未运行 | 不涉及 Pi CLI 可用性 |

### 2.2 当前 RAG 状态

| 域 | 状态 | 说明 |
|---|---|---|
| 本地工程质量 | GREEN | 166 测试通过；Python runtime、source candidate/review packet、核心硬门禁和离线 readiness 已实现 |
| 源码治理 | RED | 无 HEAD、tracked、remote |
| 数据权利 | RED | 无组织书面授权原件 |
| 研究协议 | RED | 无外部预注册原件 |
| Experiment Registry | RED | 无组织批准的真实 Registry |
| 执行成本证据 | RED | 无机构材料和独立批准 |
| Pi runtime | AMBER | 本地契约通过，本轮付费 freshness 未验证 |
| Tushare 数据 | RED | 无 Token、无真实快照 |
| 真实 baseline | RED | 当前 schema 7 的真实 Agent 成功数为 0/7 |
| 发布与归档 | RED | 无合格真实 run 和五方审批 |
| Forward lifecycle | RED | 无批准 baseline 和真实 campaign |
| OpenClaw 隔离 | GREEN | 三个旧任务禁用、旧端口无监听 |

### 2.3 当前门禁

| Gate | 当前 | 放行含义 |
|---|---|---|
| G0 继续开发 | **GO** | 允许本地工程、文档、测试、Mock 和无付费检查 |
| G1 真实数据/模型 | **NO-GO** | 未满足前不得真实调用 Tushare 或完整 Pi pipeline |
| G2 真实 baseline | **NO-GO** | 未形成合格的 Registry + 真实 7/7 + 确定性验证 |
| G3 内部 release | **NO-GO** | 未完成五方身份审批、完整性和归档恢复 |
| G4 前向调度 | **NO-GO** | 未建立批准 baseline、campaign 和生产调度证据 |
| G5 扩大策略/Agent | **NO-GO** | 未完成三个授权周期和 Agent A/B 评估 |

---

## 3. 项目范围

### 3.1 范围内

- A 股中证 500 内部研究工作流；
- 数据授权、点时快照、质量和 lineage；
- 冻结研究协议和试验预算；
- 确定性信号、回测、稳健性和执行模型；
- 七个 Pi Agent 的结构化研究审查；
- Experiment Registry、run manifest、事件链和证据包；
- 五方内部审批、归档、恢复和前向观察；
- 成本、SLO、风险、事件和模型变更管理；
- 后期只读运营视图和组织系统集成。

### 3.2 范围外

- 券商账户、API、下单、撤单、订单路由和资金管理；
- 实盘交易、跟单、自动投资组合管理；
- 对外投资建议、荐股、收益承诺和面向客户发布；
- 未授权新闻、Web、MCP、插件或数据抓取；
- 结果后自动调参、自动晋级和无限候选搜索；
- 用 LLM 输出替代数据、指标、审批和发布事实；
- 为了“跑通”静默切换 provider、模型、数据源或 Mock。

### 3.3 隔离要求

- 本项目继续使用当前独立工作区，不修改其他 OpenClaw 或业务项目；
- 旧 OpenClaw 任务保持 Disabled，不建立新的 Gateway 自启动；
- Pi 生产 turn 强制 no-tools、no-skills、no-extensions；
- 现有 5 个 skill 和 1 个 extension 只供锁定的 operator 流程使用；
- 当前目录名称虽然保留 `codex openclaw`，生产运行时唯一真相是 Pi；
- 建立私有仓库时建议使用清晰仓库名，但在绝对路径依赖审计前不移动本地目录。

---

## 4. 现实商业运行顺序

任何真实研究必须严格按以下顺序执行：

```text
内部需求与用途确认
  ↓
组织角色、预算和责任分离
  ↓
受控源码 baseline + Secret scan
  ↓
数据授权 + 研究预注册 + Registry + 执行成本证据
  ↓
当前 Pi/DeepSeek 付费 acceptance + Tushare 数据 acceptance
  ↓
Registry RESERVED
  ↓
冻结输入、快照、规则簿、成本、模型和试验预算
  ↓
Python 确定性数据/策略/回测/风险计算
  ↓
Pi 七 Agent 结构化审查
  ↓
Registry FINALIZED + manifest/事件链完整性
  ↓
独立复验和 challenge
  ↓
五方身份审批
  ↓
归档、恢复测试和内部 release
  ↓
前向 campaign
  ↓
达到最小样本后继续、暂停或退役
```

禁止跳步：

- 授权前不获取真实数据；
- 预注册前不观察结果；
- Registry reserve 前不运行实验；
- 确定性计算完成前不让 Agent 生成权威结论；
- 独立复验前不发布；
- 发布前不安装前向调度；
- 三个授权周期前不扩大策略和 Agent。

---

## 5. 关键路径与并行策略

### 5.1 关键路径

```text
WP-01 工程基线复核
  → WP-02 私有源码 baseline
  → WP-07 当前 runtime/data acceptance
  → WP-08 首个真实 baseline
  → WP-09 release/archive
  → WP-10 forward campaign
  → WP-11 研究工厂
  → WP-12 组织化平台
```

WP-03 至 WP-06 必须在 WP-02 进行时并行启动：

```text
WP-03 数据授权 ─────────────┐
WP-04 外部研究协议 ─────────┤
WP-05 真实 Experiment Registry ─┼→ WP-07
WP-06 执行成本证据 ─────────┘
```

### 5.2 当前真正的项目瓶颈

1. 平台责任人尚未建立 private Git baseline；
2. 数据、法务、量化、独立验证和合规责任人尚未提交外部原件；
3. 没有组织身份和审批系统承载真实签署；
4. 没有真实 Registry 存储和 WORM/保留决策；
5. 未批准当前付费模型与数据 acceptance 预算。

### 5.3 可继续进行的无外部依赖工作

- 维护 166 项及后续新增测试不回归；
- 保持 Mock E2E、Secret scan 和脚本契约通过；
- 整理 private repository 提交候选和忽略清单；
- 准备外部证据申请包和审批模板；
- 编写 ADR、RACI、预算表和风险登记；
- 建立 Agent 固定评估集，但不扩大生产 Agent；
- 设计执行差分 fixture，不使用未授权真实数据；
- 禁止借这些本地工作宣称真实 baseline 完成。

---

## 6. 工作流设计

## 6.1 WS-00 项目治理与 PMO

**目标**：让范围、责任、预算、决策和证据始终有人负责。

**Owner**：项目总经理/Product Owner。

**主要任务**：

1. 指定 Quant、Validator、Data、Platform、Model、Compliance 和 Cost Reviewer；
2. 记录哪些角色可由同一人实现、哪些审批必须分离；
3. 建立 issue、risk、decision、budget 和 evidence 五类台账；
4. 每周发布一页状态，只引用可验证证据；
5. 维护 G0—G5 决策记录；
6. 对范围变更执行影响分析和批准；
7. 管理暂停、恢复和终止决定。

**交付物**：

- 任命表；
- RACI；
- 项目章程；
- 风险与决策日志；
- 周报模板；
- Gate decision records。

**退出标准**：所有开放工作包都有 Owner、目标时间、依赖、证据路径和升级路径。

## 6.2 WS-01 源码、供应链与 Secret

**目标**：把当前 37 个顶层未跟踪条目（140 个候选文件）变成可审查、可恢复的受控源码基线。

**Owner**：Platform/Security。

**主要任务**：

1. 审核提交候选、`.gitignore`、生成物、outputs、cache、凭据和个人配置；
2. 执行自动 Secret scan，只记录规则、路径、行号和回执，不回显值；
3. 生成 hash-bound source review packet，由 Platform/Security 两个不同组织身份逐文件复核并记录例外；
4. 建立受控 private remote；
5. 创建最小 clean commit 和候选 tag；
6. 锁定 Python、Node、Pi 包和关键依赖；
7. 建立 branch protection、review 和 tag 规则；
8. 绑定 commit、lockfile、Secret receipt 和人工 review decision；
9. 在干净 clone 或隔离副本运行完整软件验收。

**禁止**：未经人工审查直接 `git add .`、提交 `.env`、token、outputs、缓存、真实授权原件或个人路径配置。

**退出证据**：

- clean HEAD；
- tracked file inventory；
- private remote；
- dependency lock；
- Secret scan pass receipt；
- clean-clone 166+ 全套测试与 Mock E2E；
- source provenance manifest。

## 6.3 WS-02 数据权利与数据产品

**目标**：在合法用途、接口、缓存、衍生处理、模型外发和保留边界内获取可复现数据。

**Owner**：Data Owner；Accountable：Compliance/Legal。

**主要任务**：

1. 明确组织、用户、内部商业研究用途和处理实体；
2. 取得独立书面组织授权，不能只使用公开个人非商业条款；
3. 明确 API 自动化、缓存、衍生特征、DeepSeek 处理、留存和终止处置；
4. 将原件保存在仓库外受控位置并记录 SHA-256；
5. 许可通过后由 Secret Store 注入 Tushare Token；
6. 执行七类接口的 schema 7 acceptance；
7. 建立 point-in-time universe、复权、停牌、涨跌停、新鲜度和覆盖检查；
8. 形成 immutable dataset snapshot 和数据目录；
9. 记录 vendor request、retry、版本和质量事件。

**退出证据**：approved v2 license evidence、Token 注入审计、真实请求日志、数据质量报告、snapshot hash、universe/date coverage。

## 6.4 WS-03 研究协议与独立验证

**目标**：防止结果后修改假设、样本、参数和成功阈值。

**Owner**：Quant Owner；独立挑战：Validator；监督：Compliance。

**主要任务**：

1. 选择唯一首发策略，本阶段保持 momentum baseline，不增加策略；
2. 冻结 thesis、universe、date range、feature、rebalance、成本、容量和规则簿；
3. 明确 train/validation/holdout/walk-forward/forward 边界；
4. 预先设定 trial budget、停止条件、通过阈值和退役条件；
5. 记录模型、prompt、input contract 和数据版本；
6. 在外部组织系统登记并取得不同身份批准；
7. Validator 在运行前检查 exact binding；
8. 运行后独立 replay，不允许 Quant Owner 自我验证；
9. 后续研究工厂加入 DSR、PBO 和多重检验控制。

**退出证据**：外部登记导出、时间戳、三名不同批准人、原件哈希、exact input/model binding、独立验证计划。

## 6.5 WS-04 Experiment Registry 与证据链

**目标**：保证每个真实实验先登记、后运行、成功失败都终态化。

**Owner**：Platform；共同责任：Quant、Validator、Compliance。

**主要任务**：

1. 选择仓库外受控 Registry 路径或组织服务；
2. 明确管理员、写入者、审阅者、保留期和备份；
3. 完成四方批准和 registry evidence；
4. 真实 run 前 `RESERVED`，完成或失败后 `FINALIZED`；
5. 对 orphan reservation、unregistered run 和 hash tamper 硬阻断；
6. 将 Registry ID 绑定 source、protocol、data、cost、model 和 run；
7. 执行 reconcile、restore 和 incident drill；
8. 明确当前应用哈希链不是 WORM 或数字签名；
9. 组织化阶段迁移到 IAM + object lock/WORM。

**退出证据**：批准的 Registry 原件、真实 reservation/finalization、healthy reconciliation、备份恢复、权限审计。

## 6.6 WS-05 执行模型与成本证据

**目标**：让费用、滑点、冲击、容量、T+1、整手、停牌和涨跌停不会被结果后调整。

**Owner**：Quant；独立批准：Cost Reviewer；监督：Compliance。

**主要任务**：

1. 固定执行模型 contract 和有效期 A 股规则簿；
2. 收集可引用的机构费率、委托或成本材料；
3. 明确佣金、印花税、过户费、滑点、impact、参与率和流动性下限；
4. 绑定资金规模假设，但不建立真实资金动作；
5. 独立复核材料、方法、版本和 90 天有效期；
6. 建立逐笔差分 fixture；
7. 覆盖部分成交、涨跌停、停牌、T+1、整手和容量场景；
8. 将差异逐项归因，不能只比较最终收益；
9. 成本证据过期时阻断新 run。

**退出证据**：approved v1 cost evidence、材料哈希、独立复核、规则簿 hash、逐笔差分测试报告。

## 6.7 WS-06 Pi Agent、模型与评估

**目标**：证明 Pi Agent 在不接触工具和凭据的情况下提供可量化增量价值。

**Owner**：Model/AI；平台控制：Platform；独立评价：Validator。

**主要任务**：

1. 维持 Pi `0.84.2` 和 `deepseek-v4-pro` 精确锁定；
2. 生产 child env 只传最小 allowlist；
3. 继续禁止 production skills/extensions/tools；
4. 在 G1 条件满足且预算批准后执行当前 paid ping；
5. 执行最小真实 Agent contract turn；
6. 验证 JSON-only、forbidden language、model identity、usage 和 cost；
7. 维护 prompt/model/eval registry；
8. 建立 deterministic-only、7-Agent、shadow challenger 三组 A/B；
9. 指标包括增量风险发现、错误主张、人工时间、成本和延迟；
10. 任何 Agent 未证明增量价值时删除或合并，不增加更多生产 Agent。

**退出证据**：current paid provider proof、model catalog、no-tools policy、contract response、usage/cost、固定 eval 报告。

## 6.8 WS-07 Pipeline、质量与可观测性

**目标**：让流水线在成功、失败、超时和恢复时都产生可信状态。

**Owner**：Platform/SRE。

**主要任务**：

1. 保持 Python DAG 是唯一业务编排；
2. 维护 schema、manifest、event chain 和 failure artifacts；
3. 维护 schedule installer/checker/runner 契约；
4. 禁止 real/direct/mock 静默切换；
5. 建立 run/experiment/provider/model/source 统一关联字段；
6. 记录 logs、metrics、traces、token、cost 和 duration；
7. 定义 SLI/SLO、MTTD、MTTR、RTO、RPO；
8. 演练锁竞争、陈旧 run、重复调度、篡改、恢复和 provider outage；
9. 确保 Windows 计划任务 hidden、IgnoreNew 且只在 G4 安装；
10. 每月确认 OpenClaw 任务仍 Disabled、旧端口无监听。

**退出证据**：full regression、Mock 7/7、完整性、故障演练、可观测性字段、SLO 报告。

## 6.9 WS-08 Release、归档与 Forward

**目标**：把一个合格 baseline 变成可恢复、可审批、可观察和可退役的内部研究资产。

**Owner**：GM/Release Committee；执行：Platform；挑战：Validator。

**主要任务**：

1. 生成绑定 run/manifest/input fingerprint 的 release candidate；
2. 验证无真实资金动作语言；
3. 完成 Data、Quant、Model、Platform、Compliance 五方身份审批；
4. 归档源码、环境、输入、数据快照、Agent 输出、指标和审批；
5. 从空目录恢复并执行独立检查；
6. 初始化固定起点的 forward campaign；
7. 只追加真实观察，不重写历史；
8. 按预注册阈值继续、暂停、独立复核或退役；
9. 达到 G4 后才安装生产调度；
10. 任何暂停或退役保留全部证据。

**退出证据**：五方审批、archive hash、restore pass、campaign、首条 forward status、调度验收。

## 6.10 WS-09 研究工厂与组织化平台

**目标**：在三个授权周期后，把一次性 baseline 升级为多候选可复用平台。

**Owner**：Architecture/GM。

**进入条件**：WP-10 完成、至少三个授权周期、无重大治理事故、内部用户确认价值。

**主要任务**：

1. provider adapter；
2. Parquet + DuckDB point-in-time layer；
3. dataset and artifact catalog；
4. DSR/PBO/trial-budget controls；
5. prompt/model registry and rollback；
6. Agent A/B and shadow challenger；
7. IAM/RBAC、审批 deep links、WORM/object lock；
8. independent validation workspace；
9. read-only dashboard；
10. governed candidate queue；
11. DR exercise；
12. 多策略 protocol，但每个策略单独预注册和验收。

**退出证据**：第二和第三候选复用同一治理层、多用户角色分离、100% 注册、WORM/IAM 验收、DR pass。

---

## 7. 工作包与依赖

| WP | 工作包 | 当前 | Owner | 依赖 | 退出证据 |
|---|---|---|---|---|---|
| WP-01 | P0 工程复核 | DONE/CURRENT PASS | Platform | 无 | 166 测试、锁定 Python runtime、Mock、脚本契约、离线 readiness |
| WP-02 | 私有源码 baseline | OPEN/AMBER-RED | Platform/Security | WP-01 | 机器 review packet 已就绪；仍需逐文件人工审批、clean HEAD/tag/remote/clone |
| WP-03 | 组织数据授权 | OPEN/RED | Data/Compliance | 角色任命 | approved v2 原件 |
| WP-04 | 外部研究协议 | OPEN/RED | Quant/Validator | 策略冻结 | external exact binding |
| WP-05 | 真实 Registry | OPEN/RED | Platform/Compliance | IAM/storage 决策 | approved healthy ledger |
| WP-06 | 执行成本证据 | OPEN/RED | Quant/Reviewer | execution contract | approved v1 材料 |
| WP-07 | Runtime/Data acceptance | BLOCKED | Model/Platform/Data | WP-02—06 | paid proof + real data QA |
| WP-08 | 首个真实 baseline | BLOCKED | Quant/Platform | WP-07 | real 7/7 + deterministic validation |
| WP-09 | Release/Archive | BLOCKED | Five roles | WP-08 | approval + restore pass |
| WP-10 | Forward campaign | BLOCKED | Model/Validator | WP-09 | append-only campaign |
| WP-11 | 研究工厂 | DEFERRED | Architecture | 3 个授权周期 | reusable second/third candidate |
| WP-12 | 组织化平台 | DEFERRED | GM/Platform | WP-11 | IAM/WORM/multi-user acceptance |

---

## 8. 阶段计划

### 8.1 时间定义

`T0` 不是本文日期，而是以下条件同时成立的日期：

- GM、Quant、Validator、Data、Platform、Model、Compliance 已任命；
- private repository、审批系统和外部证据 Owner 已确定；
- 数据、模型和基础设施预算已进入批准流程；
- 内部用户确认至少一个明确研究用途。

所有时间窗口从 `T0` 计算。法律、供应商和组织审批会改变日程，不能为了赶日期绕过门禁。

### 8.2 Phase A：动员与可信源码（T0—T0+10 个业务日）

**目标**：完成 WP-02，并正式启动 WP-03—06。

**任务**：

- 完成角色任命和 RACI；
- 建立 private repo、clean commit、tag 和 remote；
- 完成 Secret scan 和 clean-clone 回归；
- 选择审批、Secret、Registry 和证据存储系统；
- 发出数据授权、protocol、Registry、成本四类申请包；
- 批准 B0/B1 预算上限；
- 建立周报、风险和决策台账。

**Exit**：G0 持续 GO；source baseline PASS；四类外部证据均有 Owner、受理回执和预计决策时间；G1 继续 NO-GO。

### 8.3 Phase B：外部证据闭环（目标 T0+11—30 个业务日）

**目标**：完成 WP-03—06。

**任务**：

- 取得组织数据授权；
- 完成外部 protocol 登记；
- 建立真实 Registry 和四方批准；
- 完成执行成本证据和独立复核；
- 完成身份、保留、备份和 Secret 流程；
- 审查所有证据 freshness、hash 和 exact binding；
- 批准首个真实 acceptance 预算。

**Exit**：四类证据 PASS；无身份冲突；预算通过；才可召开 G1 decision。

### 8.4 Phase C：Runtime 与数据验收（目标 T0+31—45 个业务日）

**目标**：完成 WP-07，不产生策略发布结论。

**任务顺序**：

1. source/Secret/evidence preflight；
2. 当前 Pi/DeepSeek paid ping；
3. 最小无工具 Agent contract turn；
4. Tushare Token 受控注入；
5. 七类数据接口 acceptance；
6. PIT universe、覆盖、新鲜度和规则 QA；
7. 形成真实数据 snapshot；
8. 预算和供应商 usage 对账；
9. 所有 acceptance artifacts 归档。

**Exit**：G1 PASS；数据和模型真实验收通过；仍不得声明 baseline 或 release。

### 8.5 Phase D：首个真实 baseline（目标 T0+46—65 个业务日）

**目标**：完成 WP-08。

**任务顺序**：

1. Validator 确认 protocol exact match；
2. Registry `RESERVED`；
3. 冻结 source/data/rules/cost/model/prompt/input；
4. 执行单一策略真实 pipeline；
5. Python 完成确定性指标、稳健性和执行账本；
6. Pi 完成 7/7 结构化审查；
7. Registry `FINALIZED`；
8. manifest、event chain 和完整性检查；
9. 独立 replay 和差异解释；
10. 无论通过或失败，都保留结果并执行预注册处置。

**Exit**：一个可独立恢复的真实内部研究 baseline；结果方向不影响是否算流程完成。

### 8.6 Phase E：Release、归档与 Forward（目标 T0+66—90 个业务日）

**目标**：完成 WP-09、WP-10。

**任务**：

- release candidate；
- 五方身份审批；
- 完整归档；
- clean-room restore；
- forward campaign；
- 首次 forward status；
- 生产调度预览、安装和 checker 验收；
- 事件升级和暂停流程演练。

**Exit**：G3、G4 按证据分别决策；不得因 baseline 通过自动放行 forward。

### 8.7 Phase F：研究工厂（第 4—6 个月）

**目标**：完成 WP-11。

**进入条件**：至少三个授权运行周期，不是三个 Mock。

**重点**：provider adapter、PIT 数据层、执行差分、统计控制、Agent A/B、第二和第三候选复用。

**Exit**：新增候选不复制治理代码；三个周期都有完整 evidence、cost、incident 和 user-value 记录。

### 8.8 Phase G：组织化平台（第 7—12 个月）

**目标**：完成 WP-12。

**重点**：IAM/RBAC、WORM、approval integration、Registry service、独立验证工作区、只读 dashboard、DR 和候选队列。

**Exit**：多用户、多策略仍保持 100% 注册、完整证据和职责分离；才召开 G5 扩展决策。

---

## 9. 前 30 天详细行动表

| 窗口 | 动作 | Owner | 依赖 | 完成证据 |
|---|---|---|---|---|
| D0—D2 | 任命七类责任角色 | GM | 组织决定 | 任命表/RACI |
| D0—D3 | 确认内部用户、用途和非交易边界 | GM/Compliance | 用户访谈 | 项目章程 |
| D0—D5 | 审核 37 个顶层未跟踪条目（140 文件） | Platform/Security | 无 | inventory/review packet |
| D2—D7 | private repo、clean commit、tag、remote | Platform | 审核完成 | provenance |
| D3—D8 | clean-clone 测试、Mock、Secret scan | Platform | commit | 验收回执 |
| D0—D5 | 提交组织数据授权申请 | Data/Compliance | 用途确认 | 受理回执 |
| D0—D7 | 冻结首个 protocol 草案 | Quant/Validator | 策略选择 | review draft |
| D2—D10 | 选择 Registry/IAM/storage | Platform/Compliance | 组织系统 | 决策记录 |
| D2—D10 | 收集成本材料并独立复核 | Quant/Reviewer | execution contract | evidence draft |
| D5—D12 | 外部登记 protocol | Quant/Validator/Compliance | source hash | external record |
| D5—D15 | 初始化批准 Registry | Platform/Four roles | storage/IAM | registry evidence |
| D10—D20 | 四类证据交叉复核 | Compliance/Validator | 原件 | gate checklist |
| D15—D25 | 批准 paid/runtime/data acceptance 预算 | GM/Finance | evidence progress | budget record |
| D20—D30 | G1 readiness review | GM/Committee | WP-02—06 | signed decision |

如果外部证据在 D30 前未完成，项目保持 G1 NO-GO，时间窗顺延；不得用示例 JSON、本地自签名或口头确认替代。

---

## 10. 资源与角色规划

### 10.1 最小角色配置

| 角色 | 主要责任 | 最低独立性要求 |
|---|---|---|
| GM/Product Owner | 价值、范围、预算、优先级、Go/No-Go | 不代替专业签署 |
| Quant Owner | thesis、protocol、策略、解释 | 不得自任 Validator |
| Independent Validator | replay、统计挑战、退役建议 | 与 Quant 独立 |
| Data Owner | vendor、授权、质量、snapshot | 不自行解释法律授权 |
| Platform/SRE | source、runtime、Secret、Registry、schedule | 不自行批准 release |
| Model/AI Owner | Pi、model、prompt、eval、cost drift | 不改变确定性指标 |
| Compliance/Legal | 用途、身份、发布、保留、外发边界 | 必须有组织授权 |
| Cost Reviewer | 执行材料和模型独立复核 | 与策略作者分离 |
| Security/IT | IAM、Secret、WORM、供应链 | 与应用开发互查 |

同一人在开发期可以承担多个实现任务，但以下组合不得由同一身份同时批准：

- Quant Owner 与 Independent Validator；
- 数据申请人与最终合规批准人；
- Registry 管理员与所有四方批准人；
- Release 候选创建人与全部五方批准人；
- 成本模型作者与独立 Cost Reviewer。

### 10.2 预估投入结构

不在缺少组织费率时虚构金额。预算按以下篮子建立：

1. 数据授权与供应商；
2. 法务、合规和独立验证工时；
3. private source、IAM、Secret 和 WORM；
4. 平台、数据和研究工程；
5. Pi/DeepSeek API；
6. 存储、监控和备份；
7. 后期 dashboard 与集成。

### 10.3 预算门

| Budget Gate | 允许支出 | 前置条件 |
|---|---|---|
| B0 | 本地测试、文档、Mock | G0 GO |
| B1 | 当前 Pi paid ping 和最小 contract | source + evidence readiness + GM 批准 |
| B2 | Tushare acceptance 和首个真实 run | G1 PASS |
| B3 | 三个授权周期 pilot | 首个 release/forward 可用 |
| B4 | IAM/WORM/dashboard/规模化 | WP-11 价值证据 |

每个预算门记录：批准人、上限、有效期、供应商、计价基线、报警阈值和超限处置。

---

## 11. 项目 KPI 与 OKR

### 11.1 北极星指标

**可独立复现且证据完整的正式研究候选比例**。

不按收益方向删除失败候选，也不把 brainstorming 纳入分母。

### 11.2 第一阶段 OKR

**O1：建立可信项目基线**

- KR1：100% 提交候选经过人工清单和 Secret scan；
- KR2：建立 clean private HEAD/tag/remote；
- KR3：clean clone 全套测试和 Mock E2E 通过；
- KR4：所有外部阻断有真实 Owner、原件要求和截止决策点。

**O2：完成授权研究准备**

- KR1：四类外部证据全部批准；
- KR2：真实 Registry 能 reserve/finalize/reconcile；
- KR3：当前 Pi 和 Tushare acceptance 通过；
- KR4：未授权外部调用为 0。

**O3：完成首个真实 baseline**

- KR1：Registry 注册率 100%；
- KR2：失败/中断保留率 100%；
- KR3：真实 pipeline 7/7 且 deterministic validation 完成；
- KR4：独立 replay 和 archive restore 通过；
- KR5：Mock/real 错分为 0，Secret exposure 为 0。

### 11.3 运营 KPI

- gate lead time；
- evidence completeness；
- test pass and regression count；
- cost per real run；
- cost per accepted risk finding；
- pipeline p50/p95；
- Agent JSON contract pass；
- unsupported claim rate；
- independent replay pass；
- archive restore time；
- MTTD/MTTR；
- internal user adoption；
- retired candidate completeness。

### 11.4 不使用的 KPI

- 预计收益率；
- 预计 Sharpe；
- 策略通过率越高越好；
- Agent 数量；
- 插件数量；
- token 消耗量越多越好；
- 回测排名；
- 真实资金结果。

---

## 12. 质量与发布计划

### 12.1 每次源码候选最低检查

1. 全套 Python tests 全部通过；
2. 项目 Windows CPython 3.11 `.venv`、hash lock、包版本和 user-site 隔离通过；
3. PowerShell AST/contract 通过；
4. Secret scan receipt 与 commit 绑定；
5. Source candidate 逐文件机器清单通过并完成人工复核；
6. Mock E2E 明确标记 Mock；
7. manifest 和 event chain 完整；
8. Pi no-tools/no-skills/no-extensions 审计；
9. 文档中的测试数、run ID 和状态没有冒充当前证据；
10. 不存在 broker、order、real-money 能力；
11. OpenClaw 任务保持 Disabled；
12. 未通过 G1 时无真实外部调用。

### 12.2 真实 run 最低检查

- clean source；
- current Secret receipt；
- valid license/protocol/Registry/cost evidence；
- current rules/pricing/budget；
- approved Token and key injection；
- Registry RESERVED；
- exact model and no-tools；
- REAL_TUSHARE；
- 7/7 Agent contracts；
- deterministic metrics；
- robustness and execution acceptance；
- budget after buffer；
- Registry FINALIZED；
- manifest/event integrity；
- no funds-action language。

### 12.3 Release 最低检查

- 独立 replay；
- 五方身份审批；
- archive completeness；
- restore from clean location；
- release candidate 与 run/manifest/input fingerprint 一致；
- 没有未登记 experiment；
- 没有 orphan reservation；
- 没有未解决 CRITICAL incident；
- forward thresholds 已预注册；
- 外部分发保持禁止。

---

## 13. 风险管理

| ID | 风险 | 概率 | 影响 | Owner | 预防 | 触发处置 |
|---|---|---|---|---|---|---|
| R-01 | 无法取得组织数据授权 | 高 | 致命 | Compliance/Data | 尽早书面申请 | 暂停真实数据路线，评估其他合法 provider |
| R-02 | 源码含 Secret 或个人配置 | 中 | 高 | Security | inventory + scan + review | 停止提交、轮换凭据、事件调查 |
| R-03 | 角色无法独立 | 中 | 致命 | GM | 提前任命 | 不允许 release，缩小项目 |
| R-04 | protocol 结果后修改 | 中 | 高 | Quant/Validator | 外部预注册 | 候选作废并保留记录 |
| R-05 | Registry 只剩本地哈希 | 高 | 高 | Platform | IAM/storage 决策 | 不宣称 WORM，不放行组织化 |
| R-06 | 成本模型过于乐观 | 中 | 高 | Cost Reviewer | 材料 + 差分测试 | 重跑预注册流程，不补调结果 |
| R-07 | Pi 模型或输出漂移 | 中 | 中 | Model Owner | exact lock + fixed eval | rollback、暂停 Agent 变更 |
| R-08 | 数据质量/点时错误 | 中 | 高 | Data Owner | PIT snapshot + QA | run BLOCKED、数据事件 |
| R-09 | 自动调参导致过拟合 | 中 | 高 | Quant/Validator | trial budget + DSR/PBO | 退役候选，不扩大搜索 |
| R-10 | 插件供应链或工具越权 | 低 | 高 | Platform/Security | production disabled | 移除、轮换 Secret、审计 |
| R-11 | 调度重复或弹窗 | 中 | 中 | SRE | hidden/IgnoreNew/checker | Disable task、incident review |
| R-12 | 项目过度平台化 | 中 | 中 | GM | staged gates | 停止 dashboard/插件/规模化 |
| R-13 | 内部用户没有实际需求 | 中 | 高 | GM | 早期用途确认 | 暂停项目或只保留审计工具 |
| R-14 | 成本高于增量价值 | 中 | 中 | GM/Model | FinOps + Agent A/B | 删除 Agent 或缩小运行频次 |

---

## 14. Stop-the-Line 与 Kill Criteria

### 14.1 立即停止当前 run

- source 不 clean 或 commit 不匹配；
- Secret scan 失败；
- license、protocol、Registry 或 cost evidence 过期/不匹配；
- 未登记真实 experiment；
- model/provider/runtime 漂移；
- Tushare 数据未标记 REAL 或质量不合格；
- Agent 获得工具、skills、extensions 或额外 Secret；
- manifest、事件链、Registry 或 archive 完整性失败；
- 出现真实资金动作语言；
- 身份审批冲突；
- 预算超限；
- 任何静默 fallback。

### 14.2 暂停整个项目

- 无法取得适用的数据授权；
- 无法建立独立角色；
- 无法形成 clean source 和 Secret 安全；
- 真实 baseline 连续不可复现；
- 组织拒绝承担 IAM、WORM、备份和保留责任；
- 没有明确内部用户；
- 三个周期后可测价值不足以覆盖成本；
- 项目被要求转成真实交易或对外荐股系统。

### 14.3 退役而不是删除

任何候选、Agent 或功能被停止后，原始协议、实验、失败原因、审批和归档继续保留；不得通过删除失败记录改善指标。

---

## 15. 沟通与治理节奏

### 每周 Delivery Review

- 上周承诺与实际证据；
- WP 和 Gate 状态；
- 阻断、Owner 和升级；
- test/Mock/incident；
- 预算消耗；
- 下一周验收目标。

### 每个 Experiment Review

- protocol exact match；
- data rights and snapshot；
- Registry status；
- trial budget；
- execution/cost；
- deterministic result；
- Agent findings；
- independent challenge；
- final disposition。

### 每月 Model Risk Review

- prompt/model drift；
- Agent eval；
- unsupported claims；
- cost/latency；
- forward status；
- retirements；
- vendor/pricing freshness。

### 每季度 Steering Review

- 内部用户价值；
- 研究漏斗；
- 成本；
- 数据和模型供应商；
- 风险事件；
- 成熟度；
- continue/pause/kill。

---

## 16. 决策与变更管理

### 16.1 必须形成 ADR 的决策

1. Python remains authoritative；
2. Pi production no-tools/no-skills/no-extensions；
3. no broker/no order/no real-money boundary；
4. no silent fallback；
5. provider/data adapter strategy；
6. Registry storage and WORM path；
7. IAM and approval system；
8. prompt/model registry；
9. execution model versioning；
10. forward campaign lifecycle；
11. dashboard read-only truth-source rule；
12. local path and repository naming decision。

### 16.2 变更流程

任何涉及数据用途、策略协议、模型、prompt、执行、成本、阈值、审批、留存或 provider 的变更必须：

1. 提交 change request；
2. 说明原因、风险和受影响证据；
3. 更新版本和 effective date；
4. 由对应 A/R/C 角色批准；
5. 重新运行受影响测试与 acceptance；
6. 必要时建立新 experiment，不能修改旧结果；
7. 保留旧版本和 rollback 路径。

---

## 17. 外部与人工工作清单

这些事项不能由代码、Mock、Agent 或本地 JSON 代替：

| 事项 | 必须由谁完成 | 必需产物 | 当前 |
|---|---|---|---|
| private Git/remote | Platform/Security | repo、commit、tag、remote | OPEN |
| 组织数据授权 | Data + Legal/Compliance | 独立书面原件 | OPEN |
| 研究预注册 | Quant + Validator + Compliance | 外部登记导出 | OPEN |
| Registry 批准 | Quant + Validator + Platform + Compliance | 组织批准原件 | OPEN |
| 执行成本材料 | Quant + Cost Reviewer + Compliance | 机构材料和批准 | OPEN |
| Tushare Token | Data Owner/Secret Admin | 受控注入记录 | BLOCKED BY LICENSE |
| DeepSeek paid budget | GM/Finance/Model Owner | 预算批准 | OPEN |
| 五方 release 审批 | 五个组织身份 | 审批记录 | BLOCKED BY REAL RUN |
| WORM/IAM/保留 | IT/Security/Compliance | 组织系统配置 | DEFERRED TO SCALE |
| 内部用户验收 | Research users/GM | 使用反馈和价值记录 | OPEN |

---

## 18. 标准状态报告模板

每周只更新状态，不重写历史：

```text
Report date:
Overall RAG:
Current gate:
This-week accepted evidence:
This-week failed or blocked work:
Open WP / owner / target decision date:
External evidence status:
Test and Mock status:
Real calls performed and authorization IDs:
Incidents and exceptions:
Budget actual vs approved:
Decisions required:
Next-week exit criteria:
No-trading boundary confirmed: yes/no
```

状态规则：

- `DONE`：有可复验证据；
- `IN PROGRESS`：有 Owner 和正在产生的工作；
- `BLOCKED`：缺外部条件；
- `DEFERRED`：尚未达到进入门；
- `CANCELLED`：经正式决定不再做；
- 不使用“基本完成”“差不多”“已配置”替代验收。

---

## 19. 总体 Definition of Done

### 19.1 工程 DoD

- private clean source；
- dependency lock；
- Secret scan；
- full tests and Mock；
- Pi isolation；
- failure artifacts；
- operations and restore runbooks；
- no OpenClaw runtime drift。

### 19.2 首个真实 baseline DoD

- 四类外部证据；
- current paid runtime/data acceptance；
- Registry reserve/finalize；
- REAL_TUSHARE；
- schema 7 real 7/7；
- deterministic validation；
- trial-budget/robustness；
- independent replay；
- integrity；
- no funds-action language。

### 19.3 内部 release DoD

- 五方身份审批；
- archive and clean restore；
- release provenance；
- forward campaign；
- incident and suspension flow；
- no external distribution；
- no broker/order connectivity。

### 19.4 项目总目标 DoD

- 至少三个授权研究周期；
- 第二和第三候选复用同一治理平台；
- 100% experiment registration；
- 100% failed/interrupted retention；
- 100% release artifact integrity；
- 100% independent role separation；
- 0 unauthorized external calls；
- 0 Mock/real misclassification；
- 0 Secret exposure；
- 0 broker connectivity；
- 内部用户确认平台节省时间或提高风险发现；
- Agent A/B 证明保留的 Agent 有增量价值；
- 运营成本在批准预算内；
- 管理层完成 continue/scale/pause 决策。

---

## 20. 当前下一步动作（严格顺序）

1. **任命项目七类角色并确认独立审批约束**；
2. **使用 hash-bound packet 审查 37 个顶层未跟踪条目（140 文件），建立 private Git baseline**；
3. **启动数据授权、研究协议、Registry、执行成本四条外部证据线**；
4. **选择审批、Secret、Registry 和长期证据存储系统**；
5. **在 clean clone 重新运行全套测试、Mock 和 Secret scan**；
6. **冻结首个 momentum protocol，不增加策略或参数搜索**；
7. **批准当前 Pi paid acceptance 和 Tushare acceptance 预算**；
8. **四类证据全部通过后召开 G1，而不是直接运行**；
9. **G1 通过后先做 runtime/data acceptance，再做真实 baseline**；
10. **baseline 通过后再分别决策 release、archive、forward 和 schedule**。

当前最重要的项目动作不是写更多策略代码，而是把第 1—4 项变成组织里有名字、有日期、有原件、有责任的真实工作。

---

## 21. 总经理最终计划结论

项目采用“先可信、后真实；先单一 baseline、后研究工厂；先组织责任、后自动化扩张”的路线。

未来 90 天的唯一核心目标是：

> 在不建立交易能力、不绕过授权和审批的前提下，交付一个有 clean source、有四类外部证据、有真实数据和当前 Pi、有确定性计算、有七 Agent 审查、有独立 replay、有五方审批、有归档恢复和有 forward campaign 的首个内部研究 baseline。

在这个目标完成前：

- 不增加生产 Agent；
- 不批量安装插件；
- 不增加第二策略；
- 不自动调参；
- 不建设大型 dashboard；
- 不安装生产调度；
- 不生成真实资金买卖建议。

完成后也不自动扩张，必须用三个授权周期的质量、成本、风险和用户价值证据召开 G5 决策。

---

## 22. 2026-09-15 推进增量与下一执行批次

### 22.1 已落地的治理增量

1. 源码审查流程现在分为三层：机器生成并锁定 packet、外部 Platform/Security 双人 decision record、Gate Owner/Platform Owner 独立授权 Git baseline。任何一层都不能替代下一层。
2. `source_review.py` 对 review flag 做结构、重复和逐文件绑定校验，并把 packet 读取异常转成可审计的 BLOCKED 结果；这属于控制面加固，不改变研究算法或市场结论。
3. 离线回归脚本现在主动验证空白 decision template 必须保持 `TEMPLATE_NOT_EVIDENCE`，其验证命令必须返回退出码 `3`；因此“生成模板”不会被误报为“获得审批”。
4. 自定义 Secret receipt 可以通过 `--secret-receipt` 重新绑定验证，减少多环境部署时错误引用默认回执的风险。

### 22.2 本批次的验收口径

- 工程层：Windows CPython 3.11 项目环境、全量测试、PowerShell AST、Secret scan、source candidate、packet 和负向 decision smoke 全部通过；
- 运行层：Mock 7/7、manifest/event integrity 通过，release candidate 必须 BLOCKED；
- 商业层：无组织外部授权、无 clean HEAD/private remote、无真实 Tushare/Pi acceptance 时，G1—G5 必须保持 NO-GO；
- 安全层：不新增自启动、不恢复 OpenClaw、不接 broker/order、不输出真实资金买卖建议。

### 22.3 严格下一步顺序

1. 由 Platform/Security 使用最新 packet 完成候选清单逐文件审查，处理全部 review flags，并从组织系统导出 decision record；
2. 由 Gate Owner/Platform Owner 核验身份和同一候选哈希后，另行授权最小权限 private Git baseline，再做 clean-clone 验收；
3. 并行取得数据授权、研究预注册、Experiment Registry 和执行成本四类仓库外证据，均须有责任人、复核人、有效期和原件哈希；
4. 重新运行 offline readiness，只有所有 G1 前置项齐备时才召开 G1 决策；
5. G1 明确 GO 后，才在受控 Secret 中运行当前 Pi/Tushare acceptance，再以新 Run ID 执行首个真实 7/7；
6. 真实 baseline 通过后再讨论 release、archive、forward 和 schedule，不能倒序安装调度或扩张策略。

本增量不改变项目总目标：先交付一个可复现、可审计、可独立否证和可退役的 CSI 500 内部研究 baseline，始终不发展为交易或真实资金建议系统。
