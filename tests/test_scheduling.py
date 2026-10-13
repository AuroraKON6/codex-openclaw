import copy
import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from quant_agents.config import Config
from quant_agents.audit import canonical_json_sha256, write_json_atomic
from quant_agents.research_protocol import build_model_contract_fingerprint
from quant_agents.scheduling import build_scheduled_input

from test_input_validation import valid_input


class FakeDataClient:
    def get_trade_dates(self, start_date, end_date):
        return ["20250108", "20250109", "20250110"]


class ForwardDataClient:
    def get_trade_dates(self, start_date, end_date):
        return ["20250609", "20250610"]


class SchedulingTests(unittest.TestCase):
    def test_stable_request_id_ignores_generation_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            template = self._write_template(directory)
            with patch.object(Config, "TUSHARE_TOKEN", "test-token"):
                first = build_scheduled_input(
                    template,
                    os.path.join(directory, "first.json"),
                    as_of="20250110",
                    data_client=FakeDataClient(),
                    now=datetime(2025, 1, 10, 20, 0),
                )
                second = build_scheduled_input(
                    template,
                    os.path.join(directory, "second.json"),
                    as_of="20250110",
                    data_client=FakeDataClient(),
                    now=datetime(2025, 1, 10, 21, 0),
                )
            self.assertEqual(first["request_id"], second["request_id"])
            self.assertEqual(first["request_fingerprint"], second["request_fingerprint"])
            self.assertNotEqual(first["input_fingerprint"], second["input_fingerprint"])
            with open(os.path.join(directory, "first.json"), encoding="utf-8") as file:
                payload = json.load(file)
            self.assertEqual(payload["date_range"]["until"], "20250110")

    def test_same_day_before_cutoff_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            template = self._write_template(directory)
            with patch.object(Config, "TUSHARE_TOKEN", "test-token"):
                with self.assertRaisesRegex(RuntimeError, "cannot be generated before"):
                    build_scheduled_input(
                        template,
                        os.path.join(directory, "input.json"),
                        as_of="20250110",
                        data_client=FakeDataClient(),
                        now=datetime(2025, 1, 10, 18, 0),
                    )

    def test_licensed_schedule_uses_frozen_campaign_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = copy.deepcopy(valid_input())
            payload["schedule_controls"] = {
                "not_before_local_time": "18:30",
                "lookback_calendar_days": 365,
            }
            template = os.path.join(directory, "template.json")
            with open(template, "w", encoding="utf-8") as file:
                json.dump(payload, file)
            model_contract_sha256 = build_model_contract_fingerprint(payload)
            identity = {
                "baseline_run_id": "baseline-run",
                "baseline_manifest_snapshot_id": "a" * 64,
                "protocol_id": "test-protocol-v1",
                "protocol_version": 1,
                "model_contract_sha256": model_contract_sha256,
                "baseline_cutoff": "20250530",
            }
            campaign_id = canonical_json_sha256(identity)
            campaign_dir = os.path.join(directory, "campaign")
            os.makedirs(campaign_dir)
            write_json_atomic(
                os.path.join(campaign_dir, "campaign.json"),
                {
                    "schema_version": 1,
                    "campaign_id": campaign_id,
                    "status": "ACTIVE_FORWARD_OBSERVATION",
                    **identity,
                    "baseline_input_sha256": canonical_json_sha256(payload),
                    "source_head_commit": "b" * 40,
                    "forward_observation_controls": {
                        "warmup_since": "20250101",
                        "baseline_cutoff": "20250530",
                    },
                    "broker_connection_enabled": False,
                    "external_distribution_approved": False,
                    "live_execution_ready": False,
                },
            )
            protocol_gate = {
                "protocol_id": "test-protocol-v1",
                "protocol_version": 1,
                "model_contract_sha256": model_contract_sha256,
            }
            output = os.path.join(directory, "scheduled.json")
            with patch.object(Config, "TUSHARE_TOKEN", "test-token"), patch(
                "quant_agents.scheduling.evaluate_data_license",
                return_value={"status": "approved"},
            ), patch(
                "quant_agents.scheduling.evaluate_research_protocol",
                return_value=protocol_gate,
            ):
                result = build_scheduled_input(
                    template,
                    output,
                    as_of="20250610",
                    data_client=ForwardDataClient(),
                    now=datetime(2025, 6, 10, 20, 0),
                    campaign_path=campaign_dir,
                )
            with open(output, encoding="utf-8") as file:
                scheduled = json.load(file)
            self.assertEqual(scheduled["date_range"]["since"], "20250101")
            self.assertEqual(scheduled["date_range"]["until"], "20250610")
            self.assertEqual(
                scheduled["schedule_context"]["run_class"],
                "forward_observation_refresh",
            )
            self.assertEqual(result["campaign_id"], campaign_id)

    @staticmethod
    def _write_template(directory):
        payload = copy.deepcopy(valid_input())
        payload["governance"]["intended_use"] = "personal_non_commercial_research"
        payload["schedule_controls"] = {
            "not_before_local_time": "18:30",
            "lookback_calendar_days": 365,
        }
        path = os.path.join(directory, "template.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file)
        return path


if __name__ == "__main__":
    unittest.main()
