# 研究协议预注册运行手册

## 目的

`validation_controls.parameter_selection_policy=pre_registered_no_search` 只是输入声明，不能证明研究团队在看到结果前完成了登记。真实内部研究因此必须在调用 Tushare 或 Pi 前，通过仓库外 `RESEARCH_PROTOCOL_EVIDENCE_PATH` 绑定组织研究登记记录、精确输入、冻结模型契约、三方批准和前向观察阈值。

本门禁只允许回测与内部研究，不批准券商连接、真实订单、对外分发或真实资金建议。

## 商业顺序

1. 平台负责人先建立 clean commit/tag，确保待登记代码可复现。
2. 数据负责人及法务确认数据权利；没有合法数据用途时不登记生产研究。
3. 量化负责人冻结 `strategy_round`：假设、历史区间、参数、执行模型、样本外设计、压力阈值和调度策略不再改动。
4. 在组织研究登记/变更系统创建不可变记录，登记时间必须早于首次真实流水线执行。
5. 量化负责人、独立模型验证人、合规负责人由三名不同人员批准。
6. 导出登记原件到仓库外受控目录，计算原件 SHA-256，并创建证据 JSON。
7. 平台负责人设置 `RESEARCH_PROTOCOL_EVIDENCE_PATH`，执行 health；任何字段、日期或哈希不一致均新建修订版，不覆盖旧证据。

## 指纹生成

以下命令只读取输入并输出哈希，不调用外部服务：

```powershell
python -c "import json; from quant_agents.audit import canonical_json_sha256; from quant_agents.research_protocol import build_model_contract_fingerprint; p=json.load(open('strategy_round.example.json',encoding='utf-8')); print('registered_input_sha256=',canonical_json_sha256(p)); print('model_contract_sha256=',build_model_contract_fingerprint(p))"
```

- `registered_input_sha256` 绑定初始开发回测的完整 JSON，任何字段变化都会失配。
- `model_contract_sha256` 绑定主题、范围、治理、策略、数据、执行、验证和调度控制，但排除滚动日期与 `schedule_context`；获批前向观察只能推进截止日，不能改参数。
- 示例 `governance/research_protocol_evidence.example.json` 只能复制到仓库外后填写；占位文本不会通过。

## v1 必填控制

- `status=APPROVED_FOR_BACKTEST`、`scope=CSI500`、唯一 `protocol_id` 和递增 `protocol_version`。
- `parameter_selection_policy=pre_registered_no_search` 且 `parameter_search_count=0`。
- `registered_date_range` 与初始输入完全一致。
- `change_type=initial_registration`，或通过 `approved_amendment` 明确旧协议、原因和新版本；不得静默覆盖。
- 三个批准角色必须齐全、批准人不同、时间不早于登记时间。
- 登记记录和支持原件均存于仓库外，文件 SHA-256 必须匹配。
- `reviewed_at` 最多 90 天，且当前日期位于 `valid_from` 与 `valid_until` 之间。
- 前向计划必须使用 `fixed_origin_forward`，固定原始 warm-up 起点和基线截止日，至少 60 个交易日、3 次再平衡，并预先冻结继续观察、暂停复核和独立验证阈值。
- `live_execution_authorized=false`、`external_distribution_authorized=false`。

## 变更控制

修改因子、参数、样本、成本、阈值、资金规模、参与率、数据源或调度方式，都必须停止旧 campaign，创建 `approved_amendment` 或新协议，并从新基线重新开始。不得通过改输入、改证据文件或重写前向账本保留旧的有利结果。

本地系统只能验证结构、日期、文件哈希和人员分离声明，不能认证外部系统身份或时间戳。最终审批必须由组织身份/工作流系统保存签名、时间和不可抵赖记录。

## 方法依据

- [Federal Reserve SR 26-2 revised model risk guidance](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm) 及其 [model risk guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) 用作非约束性模型治理参考：明确用途、独立有效质疑、使用前验证、结果分析、持续监测、模型清单和变更控制。它不是本项目在中国的适用法律，且其中生成式/Agentic AI 不在该指引范围；本项目仅借鉴其传统定量模型生命周期原则。
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) 用作 Pi/LLM 生命周期治理参考：持续监控、职责、清单和安全退役。

