"""Frozen builders for the Stage C budget contract tests."""

from __future__ import annotations

from copy import deepcopy

from session_recall.codex_fix.contracts import digest
from session_recall.codex_fix.policy import model_policy as active_model_policy


SHA_INPUT = "sha256:" + "1" * 64
SHA_PREVIOUS = "sha256:" + "2" * 64
CONTROLLER_ID = "controller-1"
INCIDENT_ID = "incident-1"
UTC_DAY = "2026-09-20"


def model_policy(**changes):
    value = active_model_policy()
    value.update(changes)
    return value


def incident_ledger(**changes):
    policy_digest = digest(model_policy())
    value = {
        "format_version": 1,
        "controller_id": CONTROLLER_ID,
        "incident_id": INCIDENT_ID,
        "created_utc_day": UTC_DAY,
        "revision": 0,
        "previous_checkpoint_digest": None,
        "input_digest": SHA_INPUT,
        "policy_digest": policy_digest,
        "allowance_tokens": 32_000,
        "charged_tokens": 0,
        "held_tokens": 0,
        "requests_allowed": 1,
        "requests_started": 0,
        "grants_consumed": 0,
        "state": "ready",
        "usage_status": "none",
        "current_reservation_digest": None,
    }
    value.update(changes)
    return value


def daily_ledger(**changes):
    value = {
        "format_version": 1,
        "controller_id": CONTROLLER_ID,
        "utc_day": UTC_DAY,
        "revision": 0,
        "previous_checkpoint_digest": None,
        "policy_digest": digest(model_policy()),
        "ceiling_tokens": 64_000,
        "charged_tokens": 0,
        "held_tokens": 0,
    }
    if changes.get("revision", 0) > 0 and "previous_checkpoint_digest" not in changes:
        value["previous_checkpoint_digest"] = SHA_PREVIOUS
    value.update(changes)
    return value


def budget_grant(incident=None, daily=None, **changes):
    incident = deepcopy(incident or incident_ledger())
    daily = deepcopy(daily or daily_ledger())
    value = {
        "format_version": 1,
        "grant_id": "grant-1",
        "decision": "continue",
        "controller_id": incident["controller_id"],
        "incident_id": incident["incident_id"],
        "input_digest": incident["input_digest"],
        "policy_digest": incident["policy_digest"],
        "ledger_revision": incident["revision"],
        "checkpoint_digest": digest(incident),
        "daily_ledger_digest": digest(daily),
        "grant_tokens": 32_000,
        "new_incident_ceiling_tokens": incident["allowance_tokens"] + 32_000,
        "request_allowance": 1,
        "daily_ceiling_override_tokens": None,
        "actor_label": "maintainer",
        "approved_at": "2026-09-20T08:00:00Z",
    }
    value.update(changes)
    return value


def reservation(incident=None, daily=None, **changes):
    incident = deepcopy(incident or incident_ledger())
    daily = deepcopy(daily or daily_ledger())
    value = {
        "format_version": 1,
        "reservation_id": "reservation-1",
        "controller_id": incident["controller_id"],
        "incident_id": incident["incident_id"],
        "utc_day": daily["utc_day"],
        "input_digest": incident["input_digest"],
        "policy_digest": incident["policy_digest"],
        "ledger_revision": incident["revision"],
        "checkpoint_digest": digest(incident),
        "daily_ledger_revision": daily["revision"],
        "daily_ledger_digest": digest(daily),
        "request_ordinal": incident["requests_started"] + 1,
        "estimated_reserved_tokens": 32_000,
        "reservation_basis": "estimate",
        "pause_at_tokens": incident["allowance_tokens"] - 4_000,
    }
    value.update(changes)
    return value


def usage_evidence(request_reservation=None, **changes):
    request_reservation = deepcopy(request_reservation or reservation())
    value = {
        "format_version": 2,
        "reservation_digest": digest(request_reservation),
        "transport_request_id": "request-1",
        "requested_model": "gpt-6-astra",
        "reported_model": "gpt-6-astra",
        "requested_effort": "medium",
        "reported_effort": "medium",
        "usage_scope": "per_request",
        "usage_accounting": "estimated_with_actual_reconciliation_v1",
        "usage_basis": "actual",
        "usage_final": True,
        "response_status": "completed",
        "input_tokens": 10_000,
        "cached_input_tokens": 4_000,
        "generated_tokens": 8_000,
        "reasoning_tokens": 3_000,
    }
    value.update(changes)
    return value
