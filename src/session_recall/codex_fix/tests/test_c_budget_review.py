"""Independent regression cases for the pure Stage C budget transitions."""

from __future__ import annotations

from copy import deepcopy

import pytest

from session_recall.codex_fix.budget import (
    consume_grant,
    new_incident,
    reserve_request,
    settle_request,
    should_pause,
)
from session_recall.codex_fix.c_contracts import validate_c
from session_recall.codex_fix.contracts import ContractError

from ._c_budget_fixtures import (
    CONTROLLER_ID,
    INCIDENT_ID,
    SHA_INPUT,
    UTC_DAY,
    budget_grant,
    daily_ledger,
    incident_ledger,
    model_policy,
    usage_evidence,
)


MAX_INT = 2**63 - 1


def _new_pair():
    return (
        new_incident(
            CONTROLLER_ID,
            INCIDENT_ID,
            SHA_INPUT,
            model_policy(),
            utc_day=UTC_DAY,
        ),
        daily_ledger(),
    )


def _settle_first(*, input_tokens: int, generated_tokens: int):
    incident, daily = _new_pair()
    reserved, reserved_daily, request = reserve_request(incident, daily)
    evidence = usage_evidence(
        request,
        input_tokens=input_tokens,
        cached_input_tokens=0,
        generated_tokens=generated_tokens,
        reasoning_tokens=0,
    )
    return settle_request(reserved, reserved_daily, request, evidence)


def test_pause_checks_threshold_or_true_allowance_overrun_not_margin_crossing():
    incident, daily = _settle_first(input_tokens=15_000, generated_tokens=14_000)
    incident, _daily = consume_grant(
        incident, daily, budget_grant(incident, daily)
    )

    assert incident["allowance_tokens"] == 64_000
    assert should_pause(
        incident, observed_total_tokens=29_000, next_request_tokens=32_000
    ) is False
    assert should_pause(
        incident, observed_total_tokens=32_000, next_request_tokens=32_000
    ) is False
    assert should_pause(incident, observed_total_tokens=60_000) is True
    assert should_pause(
        incident, observed_total_tokens=32_001, next_request_tokens=32_000
    ) is True


def test_replayed_nonfinal_evidence_has_no_revision_churn_and_final_still_settles():
    incident, daily = _new_pair()
    reserved, reserved_daily, request = reserve_request(incident, daily)
    pending = usage_evidence(request, usage_final=False)
    awaiting, awaiting_daily = settle_request(
        reserved, reserved_daily, request, pending
    )
    before = (deepcopy(awaiting), deepcopy(awaiting_daily))

    try:
        replayed = settle_request(awaiting, awaiting_daily, request, pending)
    except ContractError:
        pass
    else:
        assert replayed == before

    final = usage_evidence(request)
    settled, settled_daily = settle_request(
        awaiting, awaiting_daily, request, final
    )
    assert settled["held_tokens"] == settled_daily["held_tokens"] == 0
    assert settled["charged_tokens"] == settled_daily["charged_tokens"] == 18_000


def test_positive_revision_requires_a_previous_checkpoint_digest():
    with pytest.raises(ContractError):
        validate_c(
            incident_ledger(revision=1, previous_checkpoint_digest=None),
            "IncidentLedger",
        )
    with pytest.raises(ContractError):
        validate_c(
            daily_ledger(revision=1, previous_checkpoint_digest=None),
            "DailyLedger",
        )


def test_post_midnight_settlement_remains_bound_to_the_reservation_day():
    incident, daily = _new_pair()
    reserved, reserved_daily, request = reserve_request(incident, daily)
    next_day = daily_ledger(
        utc_day="2026-09-21",
        revision=reserved_daily["revision"],
        previous_checkpoint_digest=reserved_daily["previous_checkpoint_digest"],
        held_tokens=32_000,
    )
    evidence = usage_evidence(request)

    with pytest.raises(ContractError):
        settle_request(reserved, next_day, request, evidence)
    settled, settled_daily = settle_request(
        reserved, reserved_daily, request, evidence
    )
    assert settled["charged_tokens"] == 18_000
    assert settled_daily["utc_day"] == UTC_DAY


def test_actual_overshoot_is_recorded_but_unsigned_addition_overflow_is_rejected():
    incident, daily = _new_pair()
    reserved, reserved_daily, request = reserve_request(incident, daily)
    oversized = usage_evidence(
        request,
        input_tokens=40_000,
        cached_input_tokens=5_000,
        generated_tokens=30_000,
        reasoning_tokens=10_000,
    )
    settled, settled_daily = settle_request(
        reserved, reserved_daily, request, oversized
    )
    assert settled["charged_tokens"] == settled_daily["charged_tokens"] == 70_000
    assert settled["held_tokens"] == settled_daily["held_tokens"] == 0
    assert settled["state"] == "awaiting_budget_approval"

    ceiling = (MAX_INT // 32_000) * 32_000
    grants = ceiling // 32_000 - 1
    near_limit = incident_ledger(
        allowance_tokens=ceiling,
        charged_tokens=ceiling - 32_000,
        requests_allowed=grants + 1,
        requests_started=grants,
        grants_consumed=grants,
        usage_status="actual",
    )
    near_daily = daily_ledger(
        ceiling_tokens=ceiling,
        charged_tokens=ceiling - 32_000,
    )
    held_incident, held_daily, final_request = reserve_request(
        near_limit, near_daily
    )
    overflowing = usage_evidence(
        final_request,
        input_tokens=32_000,
        cached_input_tokens=0,
        generated_tokens=32_000,
        reasoning_tokens=0,
    )
    with pytest.raises(ContractError, match="token_overflow"):
        settle_request(held_incident, held_daily, final_request, overflowing)


def test_successful_grant_and_settlement_preserve_all_inputs():
    incident, daily = _settle_first(input_tokens=10_000, generated_tokens=8_000)
    grant = budget_grant(incident, daily)
    grant_inputs = deepcopy((incident, daily, grant))
    granted, granted_daily = consume_grant(incident, daily, grant)
    assert (incident, daily, grant) == grant_inputs

    reserved, reserved_daily, request = reserve_request(granted, granted_daily)
    evidence = usage_evidence(request)
    settlement_inputs = deepcopy((reserved, reserved_daily, request, evidence))
    settle_request(reserved, reserved_daily, request, evidence)
    assert (reserved, reserved_daily, request, evidence) == settlement_inputs


def test_approval_state_can_preserve_unused_credit_after_an_actual_overshoot():
    value = incident_ledger(
        allowance_tokens=64_000,
        charged_tokens=35_000,
        requests_allowed=2,
        requests_started=1,
        grants_consumed=1,
        state="awaiting_budget_approval",
        usage_status="actual",
    )

    assert validate_c(value, "IncidentLedger") is value
