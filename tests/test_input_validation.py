import copy
import unittest

from quant_agents.input_validation import validate_research_input


def valid_input():
    return {
        "scope": "CSI500",
        "governance": {
            "intended_use": "licensed_internal_research",
            "data_provider": "tushare",
            "external_distribution_requested": False,
            "human_review_required": True,
        },
        "date_range": {"since": "20250101", "until": "20250530"},
        "strategy_params": {
            "factors": ["momentum"],
            "max_positions": 10,
            "research_universe_size": 30,
        },
        "data_controls": {
            "minimum_data_quality": "GOOD",
            "max_staleness_trade_days": 0,
        },
        "execution_controls": {
            "require_tradeability_data": True,
            "minimum_daily_amount_cny": 50_000_000,
            "simulation_notional_cny": 10_000_000,
            "max_participation_rate": 0.05,
            "execution_price_policy": "prior_close_after_signal_lag",
            "price_limit_fill_policy": "directional_close_conservative",
            "order_time_in_force": "DAY",
            "unfilled_order_policy": "cancel_at_session_end_recompute_next_rebalance",
            "round_lot_enforced": True,
            "t_plus_one_enforced": True,
            "cost_model": {
                "model_id": "test-cost-v1",
                "broker_commission_quote_mode": "all_in_regulatory",
                "broker_commission_rate": 0.00025,
                "minimum_commission_cny": 5,
                "slippage_bps": 5,
                "market_impact_bps": 2,
                "cost_assumption_source": "unit-test conservative assumption",
            },
        },
        "validation_controls": {
            "hypothesis_id": "test-momentum-v1",
            "parameter_selection_policy": "pre_registered_no_search",
            "parameter_search_count": 0,
            "holdout_fraction": 0.3,
            "minimum_holdout_trade_days": 20,
            "cost_stress_multipliers": [1.5, 2.0],
            "signal_delay_stress_trade_days": [2],
            "walk_forward": {
                "fold_count": 3,
                "fold_trade_days": 20,
                "minimum_development_trade_days": 20,
                "minimum_passing_folds": 2,
            },
            "acceptance_thresholds": {
                "minimum_holdout_trade_count": 2,
                "minimum_holdout_sharpe": -0.5,
                "maximum_holdout_drawdown": -0.25,
                "minimum_double_cost_total_return": -0.25,
            },
        },
    }


class InputValidationTests(unittest.TestCase):
    def test_accepts_production_research_input(self):
        validate_research_input(valid_input())

    def test_rejects_unsupported_factor(self):
        payload = valid_input()
        payload["strategy_params"]["factors"] = ["quality"]
        with self.assertRaises(ValueError):
            validate_research_input(payload)

    def test_rejects_disabled_tradeability_gate(self):
        payload = valid_input()
        payload["execution_controls"]["require_tradeability_data"] = False
        with self.assertRaises(ValueError):
            validate_research_input(payload)

    def test_rejects_legacy_flat_transaction_cost(self):
        payload = valid_input()
        payload["strategy_params"]["transaction_cost_rate"] = 0.001
        with self.assertRaisesRegex(ValueError, "prohibited legacy flat-cost"):
            validate_research_input(payload)

    def test_rejects_commission_below_embedded_regulatory_floor(self):
        payload = valid_input()
        payload["execution_controls"]["cost_model"]["broker_commission_rate"] = 0.00001
        with self.assertRaisesRegex(ValueError, "below the effective exchange"):
            validate_research_input(payload)

    def test_rejects_parameter_search_in_preregistered_pipeline(self):
        payload = valid_input()
        payload["validation_controls"]["parameter_search_count"] = 1
        with self.assertRaisesRegex(ValueError, "parameter_search_count"):
            validate_research_input(payload)

    def test_rejects_stress_matrix_without_double_cost(self):
        payload = valid_input()
        payload["validation_controls"]["cost_stress_multipliers"] = [1.5]
        with self.assertRaisesRegex(ValueError, "include 2.0"):
            validate_research_input(payload)

    def test_rejects_weak_walk_forward_pass_requirement(self):
        payload = valid_input()
        payload["validation_controls"]["walk_forward"]["minimum_passing_folds"] = 1
        with self.assertRaisesRegex(ValueError, "at least two-thirds"):
            validate_research_input(payload)


if __name__ == "__main__":
    unittest.main()
