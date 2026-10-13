# ADR-0006：永不在本项目建立券商/订单/真实资金能力

- 状态：已接受（永久约束）
- 日期：2026-09-06
- Owner：项目总经理 + 合规负责人
- 复审触发：无。任何引入交易语义的依赖、插件或数据源提案直接否决；推翻本 ADR 必须另立独立项目
- 关联：`install_quant_schedule.ps1`、`run_daily_research.ps1`、`check_quant_schedule.ps1`、`quant_agents/contracts.py`、`release.py`

## 背景

项目定位是内部研究 OS。交易能力会触发完全不同的监管、风控、资金与审批体系，并与"研究结论可被独立否证"的核心价值冲突。必须以永久 ADR 阻止渐进式越界（先接行情、再接模拟、再接实盘）。

## 决策

- `broker_connection_enabled` 恒为 false，由 deployment authorization schema 3 在安装器、runner、checker 三处强制校验。
- `external_distribution_approved` 恒为 false；外部分发不在本项目开启。
- Agent 输出契约禁止真实资金动作语言（买入/卖出/加仓/减仓/止损/止盈/LONG/SHORT 等）；`verify_quant_pipeline.ps1` 对 summary 复检。
- release gate 复验上述两边界；forward campaign 达标最多进入独立验证，永不自动转为交易。
- 未来真实交易执行研究必须另立项目：独立代码库、独立数据许可、独立监管与风控论证，不在本项目增量打开。

## 替代方案

- "只读券商行情接入"——否决：数据扩张走独立许可路径（ADR-0007），不借券商通道引入边界模糊。
- "纸面交易/撮合模拟服务"——否决：确定性回测引擎已承担执行研究，不引入第二套撮合语义。

## 后果

- 正面：合规边界清晰，审批范围有限且稳定，项目永不需要资金类牌照论证。
- 负面：研究结论与执行之间永远存在人工鸿沟——这是设计特性而非缺陷。
- 中性：本 ADR 无复审解除机制；项目终止后其证据仍受 retention 策略约束。

## 合规检查

`tests/test_schedule_contract.py` 断言三脚本一致校验 `broker_connection_enabled -ne $false`；Mock 验收断言 `broker_connection_enabled=false`。
