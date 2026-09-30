"""Frozen pure-transition tests for the Stage C budget ledger."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from session_recall.codex_fix.budget import (
    consume_grant,
    new_incident,
    normalize_usage,
    reserve_request,
    settle_request,
    should_pause,
)
from session_recall.codex_fix.c_contracts import validate_c
from session_recall.codex_fix.contracts import ContractError, digest

from ._c_budget_fixtures import (
    CONTROLLER_ID,
    INCIDENT_ID,
    SHA_INPUT,
    UTC_DAY,
    budget_grant,
    daily_ledger,
    model_policy,
    usage_evidence,
)


def _assert_unchanged(before, *values):
    for original, value in zip(before, values, strict=True):
        assert value == original


def test_initial_reservation_and_pause_boundaries_do_not_count_the_hold_as_usage():
    policy = model_policy()
    incident = new_incident(
        CONTROLLER_ID, INCIDENT_ID, SHA_INPUT, policy, utc_day=UTC_DAY
    )
    daily = daily_ledger()
    before = (deepcopy(incident), deepcopy(daily))

    reserved_incident, reserved_daily, request = reserve_request(incident, daily)

    _assert_unchanged(before, incident, daily)
    assert request["estimated_reserved_tokens"] == 32_000
    assert request["reservation_basis"] == "estimate"
    assert request["pause_at_tokens"] == 28_000
    assert request["utc_day"] == UTC_DAY
    assert reserved_incident["held_tokens"] == 32_000
    assert reserved_incident["requests_started"] == 1
    assert reserved_daily["held_tokens"] == 32_000
    assert should_pause(reserved_incident, observed_total_tokens=27_999) is False
    assert should_pause(reserved_incident, observed_total_tokens=28_000) is True
    assert should_pause(reserved_incident, observed_total_tokens=0) is False
    assert should_pause(
        reserved_incident, observed_total_tokens=1, next_request_tokens=32_000
    ) is True
    with pytest.raises(ContractError):
        reserve_request(reserved_incident, reserved_daily)


def test_grant_is_bound_single_use_and_updates_both_ledgers_for_daily_override():
    incident = new_incident(
        CONTROLLER_ID, INCIDENT_ID, SHA_INPUT, model_policy(), utc_day=UTC_DAY
    )
    incident = {
        **incident,
        "revision": 2,
        "previous_checkpoint_digest": digest(incident),
        "requests_started": 1,
        "state": "awaiting_budget_approval",
    }
    daily = daily_ledger(revision=2, charged_tokens=56_000)
    ordinary = budget_grant(incident, daily)
    before = (deepcopy(incident), deepcopy(daily), deepcopy(ordinary))

    with pytest.raises(ContractError):
        consume_grant(incident, daily, ordinary)
    _assert_unchanged(before, incident, daily, ordinary)

    grant = budget_grant(
        incident,
        daily,
        daily_ceiling_override_tokens=96_000,
    )
    next_incident, next_daily = consume_grant(incident, daily, grant)
    assert next_incident["allowance_tokens"] == 64_000
    assert next_incident["requests_allowed"] == 2
    assert next_incident["grants_consumed"] == 1
    assert next_incident["state"] == "ready"
    assert next_daily["ceiling_tokens"] == 96_000
    assert should_pause(next_incident, observed_total_tokens=59_999) is False
    assert should_pause(next_incident, observed_total_tokens=60_000) is True

    with pytest.raises(ContractError):
        consume_grant(next_incident, next_daily, grant)
    for field, value in (
        ("revision", incident["revision"] + 1),
        ("input_digest", "sha256:" + "9" * 64),
        ("policy_digest", "sha256:" + "8" * 64),
        ("incident_id", "incident-2"),
    ):
        tampered = {**incident, field: value}
        with pytest.raises(ContractError):
            consume_grant(tampered, daily, grant)
    with pytest.raises(ContractError):
        consume_grant(incident, {**daily, "charged_tokens": 55_999}, grant)


def test_usage_normalization_settlement_and_no_response_are_request_bound():
    incident = new_incident(
        CONTROLLER_ID, INCIDENT_ID, SHA_INPUT, model_policy(), utc_day=UTC_DAY
    )
    daily = daily_ledger()
    reserved_incident, reserved_daily, request = reserve_request(incident, daily)
    evidence = usage_evidence(request)
    before = (
        deepcopy(reserved_incident),
        deepcopy(reserved_daily),
        deepcopy(request),
        deepcopy(evidence),
    )

    assert normalize_usage(evidence) == 18_000
    settled_incident, settled_daily = settle_request(
        reserved_incident, reserved_daily, request, evidence
    )
    _assert_unchanged(
        before, reserved_incident, reserved_daily, request, evidence
    )
    assert settled_incident["charged_tokens"] == 18_000
    assert settled_incident["held_tokens"] == 0
    assert settled_incident["usage_status"] == "actual"
    assert settled_daily["charged_tokens"] == 18_000
    assert settled_daily["held_tokens"] == 0

    no_response = usage_evidence(
        request,
        response_status="no_response",
        input_tokens=0,
        cached_input_tokens=0,
        generated_tokens=0,
        reasoning_tokens=0,
    )
    paused_incident, paused_daily = settle_request(
        reserved_incident, reserved_daily, request, no_response
    )
    assert paused_incident["charged_tokens"] == 0
    assert paused_incident["held_tokens"] == 0
    assert paused_incident["usage_status"] == "actual"
    assert paused_incident["state"] == "awaiting_budget_approval"
    assert paused_daily["charged_tokens"] == paused_daily["held_tokens"] == 0

    with pytest.raises(ContractError):
        settle_request(
            reserved_incident,
            reserved_daily,
            request,
            usage_evidence(request, reservation_digest="sha256:" + "f" * 64),
        )
    estimated_incident, estimated_daily = settle_request(
        reserved_incident,
        reserved_daily,
        request,
        usage_evidence(request, usage_final=False),
    )
    assert estimated_incident["held_tokens"] == 32_000
    assert estimated_incident["usage_status"] == "estimated"
    assert estimated_incident["state"] == "awaiting_usage"
    assert estimated_daily["held_tokens"] == 32_000

    final_estimate = usage_evidence(
        request,
        usage_basis="estimated",
        response_status="interrupted",
        input_tokens=7_000,
        cached_input_tokens=2_000,
        generated_tokens=6_000,
        reasoning_tokens=1_000,
    )
    estimated_incident, estimated_daily = settle_request(
        reserved_incident, reserved_daily, request, final_estimate
    )
    assert estimated_incident["charged_tokens"] == 13_000
    assert estimated_incident["held_tokens"] == 0
    assert estimated_incident["usage_status"] == "estimated"
    assert estimated_incident["state"] == "awaiting_budget_approval"
    assert estimated_daily["charged_tokens"] == 13_000
    assert estimated_daily["held_tokens"] == 0

    overage = usage_evidence(
        request,
        input_tokens=17_000,
        cached_input_tokens=4_000,
        generated_tokens=18_000,
        reasoning_tokens=9_000,
    )
    over_incident, over_daily = settle_request(
        reserved_incident, reserved_daily, request, overage
    )
    assert normalize_usage(overage) == 35_000
    assert over_incident["charged_tokens"] == 35_000
    assert over_incident["held_tokens"] == 0
    assert over_incident["usage_status"] == "actual"
    assert over_incident["state"] == "awaiting_budget_approval"
    assert over_daily["charged_tokens"] == 35_000
    assert over_daily["held_tokens"] == 0


def test_unfinished_reservation_survives_round_trip_without_release_or_retry():
    incident = new_incident(
        CONTROLLER_ID, INCIDENT_ID, SHA_INPUT, model_policy(), utc_day=UTC_DAY
    )
    reserved_incident, reserved_daily, request = reserve_request(
        incident, daily_ledger()
    )
    restored_incident = validate_c(
        json.loads(json.dumps(reserved_incident)), "IncidentLedger"
    )
    restored_daily = validate_c(json.loads(json.dumps(reserved_daily)), "DailyLedger")

    assert restored_incident["held_tokens"] == 32_000
    assert restored_daily["held_tokens"] == 32_000
    assert restored_incident["current_reservation_digest"] == digest(request)
    assert restored_incident["requests_started"] == 1
    with pytest.raises(ContractError):
        reserve_request(restored_incident, restored_daily)


def test_later_actual_request_does_not_erase_an_earlier_estimated_basis():
    incident = new_incident(
        CONTROLLER_ID, INCIDENT_ID, SHA_INPUT, model_policy(), utc_day=UTC_DAY
    )
    daily = daily_ledger()
    reserved, reserved_daily, first_request = reserve_request(incident, daily)
    first_estimate = usage_evidence(
        first_request,
        usage_basis="estimated",
        response_status="interrupted",
        input_tokens=7_000,
        cached_input_tokens=2_000,
        generated_tokens=6_000,
        reasoning_tokens=1_000,
    )
    incident, daily = settle_request(
        reserved, reserved_daily, first_request, first_estimate
    )
    assert incident["charged_tokens"] == 13_000
    assert incident["usage_status"] == "estimated"

    incident, daily = consume_grant(
        incident, daily, budget_grant(incident, daily)
    )
    reserved, reserved_daily, second_request = reserve_request(incident, daily)
    second_actual = usage_evidence(
        second_request,
        input_tokens=10_000,
        cached_input_tokens=4_000,
        generated_tokens=8_000,
        reasoning_tokens=3_000,
    )
    incident, daily = settle_request(
        reserved, reserved_daily, second_request, second_actual
    )

    assert incident["charged_tokens"] == 31_000
    assert daily["charged_tokens"] == 31_000
    assert incident["usage_status"] == "estimated"
