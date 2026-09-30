"""Pure immutable budget transitions for the first Stage C unit."""

from __future__ import annotations

from typing import Any

from .c_contracts import validate_c
from .contracts import ContractError, digest

RESERVATION_TOKENS = 32_000
MARGIN_TOKENS = 4_000
MAX_INT = 2**63 - 1


def _advance(value: dict[str, Any], **changes: Any) -> dict[str, Any]:
    updated = {
        **value,
        "revision": value["revision"] + 1,
        "previous_checkpoint_digest": digest(value),
        **changes,
    }
    return updated


def _same_ledgers(incident: dict[str, Any], daily: dict[str, Any]) -> None:
    validate_c(incident, "IncidentLedger")
    validate_c(daily, "DailyLedger")
    if (
        incident["controller_id"] != daily["controller_id"]
        or incident["policy_digest"] != daily["policy_digest"]
        or daily["utc_day"] < incident["created_utc_day"]
    ):
        raise ContractError("ledger_binding_mismatch")


def new_incident(
    controller_id: str,
    incident_id: str,
    input_digest: str,
    policy: dict[str, Any],
    *,
    utc_day: str,
) -> dict[str, Any]:
    validate_c(policy, "ModelPolicy")
    return validate_c(
        {
            "format_version": 1,
            "controller_id": controller_id,
            "incident_id": incident_id,
            "created_utc_day": utc_day,
            "revision": 0,
            "previous_checkpoint_digest": None,
            "input_digest": input_digest,
            "policy_digest": digest(policy),
            "allowance_tokens": policy["initial_allowance_tokens"],
            "charged_tokens": 0,
            "held_tokens": 0,
            "requests_allowed": policy["requests_per_grant"],
            "requests_started": 0,
            "grants_consumed": 0,
            "state": "ready",
            "usage_status": "none",
            "current_reservation_digest": None,
        },
        "IncidentLedger",
    )


def should_pause(
    incident: dict[str, Any],
    *,
    observed_total_tokens: int,
    next_request_tokens: int = 0,
) -> bool:
    validate_c(incident, "IncidentLedger")
    if (
        type(observed_total_tokens) is not int
        or type(next_request_tokens) is not int
        or observed_total_tokens < 0
        or next_request_tokens < 0
        or observed_total_tokens > MAX_INT - next_request_tokens
    ):
        raise ContractError("invalid_tokens")
    pause_at = incident["allowance_tokens"] - MARGIN_TOKENS
    return (
        observed_total_tokens >= pause_at
        or observed_total_tokens + next_request_tokens > incident["allowance_tokens"]
    )


def reserve_request(
    incident: dict[str, Any], daily: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _same_ledgers(incident, daily)
    if (
        incident["state"] != "ready"
        or incident["current_reservation_digest"] is not None
        or incident["held_tokens"]
        or incident["requests_started"] >= incident["requests_allowed"]
    ):
        raise ContractError("request_unavailable")
    if (
        incident["charged_tokens"] + RESERVATION_TOKENS
        > incident["allowance_tokens"]
        or daily["charged_tokens"] + daily["held_tokens"] + RESERVATION_TOKENS
        > daily["ceiling_tokens"]
    ):
        raise ContractError("budget_exhausted")
    seed = {
        "controller_id": incident["controller_id"],
        "incident_id": incident["incident_id"],
        "utc_day": daily["utc_day"],
        "ledger_revision": incident["revision"],
        "daily_ledger_digest": digest(daily),
        "request_ordinal": incident["requests_started"] + 1,
    }
    request = validate_c(
        {
            "format_version": 1,
            "reservation_id": digest(seed)[7:],
            "controller_id": incident["controller_id"],
            "incident_id": incident["incident_id"],
            "utc_day": daily["utc_day"],
            "input_digest": incident["input_digest"],
            "policy_digest": incident["policy_digest"],
            "ledger_revision": incident["revision"],
            "checkpoint_digest": digest(incident),
            "daily_ledger_revision": daily["revision"],
            "daily_ledger_digest": digest(daily),
            "request_ordinal": incident["requests_started"] + 1,
            "estimated_reserved_tokens": RESERVATION_TOKENS,
            "reservation_basis": "estimate",
            "pause_at_tokens": incident["allowance_tokens"] - MARGIN_TOKENS,
        },
        "RequestReservation",
    )
    next_incident = validate_c(
        _advance(
            incident,
            held_tokens=incident["held_tokens"] + RESERVATION_TOKENS,
            requests_started=incident["requests_started"] + 1,
            state="in_flight",
            usage_status=incident["usage_status"],
            current_reservation_digest=digest(request),
        ),
        "IncidentLedger",
    )
    next_daily = validate_c(
        _advance(daily, held_tokens=daily["held_tokens"] + RESERVATION_TOKENS),
        "DailyLedger",
    )
    return next_incident, next_daily, request


def consume_grant(
    incident: dict[str, Any],
    daily: dict[str, Any],
    grant: dict[str, Any],
    *, grant_tokens: int = 32_000, request_allowance: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _same_ledgers(incident, daily)
    validate_c(grant, "BudgetGrant")
    bindings = (
        grant["controller_id"] == incident["controller_id"],
        grant["incident_id"] == incident["incident_id"],
        grant["input_digest"] == incident["input_digest"],
        grant["policy_digest"] == incident["policy_digest"],
        grant["ledger_revision"] == incident["revision"],
        grant["checkpoint_digest"] == digest(incident),
        grant["daily_ledger_digest"] == digest(daily),
        grant["new_incident_ceiling_tokens"]
        == incident["allowance_tokens"] + grant_tokens,
    )
    if not all(bindings):
        raise ContractError("grant_binding_mismatch")
    if (
        incident["state"] != "awaiting_budget_approval"
        or incident["held_tokens"]
        or incident["current_reservation_digest"] is not None
    ):
        raise ContractError("grant_unavailable")
    override = grant["daily_ceiling_override_tokens"]
    ceiling = daily["ceiling_tokens"] if override is None else override
    if override is not None and override <= daily["ceiling_tokens"]:
        raise ContractError("invalid_daily_override")
    if daily["charged_tokens"] + daily["held_tokens"] + RESERVATION_TOKENS > ceiling:
        raise ContractError("daily_budget_exhausted")
    next_incident = validate_c(
        _advance(
            incident,
            allowance_tokens=grant["new_incident_ceiling_tokens"],
            requests_allowed=incident["requests_allowed"] + request_allowance,
            grants_consumed=incident["grants_consumed"] + 1,
            state="ready",
        ),
        "IncidentLedger",
    )
    next_daily = validate_c(_advance(daily, ceiling_tokens=ceiling), "DailyLedger")
    return next_incident, next_daily


def normalize_usage(evidence: dict[str, Any]) -> int:
    validate_c(evidence, "UsageEvidence")
    return evidence["input_tokens"] + evidence["generated_tokens"]


def _request_bindings(
    incident: dict[str, Any], daily: dict[str, Any], request: dict[str, Any]
) -> None:
    _same_ledgers(incident, daily)
    validate_c(request, "RequestReservation")
    seed = {
        "controller_id": request["controller_id"],
        "incident_id": request["incident_id"],
        "utc_day": request["utc_day"],
        "ledger_revision": request["ledger_revision"],
        "daily_ledger_digest": request["daily_ledger_digest"],
        "request_ordinal": request["request_ordinal"],
    }
    immediate = incident["state"] == "in_flight"
    if (
        request["reservation_id"] != digest(seed)[7:]
        or request["controller_id"] != incident["controller_id"]
        or request["incident_id"] != incident["incident_id"]
        or request["input_digest"] != incident["input_digest"]
        or request["policy_digest"] != incident["policy_digest"]
        or request["utc_day"] != daily["utc_day"]
        or request["request_ordinal"] != incident["requests_started"]
        or incident["current_reservation_digest"] != digest(request)
        or incident["held_tokens"] != request["estimated_reserved_tokens"]
        or daily["held_tokens"] < request["estimated_reserved_tokens"]
        or incident["revision"] < request["ledger_revision"] + 1
        or daily["revision"] < request["daily_ledger_revision"] + 1
        or incident["state"] not in {"in_flight", "awaiting_usage"}
        or request["pause_at_tokens"] != incident["allowance_tokens"] - MARGIN_TOKENS
        or (
            immediate
            and (
                incident["revision"] != request["ledger_revision"] + 1
                or daily["revision"] != request["daily_ledger_revision"] + 1
                or incident["previous_checkpoint_digest"]
                != request["checkpoint_digest"]
                or daily["previous_checkpoint_digest"]
                != request["daily_ledger_digest"]
            )
        )
    ):
        raise ContractError("reservation_binding_mismatch")


def settle_request(
    incident: dict[str, Any],
    daily: dict[str, Any],
    request: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    _request_bindings(incident, daily, request)
    validate_c(evidence, "UsageEvidence")
    if evidence["reservation_digest"] != digest(request):
        raise ContractError("usage_binding_mismatch")
    if not evidence["usage_final"]:
        if incident["state"] == "awaiting_usage":
            raise ContractError("usage_still_unresolved")
        next_incident = validate_c(
            _advance(incident, state="awaiting_usage", usage_status="estimated"),
            "IncidentLedger",
        )
        next_daily = validate_c(_advance(daily), "DailyLedger")
        return next_incident, next_daily
    total = normalize_usage(evidence)
    if incident["charged_tokens"] > MAX_INT - total or daily["charged_tokens"] > MAX_INT - total:
        raise ContractError("token_overflow")
    held = request["estimated_reserved_tokens"]
    usage_status = evidence["usage_basis"]
    if incident["usage_status"] == "estimated" and incident["charged_tokens"] > 0:
        usage_status = "estimated"
    next_incident = validate_c(
        _advance(
            incident,
            charged_tokens=incident["charged_tokens"] + total,
            held_tokens=incident["held_tokens"] - held,
            state="ready" if incident["requests_started"] < incident["requests_allowed"] else "awaiting_budget_approval",
            usage_status=usage_status,
            current_reservation_digest=None,
        ),
        "IncidentLedger",
    )
    next_daily = validate_c(
        _advance(
            daily,
            charged_tokens=daily["charged_tokens"] + total,
            held_tokens=daily["held_tokens"] - held,
        ),
        "DailyLedger",
    )
    return next_incident, next_daily
