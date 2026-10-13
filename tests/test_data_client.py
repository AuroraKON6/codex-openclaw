import json
import os
import tempfile
import unittest

from quant_agents.config import Config
from quant_agents.data_client import DataClient


class FakeFrame:
    def __init__(self, records):
        self.records = records
        self.empty = not records

    def to_json(self, **kwargs):
        return json.dumps(self.records)


class FakePro:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = 0

    def daily(self, **params):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary provider failure")
        return FakeFrame(
            [
                {
                    "ts_code": params["ts_code"],
                    "trade_date": "20250102",
                    "close": 10.0,
                    "pct_chg": 1.0,
                }
            ]
        )


class DataClientTests(unittest.TestCase):
    def test_retries_then_uses_cache(self):
        old_retries = Config.TUSHARE_MAX_RETRIES
        old_delay = Config.TUSHARE_RETRY_BASE_SECONDS
        old_ttl = Config.TUSHARE_CACHE_TTL_HOURS
        try:
            Config.TUSHARE_MAX_RETRIES = 3
            Config.TUSHARE_RETRY_BASE_SECONDS = 0
            Config.TUSHARE_CACHE_TTL_HOURS = 24
            with tempfile.TemporaryDirectory() as directory:
                provider = FakePro(failures=2)
                client = DataClient(pro=provider, cache_dir=directory, sleep_fn=lambda _: None)
                first = client.get_daily("TEST.SZ", "20250101", "20250131")
                self.assertEqual(provider.calls, 3)
                self.assertEqual(first[0]["ts_code"], "TEST.SZ")

                second_provider = FakePro()
                cached_client = DataClient(
                    pro=second_provider,
                    cache_dir=directory,
                    sleep_fn=lambda _: None,
                )
                second = cached_client.get_daily("TEST.SZ", "20250101", "20250131")
                self.assertEqual(second_provider.calls, 0)
                self.assertEqual(second, first)
                self.assertTrue(cached_client.request_log[0]["cache_hit"])
        finally:
            Config.TUSHARE_MAX_RETRIES = old_retries
            Config.TUSHARE_RETRY_BASE_SECONDS = old_delay
            Config.TUSHARE_CACHE_TTL_HOURS = old_ttl


if __name__ == "__main__":
    unittest.main()
