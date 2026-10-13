# 执行成本校准手册

## 适用边界

本手册只批准中证 500 内部离线研究的模拟成本参数。它不证明可成交性，不允许连接券商，也不把回测费用解释为未来真实费用。`live_execution_ready` 必须始终为 `false`；任何真实执行能力必须在独立项目中重新完成法律、账户、风控和交易系统审批。

## 成本分层

每次校准必须拆开三类来源，禁止用一个总费率掩盖口径：

1. 法定和市场基础设施费用：交易所经手费、证管费、过户费、减少方向印花税；来源及生效区间由 `governance/a_share_market_rules.json` 管理。
2. 机构合同费用：券商佣金口径、最低佣金和适用账户/委托协议；必须来自当前有效的机构费率单或书面确认。
3. 研究估计：滑点和市场冲击；必须绑定模拟资金规模、最大参与率、流动性下限、样本范围和限制，不得冒充监管费率或券商报价。

## 责任与批准顺序

1. 量化负责人冻结本轮 `scope`、`cost_model`、`simulation_notional_cny`、`max_participation_rate` 和 `minimum_daily_amount_cny`。
2. 平台负责人从当前规则簿取得 SHA-256；规则簿变更后旧成本证据自动失配。
3. 量化负责人选择且记录唯一校准基础：
   - `approved_conservative_assumption`：没有真实委托回报，只能作为临时内部研究假设，必须 `provisional=true` 并明确局限。
   - `historical_execution_sample`：至少 30 笔可审计委托回报，必须 `provisional=false`，记录样本起止日且样本截止不得晚于复核日。
4. 独立复核人检查佣金是否重复计入规费、样本是否与当前委托类型/资金规模/流动性范围相符，以及滑点和冲击是否偏乐观。独立复核人不得与量化负责人相同。
5. 合规负责人确认材料只用于内部研究且不表示可实盘执行；三方在组织审批系统中留存身份、时间和意见。
6. 平台负责人将原始材料保存到仓库外受控目录，计算 SHA-256，再基于 `governance/execution_cost_evidence.example.json` 创建证据文件。
7. 证据最长每 90 天复核一次；券商费率、规则簿、策略资金规模、参与率、流动性下限或成本模型任何一项变化都必须立即重做，不能等待到期。
8. 先设置 `EXECUTION_COST_EVIDENCE_PATH`，再执行完整 health；门禁通过后才允许检查 Tushare 和调用 Pi/DeepSeek。

## 证据契约

证据必须同时满足：

- `schema_version=1`、`status=APPROVED_FOR_INTERNAL_RESEARCH`、`scope=CSI500`。
- 校准后的完整成本模型与运行输入逐字段一致；系统对模型、资金规模、参与率和流动性下限计算同一指纹。
- `market_rulebook_sha256` 等于当前规则簿原始文件哈希。
- `double_cost_stress_required=true`、`live_execution_ready=false`。
- 量化负责人、独立复核人、合规负责人、有效期、复核日、外部材料路径和材料 SHA-256 均非占位符。
- 至少一项实质限制；系统只能验证文件和哈希，不能认证批准人身份。

计算外部材料哈希：

```powershell
(Get-FileHash -Algorithm SHA256 -LiteralPath 'D:\controlled\quant\broker-fee-and-cost-memo.pdf').Hash.ToLowerInvariant()
```

查看当前规则簿哈希：

```powershell
python -c "from quant_agents.market_rules import load_market_rulebook; print(load_market_rulebook()[1])"
```

设置受控证据并执行门禁：

```powershell
$env:EXECUTION_COST_EVIDENCE_PATH = 'D:\controlled\quant\execution-cost-evidence-v1.json'
python -m quant_agents health --runtime pi --input .\strategy_round.example.json --no-ping
```

## 失败处置

- 缺失、过期、哈希不符、规则簿漂移或运行参数失配：真实 run 在 Tushare 和 LLM 调用前失败，保留失败审计，不切换 Mock 冒充真实完成。
- 临时假设通过：只可进入内部研究人工评审；必须在仓库外固定起点前向 campaign 或合法取得的历史委托回报可用后重新校准。
- 历史样本通过：仍需检查样本代表性、异常交易日、流动性分层和时间漂移；30 笔只是最低数据完整性门槛，不是统计充分性的保证。
- 任何校准均不解除 `broker_connection_enabled=false` 和外部分发禁令。
