# 开源量化与 Pi 生态采用评审

## 评审口径

本评审在 2026-08-25 直接核对 GitHub、Pi 官方包目录、仓库源码、许可证声明和 npm 元数据。精确 revision 与决策记录在 `governance/upstream_references.json`。Star、下载量和“支持金融/安全”的宣传都不是商业适用性证据；开源代码许可也不等于行情数据权利、券商授权、监管批准或可复现收益。

当前生产流水线继续由 Python 负责编排、数据、确定性计算、门禁和产物。Pi 只执行七个隔离的 LLM 推理 turn，并保持 `--no-tools --no-extensions --no-skills`。任何参考项目都不得绕过这个边界。

## 相似项目

| 项目 | 可学习部分 | 本项目采用方式 | 明确不采用 |
|---|---|---|---|
| [Microsoft Qlib](https://github.com/microsoft/qlib) | 模块化数据层、point-in-time 数据、Experiment/Recorder、策略与执行器分离 | **已落地概念转换**：仓库外 Registry 管理跨 run 两阶段记录，绑定 input/model/source/protocol/outcome，并由发布、监控、前向和调度复验 | 不导入其示例行情，不把通用回测结果当作 CSI 500 商业证据，不直接启用在线交易层 |
| [Microsoft RD-Agent](https://github.com/microsoft/RD-Agent) | 因子提议、实现、反馈的循环以及因子/模型协同实验 | 只把它改造成“候选假设队列”：每个新因子必须新建外部预注册、独立 holdout 和前向 campaign | 不允许 LLM 自动搜索参数后沿用旧协议，不自动晋级模型，不让 Agent 修改确定性评估器 |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | 可插拔 fee、slippage、fill、buying-power 与事件驱动执行模型 | 把接口思想转成未来的差分回测测试集，逐项校验费用、滑点、涨跌停、部分成交、T+1 和整手 | 不接入其 brokerage/live 层，不以海外默认模型替代 A 股有效期规则和本项目成本证据 |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 专业角色拆分、观点对抗和风险复核 | 仅借鉴“提出主张—反证—风险终审”；现有 Research/Risk/Review Agent 仍只能输出研究 JSON | 不引入 Trader/Portfolio Manager 决策链，不输出买卖动作，不让 LLM 计算回测绩效 |
| [RQAlpha](https://github.com/ricequant/rqalpha) | A 股事件驱动回测、账户、订单和扩展接口概念 | 只作为测试场景清单参考 | README 明示商业使用需联系授权，而包元数据又声明 Apache-2.0；在取得书面法律结论前不复制代码、不添加依赖、不使用其数据 |

## 已转化为本项目动作

1. Qlib 的 Experiment/Recorder 思路已经映射为仓库外 `registry.json` 与 `experiments.jsonl`：每个真实 `run_id` 在 Tushare/Pi 前追加 `RESERVED`，在成功、失败或中断时追加 `FINALIZED`，并绑定输入、模型、源码、协议、数据、预算与结果契约；不是另装 Qlib/MLflow，也不开放在线交易。
2. RD-Agent 的自动循环被改成受治理循环：候选生成与验证严格分离，任何参数、因子、成本或样本变化都终止旧 campaign 并重新登记。
3. LEAN 的执行模型思路进入差分测试 backlog：同一冻结订单流需要在基准模型和本项目执行器之间逐笔核对，差异必须归因，不能只比较最终收益。
4. TradingAgents 的角色争论只用于发现反例和证据缺口；终审仍由确定性门禁和独立人工批准决定。

## Pi 扩展候选

Pi 官方文档明确说明 package 中的 extension 可执行任意代码，skill 也可指示模型运行程序。因此本项目不采用“一键安装一堆插件”，而采用单包、固定版本、源码审查、隔离试运行、哈希锁和显式加载。

| 候选 | 结论 | 原因 |
|---|---|---|
| 项目自有 `quant-ops-readonly` | **已采用，operator only** | 无网络、无子进程、无写入、无 LLM tool；只注册 `/quant-status`，读取本项目 run 的运行/告警/发布元数据。生产 turn 仍禁用全部 extension |
| [CC Safety Net](https://github.com/kenryu42/cc-safety-net) | **推荐下一阶段隔离试点，不安装到生产** | 支持 Pi 和 Windows，能拦截破坏性命令、敏感文件并留本地审计；但仍是高权限第三方代码，Git 源与发布包的生命周期脚本还需逐版本核对，而且生产 Agent 本来没有工具可拦截 |
| [pi-permission-system](https://github.com/gotgenes/pi-packages/tree/main/packages/pi-permission-system) | **备选，不与前者同时启用** | allow/ask/deny、路径和外部目录门禁较完整；但依赖项目 trust、shell 解析器和复杂策略，适合开发型 Pi，不适合七个无工具业务 Agent |
| [pi-lens](https://github.com/apmantza/pi-lens) | **暂缓** | 对编码阶段的 LSP/lint 有价值，但 reviewed npm `prepare` 会构建、下载 grammar、设置 Git hooks；当前项目尚未建立批准的 Ruff/Pyright 工具链，不应让插件自行引入 |
| [pi-subagents](https://github.com/jwu/pi-subagents) | **拒绝用于生产** | Python 已经拥有七 Agent DAG、重试、预算、事件链和恢复；第二套子 Agent 编排会造成双重状态、权限和成本边界 |
| Web/MCP/search 插件 | **拒绝用于生产** | 会引入额外密钥、未授权网页、动态来源和不可冻结内容，破坏 Tushare 与证据链边界 |
| Memory/model-debugger/notification 插件 | **拒绝或暂缓** | 长期记忆扩大数据留存面；模型调试可能记录 prompt/凭据；通知和后台任务可能重新造成弹窗或自启动 |

## 当前本地扩展

- `governance/pi_extensions.lock.json` 固定扩展路径、SHA-256、能力和 upstream revision。
- `python -m quant_agents extensions-audit` 拒绝未锁文件、哈希漂移、链接、网络、子进程、写入、provider/tool 注册及生产 `--no-extensions` 漂移。
- `open_pi_ops_console.ps1` 只在用户手工运行时启动当前终端中的只读控制台；它不创建计划任务、不使用 `Start-Process`、不产生自启动窗口。
- 控制台使用隔离 Pi state、offline startup、无 session、无 tools、无自动 extension/skill/context，并只显式加载本地扩展。输入 `/quant-status` 查看 REAL 与明确标记的 MOCK 状态。

## 第三方包准入顺序

1. 固定 npm 精确版本和 registry integrity，或固定 Git 40 位 commit；禁止 `latest`、branch 和未固定 URL。
2. 用 `npm pack --ignore-scripts` 获取 tarball，核对它与 Git tag 的文件、许可证和发布 provenance；不得先执行 installer。
3. 审查 `preinstall/install/postinstall/prepare`、依赖树、网络、文件写入、shell、凭据读取、telemetry、自动更新和 Windows 行为。
4. 在仓库外隔离 `PI_CODING_AGENT_DIR`、无凭据、无生产数据的环境执行测试；记录包哈希、命令、退出码和副作用。
5. 仅在 operator profile 显式加载单个候选，进行允许/拒绝/旁路测试；不得通过 `.pi/settings.json` 自动加载到所有会话。
6. 独立复核后更新 lock 和回滚步骤。生产业务 turn 仍必须验证 `--no-extensions`，所以通过 operator 验收也不代表生产准入。

## 下一阶段建议

Qlib 风格跨 run 实验索引已经完成。下一优先级是增加 LEAN 风格逐笔执行差分测试，之后才评估 CC Safety Net 的隔离 operator 试点。RD-Agent 式自动候选生成必须等真实基线、外部预注册、实验 Registry 和前向账本可运行后再做，否则只会放大数据窥探和多重检验风险。
