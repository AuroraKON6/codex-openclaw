# ADR-0002：生产 Pi turn 永久 no-tools 隔离

- 状态：已接受
- 日期：2026-09-06
- Owner：模型负责人 + 平台负责人
- 复审触发：Pi 版本升级；任何要求生产 turn 开放工具/上下文/技能的提案；`PI_CHILD_ENV_ALLOWLIST` 变更
- 关联：`quant_agents/pi_client.py` 的 `PI_SECURITY_FLAGS` 与 `PI_CHILD_ENV_ALLOWLIST`；蓝图 §12.6、§14.2

## 背景

Pi 官方安全模型明确其为本地高权限 coding agent，不提供内建沙箱；skills、extensions 与 workspace 文件均属于用户信任边界。生产 turn 若开放工具，等于把文件、进程与网络能力交给 LLM，Tushare Token 与项目文件将暴露于提示注入与模型误用风险之下。

## 决策

生产七 Agent turn 固定：`--no-session --no-tools --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --no-approve --offline`，JSON mode、stdin 输入、临时会话。子进程环境只从 `PI_CHILD_ENV_ALLOWLIST` 白名单构造（Windows 系统变量、代理变量与 `DEEPSEEK_API_KEY`），`TUSHARE_TOKEN` 与外部证据路径物理上不进入 Pi 子进程。provider 必须为 `deepseek`、model 必须精确匹配 `deepseek-v4-pro`、检测到 tool activity 即硬失败、stop reason 异常即硬失败。

## 替代方案

- 依赖权限管控插件（pi-permission-system、CC Safety Net）——否决作为替代：它们只可作 operator 隔离试点（ADR-0009），不能替代"默认关闭"；插件本身是新增供应链面。
- 容器/沙箱化生产 turn——推迟：组织平台阶段评估，单机阶段不引入新运行时依赖。

## 后果

- 正面：LLM 无法接触数据凭据、项目文件与任意网络；泄露半径限定为单次 prompt 内容。
- 负面：Agent 只能基于显式注入的摘要工作，无法自行查证，长任务能力受限。
- 中性：operator 交互式技能与只读 extension 单独锁定审计（`skills-audit`/`extensions-audit`），与生产 turn 隔离并存。

## 合规检查

`tests/test_pi_client.py` 锁定 allowlist 行为；`AGENTS.md` 等 workspace 指令文件因 `--no-context-files` 不会进入生产 turn。
