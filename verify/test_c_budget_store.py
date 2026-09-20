"""Frozen durability and provenance tests for the C2 budget store."""

from __future__ import annotations

import multiprocessing
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from session_recall.codex_fix.contracts import ContractError

from verify.c_budget_store_fixtures import (
    CONTROLLER_ID,
    INPUT_DIGEST,
    FakeApprovalSource,
    FrozenClock,
    concurrent_reserve_worker,
    crash_approval_worker,
    crash_reserve_worker,
    initialize_with_incident,
    make_store,
    usage_evidence,
)


RECORD_KEYS = set(
    "format_version controller_id policy_digest revision initialized_at updated_at "
    "incidents days grants reservations".split()
)


def _ledger_path(root: Path) -> Path:
    return root / "budget-v2" / "controller-ledger.json"


def _bytes(root: Path) -> bytes:
    return _ledger_path(root).read_bytes()


def _incident(record, incident_id="incident-1"):
    return next(item for item in record["incidents"] if item["incident_id"] == incident_id)


def test_explicit_initialization_and_unsafe_state_fail_closed(tmp_path):
    root = tmp_path / "managed"
    store = make_store(root)
    with pytest.raises(ContractError):
        store.read()
    assert not (root / "budget-v2").exists()

    record = store.initialize()
    assert set(record) == RECORD_KEYS
    assert record["controller_id"] == CONTROLLER_ID
    assert record["revision"] == 0
    assert record["incidents"] == record["days"] == []
    assert record["grants"] == record["reservations"] == []
    assert stat.S_IMODE((root / "budget-v2").stat().st_mode) == 0o700
    assert stat.S_IMODE(_ledger_path(root).stat().st_mode) == 0o600
    original = _bytes(root)
    with pytest.raises(ContractError):
        store.initialize()
    assert _bytes(root) == original

    _ledger_path(root).write_text("{}", encoding="utf-8")
    corrupt = _bytes(root)
    with pytest.raises(ContractError):
        store.read()
    with pytest.raises(ContractError):
        store.initialize()
    assert _bytes(root) == corrupt

    unsafe_root = tmp_path / "unsafe"
    unsafe_root.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    (unsafe_root / "budget-v2").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ContractError):
        make_store(unsafe_root).initialize()


@pytest.mark.parametrize(
    ("phase", "expected_delta"),
    [("before_replace", 0), ("after_replace", 1)],
)
def test_real_process_crash_leaves_complete_old_or_new_record(
    tmp_path, phase, expected_delta
):
    root = tmp_path / phase
    store = make_store(root)
    base = initialize_with_incident(store)
    revision = base["revision"]
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=crash_reserve_worker,
        args=(str(root), revision, phase),
    )
    process.start()
    process.join(10)
    assert process.exitcode == 91

    record = store.read()
    assert record["revision"] == revision + expected_delta
    assert len(record["reservations"]) == expected_delta
    stray = _ledger_path(root).with_name(".controller-ledger.stray.tmp")
    stray.write_text("not-json", encoding="utf-8")
    assert store.read() == record


def test_concurrent_reserve_serializes_and_allows_one_global_unresolved(tmp_path):
    root = tmp_path / "concurrent"
    store = make_store(root)
    record = initialize_with_incident(store, "incident-1")
    record = store.create_incident(
        "incident-2", INPUT_DIGEST, expected_revision=record["revision"]
    )
    revision = record["revision"]
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    processes = [
        context.Process(
            target=concurrent_reserve_worker,
            args=(str(root), incident_id, revision, barrier, results),
        )
        for incident_id in ("incident-1", "incident-2")
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    outcomes = [results.get(timeout=2), results.get(timeout=2)]
    assert [item[0] for item in outcomes].count("ok") == 1
    record = store.read()
    assert len(record["reservations"]) == 1
    assert sum(item["held_tokens"] for item in record["incidents"]) == 32_000


def test_challenge_uses_trusted_bound_event_once_and_silence_writes_nothing(tmp_path):
    root = tmp_path / "approval"
    silent = FakeApprovalSource()
    store = make_store(root, source=silent)
    record = initialize_with_incident(store)
    request = store.reserve_request("incident-1", expected_revision=record["revision"])
    record = store.read()
    record = store.settle_request(
        request["reservation_id"],
        usage_evidence(request, input_tokens=0, generated_tokens=0),
        expected_revision=record["revision"],
    )
    challenge = store.checkpoint_for_approval(
        "incident-1", expected_revision=record["revision"]
    )
    challenged = store.read()
    original = _bytes(root)
    assert store.apply_verified_approval(
        challenge["challenge_id"], expected_revision=challenged["revision"]
    ) == challenged
    assert len(silent.calls) == 1
    assert _bytes(root) == original

    wrong = make_store(root, source=FakeApprovalSource("approve", wrong_binding=True))
    with pytest.raises(ContractError):
        wrong.apply_verified_approval(
            challenge["challenge_id"], expected_revision=challenged["revision"]
        )
    assert _bytes(root) == original

    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=crash_approval_worker,
        args=(str(root), challenged["revision"], challenge["challenge_id"]),
    )
    process.start()
    process.join(10)
    assert process.exitcode == 91
    approved = store.read()
    assert _incident(approved)["allowance_tokens"] == 64_000
    consumed = approved["grants"][0]
    assert consumed["status"] == "consumed"
    assert consumed["approval_event_id"] == "human-event-1"
    assert consumed["grant_digest"] is not None
    approved_bytes = _bytes(root)
    with pytest.raises(ContractError):
        make_store(root, source=FakeApprovalSource("approve")).apply_verified_approval(
            challenge["challenge_id"], expected_revision=approved["revision"]
        )
    assert _bytes(root) == approved_bytes


def test_estimate_then_actual_reconciles_delta_idempotently_and_records_overshoot(
    tmp_path,
):
    root = tmp_path / "usage"
    store = make_store(root)
    record = initialize_with_incident(store)
    request = store.reserve_request("incident-1", expected_revision=record["revision"])
    record = store.read()
    estimate = usage_evidence(
        request, basis="estimated", input_tokens=7_000, generated_tokens=6_000
    )
    record = store.settle_request(
        request["reservation_id"], estimate, expected_revision=record["revision"]
    )
    assert _incident(record)["charged_tokens"] == 13_000
    assert _incident(record)["usage_status"] == "estimated"

    actual = usage_evidence(request, input_tokens=10_000, generated_tokens=8_000)
    record = store.settle_request(
        request["reservation_id"], actual, expected_revision=record["revision"]
    )
    assert _incident(record)["charged_tokens"] == 18_000
    assert _incident(record)["usage_status"] == "actual"
    assert record["reservations"][0]["estimated_tokens"] == 13_000
    assert record["reservations"][0]["actual_tokens"] == 18_000
    settled = _bytes(root)
    same = store.settle_request(
        request["reservation_id"], actual, expected_revision=record["revision"]
    )
    assert same == record
    assert _bytes(root) == settled

    conflicting = usage_evidence(request, input_tokens=10_001, generated_tokens=8_000)
    with pytest.raises(ContractError):
        store.settle_request(
            request["reservation_id"],
            conflicting,
            expected_revision=record["revision"],
        )
    assert _bytes(root) == settled

    over_root = tmp_path / "overshoot"
    over_store = make_store(over_root)
    over_record = initialize_with_incident(over_store)
    over_request = over_store.reserve_request(
        "incident-1", expected_revision=over_record["revision"]
    )
    over_record = over_store.read()
    over_record = over_store.settle_request(
        over_request["reservation_id"],
        usage_evidence(over_request, input_tokens=17_000, generated_tokens=18_000),
        expected_revision=over_record["revision"],
    )
    assert _incident(over_record)["charged_tokens"] == 35_000
    assert _incident(over_record)["state"] == "awaiting_budget_approval"


def test_reservation_day_survives_midnight_and_capacity_failure_preserves_bytes(tmp_path):
    root = tmp_path / "days"
    clock = FrozenClock()
    store = make_store(root, clock=clock)
    record = initialize_with_incident(store)
    request = store.reserve_request("incident-1", expected_revision=record["revision"])
    clock.value = datetime(2026, 9, 21, 1, 0, tzinfo=timezone.utc)
    record = store.read()
    record = store.settle_request(
        request["reservation_id"],
        usage_evidence(request),
        expected_revision=record["revision"],
    )
    assert record["days"][0]["utc_day"] == "2026-09-20"
    assert record["days"][0]["charged_tokens"] == 18_000
    record = store.create_incident(
        "incident-2", INPUT_DIGEST, expected_revision=record["revision"]
    )
    assert [item["utc_day"] for item in record["days"]] == [
        "2026-09-20",
        "2026-09-21",
    ]
    clock.value = datetime(2026, 9, 19, 23, 0, tzinfo=timezone.utc)
    before = _bytes(root)
    with pytest.raises(ContractError):
        store.create_incident(
            "incident-3", INPUT_DIGEST, expected_revision=record["revision"]
        )
    assert _bytes(root) == before

    cap_root = tmp_path / "capacity"
    cap_store = make_store(cap_root)
    cap_record = cap_store.initialize()
    for index in range(32):
        cap_record = cap_store.create_incident(
            f"incident-{index:02d}",
            INPUT_DIGEST,
            expected_revision=cap_record["revision"],
        )
    full = _bytes(cap_root)
    with pytest.raises(ContractError):
        cap_store.create_incident(
            "incident-overflow",
            INPUT_DIGEST,
            expected_revision=cap_record["revision"],
        )
    assert _bytes(cap_root) == full
