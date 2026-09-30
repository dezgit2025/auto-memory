"""Versioned production defaults for the Codex repair worker."""

from __future__ import annotations

from typing import Any
import json
from importlib.resources import files


def model_policy() -> dict[str, Any]:
    """Return a fresh copy of the active GPT-6 Astra budget policy."""
    return {
        "format_version": 2,
        "policy_id": "astra-medium-budget-v2",
        "transport_id": "codex-runner-v1",
        "auth_mode": "existing_codex_login",
        "model": "gpt-6-astra",
        "effort": "medium",
        "initial_allowance_tokens": 32_000,
        "input_estimate_tokens": 16_000,
        "generation_estimate_tokens": 16_000,
        "checkpoint_margin_tokens": 4_000,
        "grant_increment_tokens": 32_000,
        "daily_ceiling_tokens": 64_000,
        "requests_per_grant": 1,
        "automatic_retries": 0,
        "timeout_seconds": 300,
        "usage_accounting": "estimated_with_actual_reconciliation_v1",
        "background": False,
        "auto_approve": False,
        "auto_activate": False,
    }


def production_model_policy() -> dict[str, Any]:
    """Versioned, packaged budget for new Codex repair requests."""
    return json.loads(files(__package__).joinpath("data/model-policy-v3.json").read_text(encoding="utf-8"))
