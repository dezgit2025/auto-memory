"""Digest-bound human review and locally approved recipe promotion."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
from typing import Any

from . import artifacts
from ._candidate_contracts import validate_input, validate_candidate
from ._candidate_store import identifier, read_record, write_once
from ._store_io import activation_lock, protect_root, timestamp
from ._store_preconditions import CHECK_IDS
from .contracts import ContractError, digest, validate
from .policy import model_policy, production_model_policy


def _raw_digest(data: bytes) -> str:
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def validate_review(value: dict[str, Any]) -> dict[str, Any]:
    from .candidate import ACCEPTANCE_DIGEST
    fields = {'format_version', 'request', 'candidate', 'snapshot', 'artifact_digest', 'evidence', 'result'}
    if set(value) != fields or type(value['format_version']) is not int or value['format_version'] != 1:
        raise ContractError('invalid_review')
    request = validate_input(value['request'])
    candidate = validate_candidate(value['candidate'], request)
    snapshot = validate(value['snapshot'], 'SchemaSnapshot')
    supported_policies = {digest(model_policy()), digest(production_model_policy())}
    if request['policy_digest'] not in supported_policies or request['acceptance_contract_digest'] != ACCEPTANCE_DIGEST:
        raise ContractError('stale_review_policy')
    result = value['result']
    expected = {
        'format_version': 1, 'candidate_digest': digest(candidate),
        'input_fingerprint': request['input_fingerprint'],
        'policy_digest': request['policy_digest'],
        'acceptance_contract_digest': ACCEPTANCE_DIGEST,
        'check_ids': [*CHECK_IDS, 'sandbox_denials_v1'], 'verdict': 'pass',
        'transport_evidence_digest': digest(value['evidence']),
    }
    if result != expected:
        raise ContractError('invalid_independent_result')
    if not snapshot['state']['json1'] or not snapshot['history']['json1']:
        raise ContractError('invalid_review_snapshot')
    if not isinstance(value['artifact_digest'], str) or not value['artifact_digest'].startswith('sha256:'):
        raise ContractError('invalid_artifact_digest')
    identifier(value['artifact_digest'][7:])
    return value


def save_review(root: Path, value: dict[str, Any]) -> str:
    validate_review(value)
    candidate_id = digest(value['candidate'])[7:]
    write_once(root, f'candidates/{candidate_id}/review.json', value)
    return candidate_id


def load_review(root: Path, candidate_id: str) -> dict[str, Any]:
    protect_root(root)
    identifier(candidate_id)
    folder = root / 'candidates' / candidate_id
    for path in (root / 'candidates', folder):
        if path.is_symlink() or not path.is_dir():
            raise ContractError('unsafe_candidate_record')
    value = validate_review(read_record(folder / 'review.json'))
    if digest(value['candidate'])[7:] != candidate_id:
        raise ContractError('candidate_digest_mismatch')
    return value


def verify_artifact(value: dict[str, Any], context: Any) -> Path:
    from .candidate import build_bytes
    base = artifacts.resolve(value['request']['base_artifact_digest'], context)
    expected = build_bytes(value['request'], value['candidate'], value['snapshot'], base)
    if _raw_digest(expected) != value['artifact_digest']:
        raise ContractError('candidate_artifact_mismatch')
    target = context.managed_root / 'artifacts' / 'sha256' / value['artifact_digest'][7:] / 'adapter.pyz'
    artifacts._no_symlink_components(target, context.managed_root)
    manifest = artifacts.manifest(target, value['artifact_digest'])
    if manifest['schema_fingerprint'] != value['snapshot']['schema_fingerprint']:
        raise ContractError('candidate_schema_mismatch')
    return target


def approve(candidate_id: str, context: Any, *, actor: str) -> dict[str, Any]:
    """Called only by explicit human CLI action, never by generated JSON."""
    if not isinstance(actor, str) or not actor.strip() or len(actor.encode()) > 128:
        raise ContractError('invalid_approval_actor')
    value = load_review(context.managed_root, candidate_id)
    if context.recapture()['schema_fingerprint'] != value['snapshot']['schema_fingerprint']:
        raise ContractError('stale_candidate_schema')
    if context.adapter_identity['artifact_digest'] != value['request']['base_artifact_digest']:
        raise ContractError('stale_candidate_base')
    verify_artifact(value, context)
    record = {
        'format_version': 1, 'candidate_digest': digest(value['candidate']),
        'input_fingerprint': value['request']['input_fingerprint'],
        'policy_digest': value['request']['policy_digest'],
        'independent_result_digest': digest(value['result']),
        'decision': 'approved', 'actor_label': actor, 'approved_at': timestamp(),
    }
    with activation_lock(context.managed_root) as acquired:
        if not acquired:
            raise ContractError('busy')
        from .trust import load_catalogue
        base_catalogue = load_catalogue()
        base_context = replace(context, catalogue=base_catalogue, catalogue_digest=digest(base_catalogue), current_observation=None)
        existing = effective_catalogue(base_catalogue, base_context)
        matching = [r for r in existing['recipes'] if r['source_adapter_digest'] == value['request']['base_artifact_digest'] and r['schema_fingerprint'] == value['snapshot']['schema_fingerprint']]
        if matching and any(r['recipe_id'] != 'candidate-' + candidate_id[:54] for r in matching):
            raise ContractError('ambiguous_candidate_approval')
        from .engine import observe
        observed = observe(context.recapture(), context)
        if observed['input_fingerprint'] != value['request']['input_fingerprint']:
            raise ContractError('stale_candidate_input')
        location = context.managed_root / 'approvals' / f'{candidate_id}.json'
        if location.exists():
            prior = read_record(location)
            if {k: v for k, v in prior.items() if k != 'approved_at'} != {k: v for k, v in record.items() if k != 'approved_at'}:
                raise ContractError('approval_conflict')
            return prior
        write_once(context.managed_root, f'approvals/{candidate_id}.json', record)
    return record


def effective_catalogue(base: dict[str, Any], context: Any) -> dict[str, Any]:
    """Derive trusted recipes from immutable human approvals, including on restart."""
    root = context.managed_root
    folder = root / 'approvals'
    if not folder.exists() and not folder.is_symlink():
        return base
    protect_root(root)
    if folder.is_symlink() or not folder.is_dir():
        raise ContractError('unsafe_approval_store')
    paths = sorted(folder.iterdir())
    if len(paths) + len(base['recipes']) > 128:
        raise ContractError('approval_capacity')
    catalogue = {**base, 'recipes': list(base['recipes'])}
    pending = []
    for path in paths:
        if path.suffix != '.json':
            raise ContractError('invalid_approval_record')
        candidate_id = identifier(path.stem)
        value = load_review(root, candidate_id)
        approval = read_record(path)
        expected = {
            'format_version': 1, 'candidate_digest': digest(value['candidate']),
            'input_fingerprint': value['request']['input_fingerprint'],
            'policy_digest': value['request']['policy_digest'],
            'independent_result_digest': digest(value['result']), 'decision': 'approved',
            'actor_label': approval.get('actor_label'), 'approved_at': approval.get('approved_at'),
        }
        if approval != expected or not isinstance(approval['actor_label'], str) or not approval['actor_label']:
            raise ContractError('invalid_approval_binding')
        if not isinstance(approval['approved_at'], str) or not approval['approved_at']:
            raise ContractError('invalid_approval_binding')
        pending.append((candidate_id, value))
    with tempfile.TemporaryDirectory(prefix='codex-approved-derivation-') as temporary:
        return _derive_catalogue(catalogue, context, pending, Path(temporary))


def _derive_catalogue(catalogue, context, pending, temporary):
    from .candidate import build_bytes
    derived_paths = {}
    while pending:
        known = {catalogue['seed_artifact_digest']}
        for recipe in catalogue['recipes']:
            known.update((recipe['source_adapter_digest'], recipe['target_artifact_digest']))
        ready = [(key, value) for key, value in pending if value['request']['base_artifact_digest'] in known]
        if not ready:
            raise ContractError('untrusted_candidate_base')
        for key, value in ready:
            trusted = replace(context, catalogue=catalogue, catalogue_digest=digest(catalogue))
            source_digest = value['request']['base_artifact_digest']
            source_path = derived_paths.get(source_digest)
            if source_path is None:
                source_path = artifacts.resolve(source_digest, trusted)
            built = build_bytes(value['request'], value['candidate'], value['snapshot'], source_path)
            if _raw_digest(built) != value['artifact_digest']:
                raise ContractError('candidate_artifact_mismatch')
            derived = temporary / (value['artifact_digest'][7:] + '.pyz')
            derived.write_bytes(built)
            derived_paths[value['artifact_digest']] = derived
            recipe = {
                'recipe_id': 'candidate-' + key[:54],
                'source_adapter_digest': value['request']['base_artifact_digest'],
                'schema_fingerprint': value['snapshot']['schema_fingerprint'],
                'target_artifact_digest': value['artifact_digest'], 'check_ids': list(CHECK_IDS),
            }
            if any(r['source_adapter_digest'] == recipe['source_adapter_digest'] and r['schema_fingerprint'] == recipe['schema_fingerprint'] for r in catalogue['recipes']):
                raise ContractError('ambiguous_candidate_approval')
            catalogue = {**catalogue, 'recipes': [*catalogue['recipes'], recipe]}
            pending.remove((key, value))
    return validate(catalogue, 'Catalogue')
