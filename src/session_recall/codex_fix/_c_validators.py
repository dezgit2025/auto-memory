"""Validation rules for the six frozen Stage C budget envelopes."""

from __future__ import annotations

from datetime import date, datetime, timezone
import re
from typing import Any, Callable

from .contracts import ContractError

MAX_INT = 2**63 - 1
ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def fail(message: str) -> None:
    raise ContractError("invalid_contract", message)


def obj(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        fail(f"{label} must contain exactly {sorted(fields)!r}")
    return value


def integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_INT:
        fail(f"{label} must be an integer in {minimum}..{MAX_INT}")
    return value


def exact_int(value: Any, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        fail(f"{label} must be {expected}")


def boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        fail(f"{label} must be a boolean")
    return value


def string(value: Any, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str):
        fail(f"{label} must be a string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ContractError("invalid_contract", f"{label} is invalid Unicode") from exc
    if size > maximum:
        fail(f"{label} exceeds {maximum} UTF-8 bytes")
    return value


def exact(value: Any, expected: Any, label: str) -> None:
    if type(value) is not type(expected) or value != expected:
        fail(f"{label} must be {expected!r}")


def enum(value: Any, allowed: set[str], label: str) -> str:
    string(value, label)
    if value not in allowed:
        fail(f"{label} has an unsupported value")
    return value


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        fail(f"{label} is not a valid identifier")
    return value


def digest_value(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        fail(f"{label} is not a sha256 digest")
    return value


def utc_day(value: Any, label: str) -> str:
    string(value, label, 10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError("invalid_contract", f"{label} is not a date") from exc
    if parsed.isoformat() != value:
        fail(f"{label} is not canonical")
    return value


def utc_time(value: Any, label: str) -> str:
    string(value, label, 64)
    if UTC_RE.fullmatch(value) is None:
        fail(f"{label} must be a second-resolution UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("invalid_contract", f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        fail(f"{label} must be UTC")
    return value


def version(value: dict[str, Any], label: str) -> None:
    exact_int(value["format_version"], 1, f"{label}.format_version")


def checkpoint(value: dict[str, Any], label: str) -> None:
    revision = integer(value["revision"], f"{label}.revision")
    previous = digest_value(
        value["previous_checkpoint_digest"],
        f"{label}.previous_checkpoint_digest",
        nullable=True,
    )
    if revision == 0 and previous is not None:
        fail(f"{label} revision zero cannot have a previous checkpoint")
    if revision > 0 and previous is None:
        fail(f"{label} nonzero revision requires a previous checkpoint")


def model_policy(value: Any) -> None:
    fields = {
        "format_version", "policy_id", "transport_id", "auth_mode", "model",
        "effort", "initial_allowance_tokens", "input_estimate_tokens",
        "generation_estimate_tokens", "checkpoint_margin_tokens",
        "grant_increment_tokens", "daily_ceiling_tokens", "requests_per_grant",
        "automatic_retries", "timeout_seconds", "usage_accounting", "background",
        "auto_approve", "auto_activate",
    }
    value = obj(value, fields, "ModelPolicy")
    format_version = integer(value["format_version"], "ModelPolicy.format_version", minimum=1)
    shared = {
        "transport_id": "codex-runner-v1",
        "auth_mode": "existing_codex_login",
        "effort": "medium",
        "initial_allowance_tokens": 32_000,
        "input_estimate_tokens": 16_000,
        "generation_estimate_tokens": 16_000,
        "checkpoint_margin_tokens": 4_000,
        "grant_increment_tokens": 32_000,
        "daily_ceiling_tokens": 64_000,
        "requests_per_grant": 1,
        "automatic_retries": 0,
        "timeout_seconds": 300,
        "usage_accounting": "estimated_with_actual_reconciliation_v1",
        "background": False,
        "auto_approve": False,
        "auto_activate": False,
    }
    identities = {
        1: {"policy_id": "sol-medium-budget-v1", "model": "gpt-5.6-sol"},
        2: {"policy_id": "astra-medium-budget-v2", "model": "gpt-6-astra"},
        3: {"policy_id": "astra-medium-budget-v3", "model": "gpt-6-astra",
            "initial_allowance_tokens": 100_000, "daily_ceiling_tokens": 100_000,
            "grant_increment_tokens": 100_000, "requests_per_grant": 3},
    }
    if format_version not in identities:
        fail("ModelPolicy.format_version is unsupported")
    constants = {**shared, **identities[format_version]}
    for name, expected in constants.items():
        exact(value[name], expected, f"ModelPolicy.{name}")


def incident(value: Any) -> None:
    fields = {
        "format_version", "controller_id", "incident_id", "created_utc_day",
        "revision", "previous_checkpoint_digest", "input_digest", "policy_digest",
        "allowance_tokens", "charged_tokens", "held_tokens", "requests_allowed",
        "requests_started", "grants_consumed", "state", "usage_status",
        "current_reservation_digest",
    }
    value = obj(value, fields, "IncidentLedger")
    version(value, "IncidentLedger")
    identifier(value["controller_id"], "IncidentLedger.controller_id")
    identifier(value["incident_id"], "IncidentLedger.incident_id")
    utc_day(value["created_utc_day"], "IncidentLedger.created_utc_day")
    checkpoint(value, "IncidentLedger")
    digest_value(value["input_digest"], "IncidentLedger.input_digest")
    digest_value(value["policy_digest"], "IncidentLedger.policy_digest")
    allowance = integer(value["allowance_tokens"], "IncidentLedger.allowance_tokens")
    charged = integer(value["charged_tokens"], "IncidentLedger.charged_tokens")
    held = integer(value["held_tokens"], "IncidentLedger.held_tokens")
    allowed = integer(value["requests_allowed"], "IncidentLedger.requests_allowed")
    started = integer(value["requests_started"], "IncidentLedger.requests_started")
    grants = integer(value["grants_consumed"], "IncidentLedger.grants_consumed")
    enum(value["state"], {"ready", "in_flight", "awaiting_usage", "awaiting_budget_approval"}, "IncidentLedger.state")
    enum(value["usage_status"], {"none", "estimated", "actual"}, "IncidentLedger.usage_status")
    reservation = digest_value(value["current_reservation_digest"], "IncidentLedger.current_reservation_digest", nullable=True)
    legacy_shape = allowance == 32_000 * (grants + 1) and allowed == grants + 1
    larger_shape = allowance == 100_000 * (grants + 1) and allowed == 3 * (grants + 1)
    if not (legacy_shape or larger_shape) or started > allowed:
        fail("IncidentLedger allowance/request arithmetic is inconsistent")
    if held not in {0, 32_000} or (held > 0) != (reservation is not None):
        fail("IncidentLedger reservation hold is inconsistent")
    if value["state"] in {"in_flight", "awaiting_usage"} and held != 32_000:
        fail("IncidentLedger active request requires its hold")
    if value["state"] in {"ready", "awaiting_budget_approval"} and (held or reservation):
        fail("IncidentLedger inactive state cannot retain a hold")
    if value["state"] == "ready" and (held or started >= allowed):
        fail("IncidentLedger ready state is inconsistent")
    if value["state"] == "awaiting_usage" and value["usage_status"] != "estimated":
        fail("IncidentLedger unresolved usage must remain estimated")
    if charged and value["usage_status"] == "none":
        fail("IncidentLedger charged usage cannot have none status")
    if charged > MAX_INT - held:
        fail("IncidentLedger token arithmetic overflows")


def daily(value: Any) -> None:
    fields = {"format_version", "controller_id", "utc_day", "revision", "previous_checkpoint_digest", "policy_digest", "ceiling_tokens", "charged_tokens", "held_tokens"}
    value = obj(value, fields, "DailyLedger")
    version(value, "DailyLedger")
    identifier(value["controller_id"], "DailyLedger.controller_id")
    utc_day(value["utc_day"], "DailyLedger.utc_day")
    checkpoint(value, "DailyLedger")
    digest_value(value["policy_digest"], "DailyLedger.policy_digest")
    ceiling = integer(value["ceiling_tokens"], "DailyLedger.ceiling_tokens")
    charged = integer(value["charged_tokens"], "DailyLedger.charged_tokens")
    held = integer(value["held_tokens"], "DailyLedger.held_tokens")
    valid_ceiling = (ceiling >= 64_000 and ceiling % 32_000 == 0) or (ceiling >= 100_000 and ceiling % 100_000 == 0)
    if not valid_ceiling or held % 32_000 or charged > MAX_INT - held:
        fail("DailyLedger token arithmetic is inconsistent")


def grant(value: Any) -> None:
    fields = {"format_version", "grant_id", "decision", "controller_id", "incident_id", "input_digest", "policy_digest", "ledger_revision", "checkpoint_digest", "daily_ledger_digest", "grant_tokens", "new_incident_ceiling_tokens", "request_allowance", "daily_ceiling_override_tokens", "actor_label", "approved_at"}
    value = obj(value, fields, "BudgetGrant")
    version(value, "BudgetGrant")
    identifier(value["grant_id"], "BudgetGrant.grant_id")
    exact(value["decision"], "continue", "BudgetGrant.decision")
    identifier(value["controller_id"], "BudgetGrant.controller_id")
    identifier(value["incident_id"], "BudgetGrant.incident_id")
    digest_value(value["input_digest"], "BudgetGrant.input_digest")
    digest_value(value["policy_digest"], "BudgetGrant.policy_digest")
    integer(value["ledger_revision"], "BudgetGrant.ledger_revision")
    digest_value(value["checkpoint_digest"], "BudgetGrant.checkpoint_digest")
    digest_value(value["daily_ledger_digest"], "BudgetGrant.daily_ledger_digest")
    tokens = integer(value["grant_tokens"], "BudgetGrant.grant_tokens")
    ceiling = integer(value["new_incident_ceiling_tokens"], "BudgetGrant.new_incident_ceiling_tokens")
    requests = integer(value["request_allowance"], "BudgetGrant.request_allowance")
    old_shape = tokens == 32_000 and requests == 1 and ceiling >= 64_000 and ceiling % 32_000 == 0
    new_shape = tokens == 100_000 and requests == 3 and ceiling >= 200_000 and ceiling % 100_000 == 0
    if not (old_shape or new_shape):
        fail("BudgetGrant incident ceiling is invalid")
    override = value["daily_ceiling_override_tokens"]
    if override is not None:
        override = integer(override, "BudgetGrant.daily_ceiling_override_tokens")
        if not ((old_shape and override >= 96_000 and override % 32_000 == 0) or (new_shape and override >= 200_000 and override % 100_000 == 0)):
            fail("BudgetGrant daily override is invalid")
    if not string(value["actor_label"], "BudgetGrant.actor_label", 128):
        fail("BudgetGrant.actor_label must not be empty")
    utc_time(value["approved_at"], "BudgetGrant.approved_at")


def reservation(value: Any) -> None:
    fields = {"format_version", "reservation_id", "controller_id", "incident_id", "utc_day", "input_digest", "policy_digest", "ledger_revision", "checkpoint_digest", "daily_ledger_revision", "daily_ledger_digest", "request_ordinal", "estimated_reserved_tokens", "reservation_basis", "pause_at_tokens"}
    value = obj(value, fields, "RequestReservation")
    version(value, "RequestReservation")
    identifier(value["reservation_id"], "RequestReservation.reservation_id")
    identifier(value["controller_id"], "RequestReservation.controller_id")
    identifier(value["incident_id"], "RequestReservation.incident_id")
    utc_day(value["utc_day"], "RequestReservation.utc_day")
    digest_value(value["input_digest"], "RequestReservation.input_digest")
    digest_value(value["policy_digest"], "RequestReservation.policy_digest")
    integer(value["ledger_revision"], "RequestReservation.ledger_revision")
    digest_value(value["checkpoint_digest"], "RequestReservation.checkpoint_digest")
    integer(value["daily_ledger_revision"], "RequestReservation.daily_ledger_revision")
    digest_value(value["daily_ledger_digest"], "RequestReservation.daily_ledger_digest")
    integer(value["request_ordinal"], "RequestReservation.request_ordinal", minimum=1)
    exact_int(value["estimated_reserved_tokens"], 32_000, "RequestReservation.estimated_reserved_tokens")
    exact(value["reservation_basis"], "estimate", "RequestReservation.reservation_basis")
    pause = integer(value["pause_at_tokens"], "RequestReservation.pause_at_tokens")
    if not ((pause >= 28_000 and (pause + 4_000) % 32_000 == 0) or (pause >= 96_000 and (pause + 4_000) % 100_000 == 0)):
        fail("RequestReservation pause boundary is invalid")


def usage(value: Any) -> None:
    if not isinstance(value, dict):
        fail("UsageEvidence must be an object")
    format_version = value.get("format_version")
    if type(format_version) is not int:
        fail("UsageEvidence.format_version must be an integer")
    shared = {"format_version", "reservation_digest", "transport_request_id", "requested_model", "usage_scope", "usage_accounting", "usage_basis", "usage_final", "response_status", "input_tokens", "cached_input_tokens", "generated_tokens", "reasoning_tokens"}
    versioned = {
        1: {"effective_model", "effort"},
        2: {"reported_model", "requested_effort", "reported_effort"},
        3: {"reported_model", "requested_effort", "reported_effort"},
    }
    if format_version not in versioned:
        fail("UsageEvidence.format_version is unsupported")
    fields = shared | versioned[format_version]
    value = obj(value, fields, "UsageEvidence")
    digest_value(value["reservation_digest"], "UsageEvidence.reservation_digest")
    identifier(value["transport_request_id"], "UsageEvidence.transport_request_id")
    if format_version == 1:
        exact(value["requested_model"], "gpt-5.6-sol", "UsageEvidence.requested_model")
        exact(value["effective_model"], "gpt-5.6-sol", "UsageEvidence.effective_model")
        exact(value["effort"], "medium", "UsageEvidence.effort")
    else:
        exact(value["requested_model"], "gpt-6-astra", "UsageEvidence.requested_model")
        exact(value["requested_effort"], "medium", "UsageEvidence.requested_effort")
        reported_model = value["reported_model"]
        reported_effort = value["reported_effort"]
        if reported_model is not None:
            exact(reported_model, "gpt-6-astra", "UsageEvidence.reported_model")
        if reported_effort is not None:
            exact(reported_effort, "medium", "UsageEvidence.reported_effort")
    exact(value["usage_scope"], "per_request", "UsageEvidence.usage_scope")
    exact(value["usage_accounting"], "estimated_with_actual_reconciliation_v1", "UsageEvidence.usage_accounting")
    enum(value["usage_basis"], {"actual", "estimated"}, "UsageEvidence.usage_basis")
    boolean(value["usage_final"], "UsageEvidence.usage_final")
    enum(value["response_status"], {"completed", "interrupted", "no_response", "failed"}, "UsageEvidence.response_status")
    input_tokens = integer(value["input_tokens"], "UsageEvidence.input_tokens")
    cached = integer(value["cached_input_tokens"], "UsageEvidence.cached_input_tokens")
    generated = integer(value["generated_tokens"], "UsageEvidence.generated_tokens")
    reasoning = integer(value["reasoning_tokens"], "UsageEvidence.reasoning_tokens")
    if cached > input_tokens or reasoning > generated or input_tokens > MAX_INT - generated:
        fail("UsageEvidence token subsets are inconsistent")
    if value["response_status"] == "no_response" and any((input_tokens, cached, generated, reasoning)):
        fail("UsageEvidence no_response must have zero usage")


VALIDATORS: dict[str, Callable[[Any], None]] = {
    "ModelPolicy": model_policy,
    "IncidentLedger": incident,
    "DailyLedger": daily,
    "BudgetGrant": grant,
    "RequestReservation": reservation,
    "UsageEvidence": usage,
}
