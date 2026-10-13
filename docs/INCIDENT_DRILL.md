# 故障与演练

## 分类

| 事件 | 识别证据 | 自动行为 | 人工动作 |
|---|---|---|---|
| Pi 缺失/版本漂移 | runtime integrity 失败 | 预检阻断 | 重新执行锁定安装，复核 lock/hash |
| DeepSeek 认证/余额/限速 | ping 或 Agent 非零、错误 JSONL | 当前 run 失败，下游阻断 | 不切 Mock；修复账户后新 Run |
| Provider/model 漂移 | `pi_meta` 不等于 DeepSeek V4 Pro | turn 硬失败 | 模型负责人调查配置或供应商变化 |
| 工具活动 | JSONL 出现 tool event | turn 硬失败 | 平台负责人隔离运行时并复核命令策略 |
| 超时/截断/格式错误 | timeout、stop reason、contract repair 失败 | 最多一次 repair，随后阻断 | 检查提示/服务后新 Run |
| Tushare/许可/新鲜度 | 数据预检或快照门禁失败 | LLM 前阻断 | 数据与法务补证或修复数据 |
| 执行成本证据失配/过期 | cost calibration preflight 或 fingerprint 失败 | Tushare/LLM 前阻断 | 量化、独立复核和合规重新校准并生成新证据 |
| DeepSeek 价格基线过期 | pricing reviewed date 超过30天 | 外部 API 前阻断 | 模型/平台负责人复核官方价格并更新受控配置 |
| 预算超限 | token/cost/time gate failed | 阻断后续 Agent | 模型/平台负责人复核，不删除用量证据 |
| 源码或产物篡改 | clean source、manifest、事件链失败 | 发布阻断 | 事件调查，重新建立基线和新 Run |
| 归档篡改/路径穿越 | sidecar、receipt、成员清单或安全解压失败 | 恢复和保留资格阻断 | 隔离 ZIP，使用外部保存哈希重新取证 |
| 调度授权漂移 | authorization 哈希、过期、HEAD 或审批复验失败 | 外部 API 前阻断 | 停止任务，重新走真实 run 和五方审批 |

## 定期演练

```powershell
.\invoke_quant_drill.ps1 -IncludeFullRegression
```

演练报告和各测试日志写入 `drill_reports/operational_drill_<timestamp>/`。演练应覆盖锁竞争、陈旧锁回收、幂等重试、事件链篡改、陈旧 run 恢复、生产监控排除 Mock、归档篡改/路径穿越/恢复、legal hold、Mock 发布阻断、调度截止日、许可证据、成本模型指纹失配和价格基线过期。Pi 专项还应在隔离测试环境覆盖：错误版本、模型漂移、非 JSON 行、tool event、超时和 contract repair 双失败。

## 处置顺序

1. 停止新的调度触发，不删除失败 run。
2. 保存 `state.json`、`pi_meta/`、raw JSONL、stderr、events、alerts、manifest 和数据请求日志。
3. 标记影响范围：技术健康、数据权利、研究结论、内部发布、外部分发。
4. 指定数据、量化、模型、平台和合规责任人。
5. 修复根因，在 clean source 上创建新的 Run ID；禁止原地续跑。
6. 比较输入指纹、Pi/模型版本、数据快照和输出差异。
7. 重新完成 release candidate 和人工审批。

## 目标

Pi 无常驻服务，故恢复目标针对依赖和 API，而非进程守护：

- 本地 runtime 可通过重新执行 `npm ci` 从锁恢复。
- LLM/API 故障不承诺本机自动恢复；供应商恢复后人工或受控重试。
- 数据和许可证故障永不自动绕过。
- 所有故障期间保持 broker、订单和外部分发关闭。
