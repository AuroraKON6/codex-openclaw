# Phase A Activation Pack

> 状态：READY FOR HUMAN/ORGANIZATION ACTIVATION  
> 日期：2026-08-31（Asia/Shanghai）  
> 目标：把 Phase A 从“代码候选”推进到“有真实 Owner、有外部原件、有预算决策的组织项目”  
> 当前 Gate：G0 GO；G1—G5 NO-GO  
> 禁止：不得用本包、示例 JSON、本地签名或 Agent 输出冒充真实批准

## 1. 使用方法

1. GM 指定真实组织角色；
2. 每个角色用组织身份接收对应任务；
3. 外部原件保存在仓库外受控系统；
4. 仓库中的 `.example.json` 只作为字段模板；
5. Platform 只保存原件路径、hash、状态和最小元数据；
6. Compliance/Validator 检查身份、时间、授权范围和 exact binding；
7. 所有证据通过后召开 G1，而不是直接运行真实 pipeline。

## 2. 角色激活表

不得预填或虚构姓名。由 GM 在组织系统中完成以下任命：

| 角色 | 必需身份 | 核心责任 | 不得兼任的审批 | 当前 |
|---|---|---|---|---|
| GM/Product Owner | 组织负责人 | 价值、范围、预算、Gate | 不代替专业审批 | UNASSIGNED |
| Quant Owner | 量化研究身份 | thesis、protocol、结果解释 | Independent Validator | UNASSIGNED |
| Independent Validator | 独立验证身份 | replay、challenge、退役建议 | Quant Owner | UNASSIGNED |
| Data Owner | 数据责任身份 | vendor、许可、quality、snapshot | 最终法律批准 | UNASSIGNED |
| Platform/SRE | 平台服务身份 | source、Secret、Registry、schedule | 全部 release 审批 | UNASSIGNED |
| Model/AI Owner | 模型责任身份 | Pi、prompt、eval、cost drift | 独立模型验证 | UNASSIGNED |
| Compliance/Legal | 合规或法务身份 | 用途、签署、发布、留存 | 数据申请人自批 | UNASSIGNED |
| Cost Reviewer | 独立成本复核身份 | 费率、执行、容量材料 | 策略/成本模型作者 | UNASSIGNED |
| Security/IT | 组织安全身份 | IAM、Secret、WORM、供应链 | 应用开发自审 | UNASSIGNED |

任命完成证据至少包括：姓名/组织 ID、角色、有效期、任命人、利益冲突声明和审批权限。上述信息不得随意提交到公开仓库。

## 3. E-01 数据授权申请包

**Owner**：Data Owner。  
**Accountable**：Compliance/Legal。  
**仓库模板**：`governance/data_license_evidence.example.json`。  
**运行手册**：`docs/DATA_LICENSE_RUNBOOK.md`。

### 3.1 供应商必须书面回答

- 被授权组织法定名称；
- 内部商业研究是否允许；
- 自动 API 调用是否允许；
- 允许的 endpoint；
- 本地缓存和点时快照是否允许；
- 衍生特征、回测和统计分析是否允许；
- 向 DeepSeek/Pi 传递哪些数据是否允许；
- 允许的处理实体和地区；
- 最大留存期；
- 合同终止后的删除/归档方式；
- 内部展示和外部分发边界；
- 供应商签署人、职位、时间和 reference。

### 3.2 接受条件

- 独立书面组织授权；
- 用途覆盖本项目实际处理；
- 有效期覆盖预期 run；
- permitted endpoint 覆盖七类接口；
- supporting document 在仓库外；
- SHA-256 与原件一致；
- 合规批准人真实且不同于申请人；
- 外部分发默认禁止；
- 不以公开个人非商业条款替代。

### 3.3 拒绝条件

- 仅有网页截图或聊天口头确认；
- 仅有个人账户条款；
- 未覆盖缓存、衍生分析或模型处理；
- 签署身份不可验证；
- 原件被放入源码仓库；
- 用本地 `APPROVED` 字段自我批准。

## 4. E-02 研究协议预注册包

**Owner**：Quant Owner。  
**Challenge**：Independent Validator。  
**监督**：Compliance。  
**仓库模板**：`governance/research_protocol_evidence.example.json`。  
**运行手册**：`docs/RESEARCH_PROTOCOL_RUNBOOK.md`。

### 4.1 首发 protocol 必须冻结

- 唯一 `protocol_id` 和版本；
- 研究 thesis 与可否证条件；
- CSI500 scope 和准确 universe 口径；
- date range、cutoff 和 point-in-time 规则；
- momentum 参数与 rebalance；
- 数据字段、复权、停牌、涨跌停和缺失处理；
- 费用、滑点、impact、容量、T+1 和整手；
- train/validation/holdout/walk-forward/forward；
- trial budget 和 parameter search count；
- 成功、暂停、独立复核和退役阈值；
- 精确 input hash；
- model contract hash；
- 禁止真实资金动作和外部分发。

### 4.2 接受条件

- 外部组织 system of record；
- 注册时间早于任何真实执行；
- Quant、Validator、Compliance 三名不同身份；
- exact input/model binding；
- supporting document 和 hash；
- 变更必须新版本，不能覆盖旧协议；
- 当前阶段仅一个 momentum baseline。

## 5. E-03 Experiment Registry 激活包

**Owner**：Platform。  
**批准**：Quant、Validator、Platform、Compliance 四方。  
**仓库模板**：`governance/experiment_registry_evidence.example.json`。  
**运行手册**：`docs/EXPERIMENT_REGISTRY_RUNBOOK.md`。

### 5.1 组织必须决定

- Registry 根路径或服务；
- 管理员、写入者、审阅者；
- 允许的 run class；
- append-only 机制；
- reservation/finalization 规则；
- 保留期；
- 备份、恢复、legal hold；
- IAM、时间源和审批；
- object lock/WORM 何时启用；
- incident escalation。

### 5.2 接受条件

- Registry 在仓库外；
- evidence 原件批准；
- 真实 ID 唯一；
- 真实 run 前可 `RESERVED`；
- 成功/失败/中断可 `FINALIZED`；
- reconcile 能发现 orphan、tamper 和未登记 run；
- 备份和恢复演练通过；
- 明确当前应用哈希链不是 WORM/数字签名。

## 6. E-04 执行成本证据包

**Owner**：Quant Owner。  
**Reviewer**：Independent Cost Reviewer。  
**监督**：Compliance。  
**仓库模板**：`governance/execution_cost_evidence.example.json`。  
**运行手册**：`docs/EXECUTION_COST_RUNBOOK.md`。

### 6.1 必需材料

- 佣金和最低佣金口径；
- 印花税、过户费及有效日期；
- 滑点和 impact 校准依据；
- 历史委托/成交或可接受的机构材料；
- sample order count；
- simulation notional；
- max participation rate；
- minimum daily amount；
- double-cost stress；
- A 股规则簿 hash；
- 独立复核意见；
- 90 天或更严格 freshness。

### 6.2 接受条件

- 非占位材料；
- 成本模型与 protocol 完全绑定；
- 作者与 reviewer 不同；
- 材料路径在仓库外；
- 原件 hash 一致；
- `live_execution_ready=false`；
- 任何过期或不匹配都阻断新 run。

## 7. S-01 源码基线包

**Owner**：Platform/Security。  
**准备文件**：`docs/SOURCE_BASELINE_PREPARATION.md`。

必须完成：

- candidate inventory；
- 人工文件审查；
- Secret scan；
- private repo；
- clean commit/tag/remote；
- dependency lock；
- clean-clone tests/Mock；
- source provenance；
- reviewer 分离。

本项目当前没有 HEAD，任何 health/run 在 source gate 失败是正确行为，禁止绕过。

## 8. B-01 预算申请包

### 8.1 本阶段申请范围

- private repository/IAM/Secret 基础能力；
- 数据授权评审；
- 当前 Pi paid ping；
- 最小真实 Agent contract；
- Tushare acceptance；
- 首个真实 baseline 的供应商上限；
- 独立验证和合规工时；
- Registry/storage/backup。

### 8.2 必需字段

- budget ID；
- 供应商；
- 单价基线和复核日期；
- 允许调用类型；
- 最大 token/request/storage；
- 单 run 上限；
- 项目周期上限；
- 预警阈值；
- 超限时硬失败；
- 有效期；
- 批准人；
- 禁止自动 provider fallback。

## 9. 系统选择决策表

| 能力 | 必须决定 | 最低要求 | 当前 |
|---|---|---|---|
| Private Git | 组织代码平台 | private、MFA、review、tag、backup | UNDECIDED |
| Secret Manager | 凭据系统 | 最小权限、rotation、audit | UNDECIDED |
| Approval | 组织审批系统 | 身份、时间、不可抵赖记录 | UNDECIDED |
| Registry | 目录或服务 | append-only、reserve/finalize、backup | UNDECIDED |
| Evidence storage | 原件与归档 | access control、retention、hash | UNDECIDED |
| WORM | object lock/受控存储 | trusted identity/time、legal hold | DEFERRED UNTIL DESIGN |
| Observability | logs/metrics/traces | run/experiment/provider correlation | LOCAL NOW / EXPORT LATER |

选择标准：优先使用已有组织系统，不为单个 baseline 先造大型平台；但本地 JSON 不能代替真实身份和组织批准。

## 10. G1 Readiness Meeting

### 10.1 参会角色

- GM；
- Quant；
- Validator；
- Data；
- Platform；
- Model；
- Compliance；
- Cost Reviewer；
- Security/IT（如涉及组织系统）。

### 10.2 必看证据

- clean source provenance；
- Secret scan receipt；
- E-01 data license；
- E-02 research protocol；
- E-03 Registry；
- E-04 execution cost；
- budget approval；
- Pi/Tushare acceptance plan；
- incident and rollback plan；
- no-trading boundary attestation。

### 10.3 G1 PASS 条件

- 所有证据来自真实外部/组织系统；
- 状态、有效期、身份、路径和 hash 一致；
- source clean；
- Secret isolation PASS；
- budget PASS；
- 没有职责冲突；
- 真实调用范围最小且可停止；
- 会议形成 signed decision record。

### 10.4 G1 NO-GO 条件

任一原件缺失、过期、占位、身份冲突、hash 不匹配、预算缺失或 source 不 clean，均保持 NO-GO。不得“条件通过后自动执行”；补齐后必须重新召开或重新签署。

## 11. 交付清单

Phase A 完成时必须有：

- [ ] 真实角色任命表；
- [ ] private source baseline；
- [ ] clean-clone 验收；
- [ ] E-01 approved；
- [ ] E-02 approved；
- [ ] E-03 approved；
- [ ] E-04 approved；
- [ ] B-01 approved；
- [ ] Registry/IAM/Secret/storage 决策；
- [ ] G1 signed decision；
- [ ] 所有未完成事项有 Owner 和决策日期；
- [ ] OpenClaw tasks 保持 Disabled；
- [ ] 无真实资金建议或连接。

## 12. 当前可立即转交的任务

| ID | 任务 | 接收角色 | 当前输入 | 期望输出 |
|---|---|---|---|---|
| A-01 | 建立 private source | Platform/Security | 工作区 + source prep | clean HEAD/tag/remote |
| A-02 | 申请数据授权 | Data/Compliance | E-01 | signed organizational evidence |
| A-03 | 预注册首个 protocol | Quant/Validator/Compliance | E-02 + input | external record |
| A-04 | 激活 Registry | Platform/Four roles | E-03 + runbook | approved registry |
| A-05 | 完成成本证据 | Quant/Reviewer/Compliance | E-04 + rulebook | approved v1 |
| A-06 | 批准 acceptance 预算 | GM/Finance/Model/Data | B-01 | budget record |
| A-07 | 召开 G1 | GM/Committee | A-01—06 | signed GO/NO-GO |

代码和 Agent 可以准备模板、验证结构、计算 hash 和检查一致性；它们不能完成 A-01 的真实建仓授权，也不能完成 A-02—07 的组织身份、法律、预算和审批责任。
