from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .audit import canonical_json_sha256, write_json_atomic
from .config import Config

_TUSHARE_INSTALLED = False
try:
    import tushare as ts

    _TUSHARE_INSTALLED = True
except ImportError:
    ts = None


class DataClient:
    def __init__(
        self,
        pro: Any | None = None,
        cache_dir: str | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.token = Config.TUSHARE_TOKEN
        self._pro = pro
        if self._pro is None and _TUSHARE_INSTALLED and self.token:
            ts.set_token(self.token)
            self._pro = ts.pro_api()
        self.cache_dir = os.path.abspath(cache_dir or Config.TUSHARE_CACHE_DIR)
        self.sleep_fn = sleep_fn
        self.errors: list[str] = []
        self.request_log: list[dict[str, Any]] = []

    def available(self) -> bool:
        if self._pro is not None:
            return True
        return _TUSHARE_INSTALLED and bool(self.token)

    def health(self) -> dict[str, Any]:
        if not self.available():
            return {
                "tushare_installed": _TUSHARE_INSTALLED,
                "token_set": bool(self.token),
                "ok": False,
                "error": "Tushare not available",
            }
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=14)).strftime("%Y%m%d")
        rows = self._query_records(
            "trade_cal",
            {
                "exchange": "SSE",
                "start_date": start_date,
                "end_date": end_date,
                "is_open": "1",
            },
            use_cache=False,
        )
        return {
            "tushare_installed": _TUSHARE_INSTALLED,
            "token_set": bool(self.token),
            "ok": bool(rows),
            "test_rows": len(rows),
            "error": self.errors[-1] if not rows and self.errors else None,
        }

    def get_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        rows = self._query_records(
            "trade_cal",
            {
                "exchange": "SSE",
                "start_date": start_date,
                "end_date": end_date,
                "is_open": "1",
                "fields": "cal_date,is_open",
            },
        )
        return sorted(str(row["cal_date"]) for row in rows if row.get("cal_date"))

    def get_csi500_constituent_history(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        records = []
        for month_start, month_end in _month_windows(start_date, end_date):
            rows = self._query_records(
                "index_weight",
                {
                    "index_code": Config.TUSHARE_INDEX_CODE,
                    "start_date": month_start,
                    "end_date": month_end,
                },
            )
            records.extend(rows)
        deduplicated = {}
        for row in records:
            trade_date = str(row.get("trade_date", ""))
            code = str(row.get("con_code", ""))
            if trade_date and code:
                deduplicated[(trade_date, code)] = {
                    "index_code": str(row.get("index_code") or Config.TUSHARE_INDEX_CODE),
                    "trade_date": trade_date,
                    "ts_code": code,
                    "weight": _number_or_none(row.get("weight")),
                }
        return sorted(deduplicated.values(), key=lambda row: (row["trade_date"], row["ts_code"]))

    def get_csi500_stocks(self, date: str) -> list[dict[str, Any]]:
        end = datetime.strptime(date, "%Y%m%d")
        start_date = (end - timedelta(days=120)).strftime("%Y%m%d")
        history = self.get_csi500_constituent_history(start_date, date)
        if not history:
            return []
        latest_date = max(row["trade_date"] for row in history)
        latest = [row for row in history if row["trade_date"] == latest_date]
        return sorted(latest, key=lambda row: row.get("weight") or 0.0, reverse=True)

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        rows = self._query_records(
            "daily",
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
        )
        return [_compact_daily({**row, "ts_code": row.get("ts_code") or ts_code}) for row in rows]

    def get_adj_factor(self, ts_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        return self._query_records(
            "adj_factor",
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
        )

    def get_stk_limit(self, ts_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        return self._query_records(
            "stk_limit",
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
        )

    def get_suspend_d(self, ts_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        return self._query_records(
            "suspend_d",
            {
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
                "suspend_type": "S",
            },
        )

    def get_daily_basic_snapshot(self, trade_date: str, codes: set[str]) -> list[dict[str, Any]]:
        rows = self._query_records(
            "daily_basic",
            {
                "trade_date": trade_date,
                "fields": "ts_code,trade_date,turnover_rate,pe,pb,total_mv,circ_mv",
            },
        )
        return [row for row in rows if row.get("ts_code") in codes]

    def collect_csi500_research_data(
        self,
        start_date: str,
        end_date: str,
        research_universe_size: int = 40,
        lookback_trade_days: int = 20,
    ) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("Tushare is unavailable; real mode requires TUSHARE_TOKEN")

        warmup_days = max(60, lookback_trade_days * 3)
        fetch_start = (
            datetime.strptime(start_date, "%Y%m%d") - timedelta(days=warmup_days)
        ).strftime("%Y%m%d")
        constituent_history = self.get_csi500_constituent_history(fetch_start, end_date)
        if not constituent_history:
            detail = "; ".join(self.errors[-3:]) or "no monthly index_weight rows returned"
            raise RuntimeError(f"CSI 500 constituent history unavailable: {detail}")

        research_membership = _select_research_membership(
            constituent_history,
            max(10, min(research_universe_size, 60)),
        )
        selected_codes = sorted({row["ts_code"] for row in research_membership})
        if len(selected_codes) > Config.TUSHARE_MAX_RESEARCH_SECURITIES:
            raise RuntimeError(
                f"point-in-time universe expands to {len(selected_codes)} securities, above "
                f"TUSHARE_MAX_RESEARCH_SECURITIES={Config.TUSHARE_MAX_RESEARCH_SECURITIES}; "
                "reduce date range or research_universe_size"
            )

        prices: list[dict[str, Any]] = []
        limits: list[dict[str, Any]] = []
        suspensions: list[dict[str, Any]] = []
        adjustment_factors: list[dict[str, Any]] = []
        successful_price_codes: set[str] = set()
        successful_limit_codes: set[str] = set()
        for code in selected_codes:
            code_prices = self.get_daily(code, fetch_start, end_date)
            code_factors = self.get_adj_factor(code, fetch_start, end_date)
            code_limits = self.get_stk_limit(code, fetch_start, end_date)
            code_suspensions = self.get_suspend_d(code, fetch_start, end_date)
            if code_prices:
                successful_price_codes.add(code)
                prices.extend(code_prices)
            if code_limits:
                successful_limit_codes.add(code)
                limits.extend(_compact_limits(row) for row in code_limits)
            suspensions.extend(_compact_suspension(row) for row in code_suspensions)
            adjustment_factors.extend(_compact_factor(row) for row in code_factors)

        if not prices:
            detail = "; ".join(self.errors[-5:]) or "no daily rows returned"
            raise RuntimeError(f"CSI 500 daily data unavailable: {detail}")

        prices = _attach_adjustment_factors(prices, adjustment_factors)
        trade_dates = sorted({str(row["trade_date"]) for row in prices if row.get("trade_date")})
        latest_trade_date = trade_dates[-1]
        expected_window_start = (
            datetime.strptime(end_date, "%Y%m%d") - timedelta(days=31)
        ).strftime("%Y%m%d")
        expected_trade_dates = self.get_trade_dates(expected_window_start, end_date)
        if not expected_trade_dates:
            detail = "; ".join(self.errors[-3:]) or "no trading-calendar rows returned"
            raise RuntimeError(f"trading calendar unavailable for freshness gate: {detail}")
        expected_latest_trade_date = expected_trade_dates[-1]
        freshness_lag_trade_days = sum(
            1 for value in expected_trade_dates if value > latest_trade_date
        )
        basics = self.get_daily_basic_snapshot(latest_trade_date, successful_price_codes)
        latest_snapshot_date = max(row["trade_date"] for row in constituent_history)
        latest_constituents = [
            row for row in constituent_history if row["trade_date"] == latest_snapshot_date
        ]
        latest_research_members = [
            row for row in research_membership if row["trade_date"] == latest_snapshot_date
        ]
        latest_prices = {
            row["ts_code"]: row
            for row in prices
            if str(row.get("trade_date")) == latest_trade_date and row.get("ts_code")
        }
        basic_map = {row["ts_code"]: row for row in basics if row.get("ts_code")}
        sample_stocks = []
        for item in latest_research_members:
            code = item["ts_code"]
            if code not in successful_price_codes:
                continue
            latest = latest_prices.get(code, {})
            basic = basic_map.get(code, {})
            sample_stocks.append(
                {
                    "ts_code": code,
                    "weight": item.get("weight"),
                    "pct_chg": _number_or_none(latest.get("pct_chg")),
                    "pe": _number_or_none(basic.get("pe")),
                    "pb": _number_or_none(basic.get("pb")),
                    "turnover_rate": _number_or_none(basic.get("turnover_rate")),
                }
            )

        price_coverage = len(successful_price_codes) / len(selected_codes)
        limit_coverage = len(successful_limit_codes) / len(selected_codes)
        if price_coverage >= 0.9 and limit_coverage >= 0.9 and len(trade_dates) >= 40:
            quality = "GOOD"
        elif price_coverage >= 0.7 and limit_coverage >= 0.7 and len(trade_dates) >= 20:
            quality = "PARTIAL"
        else:
            quality = "POOR"

        return {
            "index_code": Config.TUSHARE_INDEX_CODE,
            "constituent_as_of": latest_snapshot_date,
            "requested_start": start_date,
            "requested_end": end_date,
            "fetch_start": fetch_start,
            "actual_start": trade_dates[0],
            "actual_end": latest_trade_date,
            "expected_latest_trade_date": expected_latest_trade_date,
            "freshness_lag_trade_days": freshness_lag_trade_days,
            "universe_size": len(latest_constituents),
            "constituent_snapshot_count": len(
                {row["trade_date"] for row in constituent_history}
            ),
            "selected_universe_size": len(selected_codes),
            "successful_price_codes": len(successful_price_codes),
            "successful_limit_codes": len(successful_limit_codes),
            "trade_date_count": len(trade_dates),
            "coverage_ratio": round(price_coverage, 4),
            "limit_coverage_ratio": round(limit_coverage, 4),
            "data_quality": quality,
            "constituents": constituent_history,
            "research_membership": research_membership,
            "sample_stocks": sample_stocks,
            "prices": prices,
            "daily_basic": basics,
            "limits": limits,
            "suspensions": suspensions,
            "adjustment_factors": adjustment_factors,
            "request_log": self.request_log.copy(),
            "errors": self.errors.copy(),
        }

    def _query_records(
        self,
        endpoint: str,
        params: dict[str, Any],
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        if not self.available():
            self.errors.append(f"{endpoint}: Tushare unavailable")
            return []
        cache_key = canonical_json_sha256({"endpoint": endpoint, "params": params})
        cache_path = os.path.join(self.cache_dir, endpoint, f"{cache_key}.json")
        if use_cache:
            cached = self._read_cache(cache_path)
            if cached is not None:
                self.request_log.append(
                    {
                        "endpoint": endpoint,
                        "params": params,
                        "cache_hit": True,
                        "rows": len(cached),
                        "attempts": 0,
                    }
                )
                return cached

        last_error = None
        started = time.time()
        for attempt in range(1, max(1, Config.TUSHARE_MAX_RETRIES) + 1):
            try:
                frame = getattr(self._pro, endpoint)(**params)
                records = [] if frame is None or frame.empty else _records(frame)
                if use_cache:
                    write_json_atomic(
                        cache_path,
                        {
                            "schema_version": 1,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "endpoint": endpoint,
                            "params": params,
                            "records": records,
                        },
                    )
                self.request_log.append(
                    {
                        "endpoint": endpoint,
                        "params": params,
                        "cache_hit": False,
                        "rows": len(records),
                        "attempts": attempt,
                        "elapsed_s": round(time.time() - started, 3),
                    }
                )
                return records
            except Exception as exc:
                last_error = exc
                if attempt < max(1, Config.TUSHARE_MAX_RETRIES):
                    self.sleep_fn(Config.TUSHARE_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
        message = f"{endpoint} failed after {Config.TUSHARE_MAX_RETRIES} attempts: {last_error}"
        self.errors.append(message)
        self.request_log.append(
            {
                "endpoint": endpoint,
                "params": params,
                "cache_hit": False,
                "rows": 0,
                "attempts": max(1, Config.TUSHARE_MAX_RETRIES),
                "elapsed_s": round(time.time() - started, 3),
                "error": str(last_error),
            }
        )
        return []

    def _read_cache(self, path: str) -> list[dict[str, Any]] | None:
        if not os.path.isfile(path):
            return None
        age_hours = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_hours > max(0, Config.TUSHARE_CACHE_TTL_HOURS):
            return None
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            records = payload.get("records")
            return records if isinstance(records, list) else None
        except (OSError, json.JSONDecodeError):
            return None


def _month_windows(start_date: str, end_date: str) -> list[tuple[str, str]]:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    cursor = start.replace(day=1)
    windows = []
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        windows.append(
            (
                max(start, cursor).strftime("%Y%m%d"),
                min(end, month_end).strftime("%Y%m%d"),
            )
        )
        cursor = next_month
    return windows


def _select_research_membership(
    history: list[dict[str, Any]],
    size_per_snapshot: int,
) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in history:
        by_date.setdefault(row["trade_date"], []).append(row)
    selected = []
    for trade_date in sorted(by_date):
        ranked = sorted(
            by_date[trade_date],
            key=lambda row: row.get("weight") or 0.0,
            reverse=True,
        )
        selected.extend(ranked[:size_per_snapshot])
    return selected


def _attach_adjustment_factors(
    prices: list[dict[str, Any]],
    factors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    factor_map = {
        (str(row.get("ts_code")), str(row.get("trade_date"))): _number_or_none(
            row.get("adj_factor")
        )
        for row in factors
    }
    latest_by_code: dict[str, tuple[str, float]] = {}
    for row in factors:
        code = str(row.get("ts_code", ""))
        trade_date = str(row.get("trade_date", ""))
        factor = _number_or_none(row.get("adj_factor"))
        if code and trade_date and factor is not None:
            current = latest_by_code.get(code)
            if current is None or trade_date > current[0]:
                latest_by_code[code] = (trade_date, factor)
    result = []
    for row in prices:
        code = str(row.get("ts_code", ""))
        factor = factor_map.get((code, str(row.get("trade_date"))))
        close = _number_or_none(row.get("close"))
        latest = latest_by_code.get(code)
        latest_factor = latest[1] if latest else None
        enriched = dict(row)
        enriched["adj_factor"] = factor
        enriched["qfq_close"] = (
            round(close * factor / latest_factor, 6)
            if close is not None and factor is not None and latest_factor
            else None
        )
        result.append(enriched)
    return result


def _records(frame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", force_ascii=False, date_format="iso"))


def _compact_daily(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "pct_chg",
        "vol",
        "amount",
    )
    return {field: row.get(field) for field in fields}


def _compact_limits(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts_code": row.get("ts_code"),
        "trade_date": str(row.get("trade_date", "")),
        "up_limit": _number_or_none(row.get("up_limit")),
        "down_limit": _number_or_none(row.get("down_limit")),
    }


def _compact_suspension(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts_code": row.get("ts_code"),
        "trade_date": str(row.get("trade_date", "")),
        "suspend_type": row.get("suspend_type"),
        "suspend_timing": row.get("suspend_timing"),
    }


def _compact_factor(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts_code": row.get("ts_code"),
        "trade_date": str(row.get("trade_date", "")),
        "adj_factor": _number_or_none(row.get("adj_factor")),
    }


def _number_or_none(value: Any) -> float | None:
    try:
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else round(number, 6)
    except (TypeError, ValueError):
        return None
