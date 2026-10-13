from datetime import datetime, timedelta
import unittest

from quant_agents.research_engine import (
    compute_latest_momentum_signals,
    run_momentum_backtest,
)
from quant_agents.backtest_assurance import build_backtest_assurance
from quant_agents.backtest_validation import run_robustness_validation


COST_MODEL = {
    "model_id": "test-cost-v1",
    "broker_commission_quote_mode": "all_in_regulatory",
    "broker_commission_rate": 0.00025,
    "minimum_commission_cny": 5,
    "slippage_bps": 5,
    "market_impact_bps": 2,
    "cost_assumption_source": "unit-test conservative assumption",
}


def synthetic_market():
    dates = []
    cursor = datetime(2024, 11, 1)
    while len(dates) < 100:
        if cursor.weekday() < 5:
            dates.append(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)

    records = []
    limits = []
    codes = ["A.SZ", "B.SZ", "C.SZ"]
    for code_index, code in enumerate(codes):
        close = 10.0
        for day_index, trade_date in enumerate(dates):
            daily_return = 0.001 + (2 - code_index) * 0.0002
            close *= 1.0 + daily_return
            records.append(
                {
                    "ts_code": code,
                    "trade_date": trade_date,
                    "close": close,
                    "pct_chg": daily_return * 100,
                    "amount": 200_000,
                }
            )
            limits.append(
                {
                    "ts_code": code,
                    "trade_date": trade_date,
                    "up_limit": close * 1.1,
                    "down_limit": close * 0.9,
                }
            )

    membership = []
    for snapshot_date, members in ((dates[0], ["A.SZ", "B.SZ"]), (dates[55], ["B.SZ", "C.SZ"])):
        for code in members:
            membership.append({"trade_date": snapshot_date, "ts_code": code, "weight": 0.5})
    return dates, records, membership, limits


class ResearchEngineTests(unittest.TestCase):
    def test_latest_signals_respect_eligible_membership(self):
        _, records, _, _ = synthetic_market()
        signals = compute_latest_momentum_signals(
            records,
            lookback_days=10,
            limit=10,
            eligible_codes={"B.SZ", "C.SZ"},
        )
        self.assertEqual({signal["stock"] for signal in signals}, {"B.SZ", "C.SZ"})

    def test_backtest_uses_point_in_time_membership_and_signal_lag(self):
        dates, records, membership, limits = synthetic_market()
        result = run_momentum_backtest(
            records,
            start_date=dates[20],
            end_date=dates[-1],
            max_positions=1,
            lookback_days=10,
            rebalance_days=5,
            cost_model=COST_MODEL,
            membership_records=membership,
            limit_records=limits,
            suspension_records=[],
            suspension_source_present=True,
            minimum_daily_amount_cny=1,
            simulation_notional_cny=1_000_000,
            max_participation_rate=0.1,
        )
        self.assertTrue(result["methodology"]["point_in_time_membership"])
        self.assertGreater(len(result["rebalance_log"]), 2)
        for row in result["rebalance_log"]:
            self.assertLess(row["signal_window_end"], row["execution_date"])
            self.assertLess(row["execution_date"], row["effective_date"])
            if row["membership_as_of"] >= dates[55]:
                self.assertNotIn("A.SZ", row["selected_codes"])
        self.assertTrue(result["execution_diagnostics"]["cost_ledger_reconciled"])
        self.assertGreater(result["cost_summary"]["total_cost_cny"], 0)
        self.assertGreater(result["trade_count"], 0)
        for ledger in result["cost_ledger"]:
            for order in ledger["orders"]:
                if order["side"] == "B":
                    self.assertEqual(int(order["estimated_executed_shares"]) % 100, 0)

        robustness = run_robustness_validation(
            result,
            {
                "hypothesis_id": "synthetic-momentum-v1",
                "parameter_selection_policy": "pre_registered_no_search",
                "parameter_search_count": 0,
                "holdout_fraction": 0.3,
                "minimum_holdout_trade_days": 15,
                "cost_stress_multipliers": [1.5, 2.0],
                "signal_delay_stress_trade_days": [2],
                "walk_forward": {
                    "fold_count": 3,
                    "fold_trade_days": 20,
                    "minimum_development_trade_days": 20,
                    "minimum_passing_folds": 2,
                },
                "acceptance_thresholds": {
                    "minimum_holdout_trade_count": 1,
                    "minimum_holdout_sharpe": -5.0,
                    "maximum_holdout_drawdown": -1.0,
                    "minimum_double_cost_total_return": -1.0,
                },
            },
            {
                "records": records,
                "start_date": dates[20],
                "end_date": dates[-1],
                "max_positions": 1,
                "lookback_days": 10,
                "rebalance_days": 5,
                "cost_model": COST_MODEL,
                "membership_records": membership,
                "limit_records": limits,
                "suspension_records": [],
                "suspension_source_present": True,
                "minimum_daily_amount_cny": 1,
                "simulation_notional_cny": 1_000_000,
                "max_participation_rate": 0.1,
            },
        )
        self.assertEqual(robustness["decision"], "PASSED")
        self.assertEqual(robustness["scenario_count"], 13)
        self.assertEqual(robustness["walk_forward"]["decision"], "PASSED")
        self.assertEqual(robustness["walk_forward"]["passing_fold_count"], 3)
        result["robustness_validation"] = robustness
        result["snapshot_id"] = "snapshot-test"
        assurance = build_backtest_assurance(result)
        self.assertEqual(assurance["decision"], "PASSED_FOR_INTERNAL_RESEARCH")

    def test_backtest_requires_tradeability_data(self):
        dates, records, membership, _ = synthetic_market()
        with self.assertRaises(ValueError):
            run_momentum_backtest(
                records,
                start_date=dates[20],
                end_date=dates[-1],
                cost_model=COST_MODEL,
                membership_records=membership,
                limit_records=[],
                suspension_source_present=True,
            )

    def test_failed_holdout_threshold_blocks_assurance(self):
        dates, records, membership, limits = synthetic_market()
        engine_kwargs = {
            "records": records,
            "start_date": dates[20],
            "end_date": dates[-1],
            "max_positions": 1,
            "lookback_days": 10,
            "rebalance_days": 5,
            "cost_model": COST_MODEL,
            "membership_records": membership,
            "limit_records": limits,
            "suspension_records": [],
            "suspension_source_present": True,
            "minimum_daily_amount_cny": 1,
            "simulation_notional_cny": 1_000_000,
            "max_participation_rate": 0.1,
        }
        result = run_momentum_backtest(**engine_kwargs)
        result["snapshot_id"] = "snapshot-test"
        result["robustness_validation"] = run_robustness_validation(
            result,
            {
                "hypothesis_id": "synthetic-momentum-v1",
                "parameter_selection_policy": "pre_registered_no_search",
                "parameter_search_count": 0,
                "holdout_fraction": 0.3,
                "minimum_holdout_trade_days": 15,
                "cost_stress_multipliers": [1.5, 2.0],
                "signal_delay_stress_trade_days": [2],
                "walk_forward": {
                    "fold_count": 3,
                    "fold_trade_days": 20,
                    "minimum_development_trade_days": 20,
                    "minimum_passing_folds": 2,
                },
                "acceptance_thresholds": {
                    "minimum_holdout_trade_count": 100,
                    "minimum_holdout_sharpe": -5.0,
                    "maximum_holdout_drawdown": -1.0,
                    "minimum_double_cost_total_return": -1.0,
                },
            },
            engine_kwargs,
        )
        self.assertEqual(result["robustness_validation"]["decision"], "FAILED")
        self.assertIn(
            "holdout_trade_count",
            result["robustness_validation"]["failed_checks"],
        )
        assurance = build_backtest_assurance(result)
        self.assertEqual(assurance["decision"], "FAILED")
        self.assertIn(
            "chronological_holdout_and_stress_matrix",
            assurance["failed_checks"],
        )

    def test_backtest_requires_explicit_suspension_source_evidence(self):
        dates, records, membership, limits = synthetic_market()
        with self.assertRaisesRegex(ValueError, "suspension-data source"):
            run_momentum_backtest(
                records,
                start_date=dates[20],
                end_date=dates[-1],
                cost_model=COST_MODEL,
                membership_records=membership,
                limit_records=limits,
                suspension_source_present=False,
            )


if __name__ == "__main__":
    unittest.main()
