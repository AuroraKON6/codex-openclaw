import unittest
from unittest.mock import patch

from quant_agents.config import Config


class ConfigTests(unittest.TestCase):
    def test_real_runtime_rejects_stale_pricing_baseline(self):
        with patch.object(Config, "DEEPSEEK_API_KEY", "test-key"), patch.object(
            Config, "DEEPSEEK_PRICING_REVIEWED_DATE", "2000-01-01"
        ):
            errors = Config.validate(require_deepseek=True, require_tushare=False)
        self.assertTrue(any("pricing baseline is stale" in error for error in errors))

    def test_budget_contingency_multiplier_is_bounded(self):
        with patch.object(Config, "DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER", 1.9):
            errors = Config.validate(require_deepseek=False, require_tushare=False)
        self.assertTrue(any("CONTINGENCY_MULTIPLIER" in error for error in errors))

    def test_real_runtime_rejects_unapproved_price_drift(self):
        with patch.object(Config, "DEEPSEEK_API_KEY", "test-key"), patch.object(
            Config, "DEEPSEEK_OUTPUT_USD_PER_M", 0.87
        ):
            errors = Config.validate(require_deepseek=True, require_tushare=False)
        self.assertTrue(any("approved 2026-08-25" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
