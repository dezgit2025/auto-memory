"""Derived validity and audit-preserving retirement for pending C2 challenges."""

from __future__ import annotations

from typing import Any

from .contracts import digest


def pending_matches(
    record: dict[str, Any], grant: dict[str, Any], current_day: str
) -> bool:
    challenge = grant["challenge"]
    incidents = {
        item["incident_id"]: item for item in record["incidents"]
    }
    days = {item["utc_day"]: item for item in record["days"]}
    incident = incidents.get(challenge["incident_id"])
    daily = days.get(challenge["utc_day"])
    return bool(
        grant["status"] == "pending"
        and incident is not None
        and daily is not None
        and challenge["utc_day"] == current_day
        and challenge["input_digest"] == incident["input_digest"]
        and challenge["ledger_revision"] == incident["revision"]
        and challenge["checkpoint_digest"] == digest(incident)
        and challenge["daily_ledger_digest"] == digest(daily)
        and challenge["new_incident_ceiling_tokens"]
        == incident["allowance_tokens"] + challenge["grant_tokens"]
        and incident["state"] == "awaiting_budget_approval"
    )


def retire_stale_pending(
    record: dict[str, Any], current_day: str
) -> tuple[list[dict[str, Any]], bool]:
    grants: list[dict[str, Any]] = []
    changed = False
    for grant in record["grants"]:
        if grant["status"] == "pending" and not pending_matches(
            record, grant, current_day
        ):
            grants.append({**grant, "status": "invalidated"})
            changed = True
        else:
            grants.append(grant)
    return grants, changed
