# Zcode 交付验收：2026-09-21

审查对象：`E:\quant-investment-workbench`。
对照方案：`INVESTMENT_WORKBENCH_PLAN_2026-09-18.md`。
结论：**原型部分通过，整体阶段验收 FAIL；暂不进入纸面资金账本或实盘扩展。**

遵照用户要求，本次未修改业务代码、测试源码、配置、依赖或数据库结构。只新增本验收文档。执行现有测试及通过 stdin 运行补充复现；复现使用临时 SQLite 数据库和模拟模型返回，没有调用付费模型或券商，也没有操作现有开发库的审批。

## 1. 实际执行与范围

| 检查 | 本次结果 | 能证明什么 |
|---|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | 90 项全通过，进程 exit 0 | 现有测试覆盖的行为可运行 |
| `node node_modules/typescript/bin/tsc --noEmit`，cwd=`apps/web` | exit 0 | 当前前端类型检查通过 |
| 临时 DB 升级 0001→0002 | 补充复现中正常完成 | SQLite 临时库迁移能运行 |
| 8 组补充负向场景 | 发现下列缺陷 | 原测试存在重要覆盖空白 |
| `git rev-parse --verify HEAD` | exit 1，无 HEAD | 还没有可引用的提交基线 |
| 代码审查 | 阅读 API、Pi、预算、任务、审批、抓取、契约、前端测试配置 | 明确实现边界及未完成项 |

90 项测试出现 Starlette/httpx、AnyIO 弃用警告，不是本轮失败原因。Python 依赖只有宽泛下限、没有发现对应锁文件，也是后续可复现环境工作。

未复跑浏览器 e2e：现有 Playwright 配置固定连接 `127.0.0.1:8310` 的开发库，并会创建案件、任务和提案；不为了验收污染日常数据。后续须先提供独立测试栈。未重新执行真实 Pi 调用，既有文档中的真实调用记录仅视为历史交付声明，不冒充本次验收事实。没有在 PostgreSQL 上验证并发。

## 2. 必须修复的问题

### R1 / P1：来源禁止送模型，但真实调用路径没有执行权限检查

- 位置：`E:\quant-investment-workbench\services\api\wb_api\agent_service.py:58`、同文件 `:121`；`repos.py:485`。
- 路径：案件快照→runtime/key/budget 检查→模型调用，没有读取并校验每个来源的 `allow_send_to_llm` 或来源状态。快照中也没有权限版本。
- 复现：临时来源设置 `allow_send_to_llm=false`、`status=paused`，注入包含该来源的最小快照和假的 runtime/key，替换模型函数为 Mock；执行后 `mock_provider_called=true`。真实网络调用次数为零。
- 影响：数据库登记的处理权利并未约束出站内容；当前只送标题也仍然是来源内容，不能因没有正文就忽略权限。
- 修复验收：在实际调用前从权威来源表检查全部证据权限，拒绝/过滤的策略要明确；全部不可用时零模型调用。来源权限撤回、排队后权限变化、混合允许/禁止源均需测试；快照绑定当时权限版本。

### R2 / P1：模型引用不存在的证据，也能被记录为成功

- 位置：`E:\quant-investment-workbench\services\api\wb_api\agent_service.py:155`、`:168`；`repos.py:540`。
- 复现：模型 Mock 返回 `status=supports`、一个 claim、`evidence_refs=["nonexistent-document-id"]`，快照只有 `known-document`；结果 `run_status=succeeded`，不存在的引用原样被采纳。
- 原因：契约要求引用非空，但没有验证引用属于本次快照，也没有校验逐条断言支持关系。
- 影响：界面的“有证据决策”可以包含虚构引用，证据可追溯性失效。
- 修复验收：不存在、其他案件、当前快照外、尚不可得的引用均拒绝；先做引用集合校验，再逐步建立 claim→evidence 关系。提示词中写“必须来自快照”不等同服务端检查。

### R3 / P1：提案变化后旧批准仍有效，提案哈希不绑定证据内容

- 位置：`E:\quant-investment-workbench\services\api\wb_api\repos.py:594`、`:633`。
- 复现 A：创建并批准提案，然后在临时库改变案件标的集合并生成新提案。新旧 hash 不同，但旧状态仍 `approved`、旧批准 `revoked_at=null`。
- 复现 B：在临时库改变证据正文及内容 hash，保持其他输入不变，重新生成提案；`proposal_hash` 不变。该操作是依赖绑定的故障注入，未改真实数据。
- 原因：仅 supersede `draft/awaiting_approval`；hash 只覆盖 case_id、targets、部分检查和约束，不覆盖证据快照与完整决策上下文。
- 影响：后续执行端可能同时看到新提案和陈旧有效批准；证据更正不能可靠触发重新决策。
- 修复验收：明确案件当前提案版本，修改关键上下文使旧授权失效但保留历史；hash 绑定证据、策略/模型、政策、模式及适用账户范围。更正、撤稿、并发审批和版本更新都需要负向测试。

### R4 / P1：付费预算在价格未知时失效，也没有调用前预留

- 位置：`E:\quant-investment-workbench\packages\agent_runtime\wb_agents\budget.py:13`、`:25`；`services\api\wb_api\agent_service.py:104`、`:112`。
- 复现：月上限设为 1，价格缺失，`estimate_cost_cny(1000000,1000000)=null`，`evaluate_budget(0,None)` 返回 `allowed=true/level=ok`。
- 原因：SQL 汇总忽略 null，未知费用不消耗可见余额；调用一律传 `extra_cny=None`，没有最坏费用预留。失败返回路径也早于 usage/cost 持久化。
- 影响：可以持续付费调用而预算一直显示未使用；即使已配价格，最后一次调用仍可能跨越上限。
- 修复验收：未知单价/usage 采用阻断或经明确授权的保守计费上限；事务预留→结算→释放，处理失败、超时和并发。不可把未知当作零。历史成本不应伪造回填。

### R5 / P1：任务提交不幂等，网络重试可重复执行与计费

- 位置：`E:\quant-investment-workbench\services\api\wb_api\routes\jobs.py:37`；`repos.py:725`。
- 复现：相同案件、payload、`Idempotency-Key: same-request` 连续 POST 两次，返回两个不同 job_id。
- 原因：接口不消费幂等键，enqueue 每次生成 UUID，没有对应唯一约束。
- 修复验收：相同键同请求返回原任务，不重新计费；同键不同请求返回 409；并发请求与客户端超时重试都覆盖。幂等键需包含身份/接口范围，避免跨请求错误复用。

### R6 / P1：当前 SQLite 模式 RSS 第二次抓取会抛时区异常

- 位置：`E:\quant-investment-workbench\services\api\wb_api\routes\sources.py:120`。
- 复现：临时来源处于 active，Mock RSS 返回成功空 feed；第一次 POST fetch=200，第二次抛 `TypeError: can't subtract offset-naive and offset-aware datetimes`。
- 原因：SQLite 往返时间没有 tzinfo，直接与 UTC aware 的 `utcnow()` 相减。
- 影响：当前真实 RSS 虽未验收，但一旦启用就无法可靠重复抓取；原来应该返回 429 的间隔控制变成 500。
- 修复验收：持久化和比较统一 UTC；首次抓取、间隔内重试、间隔后抓取、失败后重试同时覆盖 SQLite/PostgreSQL。

### R7 / P2：RSS 失败状态随请求事务回滚，健康记录丢失

- 位置：`E:\quant-investment-workbench\services\api\wb_api\routes\sources.py:132`、`:133`；`routes\overview.py:22`。
- 复现：Mock 抓取抛 `UnsafeFetchError('review-fixture-failure')`，API 返回 502；新 session 读取健康记录，找不到该失败信息。
- 原因：记录失败后立即抛 HTTPException，session dependency 将整个事务 rollback。
- 影响：故障源没有可靠失败次数/最近失败，面板可能显示上一次成功；失败限流也可能无效。
- 修复验收：失败状态和审计事件独立可靠保存，仍返回准确 HTTP 错误；网络超时等 httpx 异常也统一处理。不能为保存健康而误提交其他半完成业务写入。

### R8 / P2：审批人由请求自报，关键字过滤不能证明人工身份

- 位置：`E:\quant-investment-workbench\services\api\wb_api\routes\proposals.py:31`、`:102`；`security.py:18`。
- 复现：持测试写令牌提交 `approver=someone-else`，返回 201，并以该名称写入人工审批记录。
- 当前边界：没有发现无令牌绕过。问题是已经认证的 token-holder 可以自行声明其他身份，而实现文档把拒绝 agent 名称当作 human-only 保证。
- 修复验收：单 Owner 版本也应从服务端认证上下文派生固定 actor，不接收可改变审计主体的 approver 字段；代理调用凭据不能具有审批权限。多用户阶段再加入具体身份、角色与 MFA。

## 3. 还不能标为完成的部分

| 项目 | 审查结论 | 下一验收条件 |
|---|---|---|
| WB-009 PiAdapter | 调用封装存在，但 R1/R2/R4 阻断整体 PASS | 权限、证据、费用边界验收 |
| WB-010 DAG | 实际是单 news_analyst job 队列，不是完整多节点 DAG | 节点依赖、阻断、检查点、重试和可见状态 |
| WB-010 并发 | `claim_next_job` 为 select 后普通 update，没有原子认领/行锁；单 worker 假设没有普遍强制 | 单实例强约束，或 PG 并发认领测试；不要声称互斥已证实 |
| WB-011 UI | TypeScript 通过，既有 e2e 历史声明未本次复测 | 临时测试栈下重跑浏览器链路 |
| WB-012 决策队列 | 已有原型，但 R3/R8 阻断可信审批 | 版本和身份绑定后验收 |
| WB-013 研究核 | 当前只抽取动量计算，5 项相关测试在90项中通过 | 不等同回测/规则簿/组合研究全部完成 |
| WB-007 真实新闻 | GDELT TODO；真实 RSS 尚无当期运行证据 | 修 R6/R7 后进行允许来源的有界试采 |
| PostgreSQL | 未验收，当前 SQLite | 驱动、实际迁移、并发、恢复实测 |
| 版本与依赖 | 无 HEAD，Python 宽版本依赖 | 依赖锁、可审查提交基线、干净环境复现 |

静态补充观察：`packages/news_ingestion/wb_news/fetch.py` 在调用 httpx 前做 DNS 公网校验，但实际连接仍按域名重新解析，未将连接绑定到已验证地址；这是 DNS rebinding 的检查/使用间隙。本轮未向任何内网目标发送请求，不把它算成已实测的攻击成功；在开放用户可配置源之前应补安全验证。

快照和模型提示目前只包含标题及元信息，没有新闻摘要正文。适合作标题分诊，不应把它宣传为完整新闻事实分析。未来加入正文先落实 R1 与内容许可，再做输入长度和质量评估。

`IMPLEMENTATION_STATUS.md` 内部有旧 TODO 与顶部 PASS 同时存在（e2e、研究核等）；需要一张唯一的当前状态表，历史批次原样留在历史段落。

## 4. 当前可接受的成果

独立工作区、API/前端基础、SQLite 迁移、fixture/real 标签、Pi 子进程隔离参数、决策展示、基本写令牌、部分研究核抽取有实际代码。90 项通过不是无效成果，但不足以覆盖上述业务边界。

目前没有资金执行服务，缺陷尚未造成实盘订单影响。建议继续作为受限开发原型，完成修复后再评审扩大范围。

## 5. 给 Zcode 的修复批次（替代下一功能扩张计划）

### 批次 A：可控模型运行，预计 2—4 工作日

处理 R1/R2/R4/R5。先增加会失败的负向用例，再修实现。

交付：按证据来源检查出站权限、引用集合验证、预算预留结算、请求幂等键、失败 usage 记录。演示两条路径：允许且正确的调用成功；禁止源/虚构引用/未知费用/重复请求均得到准确状态。

不需要付费模型即可通过大部分边界测试。确需真实验收时，只做一个获准的有界调用，记录实际模型、模式、用量与成本状态。

### 批次 B：审批与新闻连续运行，预计 2—3 工作日

处理 R3/R6/R7/R8。批准主体从认证上下文派生；上下文改变使旧授权失效；RSS 连续抓取和失败状态持久化。

交付：更正/撤稿/提案变化/过期/撤回的状态机测试，隔离浏览器审批流程，RSS 正常→间隔限制→超时→恢复的健康时间线。

### 批次 C：可复现与声明校准，预计 2—3 工作日

锁定 Python 依赖；建立不碰日常数据的 e2e 栈；修正任务卡与当前状态。若仍只有单节点 job，就明确标为“单节点持久化队列”，DAG 保持部分完成。

解决单 worker 约束或 PG 原子认领；并发领取、崩溃恢复、审批竞争需真正并行测试，不能用顺序调用替代。处理 DNS 连接校验间隙后，再允许增加真实来源。

不自行跳过外部扫描钩子。先复核钩子范围和实际报错，提供可审查的解决方案，再建立提交基线。

### 修复后复验门槛

1. 现有 90 项继续通过；新增上述失败场景的回归测试通过。
2. 同一请求重试不新增 job/费用；禁止源零出站调用；无效引用不产生 succeeded。
3. 更改证据/策略/政策使授权正确失效；审批主体来自服务端身份。
4. RSS 能连续采集、正确节流、保留失败和恢复记录。
5. 独立前端测试栈验收，真实与 fixture 页面标签及事件相符。
6. 当期状态表与证据一致，列明仍缺失的 PG/真实新闻/多代理能力。

达标后才制定下一功能冲刺：WB-007 有界新闻试采 → WB-013/014 完成研究核与点时快照 → WB-015 组合风险 → WB-016 纸面账本。真实券商依旧是更后面的独立验收，不在修复批次内。

## 6. 复现方式交接

本轮补充脚本通过 PowerShell here-string 管道传给项目 `.venv\Scripts\python.exe -`，没有新增或改动测试文件。使用 `tests/conftest.py` 的 client fixture 创建系统临时目录中的数据库，并用 `unittest.mock.patch` 替换模型和外部抓取。结束后临时目录自动释放。

Zcode 应将上述复现条件写成正式回归测试，而不是仅照本文件修改判断。验收报告以 2026-09-21 当时工作树为对象；修复后需要新的测试证据和复验报告。
