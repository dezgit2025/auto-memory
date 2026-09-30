"""Adversarial cross-record and file-safety regressions for C2 BudgetStore."""

from __future__ import annotations

import json
import multiprocessing
import os
import stat
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from session_recall.codex_fix.contracts import ContractError, canonical_bytes, digest
from verify.c_budget_store_fixtures import (
    FakeApprovalSource,
    FrozenClock,
    initialize_with_incident,
    make_store,
    usage_evidence,
)


def _path(root: Path) -> Path:
    return root / "budget-v2" / "controller-ledger.json"


def _write(root: Path, record: dict) -> bytes:
    raw = canonical_bytes(record)
    _path(root).write_bytes(raw)
    _path(root).chmod(0o600)
    return raw


def _held(root: Path, incident_id: str = "incident-1"):
    store = make_store(root)
    record = initialize_with_incident(store, incident_id)
    request = store.reserve_request(incident_id, expected_revision=record["revision"])
    return store, store.read(), request


def _approval_ready(root: Path, incident_id: str = "incident-1", source=None):
    store = make_store(root, source=source)
    record = initialize_with_incident(store, incident_id)
    request = store.reserve_request(incident_id, expected_revision=record["revision"])
    record = store.read()
    record = store.settle_request(
        request["reservation_id"],
        usage_evidence(request, input_tokens=0, generated_tokens=0),
        expected_revision=record["revision"],
    )
    challenge = store.checkpoint_for_approval(
        incident_id, expected_revision=record["revision"]
    )
    return store, store.read(), challenge


def _rebind_challenge(grant: dict, **changes) -> None:
    challenge = {**grant["challenge"], **changes}
    projection = {key: value for key, value in challenge.items() if key != "challenge_id"}
    challenge["challenge_id"] = digest(projection)[7:]
    grant["challenge_id"] = challenge["challenge_id"]
    grant["challenge"] = challenge


def _assert_corrupt_read_rejected(store, root, record):
    corrupt = _write(root, record)
    with pytest.raises(ContractError):
        store.read()
    assert _path(root).read_bytes() == corrupt


def test_record_rejects_two_global_holds_and_unbound_request_fields(tmp_path):
    store_a, record_a, _request_a = _held(tmp_path / "a", "incident-1")
    _store_b, record_b, _request_b = _held(tmp_path / "b", "incident-2")
    combined = deepcopy(record_a)
    combined["incidents"] = sorted(
        [record_a["incidents"][0], record_b["incidents"][0]],
        key=lambda item: item["incident_id"],
    )
    combined["reservations"] = sorted(
        [record_a["reservations"][0], record_b["reservations"][0]],
        key=lambda item: item["reservation_id"],
    )
    combined["days"][0]["held_tokens"] = 64_000
    _assert_corrupt_read_rejected(store_a, tmp_path / "a", combined)

    for field, value in (
        ("controller_id", "controller-2"),
        ("policy_digest", "sha256:" + "8" * 64),
        ("input_digest", "sha256:" + "9" * 64),
    ):
        corrupt = deepcopy(record_a)
        request = corrupt["reservations"][0]["request"]
        request[field] = value
        corrupt["incidents"][0]["current_reservation_digest"] = digest(request)
        _assert_corrupt_read_rejected(store_a, tmp_path / "a", corrupt)

    corrupt = deepcopy(record_a)
    request = corrupt["reservations"][0]["request"]
    request["request_ordinal"] = 2
    corrupt["incidents"][0]["current_reservation_digest"] = digest(request)
    _assert_corrupt_read_rejected(store_a, tmp_path / "a", corrupt)


def test_record_rejects_missing_reservations_and_inconsistent_evidence_pairs(tmp_path):
    root = tmp_path / "pairs"
    store, record, request = _held(root)
    record = store.settle_request(
        request["reservation_id"],
        usage_evidence(request, final=False),
        expected_revision=record["revision"],
    )
    valid_nonfinal = deepcopy(record)
    reservation = valid_nonfinal["reservations"][0]
    assert reservation["estimated_evidence_digest"] is not None
    assert reservation["estimated_tokens"] is not None
    for missing in ("estimated_evidence_digest", "estimated_tokens"):
        corrupt = deepcopy(valid_nonfinal)
        corrupt["reservations"][0][missing] = None
        _assert_corrupt_read_rejected(store, root, corrupt)
    corrupt = deepcopy(valid_nonfinal)
    corrupt["incidents"][0]["state"] = "in_flight"
    _assert_corrupt_read_rejected(store, root, corrupt)
    _write(root, valid_nonfinal)

    final_estimate = usage_evidence(
        request, basis="estimated", input_tokens=7_000, generated_tokens=6_000
    )
    record = store.settle_request(
        request["reservation_id"], final_estimate, expected_revision=record["revision"]
    )
    record = store.settle_request(
        request["reservation_id"],
        usage_evidence(request),
        expected_revision=record["revision"],
    )
    for missing in ("estimated_evidence_digest", "estimated_tokens"):
        corrupt = deepcopy(record)
        corrupt["reservations"][0][missing] = None
        _assert_corrupt_read_rejected(store, root, corrupt)

    settled_root = tmp_path / "missing"
    settled_store, settled, settled_request = _held(settled_root)
    settled = settled_store.settle_request(
        settled_request["reservation_id"],
        usage_evidence(settled_request, input_tokens=0, generated_tokens=0),
        expected_revision=settled["revision"],
    )
    settled["reservations"] = []
    _assert_corrupt_read_rejected(settled_store, settled_root, settled)


def test_challenges_grant_digest_and_human_event_are_cross_bound(tmp_path):
    root = tmp_path / "challenge"
    store, pending, _challenge = _approval_ready(root)
    for changes in (
        {"incident_id": "missing-incident"},
        {"input_digest": "sha256:" + "9" * 64},
    ):
        corrupt = deepcopy(pending)
        _rebind_challenge(corrupt["grants"][0], **changes)
        _assert_corrupt_read_rejected(store, root, corrupt)

    approved_store, approved, _challenge = _approval_ready(
        tmp_path / "approved", source=FakeApprovalSource("approve")
    )
    approved = approved_store.apply_verified_approval(
        approved["grants"][0]["challenge_id"], expected_revision=approved["revision"]
    )
    corrupt = deepcopy(approved)
    corrupt["grants"][0]["grant_digest"] = "sha256:" + "7" * 64
    _assert_corrupt_read_rejected(approved_store, tmp_path / "approved", corrupt)

    second_store, second, _challenge = _approval_ready(
        tmp_path / "second", "incident-2", FakeApprovalSource("approve")
    )
    second = second_store.apply_verified_approval(
        second["grants"][0]["challenge_id"], expected_revision=second["revision"]
    )
    replay = deepcopy(approved)
    replay["incidents"] = sorted(
        [approved["incidents"][0], second["incidents"][0]],
        key=lambda item: item["incident_id"],
    )
    replay["grants"] = sorted(
        [approved["grants"][0], second["grants"][0]],
        key=lambda item: item["challenge_id"],
    )
    replay["reservations"] = sorted(
        [approved["reservations"][0], second["reservations"][0]],
        key=lambda item: item["reservation_id"],
    )
    _assert_corrupt_read_rejected(approved_store, tmp_path / "approved", replay)


def test_backward_clock_refuses_settlement_and_approval_without_writes(tmp_path):
    clock = FrozenClock()
    settle_store, settle_record, request = _held(tmp_path / "settle-clock")
    settle_store.clock = clock
    clock.value = datetime(2026, 9, 20, 7, 59, tzinfo=timezone.utc)
    before = _path(tmp_path / "settle-clock").read_bytes()
    with pytest.raises(ContractError):
        settle_store.settle_request(
            request["reservation_id"],
            usage_evidence(request),
            expected_revision=settle_record["revision"],
        )
    assert _path(tmp_path / "settle-clock").read_bytes() == before

    approval_clock = FrozenClock()
    approval_store, approval_record, challenge = _approval_ready(
        tmp_path / "approval-clock", source=FakeApprovalSource("approve")
    )
    approval_store.clock = approval_clock
    approval_clock.value = datetime(2026, 9, 20, 7, 59, tzinfo=timezone.utc)
    before = _path(tmp_path / "approval-clock").read_bytes()
    with pytest.raises(ContractError):
        approval_store.apply_verified_approval(
            challenge["challenge_id"], expected_revision=approval_record["revision"]
        )
    assert _path(tmp_path / "approval-clock").read_bytes() == before


def _fifo_read_worker(root: str, results) -> None:
    try:
        make_store(Path(root)).read()
    except Exception as exc:
        results.put(getattr(exc, "code", type(exc).__name__))
    else:
        results.put("accepted")


def test_ledger_file_type_mode_size_and_encoding_fail_closed(tmp_path):
    mutations = ("symlink", "directory", "mode", "oversize", "duplicate", "pretty")
    for name in mutations:
        root = tmp_path / name
        store = make_store(root)
        valid = store.initialize()
        path = _path(root)
        if name == "symlink":
            target = tmp_path / "outside.json"
            target.write_bytes(canonical_bytes(valid))
            path.unlink()
            path.symlink_to(target)
        elif name == "directory":
            path.unlink()
            path.mkdir()
        elif name == "mode":
            path.chmod(0o644)
        elif name == "oversize":
            path.write_bytes(b"x" * (1024 * 1024 + 1))
        elif name == "duplicate":
            path.write_bytes(b'{"format_version":1,"format_version":1}')
        else:
            path.write_text(json.dumps(valid, indent=2), encoding="utf-8")
        preserved = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        with pytest.raises(ContractError):
            store.read()
        with pytest.raises(ContractError):
            store.initialize()
        if preserved is not None:
            assert path.read_bytes() == preserved

    fifo_root = tmp_path / "fifo"
    fifo_store = make_store(fifo_root)
    fifo_store.initialize()
    fifo_path = _path(fifo_root)
    fifo_path.unlink()
    os.mkfifo(fifo_path, 0o600)
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    process = context.Process(target=_fifo_read_worker, args=(str(fifo_root), results))
    process.start()
    process.join(2)
    assert process.exitcode == 0
    assert results.get(timeout=1) != "accepted"
    assert stat.S_ISFIFO(fifo_path.lstat().st_mode)
