"""Independent pure-budget observations used by the budget-only verifier."""

from __future__ import annotations


class VerifyFailure(AssertionError):
    pass


def policy() -> dict:
    return {
        "format_version": 2,
        "policy_id": "astra-medium-budget-v2",
        "transport_id": "codex-runner-v1",
        "auth_mode": "existing_codex_login",
        "model": "gpt-6-astra",
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


def daily(policy_digest: str) -> dict:
    return {
        "format_version": 1,
        "controller_id": "controller-verify",
        "utc_day": "2026-09-20",
        "revision": 0,
        "previous_checkpoint_digest": None,
        "policy_digest": policy_digest,
        "ceiling_tokens": 64_000,
        "charged_tokens": 0,
        "held_tokens": 0,
    }


def evidence(request: dict, input_tokens: int, generated_tokens: int) -> dict:
    from session_recall.codex_fix.contracts import digest

    return {
        "format_version": 2,
        "reservation_digest": digest(request),
        "transport_request_id": f"request-{request['request_ordinal']}",
        "requested_model": "gpt-6-astra",
        "reported_model": "gpt-6-astra",
        "requested_effort": "medium",
        "reported_effort": "medium",
        "usage_scope": "per_request",
        "usage_accounting": "estimated_with_actual_reconciliation_v1",
        "usage_basis": "actual",
        "usage_final": True,
        "response_status": "completed",
        "input_tokens": input_tokens,
        "cached_input_tokens": min(4_000, input_tokens),
        "generated_tokens": generated_tokens,
        "reasoning_tokens": min(3_000, generated_tokens),
    }


def usage_observation() -> dict:
    import session_recall.codex_fix.budget as budget_module
    from session_recall.codex_fix.budget import (
        new_incident,
        normalize_usage,
        reserve_request,
        settle_request,
    )
    from session_recall.codex_fix.contracts import digest

    chosen_policy = policy()
    incident = new_incident(
        "controller-verify", "incident-verify", "sha256:" + "1" * 64,
        chosen_policy, utc_day="2026-09-20",
    )
    chosen_daily = daily(digest(chosen_policy))
    held, held_daily, request = reserve_request(incident, chosen_daily)
    observed = evidence(request, 10_000, 8_000)
    settled, settled_daily = settle_request(held, held_daily, request, observed)
    return {
        "normalized": normalize_usage(observed),
        "incident_charged": settled["charged_tokens"],
        "daily_charged": settled_daily["charged_tokens"],
        "mutant": getattr(budget_module, "VERIFY_MUTANT_EXECUTED", False),
    }


def require_usage(observed: dict) -> None:
    wanted = {
        "normalized": 18_000,
        "incident_charged": 18_000,
        "daily_charged": 18_000,
    }
    actual = {key: observed.get(key) for key in wanted}
    if actual != wanted:
        raise VerifyFailure(f"usage_subset_double_count:{actual!r}")


def grant_replay_overshoot() -> None:
    from session_recall.codex_fix.budget import (
        consume_grant,
        new_incident,
        reserve_request,
        settle_request,
    )
    from session_recall.codex_fix.contracts import ContractError, digest

    chosen_policy = policy()
    incident = new_incident(
        "controller-verify", "incident-verify", "sha256:" + "1" * 64,
        chosen_policy, utc_day="2026-09-20",
    )
    chosen_daily = daily(digest(chosen_policy))
    incident, chosen_daily, first = reserve_request(incident, chosen_daily)
    incident, chosen_daily = settle_request(
        incident, chosen_daily, first, evidence(first, 10_000, 8_000)
    )
    grant = {
        "format_version": 1, "grant_id": "grant-verify", "decision": "continue",
        "controller_id": incident["controller_id"], "incident_id": incident["incident_id"],
        "input_digest": incident["input_digest"], "policy_digest": incident["policy_digest"],
        "ledger_revision": incident["revision"], "checkpoint_digest": digest(incident),
        "daily_ledger_digest": digest(chosen_daily), "grant_tokens": 32_000,
        "new_incident_ceiling_tokens": 64_000, "request_allowance": 1,
        "daily_ceiling_override_tokens": None, "actor_label": "maintainer",
        "approved_at": "2026-09-20T08:00:00Z",
    }
    granted, granted_daily = consume_grant(incident, chosen_daily, grant)
    if granted["allowance_tokens"] != 64_000 or granted["requests_allowed"] != 2:
        raise VerifyFailure("grant_increment_not_32000")
    try:
        consume_grant(granted, granted_daily, grant)
    except ContractError:
        pass
    else:
        raise VerifyFailure("grant_replay_accepted")
    held, held_daily, second = reserve_request(granted, granted_daily)
    settled, settled_daily = settle_request(
        held, held_daily, second, evidence(second, 17_000, 18_000)
    )
    if settled["charged_tokens"] != 53_000 or settled_daily["charged_tokens"] != 53_000:
        raise VerifyFailure("actual_overshoot_not_fully_charged")


def behavior_observation() -> dict:
    try:
        observed = usage_observation()
        require_usage(observed)
        grant_replay_overshoot()
    except VerifyFailure as exc:
        return {"verdict": "fail", "reason": str(exc)}
    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "verdict": "error",
            "reason": f"{type(exc).__name__}: {exc}",
        }
    except Exception as exc:
        return {
            "verdict": "fail",
            "reason": f"unexpected {type(exc).__name__}: {exc}",
        }
    return {"verdict": "pass", "usage": observed}
