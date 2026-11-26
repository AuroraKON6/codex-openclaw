# macOS 运行手册（darwin arm64）

本手册说明如何在 macOS（Apple Silicon）上从干净检出安装、启动和验证 CSI 500 研究流水线。Windows 入口（`*.ps1`）、Windows 安全验收和 `windows-latest` CI 均原样保留；"macOS 可运行"不替代任何 Windows 安全验收。

## 1. 平台入口对照

| 用途 | Windows（保留，未改动） | macOS / Linux |
|---|---|---|
| 创建隔离环境 | `bootstrap_python.ps1` | `./quant.sh bootstrap` |
| 重新生成哈希锁 | `lock_python_dependencies.ps1` | `./quant.sh lock [--apply]` |
| 安装锁定 Pi runtime | `install_pi_runtime.ps1` | `./quant.sh install-pi-runtime` |
| 调用 CLI | `.\quant.ps1 <子命令>` | `./quant.sh <子命令>` |
| 仅检查 Pi（不 ping） | `check_pi.ps1 -NoPing` | `./quant.sh check-pi --no-ping` |
| 研究运行 | `run_quant_agents.ps1 [-Mock]` | `./quant.sh run [--mock]` |
| 周报 | `run_weekly_report.ps1` | `./quant.sh weekly` |
| 离线全量回归 | `verify_quant_pipeline.ps1` | `./quant.sh verify` |
| 备份 / 保留计划 / 演练 | `backup_quant_runs.ps1` 等 | `./quant.sh backup` / `retention-plan` / `drill` |
| 只读运维控制台 | `open_pi_ops_console.ps1` | `./quant.sh ops-console` |
| Pi 验收（**付费**） | `invoke_pi_acceptance.ps1` | `./quant.sh pi-acceptance` |

仅 Windows、未移植：`install_quant_schedule.ps1`、`check_quant_schedule.ps1`、`run_daily_research.ps1`（依赖 schtasks 与安装器出具的授权文件）、`disable_legacy_openclaw.ps1`、`invoke_pi_skills_acceptance.ps1`（付费 skills 验收，后续任务）。

## 2. 前置版本

- macOS 14+，Apple Silicon（`uname -m` 为 `arm64`）。
- CPython 3.11.x。推荐 `uv python install 3.11`（也可 `brew install python@3.11`）。bootstrap 依次查找 `QUANT_BASE_PYTHON` → PATH 上的 `python3.11` → `uv python find 3.11`。
- Node.js `>=22.19.0` 与 npm（Pi `0.84.2` 要求）。
- Git。
- 可选：Docker Desktop（arm64），用于第 7 节的研究镜像。

## 3. 安装与启动

```bash
git clone git@github.com:AuroraKON6/codex-openclaw.git && cd codex-openclaw
cp .env.example .env            # 可选：只放占位符，按第 5 节填写
./quant.sh bootstrap            # venv + 哈希锁安装 + pip check + runtime contract + 全量单测
./quant.sh install-pi-runtime   # npm ci（禁用安装脚本）+ 离线模型目录检查
./quant.sh python-runtime --require-ready
```

预期：`bootstrap` 结尾输出 `Isolated CPython 3.11 environment is ready: .../.venv/bin/python`；`python-runtime` 输出 `"ok": true`、`"target": "macos-arm64-cpython-3.11-project-venv"`、`"locked_package_count": 32`、`"errors": []`。

bootstrap 强制 `--require-hashes --only-binary=:all:`，可用 `--wheelhouse <目录>` 离线安装；`--skip-tests` 只跳过单测，不跳过合同检查。

## 4. 依赖锁与运行时合同

- `requirements.txt`：Windows CPython 3.11 wheel 哈希，**逐字节未改动**，Windows 合同仍绑定它。
- `requirements-macos-arm64.txt`：同样的 32 个 pin，哈希来自 macOS arm64 wheel。
- `requirements-linux-aarch64.txt`：同样的 32 个 pin，供研究镜像使用。
- 运行时合同按**宿主实际平台**选择（`quant_agents/python_runtime.py` 的 `RUNTIME_CONTRACTS`），不可通过配置切换；证据里的 `target` 标签随平台变化，macOS 的运行证据不会被当成 Windows 证据。其他平台（如 x86_64 Linux）在 `operating_system` 检查上失败。
- macOS / Linux 锁的 pin 继承已评审的 `requirements.txt` 版本集，没有引入新版本；`tests/test_python_runtime.py` 断言三份锁的 pin 完全一致。
- 重新解析版本是独立的评审决定：`./quant.sh lock` 只在 `.tmp/` 生成候选并提示与已提交 pin 的差异，显式 `--apply` 才覆盖。

## 5. 配置注入

`.env.example` 只含占位符，已去掉机器专有盘符路径。本机注入方式：

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env：<ABSOLUTE_PATH_OUTSIDE_REPO> 换成仓库外的绝对路径，例如
#   /Users/<you>/controlled/quant/experiment-registry
#   SOURCE_REVIEW_PACKET_DIR 换成 `./quant.sh source-review-packet` 输出的 packet_dir
```

- `.env` 在 `.gitignore` 中，不会进入源码候选或提交；`quant.sh` 包装器只在变量未设置时从 `.env` 填充（与 PowerShell 包装器一致），优先级：进程环境 > `.env`。
- 证据、实验 Registry、前向 campaign 必须放在仓库外；项目会拒绝仓库内路径。
- 仓库外目录建议 `chmod 700`。这不是 NTFS DACL 的等价物，见第 8 节。
- 不要提交真实 `DEEPSEEK_API_KEY` / `TUSHARE_TOKEN`，也不要把密钥写进命令行历史。

## 6. 验证与主流程

```bash
./quant.sh verify                 # 离线全量回归：runtime → py_compile → secret-scan → source-candidate → packet/decision smoke → 单测 → Mock 7/7 → verify-run → release-prepare 必须退出码 3
./quant.sh run --mock             # 显式 Mock，7/7
./quant.sh run                    # 真实模式：前置不满足时退出码 2，绝不回退 Mock
./quant.sh check-pi --no-ping     # 仅本地安装与模型目录检查，不调用 LLM
./quant.sh project-readiness --input strategy_round.example.json
```

没有凭据、没有外部证据、工作区未提交时，真实模式在调用 Tushare/Pi 之前失败并生成 `preflight_failed` 的 `state.json`，这就是安全空跑的预期结果。Mock 7/7、Pi ping 或配置存在都不代表真实研究完成。

`verify` 中的 PowerShell 语法解析在 macOS 上标记为 `SKIPPED`（没有 `pwsh` 时），不会静默通过；该检查由 `verify_quant_pipeline.ps1` 和 `windows-latest` CI 承担。安装了 `pwsh` 则会实际解析保留的 `.ps1`。

## 7. Docker 研究镜像（可选）

仓库此前没有 Docker 文件；新增的是最小离线研究镜像：

```bash
docker compose config                                   # 校验 Compose 配置
docker compose build
docker compose run --rm quant                           # 最小启动：python-runtime --require-ready
docker compose run --rm quant run --mock                # 只读文件系统、无网络下的 Mock 运行
docker compose -f compose.yaml -f compose.test.yaml run --rm test   # 镜像内全量单测
```

- 镜像 `quant-research-pi-runtime:local`，`linux/arm64`，默认用户 `1000:1000`，不内含任何凭据、台账或调度。
- `quant` 服务：`read_only: true`、`network_mode: none`、不发布端口（这是批处理作业，不是服务）；仅 `/app/runs`（绑定到仓库外 `QUANT_DOCKER_RUNS_DIR`，默认 `../quant-research-runs-docker`）和 tmpfs 可写。
- Pi runtime 路径与宿主一致：`/app/pi_runtime/node_modules/@earendil-works/pi-coding-agent/dist/cli.js`，Node 二进制来自锁定阶段。
- `compose.test.yaml` 的 `test` 服务需要可写层（四个治理测试会故意在项目树内创建"仓库内证据"），只在一次性容器里使用。
- 卷属主：`QUANT_DOCKER_UID` / `QUANT_DOCKER_GID` 默认 1000，按 `id -u` / `id -g` 导出后运行。

## 8. 平台受限验收的归属

| 验收项 | 分类 | 归属 |
|---|---|---|
| KONM-136 原生 Windows DACL（`Get-Acl` / `icacls` / SDDL、扫描令牌 SID、非授权主体改写与父目录替换） | **必须 Windows** | 已在已授权的 Tailscale Windows 设备上执行（KONM-136 当前 `in_review`）。macOS 没有 DACL，POSIX 权限位不能证明"可读不可写、不可经父目录替换"这类断言，不做等价替代。 |
| KONM-120 线下"管理员持有 NTFS 夹具" | **必须 Windows** | 需要 NTFS 与提升的管理员持有者；沿用同一台外部 Windows 执行位，或 `windows-latest` CI 的提升权限作业。在 macOS 上应保持 **BLOCKED**，不得改写为通过。 |
| `install_quant_schedule.ps1` / `check_quant_schedule.ps1` / `run_daily_research.ps1` | **必须 Windows**（schtasks） | 生产调度只在 Windows 安装；macOS 不安装调度、不提供 launchd 替代。 |
| `disable_legacy_openclaw.ps1` | **必须 Windows**（计划任务） | 仅 Windows。 |
| PowerShell AST 语法解析 | **必须 Windows** | `windows-latest` CI + `verify_quant_pipeline.ps1`；macOS 上 `verify` 明确标注 SKIPPED。 |
| 文件链接/reparse 检查 | 可用 macOS 等价验证 | `_is_link_or_reparse` 在 POSIX 上检查符号链接；`st_file_attributes` 不存在时按 0 处理，行为是"只少不多"的严格。 |
| 进程存活 / 锁回收 | 可用 macOS 等价验证 | `os.name == "nt"` 分支保留，POSIX 走 `os.kill(pid, 0)`。 |
| 大小写不敏感文件系统 | 仅在 macOS 上部分成立 | macOS 默认大小写不敏感；源码候选清单本身做大小写/Unicode 折叠碰撞检查，不依赖文件系统。 |
| 路径分隔符、UTF-8 控制台 | 仅界面差异 | Python 控制面全部使用 `os.path` / `pathlib`；`quant.sh` 强制 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`。 |

KONM-136 / KONM-120 的候选代码不在本分支的 `main`（`54652b6`）上，本次移植没有触碰它们。后续把 `ef8a395` 线合流时，这些测试在非 Windows 宿主上必须显式报告 BLOCKED，不能以 skip 当作通过。

## 9. 运行数据：macOS 最小数据与迁移步骤（待 HORIZON K 决定）

本次没有迁移或复制 Windows 上的任何台账、数据库、状态卷或密钥。macOS 运行所需最小数据：

1. **源码**：从 GitHub 干净检出（已具备）。
2. **凭据**：`DEEPSEEK_API_KEY`、`TUSHARE_TOKEN`——由 HORIZON K 在本机重新注入，不经仓库、不经聊天。
3. **仓库外证据**（真实模式才需要）：数据授权、研究协议、执行成本校准三类证据原件，以及实验 Registry 目录、前向 campaign 目录。这些是组织原件，不属于"运行数据"，是否以及如何从 Windows 受控目录迁移由 HORIZON K 决定。
4. **运行产物**：`runs/` 不需要迁移；Mock 运行在本机重新生成。

建议的迁移步骤（每一步都需明确批准）：

1. HORIZON K 确认要迁移的仓库外目录清单（证据、Registry、campaign、归档根）。
2. 在 Windows 侧按 `backup_quant_runs.ps1` / `archive-run` 生成归档并记录 SHA-256。
3. 传输后用 `./quant.sh cli verify-archive --archive <zip> --expected-sha256 <哈希>` 校验再解包到 macOS 的仓库外受控目录（`chmod 700`）。
4. 重跑 `./quant.sh project-readiness`，由人工确认 Registry 哈希链在 macOS 上复核一致后，才讨论真实 run。
5. Windows 侧原件保留为只读来源，直到 macOS 侧通过一次独立的 Registry 复核。

## 10. 常见错误

| 现象 | 原因 | 处理 |
|---|---|---|
| `CPython 3.11.x is required` | 没有 3.11 解释器 | `uv python install 3.11`，或 `export QUANT_BASE_PYTHON=<路径>` |
| `Project Python environment is missing` | 未 bootstrap | `./quant.sh bootstrap` |
| `operating_system: expected Windows or Darwin or Linux; running ...` / `machine_architecture` 失败 | 非支持的宿主或架构 | 合同按宿主平台强制；x86_64 需要另行评审并生成对应哈希锁 |
| `locked_distributions` 报 unexpected | venv 里装了锁外的包 | 删除 `.venv` 重新 bootstrap |
| `Pinned Pi runtime does not expose deepseek/deepseek-v4-pro` | Pi 未安装或版本不符 | `./quant.sh install-pi-runtime`（离线目录枚举不需要真实密钥，也不会写入凭据） |
| `Pi 0.84.2 requires Node >= 22.19.0` | Node 版本过低 | 升级 Node（如 `nvm install 22`） |
| `DeepSeek pricing baseline is stale` | `DEEPSEEK_PRICING_REVIEWED_DATE` 超过 30 天复核期 | 人工复核官方价格页后更新日期；这是治理动作，不要为了让检查通过而改日期 |
| `Source revision preflight failed: workspace is dirty` | 真实模式要求干净已提交源码 | 提交/暂存改动，或改用 `--mock` 做软件回归 |
| `verify` 的单测阶段失败于 `test_operations` / `test_forward_observation` | 与平台无关的时间到期（定价复核日期、研究协议有效期） | 同上，属既有失败；见交付报告的"既有失败"清单 |
| Docker 卷不可写 | 绑定目录属主不是容器用户 | `export QUANT_DOCKER_UID=$(id -u) QUANT_DOCKER_GID=$(id -g)` |
| `.ps1` 在 macOS 上无法执行 | 设计如此 | 使用 `./quant.sh`；不要安装 pwsh 来绕过平台边界 |

## 11. 未决事项

- macOS 基础解释器来源（uv 管理的 python-build-standalone CPython 3.11.17）尚未纳入"已批准运行时"评审；Windows 基线仍指 python.org 安装包。
- `DEEPSEEK_PRICING_REVIEWED_DATE`（2026-08-25）和研究协议复核日期已过期，需要人工复核后更新；这会让当前 7 个时间到期测试恢复。
- 研究镜像目前只覆盖 `linux/arm64`；x86_64 镜像需要单独的哈希锁与评审。
