# 部署候选验收记录

验收日期：2026-08-26（初始）、2026-08-29（P0 加固）、2026-09-02（离线 readiness）、2026-09-04（Python/source 可复现性）、2026-09-05（人工源码审查交接包）、2026-09-15（双人 decision 控制与离线回归）。目标范围是 CSI 500 内部研究，不包括券商、订单、真实资金动作或外部分发。用户已决定由 Pi Agent 替代 OpenClaw，因此真实模型证明以锁定 Pi/DeepSeek V4 Pro 为准；旧 OpenClaw 仅做退出验收。

| 能力 | 当前结论 | 权威证据 | 未完成边界 |
|---|---|---|---|
| 运行互斥与恢复 | PASS | `RunLock` 原子锁/心跳/陈旧锁归档；陈旧 run 标记 interrupted，不原地续跑；故障测试通过 | 生产共享存储和服务账户环境尚未部署 |
| Python 运行基线 | PASS (local) | Windows CPython 3.11.9 项目 `.venv`；32 个 transitive pins 各绑定选定 wheel SHA-256；禁止 user site、全局 Python、版本偏差和额外运行包；health/run/Mock/readiness/release 复验 | lock 面向 Windows CPython 3.11；重解析仍需供应链复核和 clean-clone 重验 |
| 结构化监控 | PASS | `operations/metrics.json`、`alerts.json`；`ops-status` 默认排除 Mock，并复验真实数据、许可、Pi、成本、时效和完整性 | 最新真实状态为 CRITICAL，不等于生产健康 |
| 模型调用成本门禁 | PASS | 2026-08-25 官方 V4 Pro 非高峰基线；按当前高峰/非高峰2倍比率形成预算包络，再与 provider-reported 取高值；30天复核、逐 Agent 重算、80% warning | 每次实际收费取决于调用时段；真实7 Agent成本尚无授权数据run证据 |
| 执行成本证据门禁 | READY/BLOCKED | v1 证据绑定规则簿、完整成本模型、资金规模、参与率、流动性下限、材料哈希、独立复核和90天有效性；发布与监控均复验 | 未提供外部机构费率/历史委托材料和真实组织身份批准；示例不得冒充批准 |
| 数据授权门禁 | READY/BLOCKED | v2 证据强制独立书面组织授权、处理者、接口、缓存、留存、终止处置、文件哈希及30天条款复核 | 未提供服务商授权原件；本地哈希不能认证签署身份 |
| 研究预注册门禁 | READY/BLOCKED | v1 外部组织登记绑定精确输入、冻结模型契约、登记/批准时间、三名不同批准人、前向阈值和原件哈希；发布/监控复验 | 未提供组织登记导出和真实身份/时间戳证据；输入声明不算预注册 |
| 样本外验证 | PASS (deterministic) | 独立尾部 holdout 加三折锚定扩展非重叠窗口；每折基准、2倍成本、额外时滞，至少三分之二折通过 | 待真实授权数据和独立复现 |
| 前向模型生命周期 | READY/BLOCKED | 仓库外 campaign、固定起点、只取登记截止日之后路径、前缀哈希防重写、幂等追加、暂停/独立验证/退役状态 | 166 项全套测试覆盖核心状态（2026-09-05 回归）；无合格真实基线，因此没有真实 campaign/观察记录 |
| Pi 扩展供应链 | PASS (operator only) | 项目自有只读 `/quant-status`；独立 SHA-256 lock、禁止网络/子进程/写入/tool/provider 注册，显式加载；生产复验 `--no-extensions` | 未安装任何第三方 Pi package；CC Safety Net 等候选仍需隔离验收，不能进入生产七 Agent turn |
| 发布审批包 | READY/BLOCKED | candidate 绑定 run、manifest snapshot、输入指纹；五个独立角色和当前资格复验 | 本地 JSON 不认证身份；真实组织签名/工单未提供 |
| 产物完整性 | PASS | manifest 文件哈希、输入指纹、事件链、禁止未清单文件；篡改测试通过 | 真实数据 run 尚未形成 |
| 备份与恢复 | PASS | ZIP sidecar、receipt、全部成员哈希、安全路径、CRC、临时恢复及 run integrity；重复 ZIP 重新验证 | 外部不可变/WORM 存储由组织提供 |
| 保留策略 | PASS (plan only) | 默认 365 天、legal hold、有效归档与恢复前置、人工删除授权；代码不自动删除 | 组织法务需要确认最终期限和处置责任人 |
| 调度 | READY/NOT INSTALLED | 安装前复验真实 run/五方审批/campaign；任务绑定 approval、candidate、源码和 campaign 哈希；隐藏窗口、`IgnoreNew` | 因真实 run、审批和 campaign 缺失，正确拒绝安装；未创建新自启动任务 |
| 故障演练 | PASS | 锁竞争、幂等、事件篡改、恢复、生产监控、归档攻击、保留、许可、Pi 漂移/工具/超时和依赖阻断均有持久化日志 | 供应商真实故障和服务账户桌面环境需上线后演练 |
| 真实 Pi 探针 | PASS | 工作区 Pi `0.84.2`、Node `24.16.0`、DeepSeek V4 Pro 实付 ping 和无工具 Agent contract turn | 探针不是市场研究完成证明 |
| 真实市场 E2E | BLOCKED | 最新真实请求在 source gate 前置失败，Agent 0/7、token/成本 0、无 Tushare/Pi 调用和市场结论 | 需要 clean commit/tag、数据许可、研究预注册、成本证据、Tushare Token、真实 7/7 与五方审批 |
| OpenClaw 退出 | PASS | 三个精确命名自启动任务均 Disabled；18789/18790 无监听；无 OpenClaw runtime 进程 | 任务保留为可审计的禁用状态，没有删除 |
| 交易边界 | PASS | `broker_connection_enabled=false`、`external_distribution_approved=false`、summary 禁止资金动作词、Mock 发布硬阻断 | 任何未来交易能力必须另立项目和审批 |

当前发布判定：**BLOCKED，内部商业运营候选的软件与运行时能力已具备，但真实数据、源码基线和人工授权证据不具备。** 不得安装生产调度，不得把 Pi 探针或 Mock 7/7 描述为真实研究完成。

## 2026-08-26 当前验收证据（历史快照，已被 2026-08-29 节复核更新）

- `verify_quant_pipeline.ps1`：102/102 测试通过；**MOCK** run `20260825_175443_065` 为 7/7，27 个 manifest 文件和 16 个事件完整性通过，发布候选继续被真实数据、研究预注册等硬门禁阻断。
- 真实请求 `20260825_175506_414`：在 clean source 门禁失败，0/7 Agent、0 token、0 供应商成本、无 Tushare/LLM 调用；7 个 CRITICAL 告警、6 个受 manifest 管理文件和 2 个事件完整性通过，发布准备返回 BLOCKED（退出码 3）。
- `check_pi.ps1 -NoPing`：锁定 Pi `0.84.2`、Node `24.16.0`、DeepSeek V4 Pro 模型目录和 no-tools 策略通过；本轮明确跳过付费 ping，因此不把该检查记为新的真实模型调用证据。
- 静态与供应链：15 个根目录 PowerShell 文件通过 AST 解析，71 个非缓存/非运行项目 JSON 通过 Python 标准解析；5 个 operator skills/12 个锁定文件和 1 个只读 operator extension 均通过哈希与生产隔离审计；10 个 upstream 项目以精确 commit 记录采用或拒绝决策。
- 旧运行时：三个精确命名 OpenClaw 计划任务均为 Disabled，18789/18790 无监听；未结束其他 Node 进程。
- 当前外部阻断：仓库无 committed HEAD、111 个未跟踪项、无 v2 数据授权、无 v1 研究协议登记、无 v1 执行成本证据、无 Tushare Token、无真实授权数据 7/7、无组织身份五方审批，因此也不能建立真实前向 campaign。

## 2026-08-29 复核与 P0 加固证据（历史快照，已被 2026-09-02 节更新）

本节为 Zcode 接管后的当前验收记录，取代上节数字；上节保留为历史快照。

工程修复（全部有测试与回归覆盖）：

1. **调度 schema 漂移修复**：`check_quant_schedule.ps1` 由 schema 2 升级为只接受 schema 3，并新增 Registry 目录/元数据 SHA-256/身份、approval 哈希与 release-verify 复验、campaign 身份与开放状态、当前源码 commit 与干净工作区检查；新增 `tests/test_schedule_contract.py`（8 项）静态锁定 installer/runner/checker 三脚本契约。
2. **Pi 子进程最小权限修复**：`quant_agents/pi_client.py` 的 `_environment()` 由整份复制父进程环境改为显式 allowlist（`PI_CHILD_ENV_ALLOWLIST`：Windows 系统/Node 必需变量、可选代理变量、`DEEPSEEK_API_KEY`）；`TUSHARE_TOKEN`、四类证据路径及任意其他 Secret 不再进入 Pi 子进程。新增 3 项测试只断言 key 名，不打印值。
3. **自动 Secret 扫描门禁**：新增 `quant_agents/secret_scan.py` 与 `python -m quant_agents secret-scan`。固定规则版本 `2026-08-29.1`，扫描 `git ls-files --cached --others --exclude-standard` 全部提交候选；发现只记录文件/行号/规则，绝不回显命中值。回执含候选文件哈希聚合、`receipt_sha256`，源码任何变化即失效并要求重扫。逐行人工审查标记 `quant-secret-scan-allow` 仅作用于确认为测试样例的行，保留在回执 findings 中可见，无路径级或全局忽略。门禁接入三处：`health`（source gate 之后、license 之前）、真实 run preflight 首位（`secret_scan` check）、release blockers。当前回执：119 个候选文件、7 个命中全部为已审查测试样例、`status=passed`。
4. **回归脚本加固**：`verify_quant_pipeline.ps1` 新增 15 个根目录 PowerShell 脚本 AST 解析步骤。

2026-08-29 无费用基线复核：

- `verify_quant_pipeline.ps1`：exit 0；**133/133 测试通过**（原 111 + secret scan 10 + schedule contract 8 + pi child env 3 + cli gate 1）；PowerShell AST 解析 15 个脚本通过；最终回归 **MOCK** run `20260829_050653_298` 为 7/7、27 个 manifest 文件、16 个事件、完整性 `ok=true`（首次回归 run `20260829_050315_442` 数字相同），Mock 发布候选按设计返回 BLOCKED（退出码 3）。
- `check_pi.ps1 -NoPing`：Pi `0.84.2`、Node `24.16.0`、模型目录与 no-tools 策略通过；**明确跳过付费 ping，本节不构成当前真实 provider 证据**（最近一次真实 ping 证据仍为 2026-08-25，已过时效）。
- skills/extensions 审计：5 skills/12 锁定文件、1 extension，均 0 error 0 warning。
- 最新真实请求仍为 `20260826_165505_647`：source gate 失败、0/7、0 token、无 Tushare/LLM 调用；`ops-status` 保持 CRITICAL（超过 36 小时时效，符合设计）。
- 项目 JSON：governance 9 个文件、`pi_runtime/package-lock.json`、示例输入及最新 run 产物共 28 个文件 Python 标准 JSON 解析通过（npm lock 的空 property 名仅影响 PowerShell `ConvertFrom-Json`，Python 解析有效，不视为损坏）。
- 当前 Git：仍无 committed HEAD、无 remote、119 个未跟踪项（修复后新增 `secret_scan.py`、`test_secret_scan.py`、`test_schedule_contract.py`）。source gate 因此仍必然失败，这是正确行为。
- 未执行任何付费命令：本轮未运行 `check_pi.ps1`（不带 -NoPing）、`invoke_pi_acceptance.ps1`、真实 `run_quant_agents.ps1`，未安装生产调度。

剩余外部阻断与 2026-08-26 节一致：clean commit/tag（平台）、v2 数据授权、v1 研究协议登记、四方 Registry 批准、v1 执行成本证据、Tushare 组织 Token、当前 DeepSeek 付费重验、真实 7/7、五方身份审批。在这些证据完成前，商业状态保持 **BLOCKED**。

## 2026-09-02 离线 readiness 与日期稳定性加固证据

本节是当前无费用工程验收记录；未调用网络、Tushare、DeepSeek 或任何付费模型，未执行 Pi ping，也未产生市场结论。

1. 新增 `quant_agents/readiness.py` 与 CLI `python -m quant_agents project-readiness --input .\strategy_round.example.json`，一次汇总输入、source、Secret 回执、数据授权、研究协议、Experiment Registry、执行成本、离线 Pi 安装、九个组织角色、预算、provider 配置及最近付费 Pi contract 验收。报告始终明确 `g1_authorized=false`、`real_run_authorized=false`；`--require-ready` 仅在尚不具备人工 G1 评审条件时返回退出码 3，不能代替组织批准。
2. 新增 5 项 readiness 测试，覆盖全阻断收集、全机器条件满足仍不自动授权、过期和未来日期 Pi 验收拒绝、CLI 阻断退出码。修复 `tests/test_operations.py` 中固定日期夹具，使数据条款、协议登记和成本复核日期相对 run 完成时间生成，避免跨月后测试假失败。
3. `python -m unittest discover -s tests`：**138/138 PASS**；完整 `verify_quant_pipeline.ps1`：PowerShell AST 15/15，单测通过，最新明确 **MOCK** run `20260901_201003_339` 为 7/7、27 个 manifest 文件、16 个事件、完整性 `ok=true`。该 run 的 release candidate 按设计为 **BLOCKED**，列出 18 项真实数据、源码、研究、运行时和审批阻断。
4. 最终 Secret scan 覆盖 126 个提交候选文件；7 个命中全部是 `tests/test_secret_scan.py` 内已逐行标记和人工审查的测试样例，未审查命中为 0。回执位于忽略目录 `.cache/secret-scan/receipt.json`，任何后续候选文件修改都会使其失效。
5. 最终离线 readiness 共 12 项检查：输入契约、Secret 回执和本地 Pi 安装通过；其余 9 项继续阻断。主要缺口是无 Git HEAD/tracked/remote、无四类组织外部证据、九个责任角色未指派、预算未批准、无 Tushare Token，以及最近付费 Pi contract 验收已过时。DeepSeek Key 当前仅显示为已配置；这既不构成组织授权，也不构成当前 provider 验收。

当前发布判定仍为 **BLOCKED / G0 GO / G1—G5 NO-GO**。下一步不是扩张 Agent 或策略，而是由真实组织责任人完成源码基线、四类外部证据、角色与预算批准；随后才能在获授权条件下执行当前 Pi contract、Tushare 数据和 schema 7 真实验收。Mock、静态配置、本地哈希链和本文均不得被解释为真实研究或资金建议。

## 2026-09-04 Python 与源码候选可复现性验收

本节取代 2026-09-02 节作为最新无费用工程证据；未调用 Tushare、DeepSeek 或付费 Pi，完整 E2E 明确使用 **MOCK**。

1. 新增 Windows CPython 3.11 项目基线：`.python-version`、`requirements.in`、32 项 transitive hash lock、`.venv` bootstrap、项目 Python resolver、通用 `quant.ps1` 和隔离 lock regeneration。直接 PATH Python 不再是受支持运行入口。
2. 新增程序内 `python_runtime_contract`：检查 CPython 3.11、Windows、精确 `.venv` executable/prefix、user site 关闭、lock SHA-256、32 项安装版本和额外分发包；接入 `health`、真实/Mock run、readiness、bootstrap、回归和 release blocker。当前 CPython `3.11.9`，32 项锁定包 0 偏差，额外运行包 0（pip/setuptools 仅作为 bootstrap 组件）。
3. 新增 source candidate manifest：对每个候选记录路径、类别、大小、SHA-256、二进制/link/reparse 和人工复核标记；拒绝运行产物、凭据格式、archive/database/executable、大文件、路径碰撞、缺失关键源码及未锁 Python 依赖。当前 138 文件、1,335,978 bytes、0 机器阻断、9 review flags，状态仅为 `READY_FOR_HUMAN_FILE_REVIEW_NOT_AUTHORIZED`，未执行任何 Git 写操作。
4. `verify_quant_pipeline.ps1`：19 个根 PowerShell 脚本 AST 通过；**160/160** 测试通过；最新 **MOCK** run `20260904_010648_821` 为 7/7、27 个 manifest 文件、16 个事件、完整性 `ok=true`，并绑定当前 Python runtime lock。Mock release candidate 正确返回 **BLOCKED**（退出码 3，17 项阻断）。
5. Secret scan 覆盖 138 个候选文件，7 个命中全部是 `tests/test_secret_scan.py` 已审查夹具，未审查命中 0。离线 readiness 为 13 项：输入、Python runtime、Secret receipt、本地 Pi 共 4 项通过，9 项阻断；`g1_authorized=false`、`real_run_authorized=false`。
6. 当前 Git 仍无 HEAD、tracked file 和 remote；37 个顶层未跟踪条目展开为 138 个候选文件。因此 WP-02 只是“机器清单可供人工逐文件复核”，不是源码 baseline PASS。

当前判定继续为 **BLOCKED / G0 GO / G1—G5 NO-GO**。人工下一步依次为候选逐文件审查和私有 Git baseline、九角色任命与预算、四类外部证据；只有 G1 人工批准后，才能执行付费 Pi/Tushare acceptance。不得把本节 Mock 指标解释为真实市场表现或真实资金建议。

## 2026-09-05 Source Review Packet 验收

1. 新增 `quant_agents/source_review.py` 与 CLI `.\quant.ps1 source-review-packet`、`.\quant.ps1 source-review-verify --packet-dir <DIR>`。创建命令只接受内部身份一致、Secret scan 已通过且 0 blocker 的当前 source candidate；机器原件包括 candidate manifest、review request、公式注入防护 CSV、审查说明和 packet manifest，后者绑定其余四个文件的 SHA-256。
2. Packet 使用新目录且拒绝覆盖，仓库内输出必须命中 `.gitignore`，也允许显式写到仓库外受控位置。校验器检查固定文件集合、链接/reparse、artifact hash、候选身份、双角色职责分离和空人工字段；状态仍明确未授权。应用层 hash 不是签名，代码不认证 reviewer、不批准 baseline、不执行 Git 写入。
3. 新增 11 项 packet 测试，覆盖 artifact hash、CSV 公式安全、空人工字段、候选身份篡改、重算后弱化审查控制、畸形 inventory/byte count、不可覆盖、输出忽略边界以及创建/校验 CLI 严格退出；另新增 Mock summary 商业门禁顺序测试。全套回归更新为 **172/172 PASS**；19 个根 PowerShell 脚本 AST 通过。
4. 最新明确 **MOCK** run `20260905_105154_540` 为 7/7、27 文件、16 事件、完整性 `ok=true`；release 仍按设计 **BLOCKED**（17 项），没有 Tushare、DeepSeek 付费 Pi、券商、订单或真实资金动作。
5. 当前机器候选为 140 个文件、0 blocker、9 review flags；最终 packet 只能将其交给 Platform/Security 两个不同组织身份逐文件复核。Git 仍无 HEAD、tracked file 和 remote，因此 WP-02 尚未 PASS。

下一步由人完成 review packet 的 140/140 逐文件决定和例外处置，再建立最小权限 private remote、reviewed commit/tag，并从 clean clone 重跑全验收。此前继续保持 **G0 GO / G1—G5 NO-GO**。

## 2026-09-15 双人源码审查决策控制与回归增量

1. 源码 review 已明确拆成机器 packet、外部 Platform/Security decision record、Gate Owner/Platform Owner Git 授权三个状态；应用层 SHA-256 只用于一致性和篡改检测，不认证身份或签名。
2. 新增的结构校验拒绝 malformed/duplicate/unbound review flag，并将 packet 读取失败保留为 BLOCKED；自定义 Secret receipt 可通过 CLI 参数绑定，避免跨环境误用默认回执。
3. `verify_quant_pipeline.ps1` 增加空白 decision 的负向验收：模板状态必须为 `TEMPLATE_NOT_EVIDENCE`，验证退出码必须为 `3`，且不能声称 baseline、G1 或 real run authorization。
4. 本轮代码全套回归 **194/194 PASS**；没有调用 Tushare、DeepSeek 付费 Pi 或其他外部服务，没有建立 Git/remote，没有安装调度。Mock 7/7 和完整性仅证明软件合同。

当前发布结论仍为 **BLOCKED / G0 GO / G1—G5 NO-GO**。下一真正业务动作是组织责任人完成逐文件审查和外部四类证据，而不是继续扩张 Agent 或策略；任何真实运行仍须新 Run ID、授权凭据、数据快照、成本对账、独立复验和五方审批。
