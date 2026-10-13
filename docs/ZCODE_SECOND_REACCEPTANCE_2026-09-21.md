# Zcode 收尾冲刺第二轮复验

日期：2026-09-21。被验收项目：`E:\quant-investment-workbench`。

## 结论

**现有回归通过，最终验收暂不通过。** 本轮独立重跑确认 139 项 pytest 和隔离浏览器栈 4 项测试通过，但三项补充故障复现仍暴露预算持久性、跨会话租约栅栏和失败路径清理问题。不能据此宣布六项收尾全部闭环，也不能开始付费模型或真实新闻试采。

本轮只审查、测试并新增本报告；不修改业务代码，不暂存、不提交、不处理钩子、不更新记忆。补充复现使用临时目录、临时数据库和模拟提供商，没有付费模型调用。

## 一、本次独立验证的通过项

| 验证 | 本次结果 | 证据边界 |
| --- | --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q` | 139 passed，exit 0 | 现有测试集通过，不代表覆盖所有崩溃与并发条件 |
| `.\.venv\Scripts\python.exe scripts\run_e2e_stack.py` | Playwright 4 passed，exit 0 | 正常执行路径完整通过 |
| 栈身份校验 | `stack verified (stack_id match)` | 本轮 stack_id 为 `e2e-a5c15550bc92`，端口 2476 |
| 正常路径 teardown | `teardown verified: temp dir removed, daily workspace unchanged` | 临时根 `wb-e2e-q8vklxwg`；日常目录比较是元数据清单校验，非文件内容逐项哈希 |

干净环境的带哈希安装与 139 项复跑是 Zcode 提交的证据，本轮未独立重做，不能写成 Codex 本次验证。PostgreSQL 竞争及真实 TLS/SNI 握手继续标记未验收，不以 SQLite 或 MockTransport 结果代替。

## 二、剩余缺陷与复现证据

### S1 / P1：出站前预算预留未提交，异常回滚可抹除负债

位置：`E:\quant-investment-workbench\services\api\wb_api\budget_ledger.py:27`、`:37`；`E:\quant-investment-workbench\services\api\wb_api\agent_service.py:190`、`:196`。

`create_reservation` 仅执行 `flush()`，随后直接进入模型调用。worker 在执行完成后才提交；异常分支回滚。因此“数据库表中有预算预留”尚不等于“出站之前预留已经持久化”。

复现：在模拟提供商的调用入口，用独立会话查询预算预留；随后模拟请求发出后的异常，由调用方按 worker 路径回滚，再用独立会话查询。

```json
{"probe":"reservation_durable_before_dispatch","visible_to_other_session_during_dispatch":[0],"remaining_after_rollback":0}
```

影响：提供商可能已接收请求并产生费用，但本地未留下负债；重启或重试后可能继续放行。现有“返回 timeout 后保留预留”的测试没有覆盖这一事务边界。

交 Zcode 修复：设计独立且持久化的预算预留事务，出站前提交；将预留绑定稳定调用标识，异常和崩溃后保持未知负债，只有有证据的结算或释放才能改变占用。不要仅在现有业务事务中随意插入 commit，需说明它对 job、run 与事件原子性的影响。

验收：提供商入口的独立会话已能看到预留；模拟出站后异常及业务事务回滚，预留仍在；重启重试不绕过占用。另以隔离进程验证强制退出后的持久性，禁止真实付费调用。

### S2 / P1：租约栅栏依赖缓存 ORM 对象，旧 worker 可覆盖新 owner

位置：`E:\quant-investment-workbench\services\api\wb_api\queue_ops.py:73`、`:81`、`:100`。

`finish_job_owned` 在 Python 中判断 `job.lease_owner != owner`，但长期会话持有的 ORM 对象可能仍是旧 owner；后续更新没有把租约所有权作为数据库条件。

复现：会话 A 认领并保留对象；会话 B 将租约过期、回收并由新 owner 认领；A 不刷新对象，使用旧 owner 完成任务并提交。

```json
{"probe":"stale_orm_owner_fence","old_memory_owner":"worker-old","database_owner_before_finish":"worker-new","database_status_after_old_finish":"succeeded","database_owner_after_old_finish":null}
```

影响：旧 worker 实际完成了属于新 worker 的任务。现有单会话刷新后再检查 owner 的测试不能证明跨会话栅栏成立。

交 Zcode 修复：通过数据库条件更新校验 job id、running 状态及本次租约唯一代次/令牌，并核对更新行数；旧租约不得更新结果、清除新租约或产生成功事件。明确结果入库与完成栅栏的事务关系，不能仅增加 ORM refresh，后者仍可能检查后变化。

验收：保留上述双会话、旧对象不刷新的复现；旧完成被拒绝且新租约、状态与产物不变，新 owner 可以正常完成。覆盖相同 worker 标识重新认领时的租约代次变化。PG 竞争结果继续单独标记，未测不得写通过。

### S3 / P2：e2e runner 提前返回或异常绕过临时目录清理

位置：`E:\quant-investment-workbench\scripts\run_e2e_stack.py:121`、`:151`、`:165`、`:170`。

进程关停位于 finally，但日常清单校验和临时目录删除位于 finally 之后。迁移失败、健康/身份校验提前返回以及异常退出都可能跳过后两项。

复现：将迁移子命令模拟为 exit 17，不启动任何服务；runner 返回后检查其创建的临时根。

```json
{"probe":"runner_early_failure_cleanup","exit":17,"temporary_root_still_exists":true}
```

复现产生的目录由外层测试清理，不留驻后台进程。

交 Zcode 修复：把进程终止、等待、日常状态检查、临时根删除纳入统一且必执行的清理流程；保存原始错误并明确清理失败退出码优先级。只终止 runner 自己创建的进程，不批量终止 node/python。

验收：迁移失败、启动失败、身份不匹配、Playwright 非零退出及执行异常均触发清理；全部创建的临时资源删除，无子进程残留。强制制造清理失败时必须非零退出并打印可定位的残留路径，不得忽略错误。

## 三、证据表述需要校准

1. runner 的日常目录清单由路径、文件大小和整数 mtime 计算摘要，不是文件内容 SHA-256；不能证明同大小、同时间戳的内容没有被改写。若维持“日常数据未变”的强验收口径，应做内容级校验，并增加同大小同时间戳篡改的检测测试。
2. 输入提示词按字符数估算并截断不等于供应商 token 级硬限制；系统提示词与格式开销也应纳入预算解释。不要将这一实现写成精确 token 硬保证。
3. PG、真实 TLS、构建后端哈希闭包、Git 可提交基线均不得因本次单机测试通过而转为通过。扫描器问题必须走明确允许的处理流程，不能以换路径或改写形式规避安全判定。

## 四、下一批范围与提交要求

只修 S1–S3 及相关证据口径，不同时开发新闻试采、DAG 或组合风险新功能。建议顺序：S1 持久化事务边界 → S2 数据库租约栅栏 → S3 全退出路径清理 → 回归与材料更新。

向 Zcode 要求以下交付：

1. 三项修复的文件、准确行号、根因与事务/状态机说明。
2. 每个新增测试均说明旧实现如何失败，必须保留独立会话与失败路径条件。
3. 现有全量 pytest、新增负向测试及隔离 e2e 的实际结果行与退出码，不预填通过数。
4. 预算的出站前持久化、异常回滚后负债仍存在、旧租约完成被拒、失败 teardown 完整执行的可核查输出。
5. 更新状态总表，明确“代码实现”“SQLite 实测”“PG 未验收”“真实外部服务未验收”，不要混为一项。
6. Git/钩子问题保持单独阻塞；未经批准不禁用钩子、不绕过扫描、不提交。真实新闻来源与付费调用继续走原有人工批准门槛。

上述通过后，才讨论 WB-007 有界新闻试采。该阶段先确认来源授权、允许域名与路径、请求频率、失败重试、保存与删除规则、观察期和停止条件；本报告本身不构成任何外部数据采集、付费调用、交易或实盘授权。
