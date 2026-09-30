"""Cross-record invariants for a validated C2 controller ledger."""

from __future__ import annotations

from typing import Any

from ._budget_store_pending import pending_matches
from .contracts import ContractError, digest


def _fail() -> None:
    raise ContractError("invalid_budget_record")


def validate_cross(value: dict[str, Any]) -> None:
    incidents = {item["incident_id"]: item for item in value["incidents"]}
    days = {item["utc_day"]: item for item in value["days"]}
    incident_charged = {key: 0 for key in incidents}
    incident_held = {key: 0 for key in incidents}
    day_charged = {key: 0 for key in days}
    day_held = {key: 0 for key in days}
    ordinals: dict[str, list[int]] = {key: [] for key in incidents}
    held_count = 0
    for record in value["reservations"]:
        incident_id, utc_day = record["incident_id"], record["utc_day"]
        if incident_id not in incidents or utc_day not in days:
            _fail()
        incident = incidents[incident_id]
        request = record["request"]
        if (
            request["controller_id"] != value["controller_id"]
            or request["policy_digest"] != value["policy_digest"]
            or request["incident_id"] != incident_id
            or request["input_digest"] != incident["input_digest"]
            or request["utc_day"] != utc_day
        ):
            _fail()
        seed = {
            "controller_id": request["controller_id"],
            "incident_id": request["incident_id"],
            "utc_day": request["utc_day"],
            "ledger_revision": request["ledger_revision"],
            "daily_ledger_digest": request["daily_ledger_digest"],
            "request_ordinal": request["request_ordinal"],
        }
        if request["reservation_id"] != digest(seed)[7:]:
            _fail()
        ordinals[incident_id].append(request["request_ordinal"])
        incident_charged[incident_id] += record["charged_tokens"]
        day_charged[utc_day] += record["charged_tokens"]
        if record["status"] == "held":
            held_count += 1
            held = request["estimated_reserved_tokens"]
            incident_held[incident_id] += held
            day_held[utc_day] += held
            if incident["current_reservation_digest"] != digest(request):
                _fail()
            expected_state = (
                "awaiting_usage"
                if record["estimated_evidence_digest"] is not None
                else "in_flight"
            )
            if incident["state"] != expected_state:
                _fail()
    if held_count > 1:
        _fail()
    for key, incident in incidents.items():
        statuses = [
            item
            for item in value["reservations"]
            if item["incident_id"] == key
        ]
        derived_usage = _usage_status(statuses)
        if (
            incident["charged_tokens"] != incident_charged[key]
            or incident["held_tokens"] != incident_held[key]
            or sorted(ordinals[key]) != list(range(1, incident["requests_started"] + 1))
            or incident["usage_status"] != derived_usage
        ):
            _fail()
    for key, day in days.items():
        if day["charged_tokens"] != day_charged[key] or day["held_tokens"] != day_held[key]:
            _fail()
    _validate_grants(value, incidents, days)


def _usage_status(records: list[dict[str, Any]]) -> str:
    if any(item["status"] == "settled_estimated" for item in records):
        return "estimated"
    if any(
        item["status"] == "held"
        and item["estimated_evidence_digest"] is not None
        for item in records
    ):
        return "estimated"
    if any(item["status"] == "settled_actual" for item in records):
        return "actual"
    return "none"


def _validate_grants(
    value: dict[str, Any],
    incidents: dict[str, dict[str, Any]],
    days: dict[str, dict[str, Any]],
) -> None:
    consumed = {key: 0 for key in incidents}
    events: set[tuple[str, str]] = set()
    pending = 0
    ceilings: dict[str, list[int]] = {key: [] for key in incidents}
    new_policy = any(
        item["allowance_tokens"] == 100_000 * (item["grants_consumed"] + 1)
        and item["requests_allowed"] == 3 * (item["grants_consumed"] + 1)
        for item in incidents.values()
    ) or any(day["ceiling_tokens"] == 100_000 for day in days.values())
    day_ceilings = {key: 100_000 if new_policy else 64_000 for key in days}
    for item in value["grants"]:
        challenge = item["challenge"]
        incident = incidents.get(challenge["incident_id"])
        if (
            challenge["controller_id"] != value["controller_id"]
            or challenge["policy_digest"] != value["policy_digest"]
            or incident is None
            or challenge["utc_day"] not in days
            or challenge["input_digest"] != incident["input_digest"]
        ):
            _fail()
        if item["status"] == "consumed":
            event = (item["approval_source_id"], item["approval_event_id"])
            if event in events:
                _fail()
            events.add(event)
            consumed[challenge["incident_id"]] += 1
            ceilings[challenge["incident_id"]].append(
                challenge["new_incident_ceiling_tokens"]
            )
            override = challenge["daily_ceiling_override_tokens"]
            if override is not None:
                day_ceilings[challenge["utc_day"]] = max(
                    day_ceilings[challenge["utc_day"]], override
                )
        elif item["status"] == "pending":
            pending += 1
            if not pending_matches(value, item, value["updated_at"][:10]):
                _fail()
    if pending > 1:
        _fail()
    if any(incidents[key]["grants_consumed"] != count for key, count in consumed.items()):
        _fail()
    for key, values in ceilings.items():
        initial = 100_000 if new_policy else 32_000
        increment = 100_000 if new_policy else 32_000
        expected = [initial + increment * (index + 1) for index in range(len(values))]
        if sorted(values) != expected:
            _fail()
    if any(days[key]["ceiling_tokens"] != ceiling for key, ceiling in day_ceilings.items()):
        _fail()
