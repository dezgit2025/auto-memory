"""Fixtures and subprocess workers for the frozen C2 budget-store tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_recall.codex_fix.budget_store import (
    ApprovalEvent,
    BudgetStore,
    TestHooks,
)
from session_recall.codex_fix.contracts import digest


CONTROLLER_ID = "controller-1"
INPUT_DIGEST = "sha256:" + "1" * 64
DAY_ONE = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)


def model_policy() -> dict[str, Any]:
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


class FrozenClock:
    def __init__(self, value: datetime = DAY_ONE) -> None:
        self.value = value

    def now_utc(self) -> datetime:
        return self.value


class FakeApprovalSource:
    source_id = "reviewed-human-source-v1"

    def __init__(self, decision: str = "silence", *, wrong_binding: bool = False):
        self.decision = decision
        self.wrong_binding = wrong_binding
        self.calls: list[dict[str, Any]] = []

    def resolve(self, challenge: dict[str, Any]) -> ApprovalEvent | None:
        self.calls.append(challenge)
        if self.decision != "approve":
            return None
        challenge_digest = digest(challenge)
        if self.wrong_binding:
            challenge_digest = "sha256:" + "f" * 64
        return ApprovalEvent(
            source_id=self.source_id,
            event_id="human-event-1",
            challenge_digest=challenge_digest,
            decision="continue",
            actor_label="maintainer",
            approved_at="2026-09-20T08:05:00Z",
        )


def make_store(
    root: Path,
    *,
    clock: FrozenClock | None = None,
    source: FakeApprovalSource | None = None,
    hooks: TestHooks | None = None,
) -> BudgetStore:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return BudgetStore(
        root,
        CONTROLLER_ID,
        model_policy(),
        clock=clock or FrozenClock(),
        approval_source=source,
        test_hooks=hooks,
    )


def initialize_with_incident(
    store: BudgetStore, incident_id: str = "incident-1"
) -> dict[str, Any]:
    record = store.initialize()
    return store.create_incident(
        incident_id,
        INPUT_DIGEST,
        expected_revision=record["revision"],
    )


def usage_evidence(
    reservation: dict[str, Any],
    *,
    basis: str = "actual",
    final: bool = True,
    input_tokens: int = 10_000,
    generated_tokens: int = 8_000,
) -> dict[str, Any]:
    return {
        "format_version": 2,
        "reservation_digest": digest(reservation),
        "transport_request_id": "request-1",
        "requested_model": "gpt-6-astra",
        "reported_model": "gpt-6-astra",
        "requested_effort": "medium",
        "reported_effort": "medium",
        "usage_scope": "per_request",
        "usage_accounting": "estimated_with_actual_reconciliation_v1",
        "usage_basis": basis,
        "usage_final": final,
        "response_status": "completed" if final else "interrupted",
        "input_tokens": input_tokens,
        "cached_input_tokens": min(2_000, input_tokens),
        "generated_tokens": generated_tokens,
        "reasoning_tokens": min(1_000, generated_tokens),
    }


def _exit_on(target: str):
    def on_phase(phase: str) -> None:
        if phase == target:
            os._exit(91)

    return on_phase


def crash_reserve_worker(root: str, revision: int, phase: str) -> None:
    store = make_store(
        Path(root), hooks=TestHooks(on_phase=_exit_on(phase))
    )
    store.reserve_request("incident-1", expected_revision=revision)


def concurrent_reserve_worker(
    root: str,
    incident_id: str,
    revision: int,
    barrier: Any,
    results: Any,
) -> None:
    store = make_store(Path(root))
    barrier.wait()
    try:
        store.reserve_request(incident_id, expected_revision=revision)
    except Exception as exc:  # subprocess reports only the stable refusal code
        results.put(("error", getattr(exc, "code", type(exc).__name__)))
    else:
        results.put(("ok", incident_id))


def crash_approval_worker(root: str, revision: int, challenge_id: str) -> None:
    store = make_store(
        Path(root),
        source=FakeApprovalSource("approve"),
        hooks=TestHooks(on_phase=_exit_on("after_replace")),
    )
    store.apply_verified_approval(challenge_id, expected_revision=revision)
