"""Focused checks for the versioned 100,000-token Codex repair policy."""

from datetime import datetime

import pytest

from session_recall.codex_fix.budget import new_incident, reserve_request, settle_request
from session_recall.codex_fix.budget_store import BudgetStore
from session_recall.codex_fix.c_contracts import validate_c
from session_recall.codex_fix.contracts import ContractError, digest
from session_recall.codex_fix.policy import model_policy, production_model_policy

from session_recall.codex_fix.tests._c_budget_fixtures import daily_ledger, usage_evidence


class Clock:
    def __init__(self, day):
        self.day = day

    def now_utc(self):
        return datetime.fromisoformat(self.day + "T00:00:00+00:00")


def test_packaged_v3_policy_allows_three_requests_within_100k():
    policy = production_model_policy()
    assert validate_c(policy, "ModelPolicy") is policy
    assert policy["initial_allowance_tokens"] == 100_000
    assert policy["daily_ceiling_tokens"] == 100_000
    assert policy["requests_per_grant"] == 3
    incident = new_incident(
        "controller-1", "incident-1", "sha256:" + "1" * 64, policy,
        utc_day="2026-09-25",
    )
    daily = daily_ledger(
        utc_day="2026-09-25", policy_digest=digest(policy), ceiling_tokens=100_000,
    )
    for ordinal in range(3):
        incident, daily, request = reserve_request(incident, daily)
        incident, daily = settle_request(incident, daily, request, usage_evidence(request, format_version=3))
        assert incident["requests_started"] == ordinal + 1
    assert incident["state"] == "awaiting_budget_approval"
    assert daily["charged_tokens"] == 54_000
    with pytest.raises(ContractError, match="request_unavailable"):
        reserve_request(incident, daily)


def test_v3_preserves_v2_ledger_and_refuses_same_day_budget_reset(tmp_path):
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    old = BudgetStore(root, "controller-1", model_policy(), clock=Clock("2026-09-25"))
    record = old.initialize()
    record = old.create_incident(
        "old-incident", "sha256:" + "1" * 64, expected_revision=record["revision"],
    )
    request = old.reserve_request("old-incident", expected_revision=record["revision"])
    old.settle_request(
        request["reservation_id"], usage_evidence(request),
        expected_revision=old.read()["revision"],
    )
    before = old.path.read_bytes()
    current = BudgetStore(
        root, "controller-1", production_model_policy(), clock=Clock("2026-09-25"),
    )
    with pytest.raises(ContractError, match="legacy_day_budget_pending"):
        current.initialize()
    assert old.path.read_bytes() == before
    assert not current.path.exists()

    next_day = BudgetStore(
        root, "controller-1", production_model_policy(), clock=Clock("2026-09-26"),
    )
    next_day.initialize()
    assert next_day.path.parent.name == "budget-v3"
    assert old.path.read_bytes() == before


def test_v3_durable_store_allows_three_requests(tmp_path):
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    store = BudgetStore(root, "controller-1", production_model_policy(), clock=Clock("2026-09-26"))
    record = store.initialize()
    record = store.create_incident(
        "new-incident", "sha256:" + "3" * 64, expected_revision=record["revision"],
    )
    for ordinal in range(3):
        request = store.reserve_request("new-incident", expected_revision=record["revision"])
        record = store.settle_request(
            request["reservation_id"], usage_evidence(request, format_version=3),
            expected_revision=store.read()["revision"],
        )
        incident = next(item for item in record["incidents"] if item["incident_id"] == "new-incident")
        assert incident["state"] == ("ready" if ordinal < 2 else "awaiting_budget_approval")
    assert record["days"][0]["charged_tokens"] == 54_000
    assert record["days"][0]["ceiling_tokens"] == 100_000
    with pytest.raises(ContractError, match="request_unavailable"):
        store.reserve_request("new-incident", expected_revision=record["revision"])


def test_v3_approved_grant_adds_100k_and_three_requests(tmp_path):
    from session_recall.codex_fix.budget_store import ApprovalEvent

    class Approval:
        source_id = "test"

        def resolve(self, challenge):
            return ApprovalEvent(
                source_id=self.source_id,
                event_id=challenge["challenge_id"],
                challenge_digest=digest(challenge),
                decision="continue",
                actor_label="test-owner",
                approved_at="2026-09-26T00:01:00Z",
            )

    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    store = BudgetStore(
        root, "controller-1", production_model_policy(),
        clock=Clock("2026-09-26"), approval_source=Approval(),
    )
    record = store.initialize()
    record = store.create_incident(
        "new-incident", "sha256:" + "4" * 64, expected_revision=record["revision"],
    )
    for _ in range(3):
        request = store.reserve_request("new-incident", expected_revision=record["revision"])
        record = store.settle_request(
            request["reservation_id"], usage_evidence(request, format_version=3),
            expected_revision=store.read()["revision"],
        )
    challenge = store.checkpoint_for_approval(
        "new-incident", expected_revision=record["revision"],
        daily_ceiling_override_tokens=200_000,
    )
    assert challenge["grant_tokens"] == 100_000
    assert challenge["request_allowance"] == 3
    record = store.apply_verified_approval(
        challenge["challenge_id"], expected_revision=store.read()["revision"],
    )
    incident = next(item for item in record["incidents"] if item["incident_id"] == "new-incident")
    assert incident["allowance_tokens"] == 200_000
    assert incident["requests_allowed"] == 6
    assert incident["state"] == "ready"
    assert record["days"][0]["ceiling_tokens"] == 200_000
