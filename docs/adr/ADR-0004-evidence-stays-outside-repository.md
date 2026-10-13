# ADR-0004：商业证据与凭据永不入库

- 状态：已接受
- 日期：2026-09-06
- Owner：合规负责人 + 平台负责人
- 复审触发：任何"把证据副本放进仓库"的提案；Secret 轮换；供应商合同更新
- 关联：`.env.example`、`quant_agents/secret_scan.py`、`source_baseline.py`、蓝图 §13.2、§14.2

## 背景

数据授权、研究协议、实验 Registry、执行成本四类证据原件含组织身份与合同条款；Secret 一旦入库，历史极难彻底清除。仓库应能被完整审计结构而不泄露任何权利与凭据内容。

## 决策

- 四类证据路径与 Registry、forward、archive 根目录全部位于仓库外（`.env.example` 以 `D:\controlled\...` 示范，真实路径由组织决定）。
- `.env`、`runs/`、`.cache/`、`.venv/`、`drill_reports/`、`scheduled_inputs/` 等生成物与凭据载体全部 gitignore；工具生成的状态目录（含 `.mimosa/`）同样不入库。
- Secret 只经进程环境或组织批准的凭据存储注入；日志与审计产物只记录 set/not-set、长度类别或哈希，不记录值。
- `secret_scan.py` 对将要进入私有基线的源码候选做固定规则扫描并产出回执：只记录文件、行号与规则，不回显命中值；source gate 绑定有效回执。

## 替代方案

- 证据加密后入库——否决：密钥管理与仓库生命周期耦合，人员流动即风险。
- 仓库内保留脱敏副本——否决：制造第二真相源，脱敏正确性无法机器验证。

## 后果

- 正面：仓库结构可全程公开审计而不泄密；source gate 可机器验证；证据原件的责任与留存由组织系统承担。
- 负面：证据核验依赖环境变量路径配置正确，跨机器迁移必须按 runbook 执行。
- 中性：回执仅证明"扫描时点内容一致"（application hash），不证明扫描器法律效力（见 ADR-0010）。

## 合规检查

`tests/test_secret_scan.py`、`tests/test_source_review.py` 锁定不回显与外部存放约束；`.gitignore` 覆盖全部生成物目录。
