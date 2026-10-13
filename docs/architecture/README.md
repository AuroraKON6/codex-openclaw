# 架构图集（Archify 识别产物）

## 最终交付：单张全细节总图

**[full-detail.html](./full-detail.html)** —— 唯一权威架构图。67 个真实组件、58 条关系，六个生产模块区带 + 运维工具层 + 治理资产层全部展开：

| 区带（自上而下） | 覆盖内容 |
|---|---|
| 模块 1 · 治理与证据 | secret_scan / governance / research_protocol / experiment_registry / execution_cost_governance 五道门禁 + 仓库外证据与账本 |
| 模块 5 · 运行控制 | orchestrator / operations / scheduling / config / source_baseline+source_review / python_runtime / readiness |
| 模块 2 · 数据层 | data_client / market_rules + Tushare 外部接口 + 规则簿 |
| 模块 3 · 确定性研究 | input_validation / research_engine / backtest_validation / backtest_assurance + 成本账本 |
| 模块 4 · Pi 认知层 | pi_client / base_agent / contracts / agents 提示词 + Pi CLI + DeepSeek |
| 模块 6 · 发布与生命周期 | release / audit / forward_observation / weekly |
| 运维工具层（operator-only） | 19 个 .ps1 分组：Pi 安装验收 / 验证演练 / 调度安装审计 / 归档保留周报封装 / Python 环境依赖锁 / 遗留清理 |
| 治理与资产层 | .pi/skills 锁、quant-ops-readonly 扩展、pi_runtime 锁定安装、5 类证据模板、upstream_references、tests/ 30 文件 |

浏览：滚轮缩放、拖拽平移、Views 章节导航（5 个模块视图）、搜索定位、点击追踪关系。

## 早期分模块图（已被总图取代，留作过程档案）

m1-governance-evidence / m2-data / m3-deterministic-research / m4-pi-agent-plane / m5-orchestration-ops / m6-release-lifecycle / assembly-quant-research-os（概览版总装）。

## 覆盖度审查记录（2026-09-06）

三个并行只读子代理审查（Python 38 文件 AST 比对 / 19 个 .ps1 逐个核对 / runtime+skills+治理资产盘点）后补齐：
- 补入节点：python_runtime（预检第一门）、readiness、skill/extension 治理（并入资产层）、运维工具层 6 节点、治理资产层 6 节点；
- 修正失实数字：CLI "12 命令"→27 子命令；测试 133→172 用例/30 文件；
- 校验无幻觉函数名；哈希与 lock 文件一致；Pi 0.84.2 / Node ≥22.19 / deepseek-v4-pro 与代码一致。

## 已知事实基线（生成日 2026-09-06）

- 测试：**172 用例（30 文件），当前 20 失败/错误待修**（集中在 08-29 后新增的 python_runtime / readiness / source_review 及波及的 orchestrator / release / cli）；
- 商业状态：BLOCKED（不变）；Pi 0.84.2、Node ≥22.19、deepseek-v4-pro 与 lock 一致。
- 浏览器自动化视觉检查因本机无 Chrome/Chromium 未执行；deliver 确定性检查全部通过。
