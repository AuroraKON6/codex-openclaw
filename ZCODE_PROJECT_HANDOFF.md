# Zcode 项目接管主文档

> 文档用途：让 Zcode 在不依赖原开发者口头说明的情况下，准确理解项目总目标、现实商业边界、代码架构、已完成工作、当前证据、未完成事项、风险、下一阶段计划和验收标准。
>
> 生成日期：2026-08-29；最新增补：2026-09-15（Asia/Shanghai）  
> 项目绝对路径：`E:\闲鱼\codex openclaw`  
> 当前运行基座：Pi Agent，不再使用 OpenClaw 作为业务运行时  
> 研究范围：A 股中证 500 内部研究  
> 安全边界：没有券商接口、订单路由或真实资金账户，不得生成或执行真实资金交易建议
> 未来战略与目标架构：`PROJECT_GM_STRATEGY_BLUEPRINT.md`
> 全项目执行规划：`PROJECT_MASTER_PLAN.md`

---

## 0. 2026-09-05 当前接管增补

以下证据取代本文较早数字，详细权威状态见 `governance/project_execution_status.json`、`PROJECT_MASTER_PLAN.md` 和 `docs/DEPLOYMENT_ACCEPTANCE.md`：

1. 项目已固定为 Windows CPython `3.11`，使用 `.venv`；`requirements.in` 固定 3 个直依赖，`requirements.txt` 固定 32 个 transitive wheel 版本和 SHA-256。`bootstrap_python.ps1` 强制 hash/binary 安装、`pip check`、runtime contract 和测试。
2. `quant_agents/python_runtime.py` 拒绝 PATH/Anaconda Python、非 Windows/CPython 3.11、错误 `.venv`、user site、锁定版本偏差和额外运行包。门禁已接入 health、真实/Mock run、readiness、回归和 release。
3. `quant_agents/source_baseline.py` 与 `.\quant.ps1 source-candidate --require-reviewable` 生成逐文件候选清单；`source-review-packet` 绑定 manifest、review request、公式安全 CSV、说明和文件 hash，拒绝覆盖同名机器包；`source-review-verify` 检查固定文件、reparse、hash、候选身份和双角色控制弱化。应用 hash 不是签名。当前 140 个候选、0 机器阻断、9 项人工复核标记；状态只是可交给 Platform/Security 审查，不授权 `git add`、commit、tag、remote、真实 run 或 release。
4. 最新隔离环境回归为 **172/172 PASS**；19 个根 PowerShell 脚本 AST 通过。Mock summary 已强制按“私有源码基线 → 九角色/预算 → 四类外部证据 → 人工 G1 → 受控凭据和付费 acceptance → 首个真实 baseline”排序。最新明确 **MOCK** run `20260905_105154_540` 为 7/7、27 个 manifest 文件、16 个事件、完整性通过，release 按设计 BLOCKED（17 项）。
5. 离线 readiness 为 13 项：输入、Python runtime、Secret receipt、本地 Pi 共 4 项 PASS，其余 9 项 BLOCKED；`g1_authorized=false`、`real_run_authorized=false`。
6. Git 仍无 HEAD、tracked file 和 remote；37 个顶层未跟踪条目展开为 140 个候选文件。不得在未经 Platform/Security 逐文件复核时执行 `git add .` 或创建基线。
7. 下一实际关键路径不再是增加 Agent/插件/策略，而是：人工候选审查与 private baseline → 九角色和预算 → 数据授权、研究预注册、Registry、执行成本四类外部证据 → G1 人工决策 → 付费 Pi/Tushare acceptance → 首个真实 7/7 baseline。任何一步缺失均保持 NO-GO。

本增补未调用真实 Tushare、DeepSeek 或付费 Pi，不构成真实市场研究、发布授权或真实资金建议。

## 0.1 2026-08-29 Zcode 接管复核结论（历史）

本文档生成后、正式接管前，前一轮工作已完成本文 15.1 节全部 5 项 P0 工程修复，本文部分状态记录已落后于代码。Zcode 于 2026-08-29 复核确认：

1. **P0-1 schedule schema 漂移已修复**：`install_quant_schedule.ps1`（生成 schema 3）、`run_daily_research.ps1`（要求 schema 3）、`check_quant_schedule.ps1`（校验 schema 3，并完整复核 Registry 目录、`registry.json` SHA-256、Registry ID、campaign、approval、source commit 和 authorization hash）三者一致；`tests/test_schedule_contract.py` 已建立跨脚本契约测试。
2. **P0-2 Pi 子进程环境最小权限已实现**：`quant_agents/pi_client.py` 使用显式 `PI_CHILD_ENV_ALLOWLIST`（仅 Windows 系统变量、代理变量和 `DEEPSEEK_API_KEY`），`TUSHARE_TOKEN` 与外部证据路径不会进入 Pi 子进程环境。
3. **P0-3 自动 Secret 扫描已实现**：`quant_agents/secret_scan.py` + `tests/test_secret_scan.py`；README 和 source/release gate 均引用其回执。
4. **P0-4 验收文档已更新**：`docs/DEPLOYMENT_ACCEPTANCE.md` 含 2026-08-29 复核与 P0 加固节，记录 133/133 测试。
5. **P0-5 跨脚本 contract 测试已实现**：`tests/test_schedule_contract.py`（8 项，覆盖 installer/checker/runner schema 一致性）。

接管复核当日无费用基线实测证据：

- `python -m unittest discover -s tests`：**133/133 通过**（6.3s）。
- `python -m quant_agents skills-audit` / `extensions-audit`：0 error、0 warning。
- `python -m quant_agents secret-scan`：`status=passed`，回执 SHA-256 `94bf4339…539f11`，仅命中测试样例行（已带 reviewed 标记）。
- `check_pi.ps1 -NoPing`：Pi `0.84.2`、Node `24.16.0`、模型目录含 `deepseek-v4-pro`、全工具禁用通过；ping 明确跳过。
- `verify_quant_pipeline.ps1`：exit 0，`PASSED`；新 Mock run `20260829_191452_873` 7/7、27 manifest 文件、16 事件、完整性通过；Mock 发布候选 BLOCKED（17 项商业阻断，符合设计）。
- 静态复核：15 个 PowerShell 脚本 AST 解析通过；12 个项目 JSON（含 `pi_runtime/package-lock.json`）Python 标准解析全部有效。
- 已清理 16.3 节列出的 Temp 测试 Registry residue（精确目录 `quant-registry-acceptance-aa61a23d0bfe4b189880bd0607d76a87`，删除前已验证唯一性与测试产物性质）。

**仍然 BLOCKED 的不变**：商业四类外部证据、Tushare Token、当前付费 Pi 重验、真实 7/7、五方审批、clean commit/tag、私有 remote、生产调度安装均未完成。下文 15.2、15.3 和 17 节的计划保持有效，15.1 的 P0 清单仅作历史记录保留。

### 0.1 2026-09-06 第二轮推进记录（ADR、CI、契约测试、缺陷修复）

本节为 2026-09-06 夜间自主推进的当前记录。期间工作区已被 9 月 2 日前后的会话大幅推进（新增 `bootstrap_python.ps1`/`quant_python.ps1`/`quant.ps1`/`lock_python_dependencies.ps1`、CPython 3.11.9 venv、hash-locked `requirements.txt`、`source_baseline.py`/`source_review.py`/`python_runtime.py` 及配套 `source-candidate` 源码评审工作流，测试从 133 增至 172）。

1. **修复遗留缺陷**：`quant_agents/source_review.py` 的 `verify_source_review_packet` 后半段验证逻辑（88 行，含 packet_id 校验、控制声明、清单核对与返回 dict）被错位到 `_decision_result` 的 return 之后成为不可达死代码，导致 `verify_source_review_packet` 返回 None、5 项测试 ERROR。已将代码块移回原位，172/172 测试通过。
2. **`.mimosa/` 加入 `.gitignore`**：mimosa 安全扫描 hook 在工作区生成 1882 个状态文件，不清除将使未来 clean source gate（`git status --porcelain` 为空）永远无法满足；加入后 untracked 从 2044 降至 159。
3. **建立 `docs/adr/`**：按蓝图第 27 节落成 ADR-0001 至 ADR-0012 共 12 条架构决策记录 + 索引，全部含背景/决策/替代方案/后果/Owner/日期/复审触发；蓝图第 27 节已更新为"已建立"。
4. **零付费 CI**：新增 `.github/workflows/ci.yml`（windows-latest：venv 3.11 → 安装 hash-locked requirements → `verify_quant_pipeline.ps1` 全离线验证），CI 永不调用付费 LLM、市场数据或调度安装；蓝图 14.1 第 8、10 项标记完成。
5. **新增 `tests/test_ops_contract.py`（11 项）**：锁定 disable_legacy 精确三任务/两端口且永不强杀进程、ops console 无自启动且仅挂载已审计只读 extension、daily runner 永不 Mock 回退、quant_python/bootstrap 锁定 3.11 venv、verify 脚本与 CI 无付费命令、ADR 索引与文件一一对应。测试总数 172 → 184。
6. 本轮全程零外部调用、未建 remote、未 commit、未安装调度。

**验证证据（2026-09-06，venv CPython 3.11.9）**：`unittest` 184 项通过；`secret-scan` 回执 passed；`verify_quant_pipeline.ps1` exit 0 PASSED（详见验收文档新节）；15+ 根 PowerShell AST 全过；项目 JSON 全部有效。

---

## 1. 接管前必须先理解的一句话

**这是一个“软件能力和本地治理控制已基本成形，但真实商业运行仍被源码基线、数据授权、外部预注册、实验登记、执行成本证据和 Tushare 组织凭据正确阻断”的内部研究项目。**

当前不得把以下任何一项描述为“真实量化研究已经完成”：

- Pi 已安装；
- DeepSeek API Key 已被环境检测到；
- Pi 模型目录里能看到 `deepseek-v4-pro`；
- 一次 `ping` 返回成功；
- Mock 7/7 Agent 成功；
- Python 回测代码存在；
- 外部证据的示例 JSON 存在；
- 本地审批草稿存在；
- 某个哈希链本地校验通过。

只有真实授权条件、真实数据、真实 Pi 7/7、确定性回测、全部门禁、独立审批和前向观察均形成可核验证据后，才能称为“内部研究基线完成”。即使到那一步，也仍然不是实盘系统或投资建议系统。

---

## 2. 项目身份与当前结论

| 项目项 | 当前事实 |
|---|---|
| 项目名称 | CSI 500 Pi 多 Agent 可审计研究流水线 |
| 工作区 | `E:\闲鱼\codex openclaw` |
| 目录名为何仍含 openclaw | 为避免路径迁移和旧证据失效而保留；业务运行时已经迁移到 Pi |
| Python run schema | `7` |
| Pi 包 | `@earendil-works/pi-coding-agent@0.84.2` |
| Node 最低要求 | `>=22.19.0` |
| 当前本机 Node | `24.16.0`（2026-08-29 无付费检查） |
| 目标模型 | `deepseek/deepseek-v4-pro` |
| 数据源 | Tushare Pro，必须先取得覆盖实际用途的组织授权 |
| 指数代码 | `000905.SH` |
| Agent 数量 | 7 个独立、一次性、无工具 Pi turn |
| 权威计算层 | Python；LLM 不拥有数据、信号、绩效或门禁的最终决定权 |
| 当前技术状态 | 本地回归通过，代码属于内部部署候选 |
| 当前商业状态 | **BLOCKED** |
| 当前生产监控等级 | **CRITICAL**，原因是最新真实请求未完成且已经超过 36 小时时效阈值 |
| 当前真实市场结论 | **没有形成** |
| 当前生产调度 | **未安装** |
| OpenClaw 状态 | 三个旧任务均 Disabled，`18789/18790` 无监听 |
| 券商/真实交易能力 | 不存在，且业务控制强制为 false |

### 2.1 2026-08-29 当前最可靠的状态摘要

1. `verify_quant_pipeline.ps1` 当前完整执行通过。
2. 111/111 单元测试通过。
3. 最新 Mock run 为 `20260829_012811_085`：7/7 Agent、27 个 manifest 文件、16 个事件链记录、完整性通过。
4. 该 run 明确是 **MOCK**，回测验收与稳健性均为 `NOT_APPLICABLE_MOCK`，发布候选按设计为 `BLOCKED`。
5. 最新真实请求仍是 `20260826_165505_647`：源码门禁失败，0/7 Agent，0 Token，0 供应商成本，没有调用 Tushare，也没有调用真实 LLM。
6. 当前完整 health 在 source gate 立即失败：仓库没有 committed HEAD、没有 tracked source；添加本交接文档前有 115 个未跟踪项，添加后当前为 116 个。
7. 当前 Pi 本地 runtime 检查通过；本轮明确使用 `-NoPing`，没有产生新的付费 LLM 证据。
8. 当前进程环境能检测到 DeepSeek API Key，但未显示、未写入文档；Tushare Token 和四类外部证据路径均未配置。
9. ~~当前最重要的代码缺口之一：`check_quant_schedule.ps1` 仍按 deployment authorization schema `2` 校验，而安装器和 daily runner 已升级到 schema `3`。~~ **已修复（见第 0 节）**：三个脚本现一致使用 schema 3，checker 并完整复核 Registry/approval/campaign/source 绑定。
10. ~~`docs/DEPLOYMENT_ACCEPTANCE.md` 仍保留旧的 102 测试、旧 run 和旧未跟踪文件数量，不能当作当前验收报告。~~ **已更新（见第 0 节）**：该文档新增 2026-08-29 复核与 P0 加固节，记录 133/133 测试；旧节标注为历史快照。

---

## 3. 总目标、成功定义与非目标

## 3.1 总目标

建立一个符合现实组织运行顺序的、可审计、可复现、不可静默降级的 A 股中证 500 内部量化研究生命周期：

1. 先确认源码、权限、数据许可和研究协议；
2. 再登记实验，防止只保留成功结果；
3. 再采集点时数据和执行确定性研究；
4. LLM 只做结构化解释、反证和终审；
5. 对每个成功、失败和中断 run 留下完整审计证据；
6. 通过独立人员审批后，进入仓库外前向观察；
7. 永远不从研究流程自动升级到真实资金交易。

本项目的北极星不是“让 Agent 自动赚钱”，而是：

> **让每一个研究结论都能回答：谁批准了数据用途、假设何时冻结、用了哪个源码版本、用了哪些点时数据、采用了什么执行规则、模型说了什么、Python 实际算了什么、成本多少、哪些门禁通过、哪些失败结果被保留、谁批准进入下一阶段。**

## 3.2 分阶段成功定义

### 阶段 A：软件候选

- 全量测试、编译、脚本语法、skill/extension 哈希审计通过；
- Mock 7/7 只证明控制流和产物完整；
- Mock 永远不能进入 release；
- 无外部 API 调用也能验证失败顺序和审计产物。

当前状态：**已达到，但存在调度 schema 检查缺口和若干上线前加固项。**

### 阶段 B：授权真实基线

- clean committed source；
- 有效数据授权；
- 外部研究预注册；
- 外部 Experiment Registry 完成 `RESERVED` 和 `FINALIZED`；
- 有效执行成本证据；
- 真实 Tushare 点时快照；
- 真实 Pi/DeepSeek 7/7；
- Python 回测与稳健性通过；
- 预算、manifest、事件链、安全语言检查通过。

当前状态：**BLOCKED，尚未达到。**

### 阶段 C：内部发布候选

- 数据、量化、模型、平台、合规五个不同角色完成可认证审批；
- 审批绑定 run、manifest snapshot、源码、输入和 Registry；
- `external_distribution_approved=false`；
- 归档、恢复验证和保留策略形成证据。

当前状态：**BLOCKED，尚无合格真实 run。**

### 阶段 D：前向观察

- 从已批准真实基线创建仓库外 campaign；
- 每次 observation 只允许追加，不改写历史；
- 只使用预注册截止日后的路径；
- 达到阈值最多进入独立验证，不能自动进入真实交易。

当前状态：**BLOCKED，尚无合格 baseline。**

## 3.3 明确非目标

- 不接券商；
- 不提交订单；
- 不管理真实资金；
- 不输出真实资金操作方向；
- 不抓取未授权新闻、网页或社交媒体内容；
- 不让 LLM 自主改参数后复用旧实验协议；
- 不让 LLM 计算或覆盖权威绩效；
- 不自动安装一堆 Pi 插件；
- 不让 Mock 自动替代任何真实失败；
- 不因本地 JSON 审批文件存在而宣称组织身份已认证。

---

## 4. 现实商业责任与严格运行顺序

## 4.1 责任角色

| 角色 | 主要职责 | 不能替代的角色 |
|---|---|---|
| 平台负责人 | 源码、依赖、密钥扫描、运行环境、Registry 存储、调度、归档、恢复 | 不能替代数据授权、模型验证和合规 |
| 数据负责人 | 数据服务账户、接口权限、来源、覆盖率、缓存和快照 | 不能替代法务授权 |
| 法务/合规负责人 | 数据用途、处理者、留存、终止处置、内部研究边界 | 不能替代量化或平台验收 |
| 量化负责人 | 假设、因子、样本、参数、执行假设、阈值、结果解释 | 不能自己兼任独立模型验证 |
| 独立模型验证人 | 反证、复现、阈值和模型生命周期评审 | 不能与量化负责人是同一人 |
| 模型负责人 | Pi/DeepSeek 版本、提示词、输出契约、漂移和模型风险 | 不能替代数据许可 |
| 独立成本复核人 | 佣金、滑点、冲击、容量和材料核验 | 不能由策略作者自批 |

本地软件只校验角色字段、不同人员、哈希和日期，不能认证真实人员身份或电子签名。生产必须接组织 IAM、审批工单或签名系统。

## 4.2 真实运行的强制顺序

```text
P0  受控私有 Git clean commit/tag
 ↓
P1  数据组织授权证据 v2
 ↓
P2  精确输入 + 冻结模型契约的外部研究预注册 v1
 ↓
P3  外部 Experiment Registry 预登记 RESERVED
 ↓
P4  有效期 A 股规则簿 + 执行成本校准证据 v1
 ↓
P5  配置与价格/预算基线检查
 ↓
P6  Tushare health 与点时数据采集
 ↓
P7  Pi runtime/version/model/no-tools + 真实 DeepSeek ping
 ↓
P8  七 Agent DAG + Python 确定性信号/回测
 ↓
P9  Experiment Registry 终态 FINALIZED
 ↓
P10 holdout + 三折 walk-forward + 成本/时滞压力 + 预算
 ↓
P11 state/summary/metrics/alerts/manifest/event chain/integrity
 ↓
P12 五方内部评审批准
 ↓
P13 外部归档与恢复复验
 ↓
P14 仓库外 forward campaign
 ↓
P15 经授权的隐藏 Windows 日常调度
```

### 为什么顺序不能改

- Source 必须最先：不允许未版本化代码产生付费或数据外部调用。
- License 必须先于 Tushare：Token 存在不等于用途合法。
- Protocol 必须先于数据结果：避免看到结果后改假设和阈值。
- Registry 必须在 Tushare/Pi 前 `RESERVED`：失败实验也必须进入账本。
- Cost evidence 必须先于回测：不能看到表现后反向选择成本。
- Pi 在数据和确定性控制之后：Agent 不能绕过 Python 权威层。
- Release 必须在完整性之后：审批必须绑定不可变快照。
- Forward campaign 必须在真实 baseline 批准后：不能拿 Mock 或失败 run 建 campaign。

---

## 5. 系统架构

## 5.1 分层架构

| 层 | 组件 | 权限与职责 |
|---|---|---|
| 输入层 | `strategy_round.example.json`、未来受控输入 | 定义研究范围、因子、执行和验证契约；示例不是批准协议 |
| 治理层 | `governance.py`、`research_protocol.py`、`experiment_registry.py`、`execution_cost_governance.py` | 在外部调用前硬阻断不合规 run |
| 数据层 | `data_client.py` | Tushare 点时成分、交易日、行情、复权、涨跌停、停牌、估值；记录请求和快照 |
| 规则层 | `market_rules.py`、`a_share_market_rules.json` | 有效期交易规则、费用、整手、T+1、板块申报数量 |
| 确定性研究层 | `research_engine.py`、`backtest_validation.py`、`backtest_assurance.py` | 计算信号、订单、成本、绩效、holdout、walk-forward、压力矩阵 |
| Agent 层 | 7 个 Pi Agent | 只输出结构化 JSON，用于解释、反证和终审 |
| 运行控制层 | `orchestrator.py`、`operations.py` | 锁、幂等、依赖、预算、超时、恢复、alerts、事件链 |
| 发布层 | `release.py` | 完整性、发布候选、审批、归档、恢复、保留计划 |
| 生命周期层 | `forward_observation.py`、`scheduling.py` | 前向 campaign、观察账本、调度输入和状态迁移 |
| 运维辅助层 | 5 个 Pi skills、1 个只读 extension | 仅供人工 operator；生产 Agent turn 全部禁用 |

## 5.2 权威边界

### Python 拥有最终权威

- 数据请求和快照；
- 成分股点时选择；
- 动量信号；
- 回测订单和持仓；
- 费用、滑点和冲击；
- 绩效指标；
- 数据质量；
- 稳健性和预算门禁；
- 发布与前向生命周期决定。

### Pi/DeepSeek 只能做

- 根据冻结输入提出研究假设；
- 对 Python 数据摘要做结构化归纳；
- 解释 Python 生成的信号和绩效；
- 识别风险、证据缺口和反例；
- 生成图表规范；
- 输出终审 JSON 和研究性总结。

### Pi/DeepSeek 不能做

- 直接访问 Tushare；
- 使用 shell、浏览器、MCP 或任意 tool；
- 修改项目文件；
- 计算权威绩效；
- 覆盖 Python 指标；
- 指示真实资金动作；
- 自动批准发布；
- 自动创建前向 campaign；
- 自动安装插件或后台任务。

## 5.3 生产 Pi turn 的隔离策略

`quant_agents/pi_client.py` 固定以下安全参数：

- `--mode json`
- `--no-session`
- `--no-tools`
- `--no-extensions`
- `--no-skills`
- `--no-prompt-templates`
- `--no-themes`
- `--no-context-files`
- `--no-approve`
- `--offline`

同时设置：

- `PI_CODING_AGENT_DIR` 指向项目隔离 state；
- `PI_OFFLINE=1`；
- `PI_TELEMETRY=0`；
- provider 必须是 `deepseek`；
- model 必须精确匹配 `deepseek-v4-pro`；
- 最终 stop reason 必须正常；
- 输出必须是一个 JSON object；
- 检测到 tool activity 立即失败；
- 输出契约失败最多进行一次独立修复 turn，并把两次用量合并计入预算。

### 必须修复的最小权限问题

当前 `_environment()` 从父进程复制完整环境，再覆盖 Pi 自身变量。未来如果配置了 `TUSHARE_TOKEN`、证据路径或其他不相关 Secret，它们也会出现在 Pi 子进程环境中。虽然生产 turn 无工具，这仍不符合最小权限原则。

Zcode 应在真实 run 前完成：

1. 构造显式 allowlist 的 child environment；
2. 只保留 Node/系统运行必需变量与 DeepSeek provider 必需凭据；
3. 明确移除 `TUSHARE_TOKEN`、外部证据路径和其他项目 Secret；
4. 增加测试，证明 Pi 子进程环境不含数据凭据；
5. 不在日志中输出任何 Secret 值。

---

## 6. 七 Agent DAG 与职责

## 6.1 依赖图

```text
research_lead ─────────────────────────────────────┐
                                                  │
data_agent ──> strategy_agent ──> backtest_agent ─┼─> risk_agent
      │              │                 │           │       │
      │              └─────────────────┴───────────┘       │
      │                                                    v
      └──────────────────────────────> visualization_agent ─┐
                                                            v
                                                      review_agent
```

代码中的实际依赖：

- `research_lead`: 无依赖；
- `data_agent`: 无依赖，但真实模式内部调用 Python 数据层；
- `strategy_agent`: 依赖 `data_agent`；
- `backtest_agent`: 依赖 `data_agent`、`strategy_agent`；
- `risk_agent`: 依赖 `research_lead`、`data_agent`、`strategy_agent`、`backtest_agent`；
- `visualization_agent`: 依赖 `strategy_agent`、`backtest_agent`、`risk_agent`；
- `review_agent`: 依赖全部前六个 Agent。

任何依赖失败都会阻断下游。失败 run 不原地继续，修复后必须生成新 Run ID，并用 `request_id` 和 `retry_of` 记录关系。

## 6.2 Agent 职责与输出

| Agent | Pi role | 主要输出 | 权威限制 |
|---|---|---|---|
| `research_lead` | `quant-research-lead` | 宏观摘要、行业趋势、风险、研究优先级、触发等级、置信度 | 不能引入未提供的实时宏观事实 |
| `data_agent` | `quant-data-agent` | universe、样本、市场统计、质量、快照标识 | 数据由 Python/Tushare 提供，LLM 不能伪造 |
| `strategy_agent` | `quant-strategy-agent` | 策略名称、类型、研究分类信号、过滤、频率、风险估计 | 信号值由 Python 覆盖/约束 |
| `backtest_agent` | `quant-backtest-agent` | 回测区间、收益、Sharpe、回撤、胜率、摘要 | 权威指标来自 Python deterministic engine |
| `risk_agent` | `quant-risk-agent` | 风险等级、风险分数、风险因素、warnings | 不得把风险解释变成资金动作 |
| `visualization_agent` | `quant-visualization-agent` | chart specs、布局、summary visual | 实际图表由本地 Python 生成 |
| `review_agent` | `quant-review-agent` | 结论、触发等级、风险、人工问题、下一步、置信度、免责声明 | 禁止真实资金操作语言；不能批准发布 |

## 6.3 输出契约

- 所有 Agent 输出必须是有效 JSON object；
- 不能只回答 ready、pong 或“等待任务”；
- 不得虚构缺失的市场事实或绩效；
- 禁止真实资金动作语言；
- review 必须包含明确的研究免责声明；
- 原始 JSONL、结构化输出、Pi metadata、prompt hash、usage、provider、model、response/session identity 都写入 run 目录。

---

## 7. 当前研究协议示例的真实含义

当前 `strategy_round.example.json` 是**软件验收输入**，不是组织批准的生产研究协议，也不是市场结论。

## 7.1 当前示例内容

| 项目 | 当前示例 |
|---|---|
| 主题 | CSI500 价格动量研究验证 |
| 历史区间 | 2025-01-01 至 2025-05-30 |
| 因子 | 20 个交易日 momentum |
| 调仓 | 双周 |
| 最大持仓数 | 20 |
| 每个成分快照研究样本 | 40 |
| 聚焦行业文本 | 科技、消费、医药、新能源 |
| 模拟名义规模 | 1,000 万 CNY |
| 单日成交额下限 | 5,000 万 CNY |
| 最大参与率 | 5% |
| 佣金 | all-in 0.025%，最低 5 CNY |
| 滑点 | 5 bps |
| 市场冲击 | 2 bps |
| holdout | 尾部 30%，至少 20 个交易日 |
| walk-forward | 3 折，每折 20 个交易日，至少 2 折通过 |
| 成本压力 | 1.5 倍、2 倍 |
| 信号时滞压力 | 额外 2 个交易日 |

## 7.2 不能误解成“完整 CSI 500 全样本回测”

当前数据层对每个月度点时成分按指数权重降序，最多选前 40 个作为当期研究样本；跨时间合并后的 distinct securities 默认上限为 120。它不是对全部 500 个成分做完整截面研究。

这意味着：

- 当前研究更接近“CSI 500 高权重子样本动量验证”；
- 可能存在样本集中、行业集中和容量代表性偏差；
- 不能把结果宣传成完整 CSI 500 策略表现；
- 是否使用前 40、全 500 或其他分层样本，必须在看结果前由外部协议冻结；
- 如果修改 universe 规则，必须新建 protocol、实验登记和 forward campaign，不能沿用旧结果。

## 7.3 当前科学性限制

当前示例的历史区间较短、holdout 最少交易数仅 2、最低 holdout Sharpe 为 -0.5、最大允许回撤为 -25%。这些阈值适合软件流程验收，不足以自动证明商业研究质量。

真实 protocol 必须由量化负责人和独立模型验证人在结果不可见时确定：

- 更长且覆盖不同市场状态的历史区间；
- 与策略换手匹配的最小样本数；
- universe 和行业暴露规则；
- 基准、显著性、多重检验和候选淘汰规则；
- 执行价格和部分成交模型；
- 成本与容量边界；
- 前向最小观察期、暂停、独立复现和退役阈值。

不得由 Zcode 在看过真实结果后“优化”这些阈值再复用原实验 ID。

## 7.4 当前执行模型

- 信号有显式滞后；
- 使用点时成分；
- 处理停牌和涨跌停；
- 强制整手/申报数量；
- 强制 T+1；
- 使用方向保守的涨跌停成交策略；
- 当日未成交订单取消，下次调仓重新计算；
- 费用包含佣金、最低佣金、卖方印花税、过户费、滑点和冲击；
- 交易所/监管费用是否包含在 all-in 佣金中有明确布尔控制，防止重复计费；
- 每笔订单写入 cost ledger，并做账本对账。

当前 fill 和 impact 仍是研究模型，不是券商成交仿真。下一工程优先级是建立 LEAN 风格逐笔差分测试，详见后续计划。

---

## 8. 数据层现状

## 8.1 Tushare 接口

当前真实数据链涉及 7 类接口：

1. `trade_cal`：交易日和 freshness；
2. `index_weight`：中证 500 历史成分权重；
3. `daily`：日行情；
4. `adj_factor`：复权因子；
5. `stk_limit`：涨跌停价格；
6. `suspend_d`：停复牌；
7. `daily_basic`：估值、换手等快照字段。

## 8.2 点时与数据质量控制

- 成分股按历史快照选择，不使用当前成分覆盖历史；
- 为 momentum lookback 增加 warmup 区间；
- 保存真实请求日志；
- 记录请求区间、实际区间、期望最新交易日和 freshness lag；
- 价格覆盖与涨跌停覆盖达到 90%，且交易日不少于 40，才评为 `GOOD`；
- 覆盖达到 70% 且交易日不少于 20，评为 `PARTIAL`；
- 其他情况为 `POOR`；
- 研究输入默认要求 `GOOD` 和 freshness lag 0；
- 每个 run 固化 market snapshot 和哈希。

## 8.3 当前未验证的现实风险

- 没有真实 Tushare Token，所以七类接口尚未在当前源码 schema 7 上做真实 E2E；
- 当前对每个证券串行请求多个接口，真实 40 至 120 个证券时可能触发频率、积分、超时或供应商限额；
- 缓存、重试和退避已有代码，但真实吞吐、失败比例、重复请求成本尚无证据；
- 数据授权必须覆盖自动 API、缓存、衍生分析、发送给 DeepSeek 的内容、365 天留存和终止处置；
- 公开个人非商业条款不能自动当成组织商业内部研究授权；
- 数据快照和 raw outputs 的保留、访问和删除必须与合同一致。

---

## 9. 源码与目录地图

## 9.1 根目录脚本

| 文件 | 用途 | 当前注意事项 |
|---|---|---|
| `run_quant_agents.ps1` | 真实或显式 Mock 运行入口；先 recover，再执行 Python CLI | 默认真实 Pi；没有自动 fallback |
| `verify_quant_pipeline.ps1` | Python 编译、111 测试、Mock E2E、完整性、Mock 发布阻断 | 2026-08-29 当前通过 |
| `check_pi.ps1` | skills/extensions、Pi 安装、模型目录和可选付费 ping | `-NoPing` 不证明当前真实 provider 可用 |
| `invoke_pi_acceptance.ps1` | 单个真实无工具 Agent contract 验收 | 会产生真实 LLM 调用，需授权 |
| `invoke_pi_skills_acceptance.ps1` | operator skills 的真实模型加载验收 | 不属于生产研究 run |
| `install_pi_runtime.ps1` | 安装锁定 Pi 版本和完整性 | 不得改成 `latest` |
| `open_pi_ops_console.ps1` | 手工打开只读 `/quant-status` 控制台 | 不创建自启动 |
| `disable_legacy_openclaw.ps1` | 精确停止/禁用三个旧 OpenClaw 任务并检查端口 | 不允许杀掉全部 Node 进程 |
| `install_quant_schedule.ps1` | 校验真实 run、审批、Registry、campaign 后安装隐藏计划任务 | authorization schema 3 |
| `run_daily_research.ps1` | 计划任务 daily runner，复验全部绑定后执行并追加 forward observation | schema 3；只允许显式 retry |
| `check_quant_schedule.ps1` | 检查任务、authorization、hash、campaign、窗口隐藏和并发策略 | **当前仍校验 schema 2，必须修复** |
| `run_weekly_report.ps1` | 聚合同 schema/mode 的周报 | 周报不能替代单 run 证据 |
| `backup_quant_runs.ps1` | run 备份辅助 | 归档发布仍以 Python `archive-run` 为准 |
| `plan_quant_retention.ps1` | 生成保留/删除候选计划 | 不自动删除 |
| `invoke_quant_drill.ps1` | 故障演练 | 演练不等于供应商真实故障证据 |

## 9.2 Python 主包

| 模块 | 作用 |
|---|---|
| `quant_agents/__main__.py` | CLI 命令注册和退出码 |
| `quant_agents/config.py` | 环境、Pi lock、模型、预算、保留期和 pricing baseline |
| `quant_agents/orchestrator.py` | schema 7、真实门禁顺序、7 Agent DAG、失败产物、summary |
| `quant_agents/base_agent.py` | Pi/mock 双模式、输出契约、一次修复 turn、raw/meta 保存 |
| `quant_agents/pi_client.py` | Pi 命令、版本/model/no-tools 校验、JSONL 解析、usage |
| `quant_agents/contracts.py` | Agent 输出字段和禁止真实资金动作语言 |
| `quant_agents/input_validation.py` | 输入、执行和验证参数约束 |
| `quant_agents/data_client.py` | Tushare、点时成分、行情、复权、限制、停牌、质量和快照 |
| `quant_agents/research_engine.py` | momentum 信号、逐订单执行、持仓、成本、绩效 |
| `quant_agents/market_rules.py` | 有效期 A 股交易政策、申报数量和费用 |
| `quant_agents/backtest_validation.py` | holdout、3 折 walk-forward、成本/时滞 stress |
| `quant_agents/backtest_assurance.py` | 回测质量与内部研究 gate |
| `quant_agents/governance.py` | 数据许可、业务用途和安全边界 |
| `quant_agents/research_protocol.py` | 精确输入/模型契约外部预注册 |
| `quant_agents/execution_cost_governance.py` | 成本材料、独立复核、规则簿/资金/容量绑定 |
| `quant_agents/experiment_registry.py` | 仓库外 Registry、`RESERVED`/`FINALIZED`、哈希链、reconcile |
| `quant_agents/operations.py` | run lock、request 幂等、事件链、预算、alerts、recover、ops-status |
| `quant_agents/audit.py` | 原子 JSON、文件哈希、源码 provenance、manifest |
| `quant_agents/release.py` | 完整性、release、审批、归档、恢复、retention |
| `quant_agents/forward_observation.py` | campaign、observation 追加账本、状态和 closure |
| `quant_agents/scheduling.py` | 滚动输入、交易日截止和稳定 request ID |
| `quant_agents/weekly.py` | 周度聚合 |
| `quant_agents/skill_governance.py` | operator skill 锁定与生产隔离审计 |
| `quant_agents/extension_governance.py` | operator extension 能力和哈希审计 |

## 9.3 文档和治理文件

| 路径 | 用途 |
|---|---|
| `README.md` | 当前主入口和命令顺序 |
| `docs/COMMERCIAL_READINESS.md` | 商业准入门禁 |
| `docs/OPERATIONS.md` | 日常运行和故障顺序 |
| `docs/PI_RUNTIME_CONTRACT.md` | Pi 运行契约 |
| `docs/BACKTEST_EXECUTION.md` | 回测执行和成本基线 |
| `docs/DATA_LICENSE_RUNBOOK.md` | 数据授权证据操作手册 |
| `docs/RESEARCH_PROTOCOL_RUNBOOK.md` | 外部预注册操作手册 |
| `docs/EXECUTION_COST_RUNBOOK.md` | 执行成本校准操作手册 |
| `docs/EXPERIMENT_REGISTRY_RUNBOOK.md` | 外部实验账本操作手册 |
| `docs/FORWARD_OBSERVATION_RUNBOOK.md` | 前向观察生命周期 |
| `docs/DEPLOYMENT.md` | 部署、隔离、回滚和调度 |
| `docs/INCIDENT_DRILL.md` | 演练分类和目标 |
| `docs/SKILLS_GOVERNANCE.md` | Pi skills 候选、锁和准入 |
| `docs/OPEN_SOURCE_ECOSYSTEM_REVIEW.md` | Qlib、RD-Agent、LEAN、TradingAgents、RQAlpha、插件评审 |
| `docs/DEPLOYMENT_ACCEPTANCE.md` | 旧验收快照；当前数字已经过时，待更新 |
| `governance/a_share_market_rules.json` | 有效期 A 股规则簿 |
| `governance/*evidence.example.json` | 证据模板；永远不能当真实批准 |
| `governance/pi_skills.lock.json` | 5 个 operator skills 的锁 |
| `governance/pi_extensions.lock.json` | 只读 extension 锁 |
| `governance/upstream_references.json` | 10 个上游项目的固定 commit 和采用决策 |

## 9.4 生成目录

- `runs/`：每个 run 的审计产物，Git 忽略；
- `.cache/`：Pi state、Tushare cache、schedule authorization 等，Git 忽略；
- `.tmp/`：测试临时目录，Git 忽略；
- `drill_reports/`：演练报告，Git 忽略；
- `pi_runtime/node_modules/`：锁定运行时依赖，Git 忽略；
- `.pi/skills/`：项目 operator skills，源码应纳入版本控制；
- `.pi/extensions/`：项目 operator extension，源码应纳入版本控制；
- `.openclaw/`、`openclaw-profile/`：旧迁移遗留，不是当前生产 runtime。

---

## 10. 已经完成的工作

## 10.1 从 OpenClaw 迁移到 Pi

- 业务入口默认只接受 `runtime=pi`；
- 删除了 direct runtime 和自动 fallback 的业务路径；
- Mock 必须显式 `-Mock`；
- 旧 OpenClaw 三个计划任务已精确禁用；
- 旧端口 `18789/18790` 当前无监听；
- 没有通过结束全部 Node 进程的方式破坏其他项目；
- 目录名和旧配置保留为迁移证据，不代表仍使用 OpenClaw。

## 10.2 真实 Pi runtime 接线

- 安装包和版本固定；
- npm package integrity 固定；
- Node 版本检查；
- DeepSeek provider/model 精确校验；
- 生产 turn 禁用所有工具和可执行资源；
- 临时 session 和 JSON mode；
- 记录 provider、model、usage、response ID、session ID、prompt hash、Pi policy；
- 输出契约失败只允许一次修复；
- 模型漂移、tool activity、异常 stop、非 JSON 都硬失败。

## 10.3 数据与点时控制

- Tushare 请求封装、缓存、重试、退避；
- 中证 500 历史成分；
- 交易日 freshness；
- 行情、复权、涨跌停、停牌、估值；
- point-in-time membership；
- 数据请求日志和 snapshot hash；
- coverage/quality gate；
- 未授权或无 Token 时不允许真实数据 run。

## 10.4 确定性研究和回测

- 20 日横截面动量；
- 显式 signal lag；
- 点时 universe；
- 调仓、持仓、现金和订单模拟；
- T+1、整手、申报上限、奇数股退出；
- 停牌和涨跌停阻断；
- 佣金、最低佣金、印花税、过户费、滑点、冲击；
- 逐订单 cost ledger 和 reconciliation；
- holdout；
- 三折 expanding walk-forward；
- 成本倍数和额外时滞压力；
- backtest assurance；
- LLM 返回的权威指标不能覆盖 Python 结果。

## 10.5 业务治理门禁

- clean committed source；
- 数据许可 v2；
- 外部研究协议 v1；
- 执行成本证据 v1；
- DeepSeek pricing review 和预算；
- 业务用途、内部研究、外部分发、broker boundary；
- 五方 release roles；
- 所有示例证据都拒绝在仓库内作为真实证据使用。

## 10.6 Qlib 风格 Experiment Registry

已经实现：

- 仓库外 `registry.json`；
- 仓库外 `experiments.jsonl`；
- 量化、独立模型验证、平台、合规四个不同角色；
- 允许的 run class 只有 `development_backtest` 和 `forward_observation_refresh`；
- 真实 run 在 Tushare/Pi 前追加 `RESERVED`；
- 成功、失败和中断都追加 `FINALIZED`；
- sequence、previous hash、逐行 SHA-256；
- append lock；
- 幂等 reserve/finalize；
- tamper detection；
- stale reservation；
- unregistered external run reconciliation；
- release、monitor、forward、schedule 重新读取外部账本；
- run schema 从 6 升到 7；
- `experiment-init` 和 `experiment-status` CLI。

明确限制：

- 这是 application hash chain；
- 不是 WORM；
- 不是可信时间戳；
- 不是数字签名；
- 不是 IAM 身份认证；
- 硬崩溃且没有可信 running state 备份时，不允许人工伪造终态，只能 BLOCKED 并升级事件。

## 10.7 运行、审计和恢复

- 每个 run 独立目录；
- run lock 和 stale recovery；
- request ID 幂等；
- retry 必须指向同 request 的最新失败 run；
- 失败 run 不覆盖；
- append-only event chain；
- metrics 和 alerts；
- token、provider cost、预算包络；
- manifest 文件哈希；
- input fingerprint、source provenance、model contract、data snapshot、Registry binding；
- integrity verification；
- latest production status 默认忽略 Mock。

## 10.8 发布、归档和前向生命周期

- Mock release 硬阻断；
- 未完成、非 Pi、非真实数据、非 clean source、无批准证据都阻断；
- release candidate 与 approval request；
- 五个不同审批角色；
- ZIP、sidecar、receipt、成员哈希、CRC、安全路径；
- 临时解压和 run 完整性恢复复验；
- 365 天 retention plan 和 legal hold；
- retention 只列候选，不自动删除；
- 仓库外 forward campaign；
- observation 幂等追加、前缀哈希和历史防重写；
- 关闭/退役需要外部三方证据；
- 达标最多进入独立验证，永不自动转为交易。

## 10.9 Pi skills 与插件策略

已安装 5 个项目自有 operator skills：

1. `quant-data-governance`；
2. `quant-backtest-assurance`；
3. `quant-agent-evaluation`；
4. `quant-run-operations`；
5. `quant-release-review`。

已安装 1 个项目自有只读 extension：

- `quant-ops-readonly`，提供 `/quant-status`；
- 无网络；
- 无子进程；
- 无写入；
- 不注册 LLM tool/provider；
- 生产 turn 仍使用 `--no-extensions`。

没有批量安装第三方 Pi package。当前插件决策：

- `CC Safety Net`：未来只做隔离 operator 试点，不进入生产 Agent；
- `pi-permission-system`：备选，不与前者同时启用；
- `pi-lens`：暂缓；
- `pi-subagents`：拒绝用于生产，避免第二套 DAG；
- Web/MCP/search：拒绝用于生产，避免未授权动态数据；
- memory/debugger/notification：拒绝或暂缓，避免扩大留存、泄密、自启动和弹窗。

## 10.10 开源项目学习结果

固定 revision 记录在 `governance/upstream_references.json`。目前只采用概念，不复制第三方数据或交易层：

- Microsoft Qlib：采用 Experiment/Recorder 分层概念，已经落地 Registry；
- Microsoft RD-Agent：只计划采用受治理的候选假设队列，不允许自动调参晋级；
- QuantConnect LEAN：下一阶段采用逐笔执行模型差分测试思想；
- TradingAgents：只采用主张—反证—风险终审，不引入 Trader/Portfolio Manager；
- RQAlpha：只参考场景，商业许可表述存在冲突，在书面法律结论前不复制代码、不加依赖。

---

## 11. Run 产物与审计结构

## 11.1 单个 run 目录

真实完整 run 预期包含：

```text
runs/<run-id>/
├── input.json
├── state.json
├── summary.md
├── run_manifest.json
├── agent_outputs/
├── raw_outputs/
├── pi_meta/
├── market_data/
├── backtest/
│   ├── cost_ledger.json
│   ├── execution_policy.json
│   ├── robustness_validation.json
│   └── backtest_assurance.json
├── charts/
├── operations/
│   ├── events.jsonl
│   ├── metrics.json
│   ├── alerts.json
│   └── integrity_verification.json
└── release/
    ├── release_candidate.json
    └── approval_request.json
```

发布文件在原始 manifest 之后生成，因此不属于原始 run manifest；release 自身通过 candidate/approval hash 和当前重验绑定。

## 11.2 外部 Registry

必须在仓库外：

```text
<controlled-registry>/
├── registry.json
├── experiments.jsonl
└── .append.lock    # 仅追加时临时存在
```

## 11.3 外部 forward campaign

必须在仓库外：

```text
<controlled-forward-root>/<campaign-id>/
├── campaign.json
├── observations.jsonl
└── closure.json    # 关闭或退役时
```

## 11.4 关键状态语义

| 状态 | 含义 |
|---|---|
| `completed` | 控制流完成；仍需看 real/mock、数据、门禁和 release |
| `preflight_failed` | 在业务 Agent 前硬失败；可有完整失败审计 |
| `interrupted` | stale run 被恢复逻辑标记；不能原地续跑 |
| `MOCK` | 软件回归，永远不是市场证据 |
| `REAL REQUEST` | 用户请求真实模式，但可能根本没有外部调用 |
| `PASSED_FOR_INTERNAL_RESEARCH` | 回测 assurance 通过；仍不等于 release 或交易 |
| `APPROVED_FOR_INTERNAL_REVIEW` | 五方内部评审通过；外部分发仍禁止 |
| `BLOCKED` | 缺少必要证据或门禁失败，不得进入下一阶段 |

---

## 12. 2026-08-29 当前复验证据

以下是本交接前重新执行的当前证据，不是只引用旧文档。

## 12.1 全流程软件回归

命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\verify_quant_pipeline.ps1
```

结果：

- exit code `0`；
- 111 tests；
- 全部通过；
- 新建 Mock run `20260829_012811_085`；
- 7/7 Agent；
- manifest 27 files；
- event chain 16 events；
- integrity `ok=true`；
- Mock release candidate 为 `BLOCKED`，符合设计；
- 最终输出 `Quant pipeline verification PASSED`。

## 12.2 Python、脚本和 JSON

- Python `py_compile`：33 个 package `.py` 文件通过；
- 根目录 PowerShell：15 个脚本通过 AST parse；
- 项目非运行/非缓存 JSON：33 个文件通过 Python 标准 JSON 解析；
- 单元测试有两条 matplotlib/setuptools `distutils` deprecation warning，不影响当前结果，但应纳入依赖升级 backlog。

## 12.3 Pi 本地 runtime，无付费调用

命令：

```powershell
.\check_pi.ps1 -NoPing
```

结果：

- Pi package `0.84.2`；
- Node `24.16.0`；
- model catalog 含目标模型；
- all tools disabled；
- extension audit 通过；
- skills audit 通过；
- 环境检测到 DeepSeek Key；
- Tushare Token 未设置；
- 数据许可、研究协议、执行成本、Experiment Registry 路径均未设置；
- 真实 Pi/DeepSeek ping 被明确跳过。

因此当前只能说“本地 runtime 元数据和隔离策略通过”，不能说“当前 provider 真实调用通过”。

## 12.4 Skills 和 extension

- 5 个 skills；
- 12 个锁定文件；
- `production_skills_enabled=false`；
- 1 个 extension；
- extension SHA-256：`1dcdb897d349b861c76af82ae57a2c502eb24505fca891e892714ed26d4a96de`；
- `production_extensions_enabled=false`；
- 两项 audit 均无 error/warning。

## 12.5 最新真实失败 run 的完整性

run：`runs/20260826_165505_647`

- run schema 7；
- `preflight_failed`；
- 0/7 Agent；
- 0 Token；
- 0 供应商成本；
- 没有 Tushare 调用；
- 没有真实 LLM 调用；
- manifest 6 files；
- event chain 2 events；
- integrity 当前重验 `ok=true`；
- 8 个 CRITICAL alerts；
- release candidate `BLOCKED`。

完整性通过只说明失败证据没有被改坏，不表示研究通过。

## 12.6 当前生产监控

命令：

```powershell
python -m quant_agents ops-status --runs-root .\runs
```

结果：

- `ok=false`；
- `severity=CRITICAL`；
- 默认忽略更新的 Mock；
- 选择最新真实 run `20260826_165505_647`；
- run 已超过默认 36 小时时效；
- pipeline、7 Agent、预算、真实数据、回测、source、license、protocol、registry、cost、Pi live ping 等全部未通过；
- broker disabled 和 external distribution disabled 仍通过；
- artifact integrity 通过。

## 12.7 Git、任务和端口

- `.git` 存在；
- 当前分支名 `master`；
- 没有 committed HEAD；
- 没有 remote；
- 没有 tracked files；
- 添加本交接文档前有 115 个 untracked files，添加后当前为 116 个；
- `OpenClaw Gateway`：Disabled；
- `OpenClaw Gateway (quant-research)`：Disabled；
- `OpenClaw Gateway Watchdog (quant-research)`：Disabled；
- `QuantResearch_Daily_Internal`：NOT_FOUND；
- `18789/18790`：无 listener。

## 12.8 以前的真实 Pi 证据如何理解

旧验收文档记录过 2026-08-25 的真实 DeepSeek V4 Pro ping 和一个真实无工具 Agent contract turn。它可以作为历史迁移证据，但本次没有重新付费调用，因此不能把旧证据描述为 2026-08-29 的当前 provider 健康证明。真正启动真实基线前必须在批准的预算和凭据条件下重新执行。

---

## 13. 最新真实 summary.md 的关键结论

来源：`runs/20260826_165505_647/summary.md`

## 13.1 关键结论

> 研究流水线存在未完成或不合规的 Agent 输出，本轮结果不得进入后续验证或任何资金决策。

## 13.2 触发等级

**CRITICAL**

注意：这里的 CRITICAL 是治理/运行触发等级，不是市场方向或行情信号。

## 13.3 主要风险

1. 源码没有 committed HEAD；
2. 没有 tracked source；
3. 工作区全部是 untracked 文件；
4. deterministic backtest unavailable；
5. 数据商业内部研究授权未通过；
6. 研究协议没有外部预注册；
7. 实验没有外部追加式预登记/终态；
8. 执行成本没有外部材料和独立复核；
9. 没有获准组织 Tushare Token；
10. 没有真实市场快照、Pi 7/7 或市场结论。

## 13.4 需要人工确认的问题

- 平台负责人：源码和凭据扫描是否完成，是否可以纳入受控私有仓库？
- 数据负责人/法务：是否取得覆盖七类接口、自动 API、缓存、衍生分析、DeepSeek、365 天留存和终止处置的书面组织授权？
- 量化负责人/独立模型验证/合规：是否在组织系统预注册了精确输入、冻结模型契约和前向阈值？
- 四方 Registry 批准人：是否批准独立仓库外 Registry，且确认成功、失败和中断实验都不得删除？
- 量化/成本复核/合规：费率、滑点、冲击、模拟资金、参与率和流动性下限是否有外部材料绑定？
- 数据负责人：Tushare 账户的组织使用权、积分、接口权限和频率是否满足？
- 模型/平台负责人：是否批准当前 Pi/DeepSeek 版本、预算和付费 acceptance？

## 13.5 下一步动作

- 保留失败 run；
- 不切 Mock 冒充真实；
- 先修代码缺口并建立 clean source；
- 再完成四类外部证据；
- 再配置 Secret；
- 再做付费 Pi acceptance；
- 再以新 Run ID 执行真实 7/7；
- 完整性和回测通过后再做五方审批；
- 有合格 baseline 后才创建 forward campaign；
- 在此之前不安装生产调度。

---

## 14. 当前门禁状态矩阵

| Gate | 代码能力 | 当前真实证据 | 当前判定 | 责任人/下一动作 |
|---|---|---|---|---|
| Source | 已实现 clean commit/worktree gate | 无 HEAD、无 tracked、无 remote | **BLOCKED** | 平台修完 P0 后做密钥扫描并建立受控私有 baseline |
| Dependency lock | Pi npm version/integrity 已锁 | 本地 runtime metadata 通过 | PASS local | 平台保留 lock，升级需变更评审 |
| Secret scan | 文档要求，但无自动 scanner gate | 没有可复验证据 | **GAP/BLOCKED** | 加入不泄露结果的自动扫描和回执 |
| Data rights | v2 schema 和哈希校验已实现 | 无组织授权原件 | **BLOCKED** | 数据负责人 + 法务提供仓库外证据 |
| Research protocol | v1 精确 binding 已实现 | 无组织登记导出 | **BLOCKED** | 量化 + 独立模型验证 + 合规 |
| Experiment Registry | schema/ledger/reconcile 已实现并有测试 | 无真实批准 Registry | **BLOCKED** | 四方批准并在仓库外初始化 |
| Execution cost | 证据、材料哈希、规则/资金绑定已实现 | 无机构材料和批准 | **BLOCKED** | 量化 + 独立成本复核 + 合规 |
| Tushare | 7 类接口、缓存、重试、快照已实现 | 无 Token、无真实快照 | **BLOCKED** | 许可通过后由 Secret Store 注入 |
| Pi local runtime | 版本/model/no-tools 已实现 | 2026-08-29 NoPing 通过 | PASS local only | 真实 run 前重做付费 ping |
| Pi real provider | 已有 ping/acceptance 命令 | 只有旧历史证据，本次未重验 | **STALE/PENDING** | 模型 + 平台批准后执行 |
| Agent contracts | 7 role、JSON、repair、禁止动作语言 | 测试和 Mock 通过 | PASS software | 真实 7/7 待执行 |
| Deterministic engine | signal/order/cost/backtest 已实现 | 单测/Mock，不是授权市场证据 | CANDIDATE | 真实快照 + 独立复现 |
| Robustness | holdout/walk-forward/stress 已实现 | 无真实授权数据结果 | CANDIDATE/BLOCKED | 协议冻结后运行 |
| Budget | token/cost/时限和 pricing review 已实现 | Mock 通过，真实 7/7 无证据 | CANDIDATE | pricing 定期复核 + 真实 usage |
| Integrity | manifest/event hash chain 已实现 | Mock 和失败 real 重验通过 | PASS local | 生产仍需外部不可变存储 |
| Release | candidate + 5 roles 已实现 | 无合格 real run/身份审批 | **BLOCKED** | 五方组织审批 |
| Archive/restore | ZIP、hash、receipt、安全解压已实现 | 单测/历史本地验收 | PASS local | 外部 WORM/不可变存储待组织提供 |
| Forward lifecycle | campaign/ledger/status/closure 已实现 | 无真实 baseline/campaign | **BLOCKED** | release 后初始化 |
| Daily schedule | installer/runner 已实现 | 未安装；checker schema 有缺口 | **GAP/NOT INSTALLED** | 先修 schema 3，再做 `-WhatIf` |
| OpenClaw removal | 精确禁用脚本已实现 | 3 tasks Disabled，端口无监听 | PASS | 保留禁用证据，不杀其他 Node |
| Broker boundary | 强制 false 和 release 检查 | 当前通过 | PASS | 任何交易需求另立独立项目 |
| External distribution | 强制 false | 当前通过 | PASS | 不得在本项目开启 |

---

## 15. 当前明确未完成的工作

## 15.1 Zcode 可以直接完成的工程工作

> **2026-08-29 状态更新（见第 0 节）：本节全部 5 项 P0 已完成并复核通过，以下内容保留为历史需求记录。**

### P0-1 修复 schedule schema 漂移

问题：

- `install_quant_schedule.ps1` 生成 schema 3；
- `run_daily_research.ps1` 要求 schema 3；
- `check_quant_schedule.ps1` 仍要求 schema 2；
- checker 也没有完整复核新加入的 Registry path、Registry ID 和 metadata hash。

完成标准：

- checker 接受且只接受 schema 3；
- 复核 Registry directory、`registry.json` SHA-256、Registry ID；
- 复核 campaign、approval、source commit、authorization hash；
- 保留 hidden window、Limited、`IgnoreNew`、单 action；
- 增加 PowerShell 层的正向/漂移/缺失测试或可重复 smoke harness；
- 更新文档和验收记录。

### P0-2 Pi 子进程 Secret 最小权限

完成标准：

- 不复制完整父进程 Secret 环境；
- Tushare Token 绝不进入 Pi child env；
- 外部 evidence path 不进入 Pi child env，除非有明确技术需要；
- 测试只检查 key 名是否存在，绝不打印值；
- Windows PATH、SystemRoot、TEMP、Node、DeepSeek provider 所需变量仍可用。

### P0-3 自动化源码 Secret 扫描证据

当前 source gate 只检查 Git HEAD/tracked/dirty，README 虽要求密钥扫描，但代码没有自动 scanner。

完成标准：

- 选择固定版本的 scanner 或实现最小只读检查；
- 固定版本/哈希；
- 扫描 tracked candidate，不扫描/输出真实环境变量；
- 结果只保存状态、规则版本、文件数量、命中类型和证据 hash；
- 不在控制台或 run 中回显 secret；
- source release gate 绑定扫描回执；
- false positive 有人工审查流程，不能简单 ignore all。

### P0-4 更新过时验收文档

`docs/DEPLOYMENT_ACCEPTANCE.md` 当前仍写：

- 102/102 tests；
- 旧 Mock run `20260825_175443_065`；
- 旧真实 run `20260825_175506_414`；
- 111 个未跟踪项。

完成标准：

- 不覆盖历史快照语义；最好增加新的日期节或明确 superseded；
- 写入 2026-08-29 的 111 tests 和 Mock `20260829_012811_085`；
- 写入最新真实 run `20260826_165505_647`；
- 写入 schedule schema gap；
- current Git count 必须在最终改动后重新计算；
- 不能把 NoPing 记为真实 provider 通过。

### P0-5 增加跨脚本 contract 测试

当前 Python 单测很强，但 PowerShell installer/checker/runner 的 schema 契约没有被同一个测试约束，导致 schema 2/3 漂移未被 111 个测试发现。

完成标准：

- authorization schema 只在一个 machine-readable contract 中定义，或至少由测试统一检查；
- installer、checker、runner、README 命令一起验证；
- 测试不真正创建生产计划任务；
- 使用 `-WhatIf` 或隔离 fake objects；
- 验证隐藏窗口、自启动不弹窗、重复实例 `IgnoreNew`。

## 15.2 必须由人或外部组织完成的工作

Zcode 不得伪造以下内容：

1. 私有 Git remote 和组织仓库所有权；
2. 最终 commit/tag 批准；
3. 服务商书面组织数据授权；
4. 法务对许可范围的确认；
5. 研究协议在组织系统中的真实登记时间；
6. 四名真实 Registry 批准人；
7. 券商费率、历史委托或保守校准支持材料；
8. 五个真实 release 审批身份；
9. WORM/不可变归档能力；
10. 生产 service account 和 Windows Task 权限；
11. Tushare 组织 Token；
12. DeepSeek 账户预算和当前模型授权；
13. 任何声称来自真实市场的结论。

## 15.3 需要真实凭据后才能完成的验证

- Tushare 七类接口 E2E；
- 真实 data snapshot；
- 当前 DeepSeek paid ping；
- 当前无工具 Agent contract acceptance；
- 真实 7/7；
- 真实 token/provider cost；
- 真实 backtest、holdout、walk-forward、stress；
- 真实 Registry reserve/finalize；
- release candidate；
- 五方 release verification；
- 外部 archive/restore；
- forward campaign；
- daily schedule。

---

## 16. 已知缺陷、风险和技术债

## 16.1 P0：阻断上线

> **2026-08-29 状态更新（见第 0 节）**：第 2、3、4 条工程缺陷已修复；第 1 条源码基线仍待人工建仓；第 5-8 条外部证据类阻断不变。

1. **无源码基线**：没有 HEAD、remote、tracked file；真实 run 必然最先失败。
2. ~~**调度 schema 漂移**：checker schema 2，installer/runner schema 3。~~ **已修复**：三者一致 schema 3，并有 `test_schedule_contract.py` 约束。
3. ~~**Pi child env 过宽**：未来可能把不相关数据 Secret 传给 Pi 进程。~~ **已修复**：`PI_CHILD_ENV_ALLOWLIST` 显式白名单。
4. ~~**Secret scan 未自动化**：当前只存在文档责任，没有机器可验证回执。~~ **已修复**：`quant_agents/secret_scan.py` + 回执 + 测试。
5. **外部证据全部缺失**：license、protocol、Registry、cost。
6. **无 Tushare Token/快照**：没有真实市场数据证据。
7. **无当前 provider 付费重验**：NoPing 不能替代。
8. **无真实 7/7**：0 个当前市场业务 Agent 成功。

## 16.2 P1：真实 baseline 前必须处理或明确接受

1. 当前样本是每期前 40 个高权重成分，不是完整 CSI 500；
2. 示例历史区间和验收阈值偏软件验收，不足以证明商业研究质量；
3. Tushare 多接口按证券串行调用，真实吞吐/限频未证实；
4. execution fill/impact 是研究模型，没有逐笔差分基准；
5. local JSON/hash 不认证人员身份；
6. Registry/event chain 不是 WORM 或可信时间戳；
7. provider pricing baseline 复核日是 2026-08-25，超过 30 天必须重新批准；
8. DeepSeek/Pi 版本任何变化都需要 contract 回归；
9. raw outputs、market snapshots 和 cache 的许可/访问/保留必须与合同一致；
10. 真实 provider、Tushare 和 service account 故障演练尚无上线证据。

## 16.3 P2：可维护性和运营改进

1. ~~`docs/DEPLOYMENT_ACCEPTANCE.md` 数字过时~~ **已更新（2026-08-29）**：新增复核节记录 133 测试与最新 run；
2. matplotlib/setuptools 有 `distutils` deprecation warning；
3. 根目录仍含 legacy OpenClaw 配置，需长期标注为 inactive，不能误启动；
4. ~~Temp 中可能仍有测试 Registry residue：`C:\Users\轻音\AppData\Local\Temp\quant-registry-acceptance-aa61a23d0bfe4b189880bd0607d76a87`，当前检测到 4 个测试文件；清理前必须再次验证绝对路径，只删除该精确目录~~ **已清理（2026-08-29，删除前验证唯一性与测试产物性质）**；
5. PowerShell `ConvertFrom-Json` 对 npm `package-lock.json` 的空 property name 会报兼容错误；该文件已用 Python 标准 JSON parser 验证有效，不能误判损坏；
6. 当前生产状态依赖 36 小时时效，长期无真实 run 会持续 CRITICAL，这是正确行为；
7. 项目路径含中文和空格，所有脚本必须继续使用 `-LiteralPath`、正确 quoting 和 UTF-8。

---

## 17. 下一阶段总计划

## 17.1 Milestone 0：把当前代码变成可提交的受控候选

顺序：

1. 修 schedule schema 2/3 漂移；
2. 收紧 Pi child environment；
3. 加入自动 Secret scan contract；
4. 增加跨 PowerShell contract tests；
5. 更新 acceptance 文档；
6. 执行全量 111+ tests 和 Mock E2E；
7. 检查所有 JSON、PowerShell、skills/extensions lock；
8. 由平台负责人审查 diff 和 Secret scan；
9. 创建受控私有 remote；
10. 建立 clean commit/tag。

退出条件：

- `git rev-parse --verify HEAD` 成功；
- `git status --porcelain` 为空；
- tracked source 非零；
- remote 指向批准的私有仓库；
- dependency locks 完整；
- Secret scan 回执通过；
- `python -m quant_agents health ... --no-ping` 能越过 source gate。

## 17.2 Milestone 1：完成外部商业证据

可与工程修复并行，但不能由代码伪造：

1. 数据授权 v2；
2. 研究协议 v1；
3. Experiment Registry 批准证据；
4. 执行成本 v1；
5. 组织 Secret Store；
6. DeepSeek pricing/model 复核；
7. Tushare 组织账户权限核验。

退出条件：四个 evidence path 都在仓库外、原件 hash 正确、日期有效、人员不同、用途和保留范围覆盖真实流程。

## 17.3 Milestone 2：真实 runtime 与数据 acceptance

1. 只注入所需 Secret；
2. `check_pi.ps1 -NoPing`；
3. 经预算批准后 `check_pi.ps1`；
4. `invoke_pi_acceptance.ps1`；
5. `experiment-status`；
6. 完整 `health`；
7. 小范围、预注册的 Tushare data-only acceptance；
8. 核对 endpoint 权限、频率、缓存、freshness、快照和数据出境/处理边界。

退出条件：当前 provider/model/no-tools 真实证据、真实数据接口证据和完整 preflight 通过。

## 17.4 Milestone 3：首个真实研究 baseline

1. 使用冻结输入和新 request ID；
2. 确认 Registry 无 stale reservation；
3. 执行 `run_quant_agents.ps1`；
4. 观察 `RESERVED` 在外部调用前出现；
5. 观察 7 Agent 完成；
6. 观察 `FINALIZED`；
7. 验证 state/summary/pi_meta/raw/market/backtest/charts；
8. 验证 holdout、walk-forward、stress、cost ledger；
9. 验证 usage、provider cost 和预算；
10. `verify-run`；
11. `ops-status`。

退出条件：真实 Pi、7/7、`REAL_TUSHARE`、deterministic metrics、所有门禁通过、0 CRITICAL、完整性通过。结果无论好坏都保留。

## 17.5 Milestone 4：内部 release、归档和 forward

1. `release-prepare`；
2. 五方独立组织审批；
3. `release-verify`；
4. `archive-run`；
5. 在独立环境 `verify-archive`；
6. 保存 archive SHA-256 到外部系统；
7. `forward-init`；
8. `forward-status`；
9. 复核 external distribution 和 broker 均为 false。

退出条件：`APPROVED_FOR_INTERNAL_REVIEW`、归档恢复通过、真实 campaign 建立，但仍不允许真实交易。

## 17.6 Milestone 5：日常调度

前提：P0 schedule checker 已修复。

1. `install_quant_schedule.ps1 ... -WhatIf`；
2. 独立复核 authorization schema 3 和全部 hash；
3. 安装 `QuantResearch_Daily_Internal`；
4. `check_quant_schedule.ps1`；
5. 验证 `-WindowStyle Hidden`；
6. 验证 Limited、`IgnoreNew`、单 action；
7. 验证任务不会弹窗；
8. 验证 request idempotency；
9. 验证失败后不会自动 retry 或 fallback；
10. 验证成功 run 自动追加 forward observation。

## 17.7 Milestone 6：LEAN 风格执行差分测试

这是完成真实 baseline 前后都可以设计、但必须在协议变更规则下使用的下一工程目标。

建议建立冻结订单流 fixture，逐笔比较：

- 主板 100 股整手；
- 科创板最低 200 股和 1 股递增；
- 创业板申报上限；
- 奇数股全部退出；
- T+1 当日不可卖；
- 停牌；
- 涨停买入阻断；
- 跌停卖出阻断；
- 部分成交；
- DAY 订单取消；
- 佣金最低 5 CNY；
- 卖方印花税；
- all-in 佣金防重复收费；
- 滑点和 impact；
- 参与率和流动性上限；
- 现金不足；
- corporate action/复权；
- 同一订单流下成本 ledger 与净值对账。

验收不能只比较最终收益，必须逐单记录 expected、actual、difference、reason 和 rule source。

## 17.8 Milestone 7：受治理的候选假设队列

只有在真实 baseline、外部 Registry 和 forward ledger 已稳定后才考虑 RD-Agent 风格候选生成。

硬规则：

- LLM 只能提出候选；
- 每个候选新建 protocol 和 experiment ID；
- 不允许共享 holdout；
- 不允许看过结果后改阈值；
- 记录全部失败候选；
- 增加多重检验和 candidate budget；
- 自动晋级永远禁止；
- 任何模型变更都要新 campaign。

## 17.9 Milestone 8：可选 operator 安全插件试点

仅在前述核心工作稳定后评估 `CC Safety Net`：

- 仓库外隔离 profile；
- 无生产 Secret；
- 固定 commit/package hash；
- `npm pack --ignore-scripts`；
- 审查 lifecycle scripts 和依赖树；
- 记录网络、写入、子进程和 telemetry；
- 允许/拒绝/旁路测试；
- 只供人工 operator；
- 永远不进入七个生产 Agent turn。

---

## 18. Zcode 接手后的第一轮执行清单

## 18.1 先只读，不立即真实运行

```powershell
cd "E:\闲鱼\codex openclaw"

Get-Content .\AGENTS.md
Get-Content .\ZCODE_PROJECT_HANDOFF.md
Get-Content .\README.md
Get-Content .\docs\COMMERCIAL_READINESS.md
Get-Content .\docs\EXPERIMENT_REGISTRY_RUNBOOK.md
Get-Content .\docs\OPEN_SOURCE_ECOSYSTEM_REVIEW.md

git rev-parse --verify HEAD
git status --short --untracked-files=all
git remote -v
```

预期：HEAD 失败、全部未跟踪、无 remote。不要把这个失败“绕过”。

## 18.2 无外部费用的当前基线

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPYCACHEPREFIX = Join-Path (Get-Location) ".cache\zcode-pycache"

python -m unittest discover -s tests -v
python -m quant_agents skills-audit
python -m quant_agents extensions-audit
.\check_pi.ps1 -NoPing
powershell -ExecutionPolicy Bypass -File .\verify_quant_pipeline.ps1
```

注意：最后一个命令会生成新的明确 Mock run，但不会调用真实 LLM/Tushare。

## 18.3 首先修复的文件

> **2026-08-29 状态更新（见第 0 节）：以下文件的全部修复已完成并通过回归验证。**

```text
check_quant_schedule.ps1
install_quant_schedule.ps1
run_daily_research.ps1
quant_agents/pi_client.py
tests/test_pi_client.py
tests/test_scheduling.py
docs/DEPLOYMENT_ACCEPTANCE.md
docs/DEPLOYMENT.md
README.md
```

如果增加 PowerShell contract test，可以新建独立测试文件，但不要为了追求数量引入大型测试框架。

## 18.4 修复后必须重新验证

```powershell
python -m unittest discover -s tests -v
python -m quant_agents skills-audit
python -m quant_agents extensions-audit
powershell -ExecutionPolicy Bypass -File .\verify_quant_pipeline.ps1
```

再执行：

- 15+ 根 PowerShell AST parse；
- 所有非生成 JSON parse；
- `rg` 检查 schema 2/3 不一致；
- `rg` 检查旧 test count/run ID 是否仍被标记为 current；
- Git 状态和 Secret scan。

## 18.5 不要立即执行的命令

在没有明确预算和外部证据时，不要执行：

```powershell
.\check_pi.ps1
.\invoke_pi_acceptance.ps1
.\run_quant_agents.ps1
.\install_quant_schedule.ps1 ...
```

原因：前两项可能产生付费 LLM 调用；第三项虽然目前会被 source gate 阻断，但不应制造无意义失败 run；第四项绝不能在 baseline、approval、Registry、campaign 缺失时安装。

---

## 19. 标准操作命令

## 19.1 只检查 Pi，不付费

```powershell
.\check_pi.ps1 -NoPing
```

## 19.2 显式 Mock 回归

```powershell
.\run_quant_agents.ps1 -Mock
```

## 19.3 完整软件验收

```powershell
.\verify_quant_pipeline.ps1
```

## 19.4 完整真实 health

仅在 source 和外部证据已准备后：

```powershell
python -m quant_agents health `
  --runtime pi `
  --input .\strategy_round.example.json
```

## 19.5 真实 run

```powershell
.\run_quant_agents.ps1 `
  -InputPath .\strategy_round.example.json `
  -RequestId <stable-request-id>
```

失败重试：

```powershell
.\run_quant_agents.ps1 `
  -InputPath .\strategy_round.example.json `
  -RequestId <same-request-id> `
  -RetryOf <latest-failed-run-id>
```

不得直接删除失败 run 或复用其目录。

## 19.6 Registry

```powershell
python -m quant_agents experiment-init `
  --evidence <仓库外experiment-evidence.json> `
  --root <仓库外registry目录>

$env:EXPERIMENT_REGISTRY_PATH = "<仓库外registry目录>"

python -m quant_agents experiment-status `
  --registry $env:EXPERIMENT_REGISTRY_PATH `
  --runs-root .\runs
```

## 19.7 Run 完整性和发布

```powershell
python -m quant_agents verify-run --run-dir .\runs\<run-id>
python -m quant_agents release-prepare --run-dir .\runs\<run-id>
python -m quant_agents release-verify `
  --run-dir .\runs\<run-id> `
  --approval .\runs\<run-id>\release\approval_request.json
```

## 19.8 归档和恢复

```powershell
python -m quant_agents archive-run `
  --run-dir .\runs\<run-id> `
  --archive-root <仓库外归档目录>

python -m quant_agents verify-archive `
  --archive <zip> `
  --expected-sha256 <外部保存的sha256>
```

## 19.9 Forward campaign

```powershell
python -m quant_agents forward-init `
  --baseline-run .\runs\<run-id> `
  --approval .\runs\<run-id>\release\approval_request.json `
  --root <仓库外forward-root>

python -m quant_agents forward-status --campaign <campaign-dir>
```

## 19.10 调度

必须先修 schema checker，再执行：

```powershell
.\install_quant_schedule.ps1 `
  -ApprovedRunDir <真实已批准run> `
  -ApprovalPath <approval.json> `
  -ForwardCampaignPath <仓库外campaign> `
  -ExperimentRegistryPath <仓库外registry> `
  -WhatIf
```

独立复核通过后才去掉 `-WhatIf`。

---

## 20. 环境变量字典

不得在本文、代码、日志或审批 JSON 中填写真实 Secret 值。

| 环境变量 | 用途 | 当前状态/规则 |
|---|---|---|
| `DEEPSEEK_API_KEY` | Pi provider 凭据 | 当前环境只检测到已设置；不得回显 |
| `DEEPSEEK_MODEL` | 模型 | 必须为 `deepseek-v4-pro` |
| `PI_NODE_CLI` | Node executable | 默认 `node` |
| `PI_TIMEOUT_SECONDS` | 单 Agent timeout | 默认 300 |
| `PI_PING_TIMEOUT_SECONDS` | ping timeout | 默认 90 |
| `PI_METADATA_TIMEOUT_SECONDS` | metadata timeout | 默认 60 |
| `PI_THINKING_LEVEL` | Pi thinking | 默认 off，必须在允许集合内 |
| `TUSHARE_TOKEN` | 数据凭据 | 当前未设置；许可通过后注入 |
| `TUSHARE_INDEX_CODE` | 指数 | 默认 `000905.SH` |
| `TUSHARE_CACHE_DIR` | 数据缓存 | 默认 `.cache/tushare` |
| `TUSHARE_CACHE_TTL_HOURS` | cache TTL | 默认 24 |
| `TUSHARE_MAX_RETRIES` | 数据重试 | 默认 3 |
| `TUSHARE_RETRY_BASE_SECONDS` | 指数退避基线 | 默认 1 |
| `TUSHARE_MAX_RESEARCH_SECURITIES` | 跨时间 distinct security 上限 | 默认 120 |
| `DATA_LICENSE_EVIDENCE_PATH` | 仓库外数据许可证据 | 当前未设置 |
| `RESEARCH_PROTOCOL_EVIDENCE_PATH` | 仓库外研究协议 | 当前未设置 |
| `EXPERIMENT_REGISTRY_PATH` | 仓库外实验 Registry | 当前未设置 |
| `EXECUTION_COST_EVIDENCE_PATH` | 仓库外执行成本证据 | 当前未设置 |
| `MAX_LLM_TOTAL_TOKENS_PER_RUN` | run token 上限 | 默认 500,000 |
| `MAX_LLM_COST_USD_PER_RUN` | run 预算上限 | 默认 2.00 USD |
| `MAX_AGENT_RUNTIME_SECONDS` | Agent 时限 | 默认 300 |
| `MAX_PIPELINE_RUNTIME_SECONDS` | pipeline 时限 | 默认 2400 |
| `RUN_RETENTION_DAYS` | 默认保留期 | 默认 365 |
| `DEEPSEEK_*_USD_PER_M` | pricing rates | 必须匹配批准 baseline，不能随意 env 覆盖 |
| `DEEPSEEK_PRICING_REVIEWED_DATE` | pricing 复核日 | 当前 baseline 2026-08-25 |
| `DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS` | pricing 最大年龄 | 默认 30 |
| `DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER` | 高峰预算包络 | 当前 2.0 |

---

## 21. Exit code 与失败处置

| 场景 | 典型退出码 | 操作 |
|---|---:|---|
| 成功 run/验证 | 0 | 继续检查产物，不只看退出码 |
| health 失败 | 1 | 修复第一个硬门禁；不切 Mock 冒充 |
| real run preflight 失败 | 2 | 保留失败 run，修复后新 Run ID |
| release candidate 被阻断 | 3 | 查看 blockers；不得修改 candidate 绕过 |
| 其他执行异常 | 非 0 | 检查 state、events、alerts、raw/meta 和 Registry 终态 |

失败处理原则：

- 不删除失败证据；
- 不原地编辑 state/ledger；
- 不重新计算 hash 掩盖篡改；
- 不自动 fallback；
- 不重复使用旧 snapshot 冒充新数据；
- 不自动 retry；
- 不跳过独立审批；
- 新 run 通过 `retry_of` 关联旧失败。

---

## 22. Definition of Done

## 22.1 工程 DoD

- 所有 Python/PowerShell/JSON 合法；
- 全量测试通过；
- Mock E2E 通过且明确 MOCK；
- Mock release 被阻断；
- schedule installer/checker/runner schema 一致；
- Pi child env 最小权限；
- Secret scan 回执进入 source gate；
- skills/extensions lock 通过；
- 文档数字和当前证据一致；
- 没有新增自启动或弹窗；
- 没有真实交易能力。

## 22.2 首个真实 baseline DoD

- clean committed source；
- 四类外部证据有效；
- Registry `RESERVED`/`FINALIZED` 完整；
- `REAL_TUSHARE`；
- 当前 Pi/DeepSeek 真实 ping；
- 7/7；
- deterministic metrics；
- cost ledger 对账；
- holdout/walk-forward/stress 通过或如实失败；
- budget 通过；
- 0 CRITICAL；
- manifest/event/integrity 通过；
- 结果中没有真实资金动作语言。

## 22.3 内部发布 DoD

- 五方不同身份批准；
- 身份和时间由组织系统认证；
- approval 与 current candidate/manifest/source/registry 一致；
- archive 和 restore 通过；
- external distribution false；
- broker false；
- forward campaign 建立；
- 仍不构成交易授权。

## 22.4 项目总目标 DoD

- 连续前向观察达到预注册最小周期；
- observation ledger 无改写；
- 独立复现完成；
- 模型、数据、成本、规则和源码漂移可追踪；
- 失败/暂停/退役路径被真实演练；
- 调度稳定、无弹窗、无重复并发；
- 所有商业证据和保留策略由组织负责；
- 系统最多支持内部研究决策，不自动扩展成真实交易。

---

## 23. Zcode 绝对不能做的事

1. 不得创建虚假姓名、审批、合同、license ID、ticket ID 或签名；
2. 不得把仓库内 example JSON 改名后当真实证据；
3. 不得把 Mock 标成 real；
4. 不得在真实失败时自动 fallback 到 Mock；
5. 不得让 LLM 访问 Tushare Token；
6. 不得把 Secret 写进 Markdown、脚本、Git、state 或日志；
7. 不得结束所有 Node 进程来处理旧 OpenClaw；
8. 不得重新启用旧 OpenClaw 任务或端口；
9. 不得安装通用浏览器、搜索、MCP、memory 或 subagent 插件到生产 turn；
10. 不得让 Agent 修改确定性指标；
11. 不得在看真实结果后偷偷调整阈值并复用实验 ID；
12. 不得删除失败 run 或 Registry 历史行；
13. 不得在没有 WORM 时宣称本地 hash chain 是法律不可变证据；
14. 不得在没有组织 IAM 时宣称本地审批 JSON 认证了身份；
15. 不得创建券商、订单、账户或真实资金接口；
16. 不得输出真实资金操作建议；
17. 不得在真实 baseline 之前安装生产调度；
18. 不得因为测试通过就宣称商业 READY。

---

## 24. 建议 Zcode 的工作优先级

### 立即做

> **2026-08-29 状态更新（见第 0 节）：第 1-8 项已全部完成并复核；下一动作是"然后由平台/人工完成"清单。**

1. 阅读本文件和 AGENTS/README；
2. 复现无费用基线；
3. 修 schedule schema；
4. 修 Pi child env；
5. 加 Secret scan gate；
6. 加跨脚本 contract test；
7. 更新 acceptance 文档；
8. 完整回归。

### 然后由平台/人工完成

1. 私有 remote；
2. clean commit/tag；
3. 外部四类证据；
4. Secret Store；
5. pricing/model/数据账户批准。

### 再执行真实验证

1. current paid Pi acceptance；
2. Tushare data acceptance；
3. real 7/7 baseline；
4. integrity/release；
5. archive/forward；
6. schedule。

### 核心稳定后再扩展

1. LEAN-style execution differential tests；
2. governed candidate queue；
3. optional CC Safety Net operator-only pilot。

不要反过来先装插件、先生成更多因子或先做自动调参。当前最大的价值不是增加 Agent 数量，而是完成真实证据、源码基线、执行真实性和组织审批闭环。

---

## 25. 交接结论

项目已经从“演示性的多 Agent 文档流”推进为一个有明确 Python 权威层、Pi 真实运行契约、数据/研究/实验/成本门禁、确定性回测、审计、发布、归档和前向生命周期的内部研究候选。

但它目前仍然是：

- **软件回归通过**；
- **本地 runtime 可用**；
- **商业证据不完整**；
- **真实数据未运行**；
- **真实 7 Agent 市场研究未完成**；
- **内部 release 未批准**；
- **forward 未启动**；
- **生产 schedule 未安装**；
- **交易能力不存在且不应在本项目增加**。

Zcode 接管时最重要的判断标准是：

> 任何“完成”都必须同时写明验证日期、命令、退出码、run ID、real/mock、是否调用外部服务、是否具备组织授权、是否具备人工审批，以及仍然存在的阻断项。

本文件仅用于项目接管和内部研究工程管理，不构成任何真实资金交易建议。

## 26. 2026-09-15 当前接管增补

### 已完成

1. `source_review.py` 已增加 review flag 类型、重复和逐文件一致性校验；损坏 packet 的验证异常会返回 BLOCKED，而不是让 readiness 或 decision CLI 无审计地崩溃。
2. `source-review-decision-verify` 已支持 `--secret-receipt`，并严格保持“外部双人审查 claim ≠ 组织身份认证 ≠ Git 授权 ≠ G1 授权”。
3. `verify_quant_pipeline.ps1` 已加入 packet、空白 decision template 和空白 decision 的负向 smoke：模板创建可成功，但空白 decision 验证必须退出 `3`。
4. 当前代码回归为 **194/194 PASS**；已验证的 Mock 运行保持 7/7、0 错误、完整性通过，release candidate 按设计 BLOCKED。以上均为本地工程或 Mock 证据，不是市场研究。

### 当前硬阻断

- Git 无 HEAD、tracked file 和 private remote；
- 外部 Platform/Security 双人逐文件 decision record 尚未提供；
- 数据许可、研究预注册、Experiment Registry、执行成本四类外部原件尚未提供；
- Tushare Token、当前付费 Pi acceptance、真实 7/7 和五方审批尚未具备；
- 生产 schedule、forward campaign 和内部 release 必须继续 NO-GO。

### 接手后严格执行

先用最新 `source-review-packet` 和 `source-review-decision-verify` 完成组织审查，再由授权人建立最小权限 private baseline；随后完成四类外部证据和 offline readiness，只有 G1 明确 GO 后才可以执行真实 acceptance。不得创建虚假审批、不得把 example/Mock/hash 当授权、不得恢复 OpenClaw、不得接 broker/order 或生成真实资金建议。
