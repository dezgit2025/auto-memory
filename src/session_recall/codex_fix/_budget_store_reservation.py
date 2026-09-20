"""Atomic controller-wide request reservation for the C2 store."""

from __future__ import annotations

from typing import Any

from ._budget_store_io import budget_lock, protect_root
from ._budget_store_ops import (
    advance_record,
    ensure_day,
    expected_revision as check_revision,
    find,
    replace_item,
    trusted_now,
)
from .budget import reserve_request as reserve_ledger
from .contracts import ContractError


class BudgetReservationMixin:
    root: Any
    clock: Any

    def reserve_request(
        self, incident_id: str, *, expected_revision: int
    ) -> dict[str, Any]:
        protect_root(self.root)
        with budget_lock(self.root):
            self._require_active_policy()
            record = self._load()
            check_revision(record, expected_revision)
            if any(item["status"] == "held" for item in record["reservations"]):
                raise ContractError("unresolved_reservation")
            if len(record["reservations"]) >= 256:
                raise ContractError("budget_capacity")
            incident = find(
                record["incidents"], "incident_id", incident_id, "unknown_incident"
            )
            day, now = trusted_now(self.clock)
            self._guard_legacy_budget(day)
            daily, days = ensure_day(record, day)
            next_incident, next_daily, request = reserve_ledger(incident, daily)
            reservation = {
                "reservation_id": request["reservation_id"],
                "incident_id": incident_id,
                "utc_day": day,
                "request": request,
                "status": "held",
                "estimated_evidence_digest": None,
                "actual_evidence_digest": None,
                "estimated_tokens": None,
                "actual_tokens": None,
                "charged_tokens": 0,
            }
            value = advance_record(
                record,
                now,
                incidents=replace_item(
                    record["incidents"], "incident_id", next_incident
                ),
                days=replace_item(days, "utc_day", next_daily),
                reservations=[*record["reservations"], reservation],
            )
            self._publish(value)
            return request
