# Source Baseline Preparation

> 状态：PREPARED / NOT COMMITTED  
> 复核日期：2026-09-15（Asia/Shanghai）  
> 适用项目：Governed Quant Research OS  
> 当前硬阻断：Git 无 HEAD、无 tracked file、无 remote  
> 安全边界：本文件不授权真实数据、真实模型流水线、发布、调度或真实资金动作

## 1. 目的

把当前本地工作区整理成一个可以由 Platform/Security 人工审查后提交到受控私有仓库的源码候选，同时防止以下内容进入版本控制：

- API Key、Token、密码、证书和私钥；
- `.env` 和个人机器配置；
- 真实数据、真实授权原件和审批凭据；
- run、cache、临时文件和测试产物；
- `node_modules` 和可重建依赖；
- 未经审查的第三方插件或自动加载配置。

## 2. 当前只读审计结果

当前机器清单结果（后续任何候选文件编辑都必须重新生成回执和 manifest）：

| 检查 | 结果 |
|---|---|
| Git HEAD | 不存在 |
| tracked files | 0 |
| remote lines | 0 |
| 顶层 untracked entries | 37 |
| 提交候选文件 | 当前约 174 个；以最后一次 `source-candidate` 输出为准 |
| 候选总大小 | 以最后一次 `source-candidate` 输出为准 |
| 大于 1 MiB 的候选文件 | 0 |
| reparse/symlink 候选 | 0 |
| 机器阻断 | 0 |
| 人工 review flags | 9：7 个 example 证据边界、2 个 Secret scanner 可疑文件名复核 |

截至 2026-09-15，`source-candidate` 状态仍为 `READY_FOR_HUMAN_FILE_REVIEW_NOT_AUTHORIZED`：机器清单可进入逐文件人工审查，但 `source_baseline_authorized=false`、`source_release_ready=false`，未执行 stage、commit、tag 或 remote。Secret scanner 规则版本 `2026-08-29.1` 的命中只记录文件、行号和规则，不回显秘密值；最终数量、哈希和回执必须在提交前重新生成，本文数字不能替代当前机器证据。

## 3. 候选构成

预审时主要类型：

| 类型 | 数量 | 处理原则 |
|---|---:|---|
| Python `.py` | 69 | 逐模块审查，无本机路径和凭据 |
| Markdown `.md` | 28 | 保留架构、运行、治理与接管事实 |
| PowerShell `.ps1` | 19 | 审查自启动、任务计划、路径和 Secret 行为 |
| JSON `.json` | 13 | 只提交规则、锁和明确 example；不提交真实审批原件 |
| YAML `.yaml` | 5 | 只提交 Agent/operator 元数据 |
| 其他 | 6 | `.gitignore`、`.python-version`、`.env.example`、`.mjs`、`requirements.in`、`requirements.txt` |

## 4. 已确认忽略边界

`.gitignore` 当前覆盖：

- `__pycache__/`；
- `*.pyc`；
- `.venv/`；
- `.env`；
- `runs/`；
- `*.egg-info/`；
- `dist/`；
- `build/`；
- `.tmp/`；
- `.cache/`；
- `scheduled_inputs/`；
- `drill_reports/`；
- `pi_runtime/node_modules/`；
- `.pi/npm/`；
- `.pi/git/`。

提交前必须用 `git check-ignore -v --no-index` 抽查上述每一类。仅看到目录被忽略不够，还要确认其中没有应当单独归档的业务证据。

## 5. 必须纳管的源码类别

### 5.1 Python 权威控制层

- `quant_agents/`；
- 明确的 7 Agent contract；
- 数据、研究、回测、风险、Registry、release、forward 和 operations 代码；
- `tests/`；
- `.python-version`、`requirements.in`、hash-locked `requirements.txt`；
- `bootstrap_python.ps1`、`quant_python.ps1`、`quant.ps1`、`lock_python_dependencies.ps1`；
- `tools/build_python_lock.py`。

### 5.2 Pi 锁定运行时

- `pi_runtime/package.json`；
- `pi_runtime/package-lock.json`；
- 安装与检查脚本；
- `governance/pi_skills.lock.json`；
- `governance/pi_extensions.lock.json`；
- 被锁定的 operator-only skills 和只读 extension 源码。

不得纳管 `pi_runtime/node_modules/`、`.pi/npm/` 或 `.pi/git/`。

### 5.3 治理与规则

- A 股规则簿；
- upstream reference 元数据；
- 明确命名为 `.example.json` 的证据模板；
- runbook、商业门禁、部署验收和事件演练；
- 项目战略、主计划和交接文档。

真实授权原件、真实审批、真实 Registry、真实 Token 和真实快照必须保存在仓库外受控位置。

### 5.4 Windows 运维脚本

逐个审查 19 个 PowerShell 脚本：

- 不包含明文凭据；
- 不自动创建真实生产调度；
- 自启动窗口隐藏；
- 安装、checker 和 runner schema 一致；
- 不恢复 OpenClaw Gateway；
- 不静默 fallback；
- destructive action 使用固定路径和明确验证。

### 5.5 人工审查交接包

在 Secret 回执和 source candidate 均为当前状态后运行：

```powershell
$packet = .\quant.ps1 source-review-packet | ConvertFrom-Json
.\quant.ps1 source-review-verify --packet-dir $packet.packet_dir
```

每次运行在 `.cache/source-baseline/review-packets/` 下创建一个新目录且拒绝覆盖同名包。包内必须保留只读的 `candidate_manifest.json`、`review_request.json`、`review_checklist.csv`、`REVIEW_INSTRUCTIONS.md` 和 `packet_manifest.json`；最后一个文件绑定其余四个文件的 SHA-256。校验命令拒绝缺失/多余文件、链接或 reparse、artifact hash 不一致、候选身份不一致、弱化双角色职责分离、预填人工决定和 CSV 机器字段偏移。CSV 对公式起始字符做前缀防护，人工应在组织系统或受控副本中填写，不得修改机器原件后继续声称 hash 有效。

Packet 状态固定为 `AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED`；校验成功状态固定为 `VERIFIED_AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED`。应用层 hash 只能发现与 packet manifest 不一致的变化，不是组织数字签名，也不能证明 packet manifest 自身来自可信身份。它不认证人员身份、不记录批准、不执行 Git 写入，也不能替代 Platform 与 Security 两个不同组织身份的逐文件审查。

## 6. 外部双人 decision record

### 6.1 为什么需要第二层证据

`source-review-packet` 只能证明机器生成的 packet 内部没有被应用层哈希检测到篡改，不能证明谁审查了文件，也不能把本地 CSV 的填写者变成组织批准人。因此 WP-02 必须拆成三个不同状态：

1. `VERIFIED_AWAITING_HUMAN_FILE_REVIEW_NOT_AUTHORIZED`：机器 packet 完整，但尚未有外部审查记录；
2. `VALID_DUAL_FILE_REVIEW_CLAIM_AWAITING_PRIVATE_BASELINE_EXECUTION_AUTHORIZATION`：外部记录声称两名不同身份已逐文件批准，机器已核对精确候选，但仍未授权或执行 Git；
3. clean private commit/tag/remote + clean-clone：源码基线实际建立，才允许进入后续 G1 前置检查。

### 6.2 生成空白模板

```powershell
$packet = .\quant.ps1 source-review-packet | ConvertFrom-Json
.\quant.ps1 source-review-decision-template `
  --packet-dir $packet.packet_dir `
  --output D:\controlled\quant\source-review-decision-template.json
```

模板包含：

- packet/candidate 的 ID、SHA-256、数量和 review flag 数量；
- 恰好 `PLATFORM_REVIEWER`、`SECURITY_REVIEWER` 两个空白审查人记录；
- 每个候选文件一行，分别填写 Platform/Security 决定和证据引用；
- 每个机器 review flag 一行，必须填写 `RESOLVED`、理由和证据引用；
- 明确的禁止项：不包含凭据、真实数据、审批原件，不授权 Git、G1、真实运行或发布。

模板状态是 `TEMPLATE_NOT_EVIDENCE`，不能直接复制后声称完成。真实填写应在组织审查系统完成；若系统只提供导出文件，导出文件放在仓库外受控目录，并保留系统记录 ID、身份引用和导出时间。

### 6.3 机器复核完成记录

```powershell
$env:SOURCE_REVIEW_PACKET_DIR = $packet.packet_dir
$env:SOURCE_REVIEW_DECISION_PATH = 'D:\controlled\quant\source-review-decision-v1.json'
.\quant.ps1 source-review-decision-verify `
  --packet-dir $env:SOURCE_REVIEW_PACKET_DIR `
  --decision $env:SOURCE_REVIEW_DECISION_PATH
```

复核器会拒绝：decision 在项目内、链接/reparse、模板或占位字段、packet/candidate 变化、重复身份、少审文件、文件 SHA 不符、未解决 flag、未来/过期时间、拒绝文件或任何授权字段为 true。退出码 `0` 仅代表 `review_claim_valid=true`，并且仍返回 `organization_identity_verified=false`、`private_baseline_execution_authorized=false` 和 `source_baseline_authorized=false`。应用层哈希是篡改检测，不是签名。

只有 Gate Owner/Platform Owner 在组织系统核对身份后，才可以另行授权建立私有基线。任何 `git add`、commit、tag、remote 创建都必须由该人工动作完成，并绑定同一 packet/candidate identity；本工具不会执行这些动作。

## 7. 人工文件审查清单

每个候选文件至少检查：

- [ ] 文件属于当前项目；
- [ ] 没有真实 Key、Token、密码、Cookie、证书或私钥；
- [ ] 没有真实个人姓名冒充组织批准人；
- [ ] 没有真实授权原件或受限数据；
- [ ] 没有本机绝对路径被当成可移植默认值；
- [ ] example 明确不能被当成批准证据；
- [ ] Mock 明确标记 Mock；
- [ ] 没有 broker、order、live trading 或资金动作代码；
- [ ] 没有把应用哈希链称为 WORM/数字签名；
- [ ] 第三方来源、版本和用途可追溯；
- [ ] 文件是源码/文档，而不是可重建产物；
- [ ] 删除文件不会破坏审计链或运行合同。

## 8. 提交前机器检查

在最终文件编辑完成后执行：

```powershell
git status --short
git ls-files --cached --others --exclude-standard
.\quant.ps1 secret-scan
.\quant.ps1 source-candidate --require-reviewable
  $packet = .\quant.ps1 source-review-packet | ConvertFrom-Json
  .\quant.ps1 source-review-verify --packet-dir $packet.packet_dir
  .\quant.ps1 source-review-decision-verify --packet-dir $packet.packet_dir --decision D:\controlled\quant\source-review-decision-v1.json --secret-receipt .\.cache\secret-scan\receipt.json
.\quant.ps1 python-runtime --require-ready
.\.venv\Scripts\python.exe -m unittest discover -s tests
powershell -ExecutionPolicy Bypass -File .\check_pi.ps1 -NoPing
powershell -ExecutionPolicy Bypass -File .\verify_quant_pipeline.ps1
```

注意：

- `secret-scan` 回执位于忽略版本控制的 `.cache/secret-scan/receipt.json`；
- 任一候选文件变化都会使旧回执失效；
- `source-candidate` 机器通过只授权人工逐文件复核，不授权 Git 或真实运行；
- `source-review-verify` 只验证应用层 hash 和控制字段，不认证人员或批准 baseline；
- Python runtime 必须是项目 `.venv` 中的 Windows CPython 3.11，锁定包不得偏移或额外注入；
- `check_pi.ps1 -NoPing` 不产生新的付费模型证据；
- `verify_quant_pipeline.ps1` 的成功只证明软件和 Mock，不放行真实商业运行。

## 9. 建仓建议

### 9.1 仓库要求

- 私有；
- 明确组织 Owner；
- MFA；
- 最小权限；
- 默认分支保护；
- 至少一名独立 reviewer；
- Secret scanning；
- 不允许强推受保护分支；
- tag policy；
- 备份与恢复责任人；
- 禁止把真实外部证据放进源码库。

### 9.2 命名建议

仓库显示名建议使用 `governed-quant-research-os` 或其他能明确 Pi 运行时和内部研究边界的名称。

当前本地目录暂不移动。先审计所有绝对路径依赖，再单独通过 ADR 决定是否重命名目录，避免破坏脚本、计划任务和证据绑定。

### 9.3 建议提交边界

由于当前没有 HEAD，首个提交应是一个经过一次性完整审查的最小可运行基线。不得把提交拆分成多个未经验证的中间状态，也不得为追求整洁删除历史运行事实文档。

建议提交信息仅作为候选，不在未获明确授权时执行：

```text
Establish governed quant research OS source baseline
```

## 10. Clean-clone 验收

提交和 remote 建立后，由 Platform/Security 在新的隔离目录执行：

1. clone 精确 commit/tag；
2. 检查没有 `.env`、Token、run、cache、真实数据和外部原件；
3. 安装锁定依赖；
4. 全套测试；
5. Pi `-NoPing` 检查；
6. Mock E2E；
7. Secret scan；
8. 产物完整性；
9. 对比 source inventory；
10. 输出 source provenance evidence。

## 11. Source Baseline Exit Criteria

只有同时满足以下条件，WP-02 才能从 OPEN 变为 PASS：

- clean committed HEAD；
- 受控 private remote；
- candidate inventory 完成；
- Secret scan PASS 且绑定当前 source；
- dependency locks 完整；
- clean-clone 回归通过；
- tag 和 provenance 可恢复；
- 没有真实凭据、数据或审批原件；
- reviewer 身份真实且与提交者分离；
- 外部 decision record 对 100% 候选文件有 Platform/Security 双人记录，所有机器 review flag 已解决；
- `source-review-decision-verify` 对同一 packet/candidate 返回 `review_claim_valid=true`，但没有把该结果当成身份认证或 Git 授权；
- `source_gate` 能验证当前工作树。

本文件的 PREPARED 状态不满足上述条件，不能绕过 source gate。

## 12. 2026-09-15 当前推进记录

本轮继续保持 G0 开发、G1—G5 NO-GO，并把源码治理从“机器 packet 可校验”推进到“外部双人审查记录可被机器核对但不会被机器伪造授权”：

1. `quant_agents/source_review.py` 现在拒绝畸形 review flag、重复或无法绑定到文件行的 flag，并将 packet 验证异常转换为 BLOCKED 结果，避免坏 JSON 让模板生成或 readiness 直接崩溃。
2. `verify_quant_pipeline.ps1` 增加 packet、空白 decision template 和空白 decision 的离线负向 smoke path；模板明确是 `TEMPLATE_NOT_EVIDENCE`，空模板验证必须退出 `3`，不会产生 baseline、G1 或真实运行授权。
3. `source-review-decision-verify` 支持 `--secret-receipt`，使用自定义 Secret receipt 生成 packet 时可以在后续验证中绑定同一份回执。
4. 任何真实 Tushare、付费 Pi、broker、订单或资金动作仍禁止；本文件、Mock、静态配置和应用层哈希均不能替代组织身份、数据授权或 Gate Owner 决策。

最终交接以同一轮命令输出中的 `candidate_files_sha256`、`manifest_sha256`、packet ID 和 run ID 为准。外部 Platform/Security 审查完成前不得创建 Git baseline；即便外部 decision 机器核验通过，也仍需 Gate Owner/Platform Owner 在组织系统中单独授权。
