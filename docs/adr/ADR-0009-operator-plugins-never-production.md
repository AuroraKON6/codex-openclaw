# ADR-0009：operator 插件永不进入生产 turn

- 状态：已接受
- 日期：2026-09-06
- Owner：平台负责人 + 模型负责人
- 复审触发：任何新 skill/extension 候选；Pi 版本升级（重算 lock）；audit 发现未锁定文件
- 关联：`governance/pi_skills.lock.json`、`governance/pi_extensions.lock.json`、`skill_governance.py`、`extension_governance.py`、`.pi/skills/`、`.pi/extensions/`

## 背景

第三方 Pi package 的 lifecycle 脚本可执行任意代码，属于典型供应链风险。生产七 Agent turn 已通过 ADR-0002 硬隔离；本 ADR 约束交互式 operator 侧的插件引入，防止"方便运维"逐步侵蚀隔离。

## 决策

- 生产 turn 永不加载任何 skill/extension/context（ADR-0002 的 flags 锁定）。
- operator 侧当前只允许项目自有的 5 个 skills（quant-data-governance、quant-backtest-assurance、quant-agent-evaluation、quant-run-operations、quant-release-review）与 1 个只读 extension（quant-ops-readonly，提供 `/quant-status`），全部以 SHA-256 锁定于 `governance/*.lock.json`，`production_skills_enabled=false`、`production_extensions_enabled=false`。
- extension 能力边界：无网络、无子进程、无写入、不注册 LLM tool/provider。
- 第三方 package 一次只评估一个，必须：固定 commit/版本与包哈希、审查 lifecycle scripts、网络、写入、Secret 与 telemetry 行为、`npm pack --ignore-scripts` 验证；永不自动加载、永不创建自启动；只进 operator profile。
- `skills-audit`/`extensions-audit` 进入 `check_pi.ps1` 与验收链，未锁定文件即失败。

## 替代方案

- 全禁第三方插件——现状即接近此态（未安装任何第三方 package）；本 ADR 允许受控候选评估，但不放宽生产边界。
- "扫描 + 放行"批量引入——否决：供应链风险无法靠扫描穷尽。

## 后果

- 正面：operator 体验可控增强，生产攻击面零扩张；插件决策有固定 revision 可审计。
- 负面：新工具引入流程慢——有意为之。
- 中性：CC Safety Net、pi-permission-system、pi-lens、pi-subagents 等候选维持蓝图 §10.9 的既定结论；pi-subagents 永久拒绝（避免第二套 DAG）。

## 合规检查

`tests/test_skill_governance.py`、`tests/test_extension_governance.py`、`tests/test_pi_ops_extension.py` 锁定能力与隔离边界。
