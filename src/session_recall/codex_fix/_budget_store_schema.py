"""Strict validation for the single C2 controller budget record."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from ._budget_store_cross import validate_cross
from .c_contracts import validate_c
from .contracts import ContractError, canonical_bytes, digest

ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_RECORD_BYTES = 1024 * 1024
CONTROLLER_FIELDS = {
    "format_version", "controller_id", "policy_digest", "revision",
    "initialized_at", "updated_at", "incidents", "days", "grants", "reservations",
}
CHALLENGE_FIELDS = {
    "format_version", "challenge_id", "controller_id", "incident_id", "utc_day",
    "input_digest", "policy_digest", "ledger_revision", "checkpoint_digest",
    "daily_ledger_digest", "grant_tokens", "new_incident_ceiling_tokens",
    "request_allowance", "daily_ceiling_override_tokens", "created_at",
}
GRANT_FIELDS = {
    "challenge_id", "challenge", "status", "approval_source_id",
    "approval_event_id", "approval_actor_label", "approval_approved_at",
    "approval_decision", "grant_digest",
}
RESERVATION_FIELDS = {
    "reservation_id", "incident_id", "utc_day", "request", "status",
    "estimated_evidence_digest", "actual_evidence_digest", "estimated_tokens",
    "actual_tokens", "charged_tokens",
}


def _fail(code: str = "invalid_budget_record") -> None:
    raise ContractError(code)


def _exact(value: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail()
    return value


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        _fail()
    return value


def _digest(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        _fail()
    return value


def _integer(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 2**63 - 1:
        _fail()
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Z") or len(value) > 64:
        _fail()
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail()
    return value


def validate_challenge(value: Any) -> dict[str, Any]:
    value = _exact(value, CHALLENGE_FIELDS)
    if value["format_version"] != 1:
        _fail()
    _identifier(value["challenge_id"])
    _identifier(value["controller_id"])
    _identifier(value["incident_id"])
    try:
        datetime.strptime(value["utc_day"], "%Y-%m-%d")
    except (TypeError, ValueError):
        _fail()
    _digest(value["input_digest"])
    _digest(value["policy_digest"])
    _integer(value["ledger_revision"])
    _digest(value["checkpoint_digest"])
    _digest(value["daily_ledger_digest"])
    tokens = value["grant_tokens"]
    requests = value["request_allowance"]
    ceiling = _integer(value["new_incident_ceiling_tokens"])
    old_shape = tokens == 32_000 and requests == 1 and ceiling >= 64_000 and ceiling % 32_000 == 0
    new_shape = tokens == 100_000 and requests == 3 and ceiling >= 200_000 and ceiling % 100_000 == 0
    if not (old_shape or new_shape):
        _fail()
    override = value["daily_ceiling_override_tokens"]
    if override is not None and (
        type(override) is not int or not ((old_shape and override >= 96_000 and override % 32_000 == 0) or (new_shape and override >= 200_000 and override % 100_000 == 0))
    ):
        _fail()
    _timestamp(value["created_at"])
    projection = {key: item for key, item in value.items() if key != "challenge_id"}
    if value["challenge_id"] != digest(projection)[7:]:
        _fail("challenge_binding_mismatch")
    return value


def _grant_record(value: Any) -> dict[str, Any]:
    value = _exact(value, GRANT_FIELDS)
    challenge = validate_challenge(value["challenge"])
    if value["challenge_id"] != challenge["challenge_id"]:
        _fail()
    if value["status"] not in {"pending", "consumed", "invalidated"}:
        _fail()
    evidence = (
        "approval_source_id", "approval_event_id", "approval_actor_label",
        "approval_approved_at", "approval_decision", "grant_digest",
    )
    if value["status"] in {"pending", "invalidated"}:
        if any(value[name] is not None for name in evidence):
            _fail()
    else:
        for name in evidence[:3]:
            _identifier(value[name])
        _timestamp(value["approval_approved_at"])
        if value["approval_decision"] != "continue":
            _fail()
        _digest(value["grant_digest"])
        grant = {
            "format_version": 1,
            "grant_id": challenge["challenge_id"],
            "decision": value["approval_decision"],
            "controller_id": challenge["controller_id"],
            "incident_id": challenge["incident_id"],
            "input_digest": challenge["input_digest"],
            "policy_digest": challenge["policy_digest"],
            "ledger_revision": challenge["ledger_revision"],
            "checkpoint_digest": challenge["checkpoint_digest"],
            "daily_ledger_digest": challenge["daily_ledger_digest"],
            "grant_tokens": challenge["grant_tokens"],
            "new_incident_ceiling_tokens": challenge["new_incident_ceiling_tokens"],
            "request_allowance": challenge["request_allowance"],
            "daily_ceiling_override_tokens": challenge["daily_ceiling_override_tokens"],
            "actor_label": value["approval_actor_label"],
            "approved_at": value["approval_approved_at"],
        }
        validate_c(grant, "BudgetGrant")
        if value["grant_digest"] != digest(grant):
            _fail("grant_binding_mismatch")
    return value


def _reservation_record(value: Any) -> dict[str, Any]:
    value = _exact(value, RESERVATION_FIELDS)
    request = validate_c(value["request"], "RequestReservation")
    if (
        value["reservation_id"] != request["reservation_id"]
        or value["incident_id"] != request["incident_id"]
        or value["utc_day"] != request["utc_day"]
        or value["status"] not in {"held", "settled_estimated", "settled_actual"}
    ):
        _fail()
    estimated_digest = _digest(value["estimated_evidence_digest"], nullable=True)
    actual_digest = _digest(value["actual_evidence_digest"], nullable=True)
    estimated = value["estimated_tokens"]
    actual = value["actual_tokens"]
    charged = _integer(value["charged_tokens"])
    if estimated is not None:
        estimated = _integer(estimated)
    if actual is not None:
        actual = _integer(actual)
    if value["status"] == "held" and (actual_digest is not None or actual is not None or charged):
        _fail()
    if value["status"] == "held" and ((estimated_digest is None) != (estimated is None)):
        _fail()
    if value["status"] == "settled_estimated" and (
        estimated_digest is None or estimated is None or actual_digest is not None
        or actual is not None or charged != estimated
    ):
        _fail()
    if value["status"] == "settled_actual" and (
        actual_digest is None or actual is None or charged != actual
        or (estimated_digest is None) != (estimated is None)
    ):
        _fail()
    return value


def validate_record(value: Any) -> dict[str, Any]:
    if len(canonical_bytes(value)) > MAX_RECORD_BYTES:
        _fail("budget_record_too_large")
    value = _exact(value, CONTROLLER_FIELDS)
    if value["format_version"] != 1:
        _fail()
    controller = _identifier(value["controller_id"])
    policy = _digest(value["policy_digest"])
    _integer(value["revision"])
    initialized = _timestamp(value["initialized_at"])
    updated = _timestamp(value["updated_at"])
    if updated < initialized:
        _fail()
    collections = (
        ("incidents", 32, "incident_id", "IncidentLedger"),
        ("days", 8, "utc_day", "DailyLedger"),
    )
    for name, maximum, key, kind in collections:
        items = value[name]
        if not isinstance(items, list) or len(items) > maximum:
            _fail("budget_capacity")
        for item in items:
            validate_c(item, kind)
            if item["controller_id"] != controller or item["policy_digest"] != policy:
                _fail()
        keys = [item[key] for item in items]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            _fail()
    grants = value["grants"]
    reservations = value["reservations"]
    if not isinstance(grants, list) or len(grants) > 256:
        _fail("budget_capacity")
    if not isinstance(reservations, list) or len(reservations) > 256:
        _fail("budget_capacity")
    for item in grants:
        _grant_record(item)
    for item in reservations:
        _reservation_record(item)
    grant_ids = [item["challenge_id"] for item in grants]
    reservation_ids = [item["reservation_id"] for item in reservations]
    if grant_ids != sorted(grant_ids) or len(grant_ids) != len(set(grant_ids)):
        _fail()
    if reservation_ids != sorted(reservation_ids) or len(reservation_ids) != len(set(reservation_ids)):
        _fail()
    validate_cross(value)
    return value
