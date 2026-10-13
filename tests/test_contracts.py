import unittest

from quant_agents.contracts import OutputContractError, validate_agent_output


class ContractTests(unittest.TestCase):
    def test_rejects_readiness_placeholder(self):
        output = {
            "macro_summary": "ready",
            "sector_trends": [],
            "risk_factors": [],
            "research_priorities": [],
            "trigger_level": "LOW",
            "confidence": 0.0,
        }
        with self.assertRaises(OutputContractError):
            validate_agent_output("research_lead", output)

    def test_rejects_trade_direction(self):
        output = {
            "strategy_name": "test",
            "strategy_type": "momentum",
            "signals": [{"stock": "TEST.SZ", "direction": "LONG"}],
            "universe_filter": "test",
            "rebalance_frequency": "monthly",
            "expected_sharpe": 0.0,
            "max_drawdown_estimate": 0.0,
            "confidence": 0.0,
        }
        with self.assertRaises(OutputContractError):
            validate_agent_output("strategy_agent", output)

    def test_accepts_research_classification(self):
        output = {
            "strategy_name": "test",
            "strategy_type": "momentum",
            "signals": [
                {
                    "stock": "TEST.SZ",
                    "factor_score": 0.1,
                    "research_classification": "HIGH_SCORE",
                }
            ],
            "universe_filter": "point-in-time sample",
            "rebalance_frequency": "monthly",
            "expected_sharpe": 0.0,
            "max_drawdown_estimate": 0.0,
            "confidence": 0.5,
        }
        validate_agent_output("strategy_agent", output)


if __name__ == "__main__":
    unittest.main()
