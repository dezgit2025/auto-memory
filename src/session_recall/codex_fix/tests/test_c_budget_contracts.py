"""Frozen strict-envelope tests for the first Stage C budget unit."""

from __future__ import annotations

from copy import deepcopy

import pytest

from session_recall.codex_fix.c_contracts import validate_c
from session_recall.codex_fix.contracts import ContractError

from ._c_budget_fixtures import (
    budget_grant,
    daily_ledger,
    incident_ledger,
    model_policy,
    reservation,
    usage_evidence,
)


def test_exact_six_envelopes_are_the_only_accepted_shapes():
    envelopes = {
        "ModelPolicy": model_policy(),
        "IncidentLedger": incident_ledger(),
        "DailyLedger": daily_ledger(),
        "BudgetGrant": budget_grant(),
        "RequestReservation": reservation(),
        "UsageEvidence": usage_evidence(),
    }
    for kind, value in envelopes.items():
        assert validate_c(value, kind) is value
        with pytest.raises(ContractError):
            validate_c({**value, "candidate_claim": "approved"}, kind)
        missing = deepcopy(value)
        missing.pop(next(iter(missing)))
        with pytest.raises(ContractError):
            validate_c(missing, kind)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("transport_id", "responses-api"),
        ("auth_mode", "api_key"),
        ("model", "gpt-5.6-sol"),
        ("effort", "high"),
        ("initial_allowance_tokens", 31_999),
        ("input_estimate_tokens", 15_999),
        ("generation_estimate_tokens", 16_001),
        ("checkpoint_margin_tokens", 3_999),
        ("grant_increment_tokens", 64_000),
        ("daily_ceiling_tokens", 96_000),
        ("requests_per_grant", 2),
        ("automatic_retries", 1),
        ("timeout_seconds", 301),
        ("usage_accounting", "inclusive_totals_v1"),
        ("background", True),
        ("auto_approve", True),
        ("auto_activate", True),
    ],
)
def test_model_policy_is_exact_not_a_minimum(field, invalid):
    with pytest.raises(ContractError):
        validate_c(model_policy(**{field: invalid}), "ModelPolicy")


def test_grant_reservation_and_usage_semantics_are_strict():
    for changes in (
        {"grant_tokens": 31_999},
        {"request_allowance": 2},
        {"new_incident_ceiling_tokens": 63_999},
        {"daily_ceiling_override_tokens": 88_000},
    ):
        with pytest.raises(ContractError):
            validate_c(budget_grant(**changes), "BudgetGrant")

    for changes in (
        {"estimated_reserved_tokens": 31_999},
        {"reservation_basis": "hard_cap"},
        {"pause_at_tokens": 28_001},
        {"utc_day": "not-a-day"},
    ):
        with pytest.raises(ContractError):
            validate_c(reservation(**changes), "RequestReservation")

    for changes in (
        {"usage_accounting": "inclusive_totals_v1"},
        {"usage_basis": "self_attested"},
        {"usage_scope": "conversation_cumulative"},
        {"cached_input_tokens": 10_001},
        {"reasoning_tokens": 8_001},
        {"trusted": True},
    ):
        with pytest.raises(ContractError):
            validate_c(usage_evidence(**changes), "UsageEvidence")

    no_response = usage_evidence(
        response_status="no_response",
        input_tokens=0,
        cached_input_tokens=0,
        generated_tokens=0,
        reasoning_tokens=0,
    )
    assert validate_c(no_response, "UsageEvidence") is no_response
    over_estimate = usage_evidence(input_tokens=17_000, generated_tokens=18_000)
    assert validate_c(over_estimate, "UsageEvidence") is over_estimate
    final_estimate = usage_evidence(usage_basis="estimated")
    assert validate_c(final_estimate, "UsageEvidence") is final_estimate
    with pytest.raises(ContractError):
        validate_c(
            usage_evidence(response_status="no_response", input_tokens=1),
            "UsageEvidence",
        )
