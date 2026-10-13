# 回测执行与成本基线

## 适用边界

本基线只用于中证 500 沪深 A 股内部研究模拟，不连接券商、不生成订单、不支持北交所、融资融券或日内回转品种。Python 是唯一权威计算层，Pi Agent 只能解释结果。

## 业务时间顺序

每个再平衡周期严格按以下顺序运行：

1. `T-2` 收盘后冻结信号窗口和点时中证 500 研究成分。
2. 以 `T-1` 为模拟执行日，读取原始收盘价、成交额、涨跌停价和显式停牌记录。
3. 先检查现有持仓的减持可执行性，再构建目标权重；无法退出的权重保持锁定。
4. 涨停收盘只阻断增加方向，跌停收盘只阻断减少方向；缺失日线或显式停牌均不成交。
5. 先处理减少方向，再以剩余现金处理增加方向；执行板块申报数量、单笔上限和费用后的现金可负担约束。
6. 模拟委托有效期固定为 `DAY`，未成交部分在会话结束时取消，并在下一次再平衡重新计算，不跨日保留旧信号委托。
7. 权重从 `T` 开始承受收益，执行成本在同一首个绩效日扣除；算法不允许同一交易日回转 A 股。

这使信号窗口结束日、模拟执行日和收益生效日严格递增，避免使用同一收盘价同时生成信号和成交。

## 有效期规则簿

`governance/a_share_market_rules.json` 是机器可读规则簿，原始字节 SHA-256 写入 preflight、回测、run manifest 和验收产物。当前覆盖：

| 生效区间 | 规则策略 |
|---|---|
| 2023-08-28 至 2026-07-05 | `cn-a-share-2023-08-28` |
| 2026-07-06 起 | `cn-a-share-2026-07-06` |

规则簿按模拟执行日选择策略；请求区间存在空档、重叠、未知交易所或缺失官方来源时直接失败。

当前确定性约束包括：沪深主板和创业板买入以 100 股为申报单位；科创板单笔至少 200 股、超过部分按 1 股递增；A 股价格最小变动单位 0.01 元；A 股在交收前不得卖出；板块单笔申报上限按交易所规则执行。实际每日涨跌停价使用 Tushare `stk_limit`，不根据代码自行推算。

## 成本模型

输入必须提供 `execution_controls.cost_model`，旧的单一 `transaction_cost_rate` 被拒绝。每个模拟委托单独计算：

- 券商佣金及每笔最低佣金；支持含规费全佣金或净佣金加规费两种报价口径。
- A 股经手费 0.0341‰ 和证管费 0.02‰ 双边；在全佣金口径中只拆分展示，不重复加收。
- A 股过户费 0.01‰ 双边。
- 证券交易印花税 0.5‰，只计减少方向。
- 显式滑点和市场冲击基点；二者是研究假设，不是监管费率。

全佣金输入不得低于经手费与证管费合计费率。示例费率只是保守研究参数，必须由量化负责人根据适用委托协议或机构费率单独校准，不能解释为任何券商报价。

真实 run 还必须通过独立的 `EXECUTION_COST_EVIDENCE_PATH` 门禁。证据逐字段绑定成本模型、模拟资金规模、最大参与率、流动性下限和当前规则簿哈希；输入中的 `cost_assumption_source` 只是描述字段，不能替代券商材料、校准记录、独立复核和合规批准。保守假设必须标记 `provisional=true`，即使通过也只允许内部研究评审；历史委托校准至少需要 30 笔可审计记录，仍不代表可实盘执行。详见 `EXECUTION_COST_RUNBOOK.md`。

## 审计产物

真实回测写入：

- `backtest/backtest_agent.json`：权威指标、执行诊断和完整曲线。
- `backtest/cost_ledger.json`：每次再平衡、每个模拟委托、费用拆分和总额。
- `backtest/execution_policy.json`：规则簿哈希、有效策略、官方来源和成本假设。
- `backtest/backtest_assurance.json`：点时、时滞、成本、停牌、涨跌停、申报数量、T+1、容量、快照和研究边界检查。
- `backtest/robustness_validation.json`：固定参数的时间顺序 holdout、三折锚定扩展滚动样本外、1.5/2倍成本压力、额外信号时滞和预注册阈值判定。

`state.json.backtest_assurance.decision` 必须为 `PASSED_FOR_INTERNAL_RESEARCH`，且 `state.json.robustness_validation.decision` 必须为 `PASSED`；否则 run 进入错误状态，发布门禁继续阻断。通过只表示适合进入内部人工研究评审，不表示可实盘执行或商业发布。

## 样本外与压力矩阵

`validation_controls` 与输入指纹一起冻结假设 ID、零参数搜索声明、样本外比例、最少样本外交易日、成本倍数、信号时滞和接受阈值。引擎只允许 `pre_registered_no_search` 且 `parameter_search_count=0`。

基准回测完成后，系统先从有效绩效交易日尾部按时间顺序切出独立 holdout，并以同一组固定参数重复运行：holdout 基准、1.5 倍成本、2 倍成本和额外一交易日信号时滞。阈值至少覆盖样本外模拟委托数、样本外 Sharpe、样本外最大回撤和双倍成本总收益。

随后执行三折锚定扩展、非重叠 out-of-time 验证。每折保留此前全部日期作为开发历史，示例评价窗口为 20 个交易日并在输入指纹中冻结，每折重新从现金开始；每折执行基准、2 倍成本和额外时滞三个场景。所有场景必须完成，且至少三分之二折同时通过委托数、Sharpe、回撤和双倍成本阈值，否则发布门禁失败。输入日期区间在运行前按声明的开发期和折数做最低长度检查，真实交易日数量仍由引擎最终复验。

真实 run 还必须由 `research_protocol_registration` 门禁绑定仓库外组织登记原件、精确输入和冻结模型契约。该本地校验能验证结构、日期和文件哈希，但不能认证组织身份或时间戳，仍需组织工作流系统保存不可抵赖证据。

## 已知限制

- 日线无法证明收盘集合竞价排队顺序、盘口深度或部分成交，系统采用方向性保守阻断。
- 申报数量使用权重账本和原始收盘价近似；全量零股退出及公司行为后的实际股份数量仍需交易级账本复核。
- 复权收益用于绩效，公司行为股份变化没有模拟券商逐笔交收。
- 滑点和冲击参数未经真实委托回报校准时只能作为敏感性假设。
- 滚动折之间会重置模拟组合，不能替代连续前向观察；仓库外 campaign 通过固定起点重算和前缀哈希防重写补充这一证据，但仍不替代跨制度区间、因子暴露归因或独立复现。

## 官方依据

- [上海证券交易所交易规则（2026年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)
- [深圳证券交易所交易规则（2026年修订）](https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html)
- [财政部、税务总局关于减半征收证券交易印花税的公告](https://jx.mof.gov.cn/xxgk/zhengcefagui/202309/t20230904_3905337.htm)
- [上海证券交易所收费项目及标准](https://www.sse.com.cn/lawandrules/sselawsrules2025/charge/c/c_20250610_10781461.shtml)
- [深圳证券交易所收费及代收税费标准](https://investor.szse.cn/marketServices/deal/payFees/index.html)
- [中国结算上海市场收费及代收税费一览表](https://www.chinaclear.cn/zdjs/fbzyls/202506/9d22b74d9f2e40edb67b44d1f6596f18/files/%E4%B8%8A%E6%B5%B7%E5%B8%82%E5%9C%BA%E8%AF%81%E5%88%B8%E7%99%BB%E8%AE%B0%E7%BB%93%E7%AE%97%E4%B8%9A%E5%8A%A1%E6%94%B6%E8%B4%B9%E5%8F%8A%E4%BB%A3%E6%94%B6%E7%A8%8E%E8%B4%B9%E4%B8%80%E8%A7%88%E8%A1%A8.pdf)
- [Federal Reserve 2026 model-risk guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm)（仅作为风险治理参考，不是本项目适用的中国法律或监管要求）
- [The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)（研究方法参考）

规则变化必须先更新来源、有效区间、测试和规则簿哈希，再允许新的真实 run。
