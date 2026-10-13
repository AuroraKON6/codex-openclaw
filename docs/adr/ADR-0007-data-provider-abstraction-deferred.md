# ADR-0007：数据供应商视为可替换 adapter，但抽象化推迟到研究工厂阶段

- 状态：已接受
- 日期：2026-09-06
- Owner：数据负责人（架构执行：平台负责人）
- 复审触发：第二数据源采购启动；Tushare 许可条款变更；研究工厂阶段（WP-11）开工
- 关联：`quant_agents/data_client.py`、蓝图 §9.1、§9.3、§24.3

## 背景

当前七类 Tushare 接口（trade_cal、index_weight、daily、adj_factor、stk_limit、suspend_d、daily_basic）实现于单一 `data_client.py`。蓝图定义了 `MarketDataProvider` 目标接口与 provider evidence 要求。在只有一个真实实现时提前抽象接口，是未经第二实现校准的猜测；但永久绑定单一供应商又是 lock-in 风险。

## 决策

- 首个真实 baseline（WP-08）之前不做接口抽象，`data_client.py` 保持现状以最短路径交付可复现 baseline。
- 研究工厂阶段引入 provider 接口与第二供应商认证路径；届时每个 provider 必须具备：组织授权、endpoint/字段契约、频率配额、更新时间、缓存与衍生权、LLM 处理权、保留与终止处置、quality profile、provider version 与 terms hash。
- 数据存储同期演进：原始响应压缩留存（仅合同允许内容）、标准化行情与成分用 Parquet、本地点时查询用 DuckDB、catalog 用 JSON + metadata，metadata 与 artifact 分离。

## 替代方案

- 立即抽象 provider 接口——否决：单实现抽象是猜测，接口必然错。
- 永久绑定 Tushare——否决：许可不可移植即业务不可持续。

## 后果

- 正面：baseline 路径最短；抽象落地时有两个真实实现校准接口形状。
- 负面：`data_client.py` 重构成为 WP-11 的登记在案前置债务。
- 中性：point-in-time 语义、快照哈希与质量门禁在抽象前后保持不变，接口迁移不改研究语义。

## 合规检查

数据授权门禁（v2 证据）按供应商独立评估；本 ADR 不降低任何许可要求。
