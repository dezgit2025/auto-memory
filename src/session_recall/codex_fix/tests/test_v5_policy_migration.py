"""V5 policy migration compatibility and fail-closed behavior."""

from copy import deepcopy

import pytest

from session_recall.codex_fix.budget import consume_grant, new_incident, reserve_request, settle_request
from session_recall.codex_fix.budget_store import BudgetStore
from session_recall.codex_fix.c_contracts import validate_c
from session_recall.codex_fix.contracts import ContractError, canonical_bytes, digest

from ._c_budget_fixtures import budget_grant, daily_ledger, incident_ledger, model_policy, usage_evidence


def _legacy_policy():
    return {
        **model_policy(),
        "format_version": 1,
        "policy_id": "sol-medium-budget-v1",
        "model": "gpt-5.6-sol",
    }


def _legacy_usage(request=None):
    value = usage_evidence(request)
    value.pop("reported_model")
    value.pop("requested_effort")
    value.pop("reported_effort")
    return {
        **value,
        "format_version": 1,
        "requested_model": "gpt-5.6-sol",
        "effective_model": "gpt-5.6-sol",
        "effort": "medium",
    }


def _write_legacy(root, *, state="empty"):
    policy = _legacy_policy()
    incidents = []
    days = []
    reservations = []
    request = None
    if state != "empty":
        incident = new_incident("controller-1", "incident-1", "sha256:" + "1" * 64,
                                policy, utc_day="2026-09-20")
        daily = daily_ledger(policy_digest=digest(policy))
        incident, daily, request = reserve_request(incident, daily)
        reservation_record = {
            "reservation_id": request["reservation_id"], "incident_id": "incident-1",
            "utc_day": "2026-09-20", "request": request, "status": "held",
            "estimated_evidence_digest": None, "actual_evidence_digest": None,
            "estimated_tokens": None, "actual_tokens": None, "charged_tokens": 0,
        }
        if state == "charged":
            evidence = _legacy_usage(request)
            incident, daily = settle_request(incident, daily, request, evidence)
            total = evidence["input_tokens"] + evidence["generated_tokens"]
            reservation_record.update(status="settled_actual",
                                      actual_evidence_digest=digest(evidence),
                                      actual_tokens=total, charged_tokens=total)
        incidents = [incident]
        days = [daily]
        reservations = [reservation_record]
    record = {
        "format_version": 1, "controller_id": "controller-1",
        "policy_digest": digest(policy), "revision": 0,
        "initialized_at": "2026-09-20T00:00:00Z", "updated_at": "2026-09-20T00:00:00Z",
        "incidents": incidents, "days": days, "grants": [], "reservations": reservations,
    }
    directory = root / "budget-v1"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / "controller-ledger.json"
    path.write_bytes(canonical_bytes(record))
    path.chmod(0o600)
    return path, request


def test_v2_policy_has_a_new_identity_and_digest_while_v1_remains_readable():
    current = model_policy()
    legacy = _legacy_policy()
    assert validate_c(current, "ModelPolicy") is current
    assert validate_c(legacy, "ModelPolicy") is legacy
    assert current["model"] == "gpt-6-astra"
    assert current["effort"] == "medium"
    assert digest(current) != digest(legacy)


@pytest.mark.parametrize("invalid", [True, False, {}, []])
def test_policy_and_usage_versions_reject_non_integer_or_unhashable_values(invalid):
    with pytest.raises(ContractError):
        validate_c(model_policy(format_version=invalid), "ModelPolicy")
    with pytest.raises(ContractError):
        validate_c(usage_evidence(format_version=invalid), "UsageEvidence")


def test_old_usage_receipts_remain_readable_and_new_receipts_separate_reports():
    legacy = _legacy_usage()
    assert validate_c(legacy, "UsageEvidence") is legacy
    unreported = usage_evidence(reported_model=None, reported_effort=None)
    assert validate_c(unreported, "UsageEvidence") is unreported


@pytest.mark.parametrize(
    "changes",
    [
        {"reported_model": "gpt-5.6-sol"},
        {"reported_effort": "high"},
        {"requested_model": "gpt-5.6-sol"},
        {"requested_effort": "high"},
    ],
)
def test_explicit_requested_or_reported_setting_mismatch_is_rejected(changes):
    with pytest.raises(ContractError):
        validate_c(usage_evidence(**changes), "UsageEvidence")


def test_grant_from_previous_policy_digest_cannot_be_consumed():
    incident = incident_ledger()
    daily = daily_ledger()
    stale = deepcopy(budget_grant(incident, daily))
    stale["policy_digest"] = digest(_legacy_policy())
    with pytest.raises(ContractError, match="grant_binding_mismatch"):
        consume_grant(incident, daily, stale)


def test_v2_store_preserves_the_v1_history_namespace(tmp_path):
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)

    class Clock:
        def now_utc(self):
            from datetime import datetime, timezone
            return datetime(2026, 9, 20, tzinfo=timezone.utc)

    history, _request = _write_legacy(root)
    original = history.read_bytes()

    store = BudgetStore(root, "controller-1", model_policy(), clock=Clock())
    store.initialize()
    assert store.path == root / "budget-v2" / "controller-ledger.json"
    assert history.read_bytes() == original


def test_legacy_policy_is_readable_but_cannot_reactivate_stale_grants(tmp_path):
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)

    class Clock:
        def now_utc(self):
            from datetime import datetime, timezone
            return datetime(2026, 9, 20, tzinfo=timezone.utc)

    legacy = BudgetStore(root, "controller-1", _legacy_policy(), clock=Clock())
    with pytest.raises(ContractError, match="legacy_policy_read_only"):
        legacy.initialize()
    legacy.policy["format_version"] = 2
    with pytest.raises(ContractError, match="legacy_policy_read_only"):
        legacy.initialize()


def test_v2_initialization_rejects_malformed_or_current_day_legacy_usage(tmp_path):
    from datetime import datetime

    class Clock:
        def __init__(self, day):
            self.day = day

        def now_utc(self):
            return datetime.fromisoformat(self.day + "T00:00:00+00:00")

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir(mode=0o700)
    legacy_dir = malformed_root / "budget-v1"
    legacy_dir.mkdir(mode=0o700)
    malformed = legacy_dir / "controller-ledger.json"
    malformed.write_bytes(b"{}")
    malformed.chmod(0o600)
    with pytest.raises(ContractError, match="invalid_budget_record"):
        BudgetStore(malformed_root, "controller-1", model_policy(), clock=Clock("2026-09-20")).initialize()

    charged_root = tmp_path / "charged"
    charged_root.mkdir(mode=0o700)
    _write_legacy(charged_root, state="charged")
    with pytest.raises(ContractError, match="legacy_day_budget_pending"):
        BudgetStore(charged_root, "controller-1", model_policy(), clock=Clock("2026-09-20")).initialize()
    active = BudgetStore(charged_root, "controller-1", model_policy(), clock=Clock("2026-09-21"))
    active.initialize()


def test_v2_initialization_rejects_legacy_hold_even_after_day_rollover(tmp_path):
    from datetime import datetime

    class Clock:
        def __init__(self, day):
            self.day = day

        def now_utc(self):
            return datetime.fromisoformat(self.day + "T00:00:00+00:00")

    root = tmp_path / "held"
    root.mkdir(mode=0o700)
    _path, request = _write_legacy(root, state="held")
    legacy = BudgetStore(root, "controller-1", _legacy_policy(), clock=Clock("2026-09-20"))
    with pytest.raises(ContractError, match="legacy_usage_pending"):
        BudgetStore(root, "controller-1", model_policy(), clock=Clock("2026-09-21")).initialize()
    with pytest.raises(ContractError, match="legacy_policy_read_only"):
        legacy.reserve_request("incident-1", expected_revision=legacy.read()["revision"])
    record = legacy.read()
    with pytest.raises(ContractError, match="usage_policy_mismatch"):
        legacy.settle_request(
            request["reservation_id"],
            usage_evidence(request),
            expected_revision=record["revision"],
        )
    legacy.settle_request(
        request["reservation_id"],
        _legacy_usage(request),
        expected_revision=record["revision"],
    )
    BudgetStore(root, "controller-1", model_policy(), clock=Clock("2026-09-21")).initialize()


def test_v2_reservation_rechecks_legacy_same_day_debt(tmp_path):
    from datetime import datetime

    class Clock:
        def now_utc(self):
            return datetime.fromisoformat("2026-09-20T00:00:00+00:00")

    root = tmp_path / "reserve-guard"
    root.mkdir(mode=0o700)
    _write_legacy(root)

    active = BudgetStore(root, "controller-1", model_policy(), clock=Clock())
    active_record = active.initialize()
    active_record = active.create_incident(
        "new-incident", "sha256:" + "2" * 64, expected_revision=active_record["revision"]
    )

    _write_legacy(root, state="charged")

    with pytest.raises(ContractError, match="legacy_day_budget_pending"):
        active.reserve_request("new-incident", expected_revision=active_record["revision"])


def test_mutating_exposed_policy_version_cannot_change_receipt_binding(tmp_path):
    from datetime import datetime

    class Clock:
        def now_utc(self):
            return datetime.fromisoformat("2026-09-21T00:00:00+00:00")

    root = tmp_path / "immutable-version"
    root.mkdir(mode=0o700)
    store = BudgetStore(root, "controller-1", model_policy(), clock=Clock())
    record = store.initialize()
    record = store.create_incident(
        "incident-1", "sha256:" + "1" * 64, expected_revision=record["revision"]
    )
    request = store.reserve_request("incident-1", expected_revision=record["revision"])
    store.policy["format_version"] = 1
    record = store.read()
    with pytest.raises(ContractError, match="usage_policy_mismatch"):
        store.settle_request(
            request["reservation_id"],
            _legacy_usage(request),
            expected_revision=record["revision"],
        )
