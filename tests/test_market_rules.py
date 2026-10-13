import unittest

from quant_agents.market_rules import (
    board_rule,
    build_policy_snapshot,
    calculate_trade_cost,
    load_market_rulebook,
    policy_for_date,
    quantize_order_shares,
)


COST_MODEL = {
    "model_id": "test-cost-v1",
    "broker_commission_quote_mode": "all_in_regulatory",
    "broker_commission_rate": 0.00025,
    "minimum_commission_cny": 5,
    "slippage_bps": 5,
    "market_impact_bps": 2,
    "cost_assumption_source": "unit-test conservative assumption",
}


class MarketRuleTests(unittest.TestCase):
    def test_effective_policy_switches_on_20260706(self):
        rulebook, digest = load_market_rulebook()
        self.assertEqual(len(digest), 64)
        self.assertEqual(
            policy_for_date(rulebook, "20260705")["policy_id"],
            "cn-a-share-2023-08-28",
        )
        self.assertEqual(
            policy_for_date(rulebook, "20260706")["policy_id"],
            "cn-a-share-2026-07-06",
        )
        snapshot = build_policy_snapshot("20260701", "20260710", COST_MODEL)
        self.assertEqual(len(snapshot["policy_ids"]), 2)

    def test_main_and_star_order_quantization(self):
        rulebook, _ = load_market_rulebook()
        policy = policy_for_date(rulebook, "20260801")
        main = board_rule(policy, "600000.SH")
        star = board_rule(policy, "688001.SH")
        self.assertEqual(quantize_order_shares(275, main)["executed_shares"], 200)
        self.assertEqual(quantize_order_shares(275, star)["executed_shares"], 275)
        self.assertEqual(quantize_order_shares(199, star)["executed_shares"], 0)

    def test_stamp_duty_is_sell_side_only_and_regulatory_fees_are_not_double_counted(self):
        rulebook, _ = load_market_rulebook()
        policy = policy_for_date(rulebook, "20260801")
        buy = calculate_trade_cost(100_000, "B", 1, policy, COST_MODEL)
        sell = calculate_trade_cost(100_000, "S", 1, policy, COST_MODEL)
        self.assertEqual(buy["stamp_duty_cny"], 0)
        self.assertEqual(sell["stamp_duty_cny"], 50)
        self.assertAlmostEqual(
            buy["broker_net_commission_cny"]
            + buy["exchange_handling_fee_cny"]
            + buy["regulatory_fee_cny"],
            25,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
