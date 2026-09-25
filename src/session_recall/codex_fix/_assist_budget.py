"""Foreground request accounting and explicit CLI budget approvals."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .budget_store import BudgetStore, ApprovalEvent
from .contracts import ContractError, digest
from .policy import production_model_policy


class Clock:
    def now_utc(self):
        return datetime.now(timezone.utc)


def budget_store(root, *, approval_source=None):
    store = BudgetStore(root, 'codex-repair-controller', production_model_policy(), clock=Clock(), approval_source=approval_source)
    if not store.directory.exists() and not store.directory.is_symlink():
        store.initialize()
    return store


def reserve(root, request):
    store = budget_store(root)
    record = store.read()
    incident_id = request['incident_id']
    if not any(i['incident_id'] == incident_id for i in record['incidents']):
        record = store.create_incident(incident_id, digest(request), expected_revision=record['revision'])
    incident = next(i for i in record['incidents'] if i['incident_id'] == incident_id)
    if incident['input_digest'] != digest(request):
        raise ContractError('incident_input_mismatch')
    if incident['state'] in {'in_flight', 'awaiting_usage'}:
        return store, None, {'status': 'usage_pending', 'incident_id': incident_id}
    try:
        reservation = store.reserve_request(incident_id, expected_revision=record['revision'])
        return store, reservation, None
    except ContractError as exc:
        if exc.code not in {'request_unavailable', 'budget_exhausted'}:
            raise
    pending = next((g['challenge'] for g in record['grants'] if g['status'] == 'pending' and g['challenge']['incident_id'] == incident_id), None)
    if pending is None:
        day = store.clock.now_utc().strftime('%Y-%m-%d')
        daily = next((d for d in record['days'] if d['utc_day'] == day), None)
        override = None
        if daily is not None and store.policy['format_version'] == 3:
            override = daily['ceiling_tokens'] + store.policy['grant_increment_tokens']
        elif daily is not None and daily['charged_tokens'] + daily['held_tokens'] + 32_000 > daily['ceiling_tokens']:
            # Round to the next valid policy increment; approval names the exact ceiling.
            needed = daily['charged_tokens'] + daily['held_tokens'] + 32_000
            increment = store.policy['grant_increment_tokens']
            missing = needed - daily['ceiling_tokens']
            override = daily['ceiling_tokens'] + ((missing + increment - 1) // increment) * increment
        pending = store.checkpoint_for_approval(incident_id, expected_revision=record['revision'], daily_ceiling_override_tokens=override)
    return store, None, {'status': 'action_needed', 'action': 'budget_approval', 'challenge': pending}


def settle(store, reservation, result):
    evidence = result.get('evidence') or {}
    usage = evidence.get('usage')
    actual = (isinstance(usage, dict) and type(usage.get('input_tokens')) is int
              and type(usage.get('output_tokens')) is int
              and 0 <= usage['input_tokens'] < 2**62 and 0 <= usage['output_tokens'] < 2**62)
    receipt = {
        'format_version': store.policy['format_version'], 'reservation_digest': digest(reservation),
        'transport_request_id': reservation['reservation_id'],
        'requested_model': 'gpt-6-astra', 'requested_effort': 'medium',
        'reported_model': None, 'reported_effort': None,
        'usage_scope': 'per_request', 'usage_accounting': 'estimated_with_actual_reconciliation_v1',
        'usage_basis': 'actual' if actual else 'estimated', 'usage_final': True,
        'response_status': 'completed' if result['status'] == 'completed' else 'failed',
        'input_tokens': usage['input_tokens'] if actual else 16_000,
        'cached_input_tokens': 0, 'generated_tokens': usage['output_tokens'] if actual else 16_000,
        'reasoning_tokens': 0,
    }
    # Mismatches remain in transport evidence; accounting must still charge the failed attempt.
    for name, expected in (('reported_model', 'gpt-6-astra'), ('reported_effort', 'medium')):
        if evidence.get(name) == expected:
            receipt[name] = expected
    return store.settle_request(reservation['reservation_id'], receipt, expected_revision=store.read()['revision'])


class CliApproval:
    source_id = 'foreground-cli'

    def resolve(self, challenge: dict[str, Any]):
        return ApprovalEvent(
            source_id=self.source_id, event_id=challenge['challenge_id'],
            challenge_digest=digest(challenge),
            actor_label='local-cli-user', approved_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            decision='continue',
        )


def approve_budget(root, challenge_id):
    store = budget_store(root, approval_source=CliApproval())
    return store.apply_verified_approval(challenge_id, expected_revision=store.read()['revision'])
