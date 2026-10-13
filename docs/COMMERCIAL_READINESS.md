# 商业运行准入

## 当前边界

本项目是内部研究技术系统，不是投资顾问、交易系统或对外数据产品。技术健康、数据使用权、组织授权、人工审批和外部分发是相互独立的门禁，任何一个通过都不能替代其他门禁。

截至 2026-08-26 的开发验收：锁定 Pi 安装、模型目录、真实 DeepSeek V4 Pro ping、一个真实无工具 Agent contract turn、Mock 7/7、完整性、归档恢复、保留计划和 Mock 发布/调度阻断均已有本地证据；研究协议预注册、跨 run 实验登记、执行成本、价格基线、预算和仓库外前向账本已进入硬门禁。实验 Registry 代码具备仓库外元数据、预登记/终态、哈希链、未收尾盘点、发布/监控/调度复验，但没有组织批准的真实 Registry 原件。项目自有只读 operator extension 已做哈希锁和隔离审计，生产 turn 仍强制 `--no-extensions`，没有安装第三方 Pi package。三个 OpenClaw 自启动任务已禁用，18789/18790 无监听。真实商业 run 仍被 clean source、数据许可证据、研究协议原件、实验 Registry 原件、成本校准证据和 Tushare Token 正确阻断，未形成市场结论。

真实基线完成必须同时证明：clean source revision、获准数据用途、外部预注册、仓库外实验预登记和终态、经独立复核的执行成本校准、真实 Tushare 快照、真实 Pi/DeepSeek V4 Pro 7/7、确定性指标、缓冲后预算通过、完整性通过、五方审批。模型生命周期完成还需连续前向账本和独立复现。Pi ping、Mock、环境变量、配置文件、本地审批草稿、空 Registry 或单次回测都不等于商业完成。

## 硬门禁

| Gate | 必需证据 | 责任角色 | 失败动作 |
|---|---|---|---|
| Source | 受控私有仓库 clean commit/tag、依赖锁、凭据扫描 | 平台负责人 | **BLOCKED**：当前无 committed HEAD，真实 run 在外部调用前阻断 |
| Data rights | v2 服务商书面组织授权，覆盖商业内部研究、自动 API、缓存、衍生分析、DeepSeek、365 天留存、终止处置及文件 SHA-256 | 数据负责人、法务/合规 | **BLOCKED**：公开条款仅限个人非商业用途，未提供独立组织授权，不配置生产数据凭据 |
| Research protocol | v1 组织登记导出，绑定精确输入、冻结模型契约、登记时间、历史区间、前向阈值、三名不同批准人和原件 SHA-256 | 量化负责人、独立模型验证人、合规负责人 | **BLOCKED**：仓库示例是占位；输入自称预注册不能替代外部系统记录 |
| Experiment registry | 组织 Registry 导出、四名不同批准人、仓库外受控目录、365 天以上留存、每个 run 的 `RESERVED`/`FINALIZED` 和完整哈希链 | 量化负责人、独立模型验证人、平台负责人、合规负责人 | **BLOCKED**：代码和测试已具备；仓库示例不是真实批准，尚无组织 Registry 原件或真实账本 |
| Execution cost | v1 校准证据，绑定规则簿、佣金口径、滑点、冲击、资金规模、参与率、流动性下限、外部材料哈希、独立复核和90天复核 | 量化负责人、独立复核人、合规负责人 | **BLOCKED**：仓库示例只是占位；未提供机构费率/历史委托材料和组织身份批准 |
| Data quality | Tushare 请求日志、点时成分、覆盖、截止日、新鲜度、涨跌停/停牌/复权、快照哈希 | 数据负责人、量化负责人 | **BLOCKED**：无 Token 和真实快照，不能形成市场结论 |
| Pi runtime | `0.84.2` 锁、Node、无工具策略、V4 Pro catalog、真实 ping | 模型负责人、平台负责人 | **PASSED (runtime only)**：工作区锁定安装、真实 ping 和 Agent contract turn 已通过 |
| Research logic | Python 权威信号和回测、有效期规则簿、逐委托成本账本、容量/停牌/涨跌停/T+1/申报数量、固定参数 holdout、三折滚动样本外及成本/时滞压力、无 LLM 指标篡改 | 量化负责人 | **CANDIDATE**：本地确定性验收通过，待真实授权数据和外部证据 |
| Forward lifecycle | 已批准基线、固定起点的真实前向路径、重叠历史防重写、预注册最小样本/暂停/独立验证阈值、关闭/退役证据 | 模型负责人、独立验证人、平台/合规 | **BLOCKED**：代码和测试已具备，尚无合格真实基线，因此没有真实 campaign 或观察记录 |
| Operations | 锁、幂等、超时、成本、alerts、事件链、manifest、恢复/归档/保留演练 | 平台负责人 | **PASSED (local acceptance)**：生产状态仍因上游门禁为 CRITICAL |
| Release | 数据/量化/模型/平台/合规五方独立批准 | 五方责任人 | **BLOCKED**：没有合格真实 run 和组织身份审批证据 |
| Schedule | 已批准 run、源码 commit、审批哈希、有期限 authorization、任务复验 | 平台负责人 | **NOT INSTALLED**：安装脚本已证明拒绝 Mock/未审批输入 |

## 数据许可

截至 2026-08-23，公开 Tushare 数据服务条款明确限制为个人、不可转让、非商业用途。它不能自动覆盖组织商业研究。`DATA_LICENSE_EVIDENCE_PATH` 只引用本机 v2 批准证据；合同原件和密钥不得进入仓库。证据必须绑定服务商书面文件哈希和有效期，覆盖项目实际接口、自动 API、缓存、衍生分析、DeepSeek 处理、留存和终止处置，并每 30 天复核公开条款。系统只能验证文件存在和哈希，不能认证签署人身份，最终仍需组织法务和身份审批系统确认。

## 模型治理

- 只批准 `deepseek/deepseek-v4-pro`；模型或 Pi 版本变化需要独立变更评审和回归。
- Pi Agent 仅做解释和终审。市场数据、信号、回测及权威指标由 Python 计算并覆盖模型返回值。
- 生产 turn 禁用所有 Pi 工具和可执行资源；项目 skills 仅供人工运维。
- 保留每次 turn 的 provider/model/session/response/usage/prompt hash 和原始 JSONL。
- 截至 2026-08-25，DeepSeek 官方 `deepseek-v4-pro` 每百万 token 的非高峰价格为缓存命中 USD 0.022、缓存未命中 USD 0.66、输出 USD 1.98；工作日 UTC 01:00–04:00 和 06:00–10:00 的高峰价格均为两倍。系统以非高峰价格计算基础估算，再乘至少 2 倍形成当前高峰预算包络，并与供应商回报成本取高值；这不表示每次调用都按高峰计费。价格基线最多 30 天必须人工复核，来源为 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)。

## 发布边界

发布目标固定为 `internal_research_review`。系统始终记录：

- `broker_connection_enabled=false`
- `external_distribution_approved=false`
- 不生成资金动作语言
- 不自动执行任何订单或账户操作

如未来需要对外服务、投资顾问或交易能力，必须作为独立项目完成法律、数据、信息安全、模型风险和交易系统审批，不能扩展本流水线绕过门禁。

参考：[Tushare 服务条款](https://tushare.pro/document/1?doc_id=405)、[中国证监会关于证券投资咨询边界的风险提示](https://www.csrc.gov.cn/shenzhen/c105614/c1575193/content.shtml)、[Pi 安全文档](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/security.md)。

## 2026-09-15 当前商业准入更新

源码准入现在采用三段式控制：机器 packet 完整性、外部 Platform/Security 双人逐文件 decision、Gate Owner/Platform Owner 对 private baseline 的独立授权。`source-review-decision-verify` 的成功只代表精确候选上的结构化审查 claim 可核对，仍不代表组织身份已认证、Git 已授权、G1 已通过或真实运行可执行。空白模板和 incomplete record 必须阻断。

当前工程回归为 **194/194 PASS**，Mock 7/7 和 release BLOCKED 合同通过；真实 Tushare、付费 Pi、组织授权、private source baseline、四类商业证据和五方审批仍缺失。因此商业状态继续 **BLOCKED**，项目仍只允许 G0 的离线开发、测试、Mock 和文档工作。任何未来真实验收必须按 `source → rights → protocol → registry → cost → budget → G1 → paid/data acceptance → real baseline` 顺序执行。
