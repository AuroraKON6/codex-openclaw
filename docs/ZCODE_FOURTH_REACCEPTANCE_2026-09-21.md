# 第四轮复验：第三轮修复交付

日期：2026-09-21；对象：`E:\quant-investment-workbench`。

## 结论

**暂不最终通过。** 旧代次决策回滚、目录父子所有权、大文件分块哈希等修复有实质进展。但 T1 的独立结算未接入下一次预算核算，已知费用仍可漏计；T2 的 kill 失败路径仍跳过后续清理。两项均已用隔离探针复现，属于原修复范围，不要求新增业务功能。

本轮未修改业务代码、未暂存或提交、未更新记忆；仅新增本报告。补充探针使用临时库、模拟模型和模拟进程；无付费调用、无真实新闻采集。没有对日常库执行迁移。探针残留由外层临时目录管理器清除。

## 回归结果

- `.\.venv\Scripts\python.exe -m pytest -q`：157 项运行至100%，exit 0；仅两条弃用警告。本次配置下未打印数字总计行，以实际进度与退出码记录，不伪造 `157 passed` 原始输出。
- `.\.venv\Scripts\python.exe scripts/run_e2e_stack.py`：`4 passed (11.5s)`；`step exit=0, final exit=0`，进程 exit 0。
- 栈身份：`e2e-1dd195215bfc`，端口28300；runner 报告身份匹配、临时子目录删除和日常内容清单未变。

不以 Zcode 报告替代本轮结果。干净安装、PG 竞争、真实模型、真实 TLS、强杀模型调用进程恢复均未在本轮验收。现有测试全绿与下述补充探针发现缺陷并不矛盾：现有断言未覆盖后续预算门禁及真正的 kill 异常。

## Q1 / P1：已知费用结算后从预算门禁消失

位置：`E:\quant-investment-workbench\services\api\wb_api\worker.py:21`、`:38`、`:53`、`:68`；`E:\quant-investment-workbench\services\api\wb_api\agent_service.py:154`、`:165`。

旧代次回滚时，run.cost_cny 一并回滚。新事务仅将 BudgetReservation 改为 settled，并写 settled_amount_cny。下次预算检查仍计算 AgentRunRecord.cost_cny 加 reserved 状态预留，不计 settled_amount_cny。因此账本虽然显示已结算，预算门禁却把这笔费用当成零。

独立复现步骤：

1. 在临时 client/db 上运行现有 `test_t1_known_usage_settles_even_when_decision_discarded`，确认原测试通过。
2. 用独立会话查询旧 run 和已结算预留。
3. 把预算 cap 设为“下一次最坏预留 + 0.0006”；上一笔已知费用为 0.0012，正确结果必须阻断。
4. 再调用真实的 execute_agent_run 控制流，提供商继续为 Mock，并单独计数。

```json
{"probe":"discarded_usage_budget","run_cost":null,"run_status":"running","settled_amount":0.0012}
{"probe":"next_call_should_block_with_settled_cost","provider_calls":1,"status":"succeeded"}
```

这不是估算精度问题：已知费用存在于预留账本，却完全不在门禁读取的汇总口径中。旧 run 仍为 running，也与“已标记 interrupted 的废弃尝试”说法不一致。

修复要求：选择唯一且一致的费用计量来源，让正常成功、旧代次丢弃、失败但已知 usage、未知 usage 均进入预算核算；不能同时把正常 run 和 settled 预留相加造成双计。明确归属月份与幂等结算规则。对已废弃尝试使用可识别的终态/废弃标记，不得恢复有效决策。

验收必须检查下一次调用是否被阻断，而不只是断言 reservation.status==settled。至少覆盖：旧代次已知费用后零出站阻断、正常成功不双计、重复结算不重计、未知费用仍占用、废弃尝试不显示运行中且无有效决策。

## Q2 / P2：kill() 异常未受保护，临时目录和最终报告被跳过

位置：`E:\quant-investment-workbench\scripts\run_e2e_stack.py:250`、`:259`。

`proc.wait(timeout=15)` 超时后的 `proc.kill()` 位于 TimeoutExpired 分支内，但没有自己的异常保护；它抛出的 OSError 不会被同级 except 捕获。清单比较和删除仍位于外层 finally 之后，因此仍被跳过。

独立复现：模拟进程的 terminate 正常返回，wait 抛 TimeoutExpired，kill 抛 OSError；所有迁移/进程对象均为 Mock，没有真实进程被终止，也没有服务启动。

```json
{"probe":"kill_failure_skips_cleanup","temp_root_remains":true}
```

现有 `proc_kill_fail` 注入实际在 terminate 前抛异常，后续 kill 可以成功，并不覆盖 kill 真正失败。不能用该场景的通过证明 kill 失败已处理。

修复要求：进程清理函数逐项保护 terminate、wait、kill、第二次 wait；不管某个进程清理结果如何，都执行其余进程清理、清单验证、目录删除及最终报告。结束前核实自建进程实际退出；存活进程或无法确认退出必须非零，并打印对应 PID。步骤成功也不能掩盖清理失败。

验收：真实控制流上的模拟 kill OSError、第二次 wait 超时、一个进程失败但其他进程仍清理；断言清单/目录清理被尝试，最终非零且打印未确认退出 PID。禁止按进程名批量杀死 node/python。

另外，自建目录之后的 `_free_port()`（第156行）仍在清理保护之前。将资源创建后的准备操作也纳入同一保护范围，避免端口分配失败留下临时根；这仍属于原全退出路径清理要求。

## 已改善及未扩大结论

- worker 已检查 finish_job_owned 返回值；fixture 旧代次输出回滚与已知费用独立结算均有集成测试，但后者尚未完成预算闭环。
- BASE_DIR 改为父目录，实际删除自建随机子目录；大文件改为分块哈希，不再跳过50MB以上文件。
- 清单读取的 OSError 已转为 UNVERIFIED；此进展不等于所有清理异常均已覆盖。
- 编码采用显式 UTF-8；replace 是有损容错，不应描述为原始输出字节绝无损失。关键结构化结果和退出码仍应独立校验。
- 不因 SQLite/Mock 测试通过将 PG、真实外部调用或实盘能力标为已验收。

## 下一次提交范围

只完成 Q1、Q2 和相应集成回归，更新状态表及实际测试输出。不要继续重写全部项目，不扩展新闻/DAG/组合功能，不规避钩子，不启动付费调用。通过后的下一阶段仍为批准来源后的 WB-007 有界试采，而非实盘交易。
