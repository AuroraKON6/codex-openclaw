# ADR-0010：身份认证与不可变存储是外部组织服务

- 状态：已接受
- 日期：2026-09-06
- Owner：合规负责人 + 平台负责人
- 复审触发：组织 IAM/审批/WORM 服务可用；发现把本地审批叙述为"已认证身份"或"法律不可变"的文档措辞（立即修正）
- 关联：`quant_agents/release.py`、`source_review.py`、`experiment_registry.py`、蓝图 §13.2、§13.3、§16.1

## 背景

本地 JSON 审批、应用层哈希链、ZIP 归档与回执能证明"内容在时点上一致"，但不能证明"谁签署""何时在组织系统签署""管理员不可改写"。项目最高判断标准禁止把本地 hash chain 宣称为法律不可变证据、禁止宣称本地审批 JSON 认证了身份。需要以 ADR 固化这一能力边界与升级路径。

## 决策

- `release.py` 的五方角色与 `source_review.py` 的 PLATFORM_REVIEWER/SECURITY_REVIEWER 字段只是组织审批的影子：真实身份、时间与签署效力必须来自组织 IAM、审批工单或签名系统，本地字段仅做一致性与完备性检查。
- 归档的外部不可变性（WORM/object lock）与可信时间戳由组织平台服务提供；在其接入前，所有产物只声称 application-level 完整性。
- 所有对内文档与产物叙述必须按此措辞局限（`application_hash_only_not_signature: true`、`organization_identity_verified: false` 已固化为结构化字段）。
- 组织服务可用前的内部 release 判定保留 BLOCKED 边界声明，不得因本地证据齐备而宣称商业 READY。

## 替代方案

- 自建 CA/签名链——否决：自造法律证据能力超出软件项目边界，且身份溯源仍缺组织锚点。
- 引入区块链时间戳——否决：新增依赖不解决身份问题，且引入新的运维与合规面。

## 后果

- 正面：系统从不断言其不具备的合规能力；升级路径（IAM → 审批系统 → Registry 服务 → object lock → 审计导出）已在蓝图 §13.3 定义。
- 负面：内部 release 的法律效力在组织服务接入前受限，商业进度受组织侧进度约束。
- 中性：本地字段持续作为组织系统的机器可读前置清单使用。

## 合规检查

`tests/test_release.py`、`tests/test_source_review.py` 锁定 `organization_identity_verified=false`、`git_actions_performed=false` 等字段语义。
