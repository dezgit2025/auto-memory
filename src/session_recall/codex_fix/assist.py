"""Foreground, budgeted candidate generation, review and explicit activation."""
from __future__ import annotations

from dataclasses import replace
import difflib
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

from . import approval, artifacts, candidate, codex_runner, engine, store
from ._assist_budget import reserve, settle
from ._candidate_store import write_once
from ._store_io import activation_lock, atomic_json, directory, protect_root, selection
from .candidate_checks import candidate_context, guarded_registry, run_checks
from .contracts import ContractError, digest, validate
from .policy import model_policy
from .sandbox import Sandbox


def _root(context):
    root = context.managed_root
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    protect_root(root)
    return root


def _cache(root: Path, data: bytes) -> tuple[str, Path]:
    artifact_digest = 'sha256:' + hashlib.sha256(data).hexdigest()
    folder = directory(root, f'artifacts/sha256/{artifact_digest[7:]}')
    target = folder / 'adapter.pyz'
    if target.exists() or target.is_symlink():
        artifacts.manifest(target, artifact_digest)
        return artifact_digest, target
    fd, raw = tempfile.mkstemp(prefix='.adapter-', dir=folder)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(raw, target)
        except FileExistsError:
            artifacts.manifest(target, artifact_digest)
        from ._store_io import fsync_directory
        fsync_directory(folder)
    finally:
        Path(raw).unlink()
    return artifact_digest, target


def _diff(request, output):
    sources = {s['path']: s['content'] for s in request['source_files']}
    return ''.join(''.join(difflib.unified_diff(
        sources.get(s['path'], '').splitlines(keepends=True), s['content'].splitlines(keepends=True),
        fromfile='a/' + s['path'], tofile='b/' + s['path'],
    )) for s in output['files'])


def assist(context: Any, *, generate_fn=codex_runner.generate, sandbox=None) -> dict[str, Any]:
    observation = engine.observe(context.recapture(), context)
    observed = replace(context, current_observation=observation)
    classification = engine.classify(observation, observed)
    if classification['status'] != 'assistance_eligible':
        return {'status': classification['status'], 'classification': classification}
    root = _root(context)
    backend = Sandbox() if sandbox is None else sandbox
    with tempfile.TemporaryDirectory(prefix='codex-assist-preflight-') as folder:
        if backend.probe(Path(folder).resolve()).returncode != 0:
            return {'status': 'sandbox_unavailable'}
    request = candidate.prepare(observed, model_policy())
    budget, reservation, needed = reserve(root, request)
    if needed is not None:
        return needed
    write_once(root, f'incidents/{request["incident_id"]}/input.json', request)
    try:
        generated = generate_fn(request, model_policy())
    except Exception:
        # Charge the reservation estimate even when a transport unexpectedly fails.
        settle(budget, reservation, {'status': 'process_failed', 'evidence': None})
        raise
    settle(budget, reservation, generated)
    evidence = generated.get('evidence') or {}
    write_once(root, f'incidents/{request["incident_id"]}/{reservation["reservation_id"]}.json', {
        'status': generated['status'], 'evidence': evidence,
        'reservation_digest': digest(reservation),
    })
    if generated['status'] != 'completed':
        return {'status': generated['status'], 'incident_id': request['incident_id']}
    output = generated['candidate']
    snapshot = observation['snapshot']
    base = artifacts.resolve(request['base_artifact_digest'], observed)
    data = candidate.build_bytes(request, output, snapshot, base)
    artifact_digest, path = _cache(root, data)
    trial = candidate_context(observed, request, snapshot, artifact_digest)
    executed = run_checks(path, trial, sandbox=backend)
    result = {
        'format_version': 1, 'candidate_digest': digest(output),
        'input_fingerprint': request['input_fingerprint'], 'policy_digest': request['policy_digest'],
        'acceptance_contract_digest': request['acceptance_contract_digest'],
        'check_ids': executed, 'verdict': 'pass', 'transport_evidence_digest': digest(evidence),
    }
    review = {'format_version': 1, 'request': request, 'candidate': output,
              'snapshot': snapshot, 'artifact_digest': artifact_digest, 'evidence': evidence, 'result': result}
    candidate_id = approval.save_review(root, review)
    response = {
        'status': 'action_needed', 'action': 'candidate_review', 'candidate_id': candidate_id,
        'review': result, 'diff': _diff(request, output),
        'artifact_digest': artifact_digest,
        'rollback': 'session-recall-codex-fix --root ROOT rollback --repair OPERATION_ID (returned by apply-candidate)',
        'prior_artifact_digest': request['base_artifact_digest'],
    }
    write_once(root, f'candidates/{candidate_id}/action-needed.json', response)
    return response


def effective_context(context):
    catalogue = approval.effective_catalogue(context.catalogue, context)
    updated = replace(context, catalogue=catalogue, catalogue_digest=digest(catalogue),
                      check_registry=guarded_registry(catalogue), current_observation=None)
    from .factory import _identity
    return replace(updated, adapter_identity=_identity(updated.paths['current_selection'], updated.managed_root, catalogue))


def apply_candidate(candidate_id: str, context: Any) -> dict[str, Any]:
    """An approved candidate uses the existing transactional recipe application."""
    review = approval.load_review(context.managed_root, candidate_id)
    # Reconstruct from compiled base every time, avoiding duplicate derived recipes.
    from .trust import load_catalogue
    base = replace(context, catalogue=load_catalogue(), catalogue_digest=digest(load_catalogue()), current_observation=None)
    current = effective_context(base)
    if not any(r['target_artifact_digest'] == review['artifact_digest'] for r in current.catalogue['recipes']):
        raise ContractError('candidate_not_approved')
    root = _root(current)
    with activation_lock(root) as acquired:
        if not acquired:
            raise ContractError('busy')
        prior = selection(current.paths['current_selection'])
        if prior is None:
            seed = current.catalogue['seed_artifact_digest']
            if current.adapter_identity['artifact_digest'] != seed:
                raise ContractError('source_identity_mismatch')
            folder = directory(root, 'selection')
            initial = validate({
                'format_version': 1, 'generation': 0, 'artifact_digest': seed,
                'source': 'bundled', 'recipe_id': 'bundled-seed',
                'activated_plan_digest': digest({'bundled_seed': seed}),
            }, 'Selection')
            atomic_json(folder / 'current.json', initial, 'Selection')
    observation = engine.observe(current.recapture(), current)
    current = replace(current, current_observation=observation)
    classification = engine.classify(observation, current)
    if classification['status'] == 'supported' and current.adapter_identity['artifact_digest'] == review['artifact_digest']:
        prior = selection(current.paths['current_selection'])
        saved = root / 'candidates' / candidate_id / 'plan.json'
        from ._candidate_store import read_record
        return store.apply(validate(read_record(saved), 'Plan'), current)
    repair_plan = engine.plan(classification, current)
    if repair_plan['target_artifact_digest'] != review['artifact_digest']:
        raise ContractError('candidate_plan_mismatch')
    write_once(root, f'candidates/{candidate_id}/plan.json', repair_plan)
    return store.apply(repair_plan, current)
