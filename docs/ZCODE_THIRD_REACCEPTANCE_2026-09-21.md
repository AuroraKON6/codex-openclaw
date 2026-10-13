# 第三轮复验：S1–S3

日期：2026-09-21。验收对象：`E:\quant-investment-workbench`。
本轮只验收，不修改业务代码、不暂存、不提交、不更新记忆。仅新增本报告。所有补充探针使用临时数据库、临时状态目录或模拟故障，不调用付费模型、不采集真实新闻。

## 结论

**尚不能最终通过。** S1 的出站前提交已实现；S2 的数据库条件更新与代次令牌已实现，但 worker 未遵守栅栏返回值，旧 worker 的决策仍能入库；S3 覆盖了常见步骤失败，但清理本身失败时仍可跳过目录删除。剩余问题属于原 S2/S3 范围，不要求扩展新功能。

## 本轮实测

- 全量 pytest：本轮 exit 1，不是全绿；失败项为 `tests/test_sprint3.py::test_s3_all_exit_paths_run_cleanup[cleanup_fail-201]`。其他项未报告失败。不能沿用 Zcode 的“149 项 exit 0”作为本轮结果。
- 原有隔离 e2e：4 passed (11.6s)，exit 0；`step exit=0, final exit=0`。
- e2e 栈：`e2e-1dc3cebbd6a0`，端口 54471；栈身份检查通过，runner 报告临时目录删除、日常工作区未变。
- 临时库迁移执行到 0005；没有对日常数据库执行迁移。
- 干净环境依赖安装、PostgreSQL 竞争、真实 TLS 握手、真实模型调用，本轮未验收。

## T1 / P1：job 更新被拒，但过期 worker 的决策仍提交

位置：`E:\quant-investment-workbench\services\api\wb_api\worker.py:47`、`:70`；`E:\quant-investment-workbench\services\api\wb_api\agent_service.py:82`、`:295`。

`finish_job_owned` 的数据库栅栏本身方向正确。但 worker 不检查它的布尔返回值，而 `execute_agent_run` 已将决策写入当前事务。即使完成任务被拒，最后仍执行 `session.commit()`，使旧 worker 的业务输出可见。

独立复现：创建临时 case 和 fixture job；worker 完成认领后，在执行入口用独立会话把所有权与令牌切换为新代次，模拟已发生的接管；然后让原 worker 运行真实的 fixture 决策代码和真实的 `tick_once` 收尾逻辑。

```json
{"probe":"worker_fence_output_atomicity","job_status":"running","owner":"new-worker","decisions_committed":1}
```

结果：新 owner 的 job 没被覆盖，但旧 worker 的决策已经落库。此次探针聚焦“接管已经发生后”的输出提交，不是 PG 并发压力测试。现有直接测试 `finish_job_owned`、且未先产生业务输出的测试不足以证明整个 worker 的输出隔离。

修复要求：把完成栅栏与业务结果采纳放在一致的事务边界内，拒绝时不能提交旧代次的决策、成功状态或成功事件。可以保留明确标记为废弃的尝试和真实费用审计，但不得作为有效结果对外使用。特别注意不能因回滚结果而丢掉 S1 已提交的预留；如果实际 usage 已知，应设计与有效决策采纳分离的费用结算路径。

验收：增加 `tick_once` 集成测试，在产生结果前模拟独立会话接管；拒绝后无旧代次有效决策/成功事件，新租约不变，新 owner 可完成。覆盖同名 worker 的代次变化。不要仅把原有队列单元测试再跑一遍。

## T2 / P2：清理阶段异常仍会阻断剩余清理

位置：`E:\quant-investment-workbench\scripts\run_e2e_stack.py:124`、`:179`、`:198`。

实际代码仅将进程关停放在 finally；清单比较和目录删除仍在 finally 之后。捕获了 run_steps 的常规异常，使已有六场景通过，但清理阶段的 `_daily_manifest()` 读文件失败会直接抛出，目录删除与最终退出码打印均跳过。初始清单检查也在 try 之前；进程 terminate/wait 的非 TimeoutExpired 异常同样缺少逐项保护。

独立复现：临时根内运行 runner，注入步骤异常；初始清单成功，清理时的清单读取模拟抛出 OSError。不启动服务，不触碰日常文件。

```json
{"probe":"cleanup_manifest_exception","temp_root_remains":true}
```

探针的外层临时目录管理器已删除残留。这里模拟的是磁盘/文件读取故障，不声称本次发生了真实磁盘损坏。

修复要求：从资源创建开始建立外层清理保护；进程关停、清单验证、临时目录删除应分别容错并汇总错误，前一步失败不能使后一步不执行。始终打印原始步骤码、最终码及未清理资源位置；无法验证清单不能打印“未变化”。

验收：除现有六种步骤注入外，增加清理阶段清单读取失败、单个进程关停失败、初始清单失败；验证其他清理动作仍执行、最终非零退出且报告准确。

## S3 同范围的安全边界

1. `_daily_manifest` 完全跳过大于 50MB 的文件，不能据此无条件声明全部日常数据内容未变。应使用分块内容哈希覆盖大文件，或明确未验证并拒绝输出全量通过结论。
2. `WB_E2E_BASE_DIR` 当前可指向既有目录，runner 会把该目录整体递归删除。此次未运行破坏性复现。应把该变量限定为父目录、在其内创建自己独占的随机子目录，删除前验证解析后的绝对路径及所有权；拒绝仓库、日常状态根、磁盘根和非本次创建的目录。不得依赖“仅测试使用”的注释作为保护。

## 本轮回归额外阻塞：Windows 子进程输出解码

`tests/test_sprint3.py:329` 的 `result.stdout + result.stderr` 报 TypeError，因为 stdout 为 None；此前 subprocess 读取线程已出现 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xba ...`。这属于测试/进程输出编码问题，不能据此断言 cleanup_fail 的业务断言实际失败，也不能把整轮测试判为通过。

应显式统一子进程输出和读取端的编码（包括 npm/Playwright 输出），不要只用空串替换 None 或忽略解码错误掩盖证据丢失。修复后重跑该场景及全量 pytest，保留实际退出码。本轮正常 e2e 独立运行 exit 0，不代替该故障场景的验收。

## S1 验收边界

出站前 commit、独立会话可见、异常回滚后仍保留预留，是本次实现与回归覆盖的进展。该 commit 使用同一 Session 提交 run/事件/预留，不是独立数据库连接的账本事务，文档宜准确表述为单独提交的事务阶段。强制终止子进程后的恢复验收仍未在新增测试中看到，本轮不把异常回滚测试称为真实进程崩溃验收。

## 发给 Zcode 的下一步

只完成 T1、T2 与 S3 所有权/大文件校验边界，保留已经修好的 S1 和队列 CAS。提交新增集成/故障测试、旧实现失败条件、实际测试行与退出码、准确状态总表。不要继续扩展新闻、DAG 或组合风险功能；不绕过扫描钩子，不启用付费调用。通过后再按原批准门槛讨论 WB-007。
