from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any


TRIGGER_ORDER = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
SUPPORTED_RUN_SCHEMA_VERSION = 7


def generate_weekly_report(
    since: str,
    until: str,
    output_dir: str,
    mock: bool = False,
    runtime: str = "pi",
) -> str:
    start = datetime.strptime(since.replace("-", ""), "%Y%m%d")
    end = datetime.strptime(until.replace("-", ""), "%Y%m%d")
    if start > end:
        raise RuntimeError("weekly since must not be after until")
    os.makedirs(output_dir, exist_ok=True)

    runs_root = os.path.dirname(os.path.abspath(output_dir))
    runs = _load_runs(runs_root, start, end, mock=mock, runtime=runtime)
    report = _aggregate_runs(runs, since, until, mock)
    report_path = os.path.join(output_dir, "weekly_report.md")
    with open(report_path, "w", encoding="utf-8") as file:
        file.write(_render_weekly_markdown(report))
    with open(os.path.join(output_dir, "weekly_state.json"), "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    return report_path


def _load_runs(
    runs_root: str,
    start: datetime,
    end: datetime,
    mock: bool,
    runtime: str,
) -> list[dict[str, Any]]:
    loaded = []
    if not os.path.isdir(runs_root):
        return loaded
    for entry in os.scandir(runs_root):
        if not entry.is_dir() or entry.name.startswith("weekly_"):
            continue
        state_path = os.path.join(entry.path, "state.json")
        if not os.path.isfile(state_path):
            continue
        try:
            with open(state_path, "r", encoding="utf-8") as file:
                state = json.load(file)
            if state.get("schema_version") != SUPPORTED_RUN_SCHEMA_VERSION:
                continue
            finished = datetime.fromisoformat(state.get("finished_at", ""))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if not start.date() <= finished.date() <= end.date():
            continue
        if bool(state.get("mock")) != mock:
            continue
        if not mock and state.get("runtime") != runtime:
            continue
        state["_run_name"] = entry.name
        loaded.append(state)
    return sorted(loaded, key=lambda item: item.get("finished_at", ""))


def _aggregate_runs(
    runs: list[dict[str, Any]],
    since: str,
    until: str,
    mock: bool,
) -> dict[str, Any]:
    successful = [run for run in runs if int(run.get("error_count", 0)) == 0]
    failed = [run for run in runs if int(run.get("error_count", 0)) > 0]
    triggers = [_run_trigger(run) for run in runs]
    trigger = max(triggers, key=lambda value: TRIGGER_ORDER.get(value, 0)) if triggers else "CRITICAL"
    risks = []
    human_items = []
    next_actions = []
    conclusions = []
    run_rows = []

    for run in runs:
        review = run.get("agent_outputs", {}).get("review_agent", {})
        if review.get("conclusion"):
            conclusions.append(f"{run['_run_name']}: {review['conclusion']}")
        for item in review.get("key_risks", []):
            _append_unique(risks, str(item))
        for item in run.get("errors", []):
            _append_unique(risks, f"{run['_run_name']}: {item}")
        for item in review.get("human_confirmation_needed", []):
            _append_unique(human_items, str(item))
        for item in review.get("next_actions", []):
            _append_unique(next_actions, str(item))
        source = run.get("source_provenance", {})
        if source.get("release_ready") is not True:
            _append_unique(
                risks,
                f"{run['_run_name']}: 源码版本门禁未通过 ({source.get('reason', 'source provenance missing')})",
            )
            _append_unique(human_items, "平台负责人确认所有源 Run 均来自 clean commit/tag")
            _append_unique(next_actions, "从受控源码基线重新生成不合格的源 Run")
        run_rows.append(
            {
                "run": run["_run_name"],
                "runtime": run.get("runtime", "unknown"),
                "mode": "MOCK" if run.get("mock") else "REAL",
                "data_mode": run.get("data_mode", "UNKNOWN"),
                "agents": f"{run.get('success_count', 0)}/{run.get('total_agents', 0)}",
                "trigger": _run_trigger(run),
                "source": (source.get("head_commit") or "UNVERSIONED")[:12],
            }
        )

    if not runs:
        conclusions = ["本周期没有符合模式和运行时条件的研究轮次，无法形成有效周报结论。"]
        risks = ["缺少可审计的源研究运行"]
        human_items = ["确认周报日期、运行模式和源研究任务是否正确"]
        next_actions = ["先完成至少一轮合格研究流水线，再重新生成周报"]
    elif failed:
        _append_unique(human_items, "确认本周期所有失败运行已闭环处理")
        _append_unique(next_actions, "修复失败运行并重新执行对应研究轮次")

    return {
        "report_type": "weekly_aggregate",
        "period": {"since": since, "until": until},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "MOCK" if mock else "REAL",
        "source_run_count": len(runs),
        "successful_run_count": len(successful),
        "failed_run_count": len(failed),
        "trigger_level": trigger,
        "key_conclusions": conclusions[-10:],
        "key_risks": risks[:20],
        "human_confirmation_needed": human_items[:20],
        "next_actions": next_actions[:20],
        "source_runs": run_rows[-20:],
        "disclaimer": "本周报仅聚合离线研究运行，不构成任何真实资金买卖建议。",
    }


def _run_trigger(run: dict[str, Any]) -> str:
    if run.get("errors") or run.get("source_provenance", {}).get("release_ready") is not True:
        return "CRITICAL"
    review = run.get("agent_outputs", {}).get("review_agent", {})
    value = str(review.get("trigger_level", "UNKNOWN")).upper()
    return value if value in TRIGGER_ORDER else "UNKNOWN"


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _render_weekly_markdown(report: dict[str, Any]) -> str:
    period = report["period"]
    lines = [
        "# CSI 500 量化研究周报",
        "",
        f"**周期**: {period['since']} ~ {period['until']}",
        f"**生成时间**: {report['generated_at']}",
        f"**模式**: {report['mode']}",
        f"**源运行**: {report['source_run_count']}（成功 {report['successful_run_count']} / 失败 {report['failed_run_count']}）",
        f"**研究流程触发等级**: {report['trigger_level']}",
        "",
        "## 关键结论",
        "",
    ]
    lines.extend(f"- {item}" for item in report["key_conclusions"])
    lines.extend(["", "## 主要风险", ""])
    lines.extend(f"- {item}" for item in report["key_risks"])
    lines.extend(["", "## 需要人工确认的问题", ""])
    lines.extend(f"- [ ] {item}" for item in report["human_confirmation_needed"])
    lines.extend(["", "## 下一步动作", ""])
    lines.extend(f"- {item}" for item in report["next_actions"])
    lines.extend(
        [
            "",
            "## 源运行",
            "",
            "| Run | Runtime | Mode | Data | Agents | Source | Trigger |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in report["source_runs"]:
        lines.append(
            f"| {row['run']} | {row['runtime']} | {row['mode']} | "
            f"{row['data_mode']} | {row['agents']} | {row['source']} | {row['trigger']} |"
        )
    lines.extend(["", "---", "", f"> {report['disclaimer']}", ""])
    return "\n".join(lines)
