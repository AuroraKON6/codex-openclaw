from __future__ import annotations
import os
from datetime import date, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APPROVED_DEEPSEEK_PRICING_BASELINE_ID = "deepseek-v4-pro-2026-08-25"
APPROVED_DEEPSEEK_OFF_PEAK_RATES = {
    "input_cache_hit_usd_per_m": 0.022,
    "input_cache_miss_usd_per_m": 0.66,
    "output_usd_per_m": 1.98,
}


class Config:
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    TUSHARE_TOKEN: str = os.getenv("TUSHARE_TOKEN", "")
    TUSHARE_INDEX_CODE: str = os.getenv("TUSHARE_INDEX_CODE", "000905.SH")
    TUSHARE_CACHE_DIR: str = os.getenv("TUSHARE_CACHE_DIR", ".cache/tushare")
    TUSHARE_CACHE_TTL_HOURS: int = int(os.getenv("TUSHARE_CACHE_TTL_HOURS", "24"))
    TUSHARE_MAX_RETRIES: int = int(os.getenv("TUSHARE_MAX_RETRIES", "3"))
    TUSHARE_RETRY_BASE_SECONDS: float = float(os.getenv("TUSHARE_RETRY_BASE_SECONDS", "1"))
    TUSHARE_MAX_RESEARCH_SECURITIES: int = int(
        os.getenv("TUSHARE_MAX_RESEARCH_SECURITIES", "120")
    )
    PI_PACKAGE_NAME: str = "@earendil-works/pi-coding-agent"
    PI_VERSION: str = "0.84.2"
    PI_PACKAGE_INTEGRITY: str = (
        "sha512-l4E+B7hgXKWddRo8bC/eSue2aWZjEgJ9xIpf5p0Og+lq8a2TArCwJ0HCoCPCgaBP/"
        "tN4zbYH/wOwvx9pJpeLCA=="
    )
    PI_NODE_CLI: str = os.getenv("PI_NODE_CLI", "node")
    PI_CLI_PATH: str = os.getenv(
        "PI_CLI_PATH",
        str(
            PROJECT_ROOT
            / "pi_runtime"
            / "node_modules"
            / "@earendil-works"
            / "pi-coding-agent"
            / "dist"
            / "cli.js"
        ),
    )
    PI_STATE_DIR: str = os.getenv(
        "PI_STATE_DIR", str(PROJECT_ROOT / ".cache" / "pi-agent")
    )
    PI_TIMEOUT_SECONDS: int = int(os.getenv("PI_TIMEOUT_SECONDS", "300"))
    PI_PING_TIMEOUT_SECONDS: int = int(os.getenv("PI_PING_TIMEOUT_SECONDS", "90"))
    PI_METADATA_TIMEOUT_SECONDS: int = int(
        os.getenv("PI_METADATA_TIMEOUT_SECONDS", "60")
    )
    PI_THINKING_LEVEL: str = os.getenv("PI_THINKING_LEVEL", "off")
    DATA_LICENSE_EVIDENCE_PATH: str = os.getenv("DATA_LICENSE_EVIDENCE_PATH", "")
    RESEARCH_PROTOCOL_EVIDENCE_PATH: str = os.getenv(
        "RESEARCH_PROTOCOL_EVIDENCE_PATH", ""
    )
    EXECUTION_COST_EVIDENCE_PATH: str = os.getenv(
        "EXECUTION_COST_EVIDENCE_PATH", ""
    )
    EXPERIMENT_REGISTRY_PATH: str = os.getenv("EXPERIMENT_REGISTRY_PATH", "")
    SECRET_SCAN_RECEIPT_PATH: str = os.getenv(
        "SECRET_SCAN_RECEIPT_PATH",
        str(PROJECT_ROOT / ".cache" / "secret-scan" / "receipt.json"),
    )
    SOURCE_REVIEW_PACKET_DIR: str = os.getenv("SOURCE_REVIEW_PACKET_DIR", "")
    SOURCE_REVIEW_DECISION_PATH: str = os.getenv(
        "SOURCE_REVIEW_DECISION_PATH", ""
    )
    RUN_LOCK_STALE_SECONDS: int = int(os.getenv("RUN_LOCK_STALE_SECONDS", "1800"))
    MAX_LLM_TOTAL_TOKENS_PER_RUN: int = int(
        os.getenv("MAX_LLM_TOTAL_TOKENS_PER_RUN", "500000")
    )
    MAX_LLM_COST_USD_PER_RUN: float = float(
        os.getenv("MAX_LLM_COST_USD_PER_RUN", "2.00")
    )
    MAX_AGENT_RUNTIME_SECONDS: int = int(
        os.getenv("MAX_AGENT_RUNTIME_SECONDS", "300")
    )
    MAX_PIPELINE_RUNTIME_SECONDS: int = int(
        os.getenv("MAX_PIPELINE_RUNTIME_SECONDS", "2400")
    )
    DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M: float = float(
        os.getenv("DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M", "0.022")
    )
    DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M: float = float(
        os.getenv("DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M", "0.66")
    )
    DEEPSEEK_OUTPUT_USD_PER_M: float = float(
        os.getenv("DEEPSEEK_OUTPUT_USD_PER_M", "1.98")
    )
    DEEPSEEK_PRICING_REVIEWED_DATE: str = os.getenv(
        "DEEPSEEK_PRICING_REVIEWED_DATE",
        os.getenv("DEEPSEEK_PRICING_EFFECTIVE_DATE", "2026-08-25"),
    )
    DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS: int = int(
        os.getenv("DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS", "30")
    )
    DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER: float = float(
        os.getenv("DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER", "2.0")
    )
    RUN_RETENTION_DAYS: int = int(os.getenv("RUN_RETENTION_DAYS", "365"))

    @classmethod
    def validate(
        cls,
        require_deepseek: bool = True,
        require_tushare: bool = False,
    ) -> list[str]:
        errors = []
        if require_deepseek and not cls.DEEPSEEK_API_KEY:
            errors.append("DEEPSEEK_API_KEY not set")
        if cls.DEEPSEEK_MODEL != "deepseek-v4-pro":
            errors.append("DEEPSEEK_MODEL must be deepseek-v4-pro for the approved Pi runtime")
        if cls.PI_THINKING_LEVEL not in {
            "off", "minimal", "low", "medium", "high", "xhigh", "max"
        }:
            errors.append("PI_THINKING_LEVEL is invalid")
        positive_limits = {
            "PI_TIMEOUT_SECONDS": cls.PI_TIMEOUT_SECONDS,
            "PI_PING_TIMEOUT_SECONDS": cls.PI_PING_TIMEOUT_SECONDS,
            "PI_METADATA_TIMEOUT_SECONDS": cls.PI_METADATA_TIMEOUT_SECONDS,
            "RUN_LOCK_STALE_SECONDS": cls.RUN_LOCK_STALE_SECONDS,
            "MAX_LLM_TOTAL_TOKENS_PER_RUN": cls.MAX_LLM_TOTAL_TOKENS_PER_RUN,
            "MAX_LLM_COST_USD_PER_RUN": cls.MAX_LLM_COST_USD_PER_RUN,
            "MAX_AGENT_RUNTIME_SECONDS": cls.MAX_AGENT_RUNTIME_SECONDS,
            "MAX_PIPELINE_RUNTIME_SECONDS": cls.MAX_PIPELINE_RUNTIME_SECONDS,
            "DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M": cls.DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M,
            "DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M": cls.DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M,
            "DEEPSEEK_OUTPUT_USD_PER_M": cls.DEEPSEEK_OUTPUT_USD_PER_M,
            "DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS": cls.DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS,
            "RUN_RETENTION_DAYS": cls.RUN_RETENTION_DAYS,
        }
        for name, value in positive_limits.items():
            if value <= 0:
                errors.append(f"{name} must be positive")
        if not 1 <= cls.TUSHARE_MAX_RESEARCH_SECURITIES <= 500:
            errors.append("TUSHARE_MAX_RESEARCH_SECURITIES must be between 1 and 500")
        if require_tushare and not cls.TUSHARE_TOKEN:
            errors.append("TUSHARE_TOKEN not set")
        if not 2.0 <= cls.DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER <= 3.0:
            errors.append(
                "DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER must be between 2.0 and 3.0"
            )
        if require_deepseek:
            observed_rates = {
                "input_cache_hit_usd_per_m": cls.DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M,
                "input_cache_miss_usd_per_m": cls.DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M,
                "output_usd_per_m": cls.DEEPSEEK_OUTPUT_USD_PER_M,
            }
            if observed_rates != APPROVED_DEEPSEEK_OFF_PEAK_RATES:
                errors.append(
                    "DeepSeek rates do not match the approved 2026-08-25 V4 Pro "
                    "off-peak baseline; update source, tests, and review evidence together"
                )
            try:
                pricing_date = datetime.strptime(
                    cls.DEEPSEEK_PRICING_REVIEWED_DATE, "%Y-%m-%d"
                ).date()
            except ValueError:
                errors.append("DEEPSEEK_PRICING_REVIEWED_DATE must use YYYY-MM-DD")
            else:
                today = date.today()
                if pricing_date > today:
                    errors.append("DEEPSEEK_PRICING_REVIEWED_DATE must not be in the future")
                elif (today - pricing_date).days > cls.DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS:
                    errors.append(
                        "DeepSeek pricing baseline is stale; review the official pricing "
                        "page and refresh DEEPSEEK_PRICING_REVIEWED_DATE"
                    )
        return errors

    @classmethod
    def snapshot(cls) -> dict:
        return {
            "deepseek_model": cls.DEEPSEEK_MODEL,
            "deepseek_api_key_set": bool(cls.DEEPSEEK_API_KEY),
            "tushare_token_set": bool(cls.TUSHARE_TOKEN),
            "tushare_index_code": cls.TUSHARE_INDEX_CODE,
            "tushare_cache_dir": cls.TUSHARE_CACHE_DIR,
            "tushare_cache_ttl_hours": cls.TUSHARE_CACHE_TTL_HOURS,
            "tushare_max_retries": cls.TUSHARE_MAX_RETRIES,
            "tushare_max_research_securities": cls.TUSHARE_MAX_RESEARCH_SECURITIES,
            "pi_package": cls.PI_PACKAGE_NAME,
            "pi_version": cls.PI_VERSION,
            "pi_cli_path": cls.PI_CLI_PATH,
            "pi_node_cli": cls.PI_NODE_CLI,
            "pi_state_dir": cls.PI_STATE_DIR,
            "pi_thinking_level": cls.PI_THINKING_LEVEL,
            "pi_metadata_timeout_seconds": cls.PI_METADATA_TIMEOUT_SECONDS,
            "pi_security_policy": {
                "ephemeral_session": True,
                "all_tools_disabled": True,
                "extensions_disabled": True,
                "skills_disabled": True,
                "prompt_templates_disabled": True,
                "themes_disabled": True,
                "context_files_disabled": True,
                "project_resources_ignored": True,
                "startup_network_disabled": True,
            },
            "data_license_evidence_path_set": bool(cls.DATA_LICENSE_EVIDENCE_PATH),
            "research_protocol_evidence_path_set": bool(
                cls.RESEARCH_PROTOCOL_EVIDENCE_PATH
            ),
            "execution_cost_evidence_path_set": bool(
                cls.EXECUTION_COST_EVIDENCE_PATH
            ),
            "experiment_registry_path_set": bool(cls.EXPERIMENT_REGISTRY_PATH),
            "secret_scan_receipt_path": cls.SECRET_SCAN_RECEIPT_PATH,
            "source_review_packet_dir_set": bool(cls.SOURCE_REVIEW_PACKET_DIR),
            "source_review_decision_path_set": bool(cls.SOURCE_REVIEW_DECISION_PATH),
            "run_lock_stale_seconds": cls.RUN_LOCK_STALE_SECONDS,
            "max_llm_total_tokens_per_run": cls.MAX_LLM_TOTAL_TOKENS_PER_RUN,
            "max_llm_cost_usd_per_run": cls.MAX_LLM_COST_USD_PER_RUN,
            "max_agent_runtime_seconds": cls.MAX_AGENT_RUNTIME_SECONDS,
            "max_pipeline_runtime_seconds": cls.MAX_PIPELINE_RUNTIME_SECONDS,
            "deepseek_pricing": {
                "baseline_id": APPROVED_DEEPSEEK_PRICING_BASELINE_ID,
                "input_cache_hit_usd_per_m": cls.DEEPSEEK_INPUT_CACHE_HIT_USD_PER_M,
                "input_cache_miss_usd_per_m": cls.DEEPSEEK_INPUT_CACHE_MISS_USD_PER_M,
                "output_usd_per_m": cls.DEEPSEEK_OUTPUT_USD_PER_M,
                "reviewed_at": cls.DEEPSEEK_PRICING_REVIEWED_DATE,
                "review_max_age_days": cls.DEEPSEEK_PRICING_REVIEW_MAX_AGE_DAYS,
                "budget_contingency_multiplier": cls.DEEPSEEK_BUDGET_CONTINGENCY_MULTIPLIER,
            },
            "run_retention_days": cls.RUN_RETENTION_DAYS,
        }
