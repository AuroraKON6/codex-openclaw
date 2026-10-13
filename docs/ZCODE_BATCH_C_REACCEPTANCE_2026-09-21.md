# 批次 A—C 修复复验报告

日期：2026-09-21。对象：`E:\quant-investment-workbench` 当前工作树。

结论：**部分修复通过；整体复验仍 FAIL，不接受“R1–R8 已全部闭环”的声明。**

遵守用户“不要改代码”的要求：没有修改业务/测试源码、依赖、配置，没有接触真实资金，没有执行付费模型调用。本轮只新增本报告。补充复现由 stdin 执行，使用临时库、临时快照目录、模拟模型返回；原代码本身未修改。

## 一、当期验证证据

| 检查 | 实际结果 | 证据边界 |
|---|---|---|
| 原测试全量执行 | 126 项通过、exit 0 | 在进程内把 `wb_api.repos.PROJECT_ROOT` 指到系统临时目录后运行 `pytest.main(['-q'])`，防止测试快照污染日常目录；计算/业务实现不变 |
| SQLite 真并行认领 | 批次 C 两个线程竞争测试通过 | 只证明测试覆盖的 SQLite 场景，不证明 PostgreSQL |
| DNS 请求绑定 | IPv4/IPv6、Host/SNI、重定向私网拒绝测试通过 | MockTransport 检查请求字段；不是实际 TLS 握手/代理环境验收 |
| 依赖版本 | 31 个锁定包与当前 venv 版本全部相同 | 没有重装环境，不把版本比对当作 hash 安装验收 |
| 未知费用补充复现 | 连续两次超时，费用均 null，模型 Mock 被调用两次 | 每次执行后明确 commit，第一轮未知费用确实已持久化 |
| 点时补充复现 | `available_at=2099-01-01` 的引用被接受，run=succeeded | 临时库，模型响应为 Mock |
| 并发幂等补充复现 | 一次 202，一次未处理 `IntegrityError` | 两个独立 session，barrier 保证两者都查不到记录后竞争插入 |
| 独立 e2e runner | 静态审查，未执行 | 发现快照路径仍共享，不为复验污染日常产物；用户给出的 4/4 保留为 Zcode 历史结果 |
| PostgreSQL | 未实测 | 当前 PATH 未发现 psql/docker，未额外安装或启动数据库 |

现有测试通过是有效成果。R1 来源权限、R2 不存在引用拒绝、R3 新提案覆盖旧 approved 状态、R6 时区修复、R7 错误留存、R8 服务端 Owner 身份，都有新增测试通过；但原验收目标还包含下面遗漏的边界。

## 二、需要继续处理的问题

### C-R1 / P1：PostgreSQL 认领仍缺少防止重复认领的条件

位置：`E:\quant-investment-workbench\services\api\wb_api\queue_ops.py:33`。

当前结构是：外层 `UPDATE ... WHERE job_id=(SELECT ... WHERE status='queued' LIMIT 1) RETURNING ...`。外层没有 `status='queued'` 的 compare-and-set 条件，子查询也没有 `FOR UPDATE SKIP LOCKED`。

根据 PostgreSQL READ COMMITTED 的语义，两条并发语句可能先选中相同候选，后更新者等待前者提交，再重新判断外层条件；候选 ID 没有改变时，缺乏外层状态检查就存在再次更新、覆盖 lease_owner 和增加 attempt 的风险。这里是代码与数据库语义分析，**本机没有进行 PostgreSQL 复现**。

来源：[PostgreSQL 官方事务隔离文档](https://www.postgresql.org/docs/current/transaction-iso.html)。SQLite 单写者串行化不能证明同一语句在 PostgreSQL 下具有同样的认领语义。

修复要求：使用经验证的 PostgreSQL 队列认领模式，例如受锁候选选择结合外层状态条件；SQLite 单独保留适合其锁模型的实现。两种方言分别真并行验证。还应覆盖回滚、租约过期与旧 worker 完成时的 ownership/fencing 检查。没有 PG 环境时，明确标为“SQLite 验收通过、PG BLOCKED”，不要写“任意并发恰一胜者”。

### C-R2 / P1：预算“预留”没有落库，超时未知费用不占额度

位置：`E:\quant-investment-workbench\services\api\wb_api\agent_service.py:142`、`:163`、`:175`。

`reservation = worst_case_cost_cny()` 只是局部变量，传入 gate 比较后就开始外部调用；不存在持久化 reservation、余额扣占或状态转换。下次仍然只 SUM 已知 cost_cny。

补充复现使用已配单价、月预算 0.2、每次预计上限 0.116；让模型 Mock 返回超时且 usage 未知。第一轮 commit 后再次调用，两个 run 都 timed_out/cost=null，模型 Mock 调用了两次。两次需要保留的上限合计 0.232，超过月限额，却均被放行。这不证明实际已花费 0.232，只证明未知负债没有按所声称上限保留。

另外 `WB_PI_MAX_TOKENS_IN/OUT` 只用于估算，没有看到相应输入截断/拒绝或供应商输出上限绑定；因此不能把这些数值称为实际最坏费用保证。

修复要求：单独持久化预算预留，原子检查 available budget 与扣占；调用成功按实际结算，超时未知保持预留待核对，确定无费用才能释放；崩溃重启不能消失。并发预留应互斥。token 上限必须真正执行，或用明确的保守限制策略。owner 允许未知费用也需要一个有界、可审计的风险额度。

### C-R3 / P1：点时检查只写在提示词，未来证据仍进入成功决策

位置：`E:\quant-investment-workbench\services\api\wb_api\repos.py:485`；`agent_service.py:208`。

快照收集 CaseEvidence 时没有按可决策时间过滤。后续 allowed_refs 只检查 ID 属于快照，没检查 `available_at`。

补充复现：将临时案件证据的 available_at 设为 2099 年，模型 Mock 正常引用该证据，结果 succeeded。

修复要求：服务器冻结明确的 decision_as_of；构建快照及验证引用时执行 available_at≤decision_as_of。未来/无可靠可得时间的输入需要拒绝或显式标为不可用于该时点决策，不允许仅靠提示词提醒模型。增加未来证据、时区转换、排队后截止时间及回放测试。

### C-R4 / P2：并发提交相同幂等键会出现未处理异常

位置：`E:\quant-investment-workbench\services\api\wb_api\routes\jobs.py:51`、`:72`。

新增唯一约束确实阻止了两个 job 落库，但接口仍是先查后插，没有处理插入竞争。补充复现用两个 session 同时查到不存在、再竞争插入：一个返回 202，另一个抛 IntegrityError；没有异常转换时对应请求可能成为 500。

这次未发现两个任务成功落库，所以不要把问题描述成“唯一约束无效”。缺陷在于并发重试没有兑现原任务重放/明确409的 API 合同。

修复要求：用适当 upsert 或在正确事务/savepoint 边界捕获唯一键冲突后重读。相同键同 payload 返回原任务；不同 payload 返回409；不得吞掉无关完整性错误。增加真实并发 HTTP/服务层用例，记录全部线程返回与有界超时。

### C-R5 / P2：e2e 隔离没有覆盖快照，直接调用仍默认日常端口

位置：`E:\quant-investment-workbench\services\api\wb_api\repos.py:547`；`scripts/run_e2e_stack.py:56`；`apps/web/playwright.config.ts:15`。

runner 设置了临时数据库、端口和令牌，这部分正确。但 fixture Agent 同样调用 snapshot_case_evidence，其目录固定为项目 `var/snapshots`，所以 e2e 仍会把测试产物写到日常目录。

Playwright 缺少 E2E_BASE_URL 时仍回退 8310。只靠文档要求“必须用 runner”不能防止直接 `npm run test:e2e` 误用日常服务；若当时环境有有效令牌，写操作仍可发生。

修复要求：统一可配置 artifact/state root，e2e 的数据库、快照、Pi state、日志与报告都落在隔离根；缺少隔离配置时直接失败，不能默认日常端口。运行前校验服务器随机 stack_id/test-mode；运行前后核对日常数据库及产物目录不变。当前实现有空 key 覆盖配置，尚未发现该路径会回退真实 key；但“预算上限=1”本身不是硬禁付费机制，建议另设执行层禁外部调用并负向验证。

### C-R6 / P2：吞掉清理失败不能证明“跑完即焚”

位置：`E:\quant-investment-workbench\scripts\run_e2e_stack.py:50`、`:105`。

`ignore_cleanup_errors=True` 会让测试通过但临时目录可能残留；kill 后未再次 wait，也没有退出进程树/端口释放/目录不存在的断言。本轮没有实际观测到残留，不把潜在情况说成已发生。

修复要求：管理并等待本测试栈拥有的子进程退出，kill 后 wait，限定次数重试清理。清理不成功明确报告 teardown failed/残留路径并返回非零或单独未通过状态，不能继续宣称完全销毁。不得通过杀死所有 Python/node 进程解决。

## 三、不能混同的证据

1. SQLite 线程竞争 PASS，不等于 PostgreSQL 竞争 PASS。
2. 请求上写了 SNI/Host，不等于经过真实 TLS 栈和证书主机名验证。本轮认可实现方向与请求字段测试，后续补控制环境 TLS 测试。
3. 锁文件里有哈希、当前版本一致，不等于已经在干净环境 `--require-hashes` 安装成功；应明确 Python/平台范围以及项目自身和构建依赖的安装步骤。
4. 模型接口返回真实格式，不等于内容在那个时点可得或费用已受控制。
5. 基础测试126项通过，不代表审查发现的未覆盖场景已闭环。

## 四、给 Zcode 的最后修复冲刺

本轮不批准跳入 WB-007 日常真实试采或 WB-016 资金账本。先做以下范围明确的收尾，不再添加新产品功能：

| 顺序 | 工作 | 必须交付的证据 |
|---|---|---|
| 1 | e2e 隔离根、缺配置拒绝、严格 teardown | 日常目录前后清单不变；临时目录/端口/进程均清除；故障清理也通过 |
| 2 | 预算真实预留与未知费用负债 | 已提交超时→第二次调用正确阻断；并发预留和崩溃恢复 |
| 3 | 决策截止时间与未来证据检查 | 2099样例不可成功；合法时点样例成功；时区边界 |
| 4 | 并发请求幂等 | 同键同请求无500、只一个任务；同键异请求409 |
| 5 | PG认领与租约所有权 | 实际PG竞争测试；若无环境则显式BLOCKED并限制部署能力 |
| 6 | 清洁环境安装、TLS验证、状态表 | 将实测/静态/历史证据分列，不提前标全部完成 |

修复时先把复现条件写成会失败的回归测试，再修业务代码；不得删除断言或把允许行为改成文档规定以跳过缺陷。代码由 Zcode 修改，本报告作者未修改。

满足上述复验条件后再制定功能冲刺：有界新闻采集与7日观察 → 点时研究快照/实验注册 → 组合风险 → 模拟账本。没有获得本次完整 PASS 前，不把历史4/4或126项通过替代剩余验收。
