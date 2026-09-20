"""Usage settlement and estimated-to-actual reconciliation for C2."""

from __future__ import annotations

from typing import Any

from ._budget_store_io import budget_lock, protect_root
from ._budget_store_ops import (
    advance_record,
    aggregate_usage_status,
    expected_revision as check_revision,
    find,
    reconcile_actual,
    replace_item,
    trusted_now,
)
from .budget import normalize_usage, settle_request as settle_ledger
from .c_contracts import validate_c
from .contracts import ContractError, digest


class BudgetSettlementMixin:
    root: Any
    clock: Any

    def settle_request(
        self,
        reservation_id: str,
        evidence: dict[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        protect_root(self.root)
        with budget_lock(self.root):
            record = self._load()
            check_revision(record, expected_revision)
            reservation = find(
                record["reservations"],
                "reservation_id",
                reservation_id,
                "unknown_reservation",
            )
            validate_c(evidence, "UsageEvidence")
            if evidence["format_version"] != self._policy_version:
                raise ContractError("usage_policy_mismatch")
            if evidence["reservation_digest"] != digest(reservation["request"]):
                raise ContractError("usage_binding_mismatch")
            evidence_digest = digest(evidence)
            status = reservation["status"]
            if status == "settled_actual":
                if reservation["actual_evidence_digest"] == evidence_digest:
                    return record
                raise ContractError("conflicting_actual_usage")
            if status == "settled_estimated":
                if reservation["estimated_evidence_digest"] == evidence_digest:
                    return record
                return self._reconcile_actual(
                    record, reservation, evidence, evidence_digest
                )
            if reservation["estimated_evidence_digest"] == evidence_digest:
                return record
            return self._settle_held(record, reservation, evidence, evidence_digest)

    def _settle_held(
        self,
        record: dict[str, Any],
        reservation: dict[str, Any],
        evidence: dict[str, Any],
        evidence_digest: str,
    ) -> dict[str, Any]:
        request = reservation["request"]
        incident = find(
            record["incidents"],
            "incident_id",
            reservation["incident_id"],
            "unknown_incident",
        )
        daily = find(
            record["days"], "utc_day", reservation["utc_day"], "unknown_day"
        )
        next_incident, next_daily = settle_ledger(
            incident, daily, request, evidence
        )
        total = normalize_usage(evidence)
        next_reservation = dict(reservation)
        if not evidence["usage_final"]:
            next_reservation.update(
                estimated_evidence_digest=evidence_digest,
                estimated_tokens=total,
            )
        elif evidence["usage_basis"] == "estimated":
            next_reservation.update(
                status="settled_estimated",
                estimated_evidence_digest=evidence_digest,
                estimated_tokens=total,
                charged_tokens=total,
            )
        else:
            next_reservation.update(
                status="settled_actual",
                actual_evidence_digest=evidence_digest,
                actual_tokens=total,
                charged_tokens=total,
            )
        reservations = replace_item(
            record["reservations"], "reservation_id", next_reservation
        )
        if evidence["usage_final"]:
            next_incident = validate_c(
                {
                    **next_incident,
                    "usage_status": aggregate_usage_status(
                        incident["incident_id"], reservations
                    ),
                },
                "IncidentLedger",
            )
        _day, now = trusted_now(self.clock)
        value = advance_record(
            record,
            now,
            incidents=replace_item(
                record["incidents"], "incident_id", next_incident
            ),
            days=replace_item(record["days"], "utc_day", next_daily),
            reservations=reservations,
        )
        return self._publish(value)

    def _reconcile_actual(
        self,
        record: dict[str, Any],
        reservation: dict[str, Any],
        evidence: dict[str, Any],
        evidence_digest: str,
    ) -> dict[str, Any]:
        if not evidence["usage_final"] or evidence["usage_basis"] != "actual":
            raise ContractError("conflicting_estimated_usage")
        incident = find(
            record["incidents"],
            "incident_id",
            reservation["incident_id"],
            "unknown_incident",
        )
        daily = find(
            record["days"], "utc_day", reservation["utc_day"], "unknown_day"
        )
        actual = normalize_usage(evidence)
        next_incident, next_daily = reconcile_actual(
            incident, daily, reservation["estimated_tokens"], actual
        )
        next_reservation = {
            **reservation,
            "status": "settled_actual",
            "actual_evidence_digest": evidence_digest,
            "actual_tokens": actual,
            "charged_tokens": actual,
        }
        reservations = replace_item(
            record["reservations"], "reservation_id", next_reservation
        )
        next_incident = validate_c(
            {
                **next_incident,
                "usage_status": aggregate_usage_status(
                    incident["incident_id"], reservations
                ),
            },
            "IncidentLedger",
        )
        next_daily = validate_c(next_daily, "DailyLedger")
        _day, now = trusted_now(self.clock)
        value = advance_record(
            record,
            now,
            incidents=replace_item(
                record["incidents"], "incident_id", next_incident
            ),
            days=replace_item(record["days"], "utc_day", next_daily),
            reservations=reservations,
        )
        return self._publish(value)
