# 给 Zcode 的启动指令

请先完整读取：

`E:\闲鱼\codex openclaw\docs\INVESTMENT_WORKBENCH_PLAN_2026-09-18.md`

你负责实施一个 Pi 驱动的 AI 量化投资工作台。用户做关键决策，AI 负责新闻筛选、研究、反证、组合提案与复盘；Python 确定性模块负责数值、风险约束、账本、任务状态与授权校验。

## 工作位置

先检查建议目录 `E:\quant-investment-workbench` 是否存在；不存在则新建，已存在则先调查，禁止覆盖。以下两个项目作为只读资产来源：

- `E:\闲鱼\codex openclaw`：Pi、回测、数据快照、审计和测试。
- `E:\stock agent`：新闻来源、RSS、去重、证据、复核队列与页面经验。

旧研究项目 ADR-0006 明确禁止券商与模拟执行，不能在旧目录偷偷解除。新项目建立自己的 charter 与 ADR，完整说明 research、paper、shadow、live 四模式及人机权限。首批只实施新闻、研究和可见的 Agent 工作流。

## 第一批任务

按总方案 WB-001→WB-002→WB-003 推进，然后完成 WB-004/005/006/008 的最小纵向闭环：

1. 清点实际代码、来源、许可证、依赖、测试与运行证据，区分存在/可运行/已验收。
2. 写 `docs/inventory.md`、`docs/reuse-map.md`、产品 charter 与关键 ADR。
3. 定义 Source、DocumentVersion、Case、AgentRun、AgentDecision、Proposal、Approval 和 Event 合同。
4. 搭建 React/TypeScript 前端、FastAPI、PostgreSQL 与 migration。
5. 先用明确标记的 fixture，再加入人工导入和允许使用的 RSS，形成新闻→案件→证据详情闭环。
6. 展示真实采集状态、来源链接、可得时间、重复/修订和错误；只读导入旧 Mock run 时保留历史 Mock 标签。
7. 跑契约、去重、抓取安全、迁移、权限和浏览器测试；给出可访问入口及操作演示。

第二批再做真实 PiAdapter、持久化 DAG、预算、SSE、Agent 决策详情、人工队列；不要提前堆 Qlib、Langfuse、Dagster 和券商依赖。

## 必须遵守的实现规则

- 生产代理通过固定 Pi runtime 运行，Python 主编排；第三方 skills/开发 subagents 不拿生产数据或券商权限。
- 不让 LLM 计算账户余额、回测绩效、风险限额或自行批准真实资金行为。
- 代理详情展示证据与简要决策理由，不伪造思维过程、运行日志或真实调用。
- 新闻 API 免费不等于允许生产使用；NewsAPI Developer 不纳入免费生产来源。
- AKShare 是适配候选，具体源的数据权利、时效和稳定性独立核验；有问题就 BLOCKED。
- 不整仓复制 OpenStock（本地 AGPL）、AI Hedge Fund 或 OpenClaw 面板；先按方案做选择性复用。
- 不复制 `.env`、个人数据、现有数据库和审批原件，不打印密钥，不修改其他项目自启动。
- 服务默认 localhost；Windows 子进程隐藏窗口，保留日志和 stop/status 命令。
- 模型调用超时、缺 key、无效响应都真实报告，不自动降为 mock 并声称成功。
- 真实订单功能必须等总方案 P6 前置条件满足，并有具体的人工启用决定；当前批次不连接资金账户。

## 输出与验收

持续更新 `docs/IMPLEMENTATION_STATUS.md`，每项只用 TODO/DOING/PASS/FAIL/BLOCKED。每批给出修改清单、运行命令、退出码、页面入口、测试结果、演示证据、限制和下一任务。

优先交付能被用户操作的一条真实业务链路，不要只增加规划文档。没有实际测试或调用，就写未测试/未调用。日期、数量、性能、费用均从真实产物读取。
