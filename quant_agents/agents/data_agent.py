from __future__ import annotations
import json
import os
import statistics
from typing import Any

from ..audit import build_file_manifest, write_json_atomic
from ..base_agent import BaseAgent, save_raw, save_agent_json
from ..data_client import DataClient


class DataAgent(BaseAgent):
    name = "data_agent"
    description = "Fetches and processes A-share market data from Tushare Pro"
    system_prompt = """You are a data processing specialist for A-share quantitative research.
Given raw market data and index constituent data, produce a structured summary.

You MUST output valid JSON:
{
  "universe_size": number,
  "sample_stocks": [{"ts_code": "string", "weight": number}],
  "market_stats": {
    "avg_pe": number,
    "avg_pb": number,
    "avg_turnover": number,
    "up_count": number,
    "down_count": number
  },
  "data_quality": "string - GOOD/PARTIAL/POOR",
  "notes": ["string"]
}

The Python orchestrator supplies authoritative measured values. Copy those values exactly.
If data is insufficient, say so in notes. Do NOT fabricate data or answer with readiness text."""

    def build_prompt(self, context: dict[str, Any]) -> str:
        summary = context.get("_authoritative_data_summary", {})
        return f"""Complete the data-quality review for this saved CSI 500 Tushare snapshot.

Authoritative measured JSON (copy all numeric values exactly):
{json.dumps(summary, ensure_ascii=False, default=str)}

Return the required final JSON object now. Notes may explain limitations, but must not change measured values."""

    def execute_pi(self, context: dict[str, Any]) -> dict[str, Any]:
        summary = self._prepare_data(context)
        prompt_context = dict(context)
        prompt_context["_authoritative_data_summary"] = summary
        data = super().execute_pi(prompt_context)
        data = self._enforce_authoritative_values(data, summary)
        save_agent_json(context["output_dir"], self.name, data)
        return data

    def _prepare_data(self, context: dict[str, Any]) -> dict[str, Any]:
        date_range = context.get("date_range", {})
        start_date = str(date_range.get("since", "")).replace("-", "")
        end_date = str(date_range.get("until", "")).replace("-", "")
        if not start_date or not end_date:
            raise RuntimeError("date_range.since and date_range.until are required")

        strategy_params = context.get("input", {}).get("strategy_params", {})
        max_positions = int(strategy_params.get("max_positions", 20))
        research_universe_size = int(
            strategy_params.get("research_universe_size", max(30, max_positions * 2))
        )
        data_client = DataClient()
        dataset = data_client.collect_csi500_research_data(
            start_date=start_date,
            end_date=end_date,
            research_universe_size=research_universe_size,
            lookback_trade_days=int(strategy_params.get("lookback_trade_days", 20)),
        )
        market_dir = os.path.join(context["output_dir"], "market_data")
        os.makedirs(market_dir, exist_ok=True)
        record_files = {
            "prices.json": dataset["prices"],
            "constituents.json": dataset["constituents"],
            "research_membership.json": dataset["research_membership"],
            "daily_basic.json": dataset["daily_basic"],
            "limits.json": dataset["limits"],
            "suspensions.json": dataset["suspensions"],
            "adjustment_factors.json": dataset["adjustment_factors"],
            "data_requests.json": dataset["request_log"],
        }
        for filename, records in record_files.items():
            write_json_atomic(
                os.path.join(market_dir, filename),
                {"records": records},
            )

        market_stats = {
            "avg_pe": _average(item.get("pe") for item in dataset["sample_stocks"]),
            "avg_pb": _average(item.get("pb") for item in dataset["sample_stocks"]),
            "avg_turnover": _average(
                item.get("turnover_rate") for item in dataset["sample_stocks"]
            ),
            "up_count": sum(
                1 for item in dataset["sample_stocks"] if (item.get("pct_chg") or 0) > 0
            ),
            "down_count": sum(
                1 for item in dataset["sample_stocks"] if (item.get("pct_chg") or 0) < 0
            ),
            "flat_or_missing_count": sum(
                1 for item in dataset["sample_stocks"] if (item.get("pct_chg") or 0) == 0
            ),
            "latest_trade_date": dataset["actual_end"],
            "expected_latest_trade_date": dataset["expected_latest_trade_date"],
            "freshness_lag_trade_days": dataset["freshness_lag_trade_days"],
        }
        notes = [
            f"Constituents use {dataset['constituent_snapshot_count']} monthly point-in-time index_weight snapshots.",
            f"Price coverage is {dataset['successful_price_codes']}/{dataset['selected_universe_size']} selected securities.",
            f"Limit-price coverage is {dataset['successful_limit_codes']}/{dataset['selected_universe_size']} selected securities.",
            "Raw Tushare responses used by downstream calculations are saved under market_data/.",
        ]
        notes.extend(dataset["errors"][-5:])
        summary = {
            "universe_size": dataset["universe_size"],
            "sample_stocks": dataset["sample_stocks"][:20],
            "market_stats": market_stats,
            "data_quality": dataset["data_quality"],
            "notes": notes,
            "data_mode": "REAL_TUSHARE",
            "coverage": {
                "selected_universe_size": dataset["selected_universe_size"],
                "successful_price_codes": dataset["successful_price_codes"],
                "trade_date_count": dataset["trade_date_count"],
                "coverage_ratio": dataset["coverage_ratio"],
                "limit_coverage_ratio": dataset["limit_coverage_ratio"],
                "requested_start": dataset["requested_start"],
                "requested_end": dataset["requested_end"],
                "fetch_start": dataset["fetch_start"],
                "actual_start": dataset["actual_start"],
                "actual_end": dataset["actual_end"],
                "expected_latest_trade_date": dataset["expected_latest_trade_date"],
                "freshness_lag_trade_days": dataset["freshness_lag_trade_days"],
                "constituent_as_of": dataset["constituent_as_of"],
                "constituent_snapshot_count": dataset["constituent_snapshot_count"],
            },
            "data_files": {
                "prices": "market_data/prices.json",
                "constituents": "market_data/constituents.json",
                "research_membership": "market_data/research_membership.json",
                "daily_basic": "market_data/daily_basic.json",
                "limits": "market_data/limits.json",
                "suspensions": "market_data/suspensions.json",
                "adjustment_factors": "market_data/adjustment_factors.json",
                "data_requests": "market_data/data_requests.json",
            },
            "point_in_time_membership": True,
        }
        write_json_atomic(os.path.join(market_dir, "manifest.json"), summary)
        snapshot_manifest = build_file_manifest(
            market_dir,
            list(record_files),
            metadata={
                "provider": "Tushare Pro",
                "index_code": dataset["index_code"],
                "requested_start": start_date,
                "requested_end": end_date,
                "fetch_start": dataset["fetch_start"],
                "point_in_time_membership": True,
                "row_counts": {name: len(records) for name, records in record_files.items()},
            },
        )
        write_json_atomic(
            os.path.join(market_dir, "snapshot_manifest.json"),
            snapshot_manifest,
        )
        summary["snapshot_id"] = snapshot_manifest["snapshot_id"]
        summary["data_files"]["snapshot_manifest"] = "market_data/snapshot_manifest.json"
        write_json_atomic(os.path.join(market_dir, "manifest.json"), summary)

        minimum_quality = str(
            context.get("input", {}).get("data_controls", {}).get(
                "minimum_data_quality", "GOOD"
            )
        ).upper()
        quality_rank = {"POOR": 0, "PARTIAL": 1, "GOOD": 2}
        if quality_rank.get(dataset["data_quality"], -1) < quality_rank.get(
            minimum_quality, 2
        ):
            raise RuntimeError(
                f"data quality gate failed: {dataset['data_quality']} < {minimum_quality}; "
                f"snapshot_id={snapshot_manifest['snapshot_id']}"
            )
        max_staleness = int(
            context.get("input", {}).get("data_controls", {}).get(
                "max_staleness_trade_days", 0
            )
        )
        if dataset["freshness_lag_trade_days"] > max_staleness:
            raise RuntimeError(
                "data freshness gate failed: "
                f"actual_end={dataset['actual_end']}, "
                f"expected_end={dataset['expected_latest_trade_date']}, "
                f"lag={dataset['freshness_lag_trade_days']} trade days, "
                f"allowed={max_staleness}; snapshot_id={snapshot_manifest['snapshot_id']}"
            )
        return summary

    @staticmethod
    def _enforce_authoritative_values(data: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
        data.update(summary)
        return data

    def mock_execute(self, context: dict[str, Any]) -> dict[str, Any]:
        data = {
            "universe_size": 500,
            "sample_stocks": [
                {"ts_code": "000001.SZ", "weight": 0.45},
                {"ts_code": "000002.SZ", "weight": 0.38},
                {"ts_code": "000009.SZ", "weight": 0.32},
            ],
            "market_stats": {"avg_pe": 22.5, "avg_pb": 1.8, "avg_turnover": 1.2, "up_count": 280, "down_count": 220},
            "data_quality": "MOCK",
            "notes": ["MOCK: synthetic data; no Tushare request was made."],
            "data_mode": "MOCK",
            "coverage": {"coverage_ratio": 0.0, "trade_date_count": 0},
            "data_files": {},
        }
        save_raw(context["output_dir"], self.name, json.dumps(data, ensure_ascii=False, indent=2))
        save_agent_json(context["output_dir"], self.name, data)
        return data


def _average(values) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(statistics.fmean(numbers), 6) if numbers else None
