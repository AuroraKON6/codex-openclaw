# 数据授权落地手册

## 现实边界

截至 2026-08-23，Tushare 公开数据服务条款授予个人、不可转让、非商业用途许可。组织内部商业研究不能使用个人 Token 或自行填写的 `APPROVED` JSON 代替服务商授权。项目只接受服务商签署的企业订单、合同或书面修订；本手册不构成法律意见。

## 责任顺序

1. 数据负责人以实际使用组织的法定名称向服务商申请书面授权，不先配置生产 Token。
2. 法务/合规确认授权明确覆盖 `licensed_internal_research`、七个必需接口、自动 API、运行快照、缓存、衍生分析和向 DeepSeek 发送派生研究上下文。
3. 双方确认允许的最长留存不少于系统 `RUN_RETENTION_DAYS`，并写明到期、撤销或终止后的删除/返还责任。
4. 数据负责人保存签署原件到仓库外受控目录，计算 SHA-256，填写 `governance/data_license_evidence.example.json` 的副本。
5. 平台负责人只把证据 JSON 路径写入受控环境变量 `DATA_LICENSE_EVIDENCE_PATH`；Token 进入 Secret/进程环境，不进入 JSON、源码或日志。
6. 先执行 health。授权失败必须停止，不得切换 Mock、个人 Token 或旧快照继续真实作业。

## v2 必填证据

- 法律主体、合同编号、服务商批准编号及双方签署人姓名/职务。
- `separate_written_organizational_authorization=true`、组织使用和商业内部研究均明确允许。
- 七个接口：`trade_cal`、`index_weight`、`daily`、`adj_factor`、`stk_limit`、`suspend_d`、`daily_basic`。
- 处理权：`automated_api_access`、`local_cache`、`derived_analytics`、`third_party_llm_processing`；处理者包含 `deepseek`。
- 留存天数覆盖系统配置，终止处置固定为按服务商指令删除或返还，外部分发必须为 false。
- 服务商文件路径、SHA-256、文件类型、授权有效期、公开条款 URL 和最近 30 天复核日期。

## 生成哈希

```powershell
$document = "D:\controlled\provider-authorization.pdf"
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $document).Hash.ToLowerInvariant()
$hash
```

复制示例到仓库外目录后填写真实值；不要修改仓库中的示例为 `APPROVED`，不要提交合同或证据副本。

## 验证

```powershell
$env:DATA_LICENSE_EVIDENCE_PATH = "D:\controlled\quant\data-license-v2.json"
$env:TUSHARE_TOKEN = "<secret-store-injected>"
python -m quant_agents health --runtime pi --input .\strategy_round.example.json
```

通过结果必须记录 schema 2、证据文件哈希、服务商文件哈希、授权期限、处理权和 `identity_assurance=document_hash_only_not_signature_authenticated`。最后一项表示软件没有认证电子签名或人员身份，五方审批不能省略。

## 变更与终止

- 每 30 天以及服务条款、接口、处理者、留存期或用途变化时重新复核并生成新证据文件；旧 run 保留原哈希，不原地改写。
- 授权过期、撤销、服务商文件哈希变化或 DeepSeek 不再获准时，停止调度和新 run，按合同执行删除/返还并保存工单证据。
- 外部分发、投资顾问或交易用途不在本授权范围，必须另立项目和审批。
