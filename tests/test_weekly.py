import os
import tempfile
import unittest

from quant_agents.audit import write_json_atomic
from quant_agents.weekly import generate_weekly_report


class WeeklyTests(unittest.TestCase):
    def test_aggregates_only_current_schema_and_mode(self):
        with tempfile.TemporaryDirectory() as root:
            valid_run = os.path.join(root, "20260811_010000")
            legacy_run = os.path.join(root, "20260811_020000")
            os.makedirs(valid_run)
            os.makedirs(legacy_run)
            write_json_atomic(
                os.path.join(valid_run, "state.json"),
                {
                    "schema_version": 7,
                    "finished_at": "2026-08-11T01:00:00",
                    "mock": True,
                    "runtime": "mock",
                    "error_count": 0,
                    "success_count": 7,
                    "total_agents": 7,
                    "data_mode": "MOCK",
                    "errors": [],
                    "agent_outputs": {
                        "review_agent": {
                            "conclusion": "mock complete",
                            "trigger_level": "CRITICAL",
                            "key_risks": ["mock only"],
                            "human_confirmation_needed": ["review"],
                            "next_actions": ["run real research"],
                        }
                    },
                },
            )
            write_json_atomic(
                os.path.join(legacy_run, "state.json"),
                {
                    "schema_version": 2,
                    "finished_at": "2026-08-11T02:00:00",
                    "mock": True,
                },
            )
            output_dir = os.path.join(root, "weekly_20260804_20260811")
            generate_weekly_report(
                "20260804",
                "20260811",
                output_dir,
                mock=True,
                runtime="pi",
            )
            import json

            with open(os.path.join(output_dir, "weekly_state.json"), "r", encoding="utf-8") as file:
                report = json.load(file)
            self.assertEqual(report["source_run_count"], 1)
            self.assertEqual(report["source_runs"][0]["run"], "20260811_010000")
            self.assertEqual(report["source_runs"][0]["source"], "UNVERSIONED")
            self.assertTrue(any("源码版本门禁未通过" in item for item in report["key_risks"]))


if __name__ == "__main__":
    unittest.main()
