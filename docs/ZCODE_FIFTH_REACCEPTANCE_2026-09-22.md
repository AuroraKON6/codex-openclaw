# 第五轮复验：Q1/Q2 收尾

日期：2026-09-22。项目：`E:\quant-investment-workbench`。

## 结论与范围

**部分修复可确认，最终验收暂不通过。** 统一账本修复了前轮“旧代次已结算费用漏计”的直接原因；kill 异常现在不会直接跳过后续目录删除。但还有同范围的两个缺口：月预算变成了累计预算，以及进程未确认退出仍可报告清理通过并 exit 0。

本轮只读业务代码、运行隔离测试并新增本报告；没有业务代码修改、暂存、提交、记忆更新、真实新闻或付费模型调用。没有向日常库执行迁移。不要把用户转贴的 Zcode 操作记录当成对本轮暂存/记忆写入的授权。

## 本轮回归

- `.\.venv\Scripts\python.exe -m pytest -o addopts='' -q`：`160 passed, 2 warnings in 202.66s (0:03:22)`，exit 0。
- `.\.venv\Scripts\python.exe scripts/run_e2e_stack.py`：`4 passed (10.1s)`，`step exit=0, final exit=0`，进程exit 0。
- 正常 e2e 栈：`e2e-76c3ce4b0fbf`，端口13549；身份匹配，runner报告临时子目录删除与日常清单未变。

独立负向探针均已完成，见下。现有回归通过不覆盖探针发现的缺口。干净环境安装、PG、真实 TLS、真实模型与强制终止模型进程恢复均未验收。

## V1 / P2：月预算缺失月份边界

位置：`E:\quant-investment-workbench\services\api\wb_api\budget_ledger.py:27`、`:35`。

`settled_reservations_total` 只筛选 status=settled，不筛选预算归属期；`consumed_total` 因此把所有历史已结算费用加入当前 WB_MONTHLY_BUDGET_CNY 门禁。旧实现按月筛选 run 费用，换统一账本时该边界丢失。第四轮已要求明确归属月份，本项不是新增业务功能。

独立探针：临时数据库仅放一笔 2025-01-01 创建并结算的 2 元预留；在当前 2026-09 查询统一消费值。

```json
{"probe":"prior_month_settled_in_current_consumption","consumed":2.0}
```

后果：历史费用会永久占用未来月份额度，月预算无法按预期恢复；不能将这一行为仅解释为“保守预算”。

修复要求：明确并固定预算归属规则。建议结算费用按出站预留所属预算月计入，未结算未知负债跨月继续占用；字段、时区、迁移旧账规则及状态说明保持一致。不得简单丢弃跨月 open 负债，也不得重新引入 run 与 ledger 双计。

最低验收：上月已结算不占本月；上月未知预留继续占用；本月正常/被弃代次已知费用各计一次；跨月结算按声明的归属期处理；重复结算不会重复计入。若产品实际希望累计额度，需正式更名并改变接口/文档，不能保留 MONTHLY 名称悄悄改变含义。

## V2 / P2：存活进程清理失败没有进入最终退出码

位置：`E:\quant-investment-workbench\scripts\run_e2e_stack.py:258`、`:264`、`:283`。

terminate/kill/wait-after-kill 的异常只打印，不设置清理失败状态，也不核实最终退出。目录删除与清单通过即可打印 teardown verified；若业务步骤成功，则 final exit=0。

独立探针：全部外部进程为 Mock，业务步骤返回0；两个模拟进程 terminate/kill 均抛 OSError，两个 wait 均超时，poll 持续为 None。没有启动或残留任何真实进程。

实际输出包含：

```text
process kill failed (pid=999991): OSError('simulated kill denied')
process wait-after-kill failed: TimeoutExpired('fake', 10)
teardown verified: temp dir removed, daily workspace unchanged
step exit=0, final exit=0
```

```json
{"probe":"unconfirmed_live_process_final_exit","exit":0,"temp_removed":true}
```

现有 kill_fail 注入发生于已 terminate 的进程，并提前让业务步骤返回3，因此不能验证“步骤成功但进程仍活着时必须失败”。非零步骤码掩盖了清理状态缺失。第四轮报告已经明确要求验证最终退出与 PID。

修复要求：逐个收集本 runner 自建进程的最终退出状态；未退出/无法确认退出设明确清理失败码并报告 PID；仅在所有进程已退出、清单已验证、临时根已删除时输出完整 teardown verified。kill 曾报错但后续已确认退出可以视为恢复，不要求机械地把所有瞬时异常都算失败。禁止批量结束同名 node/python。

最低验收：step=0+进程持续存活必须非零且不能输出完整通过；第一个进程失败不影响第二个清理；kill报错但随后确认退出可正常收尾；目录/清单失败有明确优先级；打印原始步骤码和未退出PID。

## 保留事项：前轮要求尚未完成

- `scripts/run_e2e_stack.py:156` 的端口分配仍在建立临时根之后、清理 try/finally 之前。按第四轮既定要求，把资源创建后的准备操作纳入保护，并补端口分配失败不残留测试。
- 被丢弃真实尝试的 run 终态仍需对照第四轮“不得显示运行中”的要求验收；不能仅以决策回滚说明已经写入 interrupted 状态。本轮不宣称此项已完成。
- Git 基线/钩子和 PG/真实外服继续单独报告；本轮测试不构成付费、采集、生产部署或交易授权。

## 下一次交付清单（冻结在原范围）

1. V1 的预算归属规则、迁移处理、跨月与幂等回归证据。
2. V2 的进程退出核实、独立清理状态码、step=0+存活进程负向证据。
3. 两项保留事项按既定条件完成或明确列为未完成，不写“全部完成”。
4. 完整 pytest、隔离 e2e 的真实结果与退出码；没有测试的外部环境继续未验收。

不扩展新闻、DAG、组合或交易功能，不重写全部架构，不规避扫描器。通过后再进入经批准来源的 WB-007 有界试采。
