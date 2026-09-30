"""Derived-state proofs that prevent naive C2 validator hardening."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from session_recall.codex_fix.budget_store import ApprovalEvent
from session_recall.codex_fix.contracts import ContractError, canonical_bytes, digest
from verify.c_budget_store_fixtures import (
    INPUT_DIGEST,
    FrozenClock,
    initialize_with_incident,
    make_store,
    usage_evidence,
)


class SequencedApprovalSource:
    source_id = "sequenced-human-source-v1"

    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, challenge):
        self.calls += 1
        return ApprovalEvent(
            source_id=self.source_id,
            event_id=f"human-event-{self.calls}",
            challenge_digest=digest(challenge),
            decision="continue",
            actor_label="maintainer",
            approved_at=f"2026-09-20T08:0{self.calls}:00Z",
        )


def _path(root: Path) -> Path:
    return root / "budget-v2" / "controller-ledger.json"


def _write(root: Path, record: dict) -> bytes:
    raw = canonical_bytes(record)
    _path(root).write_bytes(raw)
    _path(root).chmod(0o600)
    return raw


def _rejects_without_write(store, root: Path, record: dict) -> None:
    corrupt = _write(root, record)
    with pytest.raises(ContractError):
        store.read()
    assert _path(root).read_bytes() == corrupt


def _held(root: Path):
    store = make_store(root)
    record = initialize_with_incident(store)
    request = store.reserve_request("incident-1", expected_revision=record["revision"])
    return store, store.read(), request


def _estimated(root: Path, *, source=None):
    store, record, request = _held(root)
    if source is not None:
        store.approval_source = source
    evidence = usage_evidence(
        request, basis="estimated", input_tokens=7_000, generated_tokens=6_000
    )
    record = store.settle_request(
        request["reservation_id"], evidence, expected_revision=record["revision"]
    )
    return store, record, request


def _rebind_pending(grant: dict, **changes) -> None:
    challenge = {**grant["challenge"], **changes}
    projection = {key: value for key, value in challenge.items() if key != "challenge_id"}
    challenge["challenge_id"] = digest(projection)[7:]
    grant["challenge_id"] = challenge["challenge_id"]
    grant["challenge"] = challenge


def _grant_digest(grant_record: dict) -> str:
    challenge = grant_record["challenge"]
    grant = {
        "format_version": 1,
        "grant_id": challenge["challenge_id"],
        "decision": grant_record["approval_decision"],
        "controller_id": challenge["controller_id"],
        "incident_id": challenge["incident_id"],
        "input_digest": challenge["input_digest"],
        "policy_digest": challenge["policy_digest"],
        "ledger_revision": challenge["ledger_revision"],
        "checkpoint_digest": challenge["checkpoint_digest"],
        "daily_ledger_digest": challenge["daily_ledger_digest"],
        "grant_tokens": challenge["grant_tokens"],
        "new_incident_ceiling_tokens": challenge["new_incident_ceiling_tokens"],
        "request_allowance": challenge["request_allowance"],
        "daily_ceiling_override_tokens": challenge["daily_ceiling_override_tokens"],
        "actor_label": grant_record["approval_actor_label"],
        "approved_at": grant_record["approval_approved_at"],
    }
    return digest(grant)


def test_actual_reconciliation_retires_pending_history_and_allows_fresh_challenge(
    tmp_path,
):
    root = tmp_path / "stale-pending"
    source = SequencedApprovalSource()
    store, record, request = _estimated(root, source=source)
    old = store.checkpoint_for_approval(
        "incident-1", expected_revision=record["revision"]
    )
    record = store.read()
    actual = usage_evidence(request, input_tokens=10_000, generated_tokens=8_000)
    record = store.settle_request(
        request["reservation_id"], actual, expected_revision=record["revision"]
    )
    assert record["incidents"][0]["charged_tokens"] == 18_000
    historical = next(
        item for item in record["grants"] if item["challenge_id"] == old["challenge_id"]
    )
    assert historical["status"] not in {"pending", "consumed"}
    assert historical["approval_event_id"] is None
    before = _path(root).read_bytes()
    with pytest.raises(ContractError):
        store.apply_verified_approval(
            old["challenge_id"], expected_revision=record["revision"]
        )
    assert source.calls == 0
    assert _path(root).read_bytes() == before
    fresh = store.checkpoint_for_approval(
        "incident-1", expected_revision=record["revision"]
    )
    updated = store.read()
    incident, day = updated["incidents"][0], updated["days"][0]
    assert fresh["checkpoint_digest"] == digest(incident)
    assert fresh["daily_ledger_digest"] == digest(day)
    assert fresh["new_incident_ceiling_tokens"] == incident["allowance_tokens"] + 32_000
    assert sum(item["status"] == "pending" for item in updated["grants"]) == 1
    assert len(updated["grants"]) == 2


def test_other_incident_daily_mutation_retires_pending_without_deadlock(tmp_path):
    root = tmp_path / "shared-day"
    source = SequencedApprovalSource()
    store, record, _request = _estimated(root, source=source)
    old = store.checkpoint_for_approval(
        "incident-1", expected_revision=record["revision"]
    )
    record = store.read()
    record = store.create_incident(
        "incident-2", INPUT_DIGEST, expected_revision=record["revision"]
    )
    second = store.reserve_request(
        "incident-2", expected_revision=record["revision"]
    )
    record = store.read()
    record = store.settle_request(
        second["reservation_id"],
        usage_evidence(second, input_tokens=0, generated_tokens=0),
        expected_revision=record["revision"],
    )
    historical = next(
        item for item in record["grants"] if item["challenge_id"] == old["challenge_id"]
    )
    assert historical["status"] not in {"pending", "consumed"}
    before = _path(root).read_bytes()
    with pytest.raises(ContractError):
        store.apply_verified_approval(
            old["challenge_id"], expected_revision=record["revision"]
        )
    assert source.calls == 0
    assert _path(root).read_bytes() == before
    fresh = store.checkpoint_for_approval(
        "incident-1", expected_revision=record["revision"]
    )
    assert fresh["daily_ledger_digest"] == digest(store.read()["days"][0])


def test_midnight_retires_old_question_and_allows_new_day_challenge(tmp_path):
    root = tmp_path / "midnight"
    clock = FrozenClock()
    source = SequencedApprovalSource()
    store, record, _request = _estimated(root, source=source)
    store.clock = clock
    old = store.checkpoint_for_approval(
        "incident-1", expected_revision=record["revision"]
    )
    record = store.read()
    clock.value = datetime(2026, 9, 21, 0, 1, tzinfo=timezone.utc)
    with pytest.raises(ContractError):
        store.apply_verified_approval(
            old["challenge_id"], expected_revision=record["revision"]
        )
    retired = store.read()
    historical = next(
        item for item in retired["grants"] if item["challenge_id"] == old["challenge_id"]
    )
    assert historical["status"] not in {"pending", "consumed"}
    assert retired["incidents"][0]["allowance_tokens"] == 32_000
    assert source.calls == 0
    fresh = store.checkpoint_for_approval(
        "incident-1", expected_revision=retired["revision"]
    )
    assert fresh["utc_day"] == "2026-09-21"


def test_pending_challenges_are_unique_and_exactly_bound_to_current_state(tmp_path):
    root = tmp_path / "pending"
    store, record, _request = _estimated(root)
    store.checkpoint_for_approval("incident-1", expected_revision=record["revision"])
    pending = store.read()
    duplicate = deepcopy(pending)
    second = deepcopy(duplicate["grants"][0])
    _rebind_pending(second, created_at="2026-09-20T08:01:00Z")
    duplicate["grants"] = sorted(
        [*duplicate["grants"], second], key=lambda item: item["challenge_id"]
    )
    _rejects_without_write(store, root, duplicate)
    mutations = (
        {"ledger_revision": pending["incidents"][0]["revision"] + 1},
        {"checkpoint_digest": "sha256:" + "7" * 64},
        {"daily_ledger_digest": "sha256:" + "8" * 64},
        {"new_incident_ceiling_tokens": 96_000},
    )
    for changes in mutations:
        corrupt = deepcopy(pending)
        _rebind_pending(corrupt["grants"][0], **changes)
        _rejects_without_write(store, root, corrupt)
    corrupt = deepcopy(pending)
    corrupt["incidents"][0]["state"] = "ready"
    _rejects_without_write(store, root, corrupt)


def test_daily_ceiling_and_usage_uncertainty_are_derived_not_self_asserted(tmp_path):
    root = tmp_path / "derived"
    store, record, _request = _estimated(root)
    assert record["incidents"][0]["usage_status"] == "estimated"
    ceiling = deepcopy(record)
    ceiling["days"][0]["ceiling_tokens"] = 96_000
    _rejects_without_write(store, root, ceiling)
    certainty = deepcopy(record)
    certainty["incidents"][0]["usage_status"] = "actual"
    _rejects_without_write(store, root, certainty)


def test_reservation_id_is_recomputed_from_its_deterministic_seed(tmp_path):
    root = tmp_path / "reservation-id"
    store, record, _request = _held(root)
    corrupt = deepcopy(record)
    reservation = corrupt["reservations"][0]
    forged_id = "f" * 64
    reservation["reservation_id"] = forged_id
    reservation["request"]["reservation_id"] = forged_id
    corrupt["incidents"][0]["current_reservation_digest"] = digest(
        reservation["request"]
    )
    _rejects_without_write(store, root, corrupt)


def test_consumed_grant_ceilings_form_exact_32k_sequence(tmp_path):
    root = tmp_path / "grant-sequence"
    source = SequencedApprovalSource()
    store = make_store(root, source=source)
    record = initialize_with_incident(store)
    for _index in range(2):
        request = store.reserve_request(
            "incident-1", expected_revision=record["revision"]
        )
        record = store.read()
        record = store.settle_request(
            request["reservation_id"],
            usage_evidence(request, input_tokens=0, generated_tokens=0),
            expected_revision=record["revision"],
        )
        challenge = store.checkpoint_for_approval(
            "incident-1", expected_revision=record["revision"]
        )
        record = store.read()
        record = store.apply_verified_approval(
            challenge["challenge_id"], expected_revision=record["revision"]
        )
    assert record["incidents"][0]["allowance_tokens"] == 96_000
    corrupt = deepcopy(record)
    second = max(
        corrupt["grants"],
        key=lambda item: item["challenge"]["new_incident_ceiling_tokens"],
    )
    _rebind_pending(second, new_incident_ceiling_tokens=64_000)
    second["grant_digest"] = _grant_digest(second)
    corrupt["grants"] = sorted(
        corrupt["grants"], key=lambda item: item["challenge_id"]
    )
    _rejects_without_write(store, root, corrupt)
