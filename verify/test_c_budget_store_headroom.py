"""Functional proof for human-approved headroom after an actual overshoot."""

from __future__ import annotations

from pathlib import Path

import pytest

from session_recall.codex_fix.budget_store import ApprovalEvent
from session_recall.codex_fix.contracts import ContractError, digest
from verify.c_budget_store_fixtures import (
    initialize_with_incident,
    make_store,
    usage_evidence,
)


class ApprovalSource:
    source_id = "headroom-human-source-v1"

    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, challenge):
        self.calls += 1
        return ApprovalEvent(
            source_id=self.source_id,
            event_id=f"headroom-event-{self.calls}",
            challenge_digest=digest(challenge),
            decision="continue",
            actor_label="maintainer",
            approved_at=f"2026-09-20T08:0{self.calls}:00Z",
        )


def _path(root: Path) -> Path:
    return root / "budget-v2" / "controller-ledger.json"


def _settle_first(store, record, *, input_tokens: int, generated_tokens: int):
    request = store.reserve_request("incident-1", expected_revision=record["revision"])
    record = store.read()
    return store.settle_request(
        request["reservation_id"],
        usage_evidence(
            request,
            input_tokens=input_tokens,
            generated_tokens=generated_tokens,
        ),
        expected_revision=record["revision"],
    )


def _approve(store, record, *, daily_override=None):
    challenge = store.checkpoint_for_approval(
        "incident-1",
        expected_revision=record["revision"],
        daily_ceiling_override_tokens=daily_override,
    )
    record = store.read()
    return store.apply_verified_approval(
        challenge["challenge_id"], expected_revision=record["revision"]
    )


def test_blocked_ready_incident_can_request_another_human_32k_grant(tmp_path):
    root = tmp_path / "blocked-ready"
    source = ApprovalSource()
    store = make_store(root, source=source)
    record = initialize_with_incident(store)
    record = _settle_first(store, record, input_tokens=17_000, generated_tokens=18_000)
    assert record["incidents"][0]["charged_tokens"] == 35_000

    record = _approve(store, record, daily_override=96_000)
    incident = record["incidents"][0]
    assert (incident["allowance_tokens"], incident["requests_started"]) == (64_000, 1)
    assert (incident["requests_allowed"], incident["state"]) == (2, "ready")

    before = _path(root).read_bytes()
    with pytest.raises(ContractError):
        store.reserve_request("incident-1", expected_revision=record["revision"])
    blocked = store.read()
    assert _path(root).read_bytes() == before
    incident = blocked["incidents"][0]
    assert incident["state"] == "ready"
    assert incident["requests_started"] < incident["requests_allowed"]
    assert incident["held_tokens"] == 0

    challenge = store.checkpoint_for_approval(
        "incident-1", expected_revision=blocked["revision"]
    )
    questioned = store.read()
    incident = questioned["incidents"][0]
    assert incident["state"] == "awaiting_budget_approval"
    assert (incident["requests_started"], incident["held_tokens"]) == (1, 0)
    assert challenge["ledger_revision"] == incident["revision"]
    assert challenge["checkpoint_digest"] == digest(incident)
    record = store.apply_verified_approval(
        challenge["challenge_id"], expected_revision=questioned["revision"]
    )
    incident = record["incidents"][0]
    assert (incident["allowance_tokens"], incident["requests_allowed"]) == (96_000, 3)
    request = store.reserve_request(
        "incident-1", expected_revision=record["revision"]
    )
    assert request["request_ordinal"] == 2
    assert source.calls == 2


def test_ready_incident_with_enough_headroom_cannot_prestack_a_grant(tmp_path):
    root = tmp_path / "adequate-headroom"
    store = make_store(root, source=ApprovalSource())
    record = initialize_with_incident(store)
    record = _settle_first(store, record, input_tokens=10_000, generated_tokens=8_000)
    record = _approve(store, record)
    incident = record["incidents"][0]
    assert incident["charged_tokens"] + 32_000 <= incident["allowance_tokens"]
    assert incident["state"] == "ready"
    before = _path(root).read_bytes()

    with pytest.raises(ContractError):
        store.checkpoint_for_approval(
            "incident-1", expected_revision=record["revision"]
        )
    assert _path(root).read_bytes() == before
