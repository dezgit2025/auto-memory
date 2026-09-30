"""Pure record-building helpers for the durable C2 budget store."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ._budget_store_schema import validate_challenge
from .c_contracts import validate_c
from .contracts import ContractError, digest

MAX_INT = 2**63 - 1


def trusted_now(clock: Any) -> tuple[str, str]:
    try:
        value = clock.now_utc()
    except Exception as exc:
        raise ContractError("clock_unavailable") from exc
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ContractError("invalid_clock")
    utc = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc.date().isoformat(), utc.isoformat().replace("+00:00", "Z")


def expected_revision(record: dict[str, Any], expected: int) -> None:
    if type(expected) is not int or expected < 0 or record["revision"] != expected:
        raise ContractError("stale_budget_revision")


def find(items: list[dict[str, Any]], key: str, value: str, code: str) -> dict[str, Any]:
    matches = [item for item in items if item[key] == value]
    if len(matches) != 1:
        raise ContractError(code)
    return matches[0]


def advance_record(
    record: dict[str, Any],
    updated_at: str,
    **collections: list[dict[str, Any]],
) -> dict[str, Any]:
    if record["revision"] >= MAX_INT:
        raise ContractError("budget_revision_overflow")
    if updated_at < record["updated_at"]:
        raise ContractError("clock_regression")
    value = {**record, "revision": record["revision"] + 1, "updated_at": updated_at}
    value.update(collections)
    for name, key in (
        ("incidents", "incident_id"),
        ("days", "utc_day"),
        ("grants", "challenge_id"),
        ("reservations", "reservation_id"),
    ):
        value[name] = sorted(value[name], key=lambda item: item[key])
    return value


def ensure_day(
    record: dict[str, Any], day: str, *, ceiling_tokens: int = 64_000
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if record["days"] and day < record["days"][-1]["utc_day"]:
        raise ContractError("clock_regression")
    for item in record["days"]:
        if item["utc_day"] == day:
            return item, list(record["days"])
    if len(record["days"]) >= 8:
        raise ContractError("budget_capacity")
    value = validate_c(
        {
            "format_version": 1,
            "controller_id": record["controller_id"],
            "utc_day": day,
            "revision": 0,
            "previous_checkpoint_digest": None,
            "policy_digest": record["policy_digest"],
            "ceiling_tokens": ceiling_tokens,
            "charged_tokens": 0,
            "held_tokens": 0,
        },
        "DailyLedger",
    )
    return value, [*record["days"], value]


def replace_item(
    items: list[dict[str, Any]], key: str, replacement: dict[str, Any]
) -> list[dict[str, Any]]:
    return [replacement if item[key] == replacement[key] else item for item in items]


def make_challenge(
    record: dict[str, Any],
    incident: dict[str, Any],
    daily: dict[str, Any],
    created_at: str,
    override: int | None,
    *, grant_tokens: int = 32_000, request_allowance: int = 1,
) -> dict[str, Any]:
    projection = {
        "format_version": 1,
        "controller_id": record["controller_id"],
        "incident_id": incident["incident_id"],
        "utc_day": daily["utc_day"],
        "input_digest": incident["input_digest"],
        "policy_digest": record["policy_digest"],
        "ledger_revision": incident["revision"],
        "checkpoint_digest": digest(incident),
        "daily_ledger_digest": digest(daily),
        "grant_tokens": grant_tokens,
        "new_incident_ceiling_tokens": incident["allowance_tokens"] + grant_tokens,
        "request_allowance": request_allowance,
        "daily_ceiling_override_tokens": override,
        "created_at": created_at,
    }
    return validate_challenge({"challenge_id": digest(projection)[7:], **projection})


def advance_ledger(value: dict[str, Any], **changes: Any) -> dict[str, Any]:
    if value["revision"] >= MAX_INT:
        raise ContractError("budget_revision_overflow")
    updated = {
        **value,
        "revision": value["revision"] + 1,
        "previous_checkpoint_digest": digest(value),
        **changes,
    }
    return updated


def aggregate_usage_status(
    incident_id: str, reservations: list[dict[str, Any]]
) -> str:
    statuses = [
        item["status"]
        for item in reservations
        if item["incident_id"] == incident_id and item["status"] != "held"
    ]
    if not statuses:
        return "none"
    if "settled_estimated" in statuses:
        return "estimated"
    return "actual"


def reconcile_actual(
    incident: dict[str, Any],
    daily: dict[str, Any],
    estimated_tokens: int,
    actual_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    delta = actual_tokens - estimated_tokens
    next_incident_charge = incident["charged_tokens"] + delta
    next_daily_charge = daily["charged_tokens"] + delta
    if (
        next_incident_charge < 0
        or next_daily_charge < 0
        or next_incident_charge > MAX_INT
        or next_daily_charge > MAX_INT
    ):
        raise ContractError("token_overflow")
    next_incident = advance_ledger(
        incident, charged_tokens=next_incident_charge
    )
    next_daily = advance_ledger(daily, charged_tokens=next_daily_charge)
    return next_incident, next_daily
