"""Durable single-record budget store for the second Stage C unit."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from ._budget_store_io import (
    atomic_record,
    budget_lock,
    initialize_record,
    protect_root,
    read_bytes,
    safe_directory,
)
from ._budget_store_approval import ApprovalEvent, validate_event
from ._budget_store_ops import (
    advance_ledger,
    advance_record,
    ensure_day,
    expected_revision as expected_revision_check,
    find,
    make_challenge,
    replace_item,
    trusted_now,
)
from ._budget_store_pending import retire_stale_pending
from ._budget_store_schema import validate_record
from ._budget_store_reservation import BudgetReservationMixin
from ._budget_store_settlement import BudgetSettlementMixin
from .budget import consume_grant, new_incident
from .c_contracts import validate_c
from .contracts import ContractError, canonical_bytes, digest

__all__ = ["ApprovalEvent", "BudgetStore", "TestHooks"]

@dataclass(frozen=True)
class TestHooks:
    on_phase: Callable[[str], None]


class BudgetStore(BudgetReservationMixin, BudgetSettlementMixin):
    def __init__(
        self,
        managed_root: Path,
        controller_id: str,
        policy: dict[str, Any],
        *,
        clock: Any,
        approval_source: Any | None = None,
        test_hooks: TestHooks | None = None,
    ) -> None:
        validate_c(policy, "ModelPolicy")
        if not isinstance(managed_root, Path) or not isinstance(controller_id, str):
            raise ContractError("invalid_budget_context")
        self.root = managed_root
        self.controller_id = controller_id
        self.policy = deepcopy(policy)
        self._policy_version = policy["format_version"]
        self.policy_digest = digest(policy)
        self.clock = clock
        self.approval_source = approval_source
        self.test_hooks = test_hooks
        # A policy generation owns its ledger namespace.  This keeps the v1
        # audit record intact and prevents its pending grants from becoming
        # usable under a different policy digest.
        self.directory = managed_root / f"budget-v{policy['format_version']}"
        self.path = self.directory / "controller-ledger.json"

    def _require_active_policy(self) -> None:
        if self._policy_version != 2:
            raise ContractError("legacy_policy_read_only")

    def _guard_legacy_budget(self, current_day: str) -> None:
        """Refuse to forget unresolved or same-day spend in an immutable v1 ledger."""
        legacy_directory = self.root / "budget-v1"
        if not legacy_directory.exists() and not legacy_directory.is_symlink():
            return
        safe_directory(legacy_directory)
        raw = read_bytes(legacy_directory / "controller-ledger.json")
        try:
            legacy = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("invalid_budget_record") from exc
        if canonical_bytes(legacy) != raw:
            raise ContractError("invalid_budget_record")
        validate_record(legacy)
        if legacy["controller_id"] != self.controller_id:
            raise ContractError("budget_context_mismatch")
        if any(item["held_tokens"] for item in legacy["incidents"]) or any(
            item["status"] == "held" for item in legacy["reservations"]
        ):
            raise ContractError("legacy_usage_pending")
        if any(
            item["utc_day"] == current_day
            and (item["charged_tokens"] or item["held_tokens"])
            for item in legacy["days"]
        ):
            raise ContractError("legacy_day_budget_pending")

    def _load(self) -> dict[str, Any]:
        safe_directory(self.directory)
        raw = read_bytes(self.path)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("invalid_budget_record") from exc
        if canonical_bytes(value) != raw:
            raise ContractError("invalid_budget_record")
        validate_record(value)
        if (
            value["controller_id"] != self.controller_id
            or value["policy_digest"] != self.policy_digest
        ):
            raise ContractError("budget_context_mismatch")
        return value

    def _publish(self, value: dict[str, Any]) -> dict[str, Any]:
        grants, changed = retire_stale_pending(value, value["updated_at"][:10])
        if changed:
            value = {**value, "grants": grants}
        validate_record(value)
        atomic_record(self.path, value, self.test_hooks)
        return value

    def initialize(self) -> dict[str, Any]:
        protect_root(self.root)
        with budget_lock(self.root):
            self._require_active_policy()
            day, now = trusted_now(self.clock)
            self._guard_legacy_budget(day)
            value = validate_record(
                {
                    "format_version": 1,
                    "controller_id": self.controller_id,
                    "policy_digest": self.policy_digest,
                    "revision": 0,
                    "initialized_at": now,
                    "updated_at": now,
                    "incidents": [],
                    "days": [],
                    "grants": [],
                    "reservations": [],
                }
            )
            initialize_record(
                self.root, self.directory, self.path, value, self.test_hooks
            )
            return value

    def read(self) -> dict[str, Any]:
        protect_root(self.root)
        return self._load()

    def create_incident(
        self, incident_id: str, input_digest: str, *, expected_revision: int
    ) -> dict[str, Any]:
        protect_root(self.root)
        with budget_lock(self.root):
            self._require_active_policy()
            record = self._load()
            expected_revision_check(record, expected_revision)
            if any(item["incident_id"] == incident_id for item in record["incidents"]):
                raise ContractError("incident_exists")
            if len(record["incidents"]) >= 32:
                raise ContractError("budget_capacity")
            day, now = trusted_now(self.clock)
            _daily, days = ensure_day(record, day)
            incident = new_incident(
                self.controller_id,
                incident_id,
                input_digest,
                self.policy,
                utc_day=day,
            )
            value = advance_record(
                record, now, incidents=[*record["incidents"], incident], days=days
            )
            return self._publish(value)

    def checkpoint_for_approval(
        self,
        incident_id: str,
        *,
        expected_revision: int,
        daily_ceiling_override_tokens: int | None = None,
    ) -> dict[str, Any]:
        protect_root(self.root)
        with budget_lock(self.root):
            self._require_active_policy()
            record = self._load()
            expected_revision_check(record, expected_revision)
            incident = find(record["incidents"], "incident_id", incident_id, "unknown_incident")
            if len(record["grants"]) >= 256:
                raise ContractError("budget_capacity")
            day, now = trusted_now(self.clock)
            grants, _changed = retire_stale_pending(record, day)
            working = {**record, "grants": grants}
            if any(
                item["status"] == "pending"
                and item["challenge"]["incident_id"] == incident_id
                for item in working["grants"]
            ):
                raise ContractError("approval_pending")
            daily, days = ensure_day(working, day)
            if incident["state"] == "ready":
                incident_blocked = (
                    incident["charged_tokens"] + 32_000
                    > incident["allowance_tokens"]
                )
                daily_blocked = (
                    daily["charged_tokens"] + daily["held_tokens"] + 32_000
                    > daily["ceiling_tokens"]
                )
                if not (incident_blocked or daily_blocked):
                    raise ContractError("approval_not_ready")
                incident = validate_c(
                    advance_ledger(
                        incident, state="awaiting_budget_approval"
                    ),
                    "IncidentLedger",
                )
                working = {
                    **working,
                    "incidents": replace_item(
                        working["incidents"], "incident_id", incident
                    ),
                }
            elif incident["state"] != "awaiting_budget_approval":
                raise ContractError("approval_not_ready")
            effective_ceiling = (
                daily["ceiling_tokens"]
                if daily_ceiling_override_tokens is None
                else daily_ceiling_override_tokens
            )
            if (
                daily_ceiling_override_tokens is not None
                and daily_ceiling_override_tokens <= daily["ceiling_tokens"]
            ) or daily["charged_tokens"] + daily["held_tokens"] + 32_000 > effective_ceiling:
                raise ContractError("daily_budget_exhausted")
            challenge = make_challenge(
                working, incident, daily, now, daily_ceiling_override_tokens
            )
            grant_record = {
                "challenge_id": challenge["challenge_id"],
                "challenge": challenge,
                "status": "pending",
                "approval_source_id": None,
                "approval_event_id": None,
                "approval_actor_label": None,
                "approval_approved_at": None,
                "approval_decision": None,
                "grant_digest": None,
            }
            value = advance_record(
                working, now, days=days, grants=[*working["grants"], grant_record]
            )
            self._publish(value)
            return challenge

    def apply_verified_approval(
        self, challenge_id: str, *, expected_revision: int
    ) -> dict[str, Any]:
        protect_root(self.root)
        with budget_lock(self.root):
            self._require_active_policy()
            record = self._load()
            expected_revision_check(record, expected_revision)
            day, now = trusted_now(self.clock)
            grants, retired = retire_stale_pending(record, day)
            if retired:
                self._publish(advance_record(record, now, grants=grants))
                raise ContractError("stale_approval_challenge")
            grant_record = find(record["grants"], "challenge_id", challenge_id, "unknown_challenge")
            if grant_record["status"] != "pending":
                raise ContractError("approval_already_consumed")
            challenge = deepcopy(grant_record["challenge"])
        if self.approval_source is None:
            raise ContractError("approval_source_unavailable")
        event = self.approval_source.resolve(deepcopy(challenge))
        with budget_lock(self.root):
            record = self._load()
            expected_revision_check(record, expected_revision)
            day, now = trusted_now(self.clock)
            grants, retired = retire_stale_pending(record, day)
            if retired:
                self._publish(advance_record(record, now, grants=grants))
                raise ContractError("stale_approval_challenge")
            stored = find(record["grants"], "challenge_id", challenge_id, "unknown_challenge")
            if stored["status"] != "pending" or stored["challenge"] != challenge:
                raise ContractError("stale_approval_challenge")
            if event is None:
                return record
            validate_event(event, self.approval_source, challenge)
            incident = find(record["incidents"], "incident_id", challenge["incident_id"], "unknown_incident")
            daily = find(record["days"], "utc_day", challenge["utc_day"], "unknown_day")
            grant = validate_c(
                {
                    "format_version": 1,
                    "grant_id": challenge_id,
                    "decision": event.decision,
                    "controller_id": self.controller_id,
                    "incident_id": incident["incident_id"],
                    "input_digest": incident["input_digest"],
                    "policy_digest": self.policy_digest,
                    "ledger_revision": challenge["ledger_revision"],
                    "checkpoint_digest": challenge["checkpoint_digest"],
                    "daily_ledger_digest": challenge["daily_ledger_digest"],
                    "grant_tokens": challenge["grant_tokens"],
                    "new_incident_ceiling_tokens": challenge["new_incident_ceiling_tokens"],
                    "request_allowance": challenge["request_allowance"],
                    "daily_ceiling_override_tokens": challenge["daily_ceiling_override_tokens"],
                    "actor_label": event.actor_label,
                    "approved_at": event.approved_at,
                },
                "BudgetGrant",
            )
            next_incident, next_daily = consume_grant(incident, daily, grant)
            consumed = {
                **stored,
                "status": "consumed",
                "approval_source_id": event.source_id,
                "approval_event_id": event.event_id,
                "approval_actor_label": event.actor_label,
                "approval_approved_at": event.approved_at,
                "approval_decision": event.decision,
                "grant_digest": digest(grant),
            }
            value = advance_record(
                record,
                now,
                incidents=replace_item(record["incidents"], "incident_id", next_incident),
                days=replace_item(record["days"], "utc_day", next_daily),
                grants=replace_item(record["grants"], "challenge_id", consumed),
            )
            return self._publish(value)
