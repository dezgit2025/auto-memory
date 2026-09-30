"""Fixed adapter checks executed outside the candidate's filesystem authority."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any

from . import checks
from ._check_runtime import isolated_checks
from ._store_preconditions import CHECK_IDS
from .contracts import ContractError, digest
from .sandbox import Sandbox


def candidate_context(context: Any, request: dict, snapshot: dict, artifact_digest: str) -> Any:
    recipe = {
        'recipe_id': 'candidate-trial', 'source_adapter_digest': request['base_artifact_digest'],
        'schema_fingerprint': snapshot['schema_fingerprint'],
        'target_artifact_digest': artifact_digest, 'check_ids': list(CHECK_IDS),
    }
    catalogue = {**context.catalogue, 'recipes': [*context.catalogue['recipes'], recipe]}
    return replace(context, catalogue=catalogue, catalogue_digest=digest(catalogue))


def run_checks(artifact: Path, context: Any, *, sandbox: Any = None) -> list[str]:
    backend = Sandbox() if sandbox is None else sandbox
    with tempfile.TemporaryDirectory(prefix='codex-candidate-probe-') as folder:
        probe = backend.probe(Path(folder).resolve())
        if probe.returncode != 0:
            raise ContractError('sandbox_unavailable')
    with isolated_checks(backend):
        for name in CHECK_IDS:
            if checks.registry()[name](artifact, context) is not True:
                raise ContractError('candidate_check_failed', name)
    return [*CHECK_IDS, 'sandbox_denials_v1']


def guarded_registry(catalogue: dict) -> Any:
    targets = {r['target_artifact_digest'] for r in catalogue['recipes'] if r['recipe_id'].startswith('candidate-')}
    if not targets:
        return checks.registry()

    def wrap(callback):
        def guarded(artifact, context):
            from .artifacts import _artifact_bytes
            from hashlib import sha256
            if 'sha256:' + sha256(_artifact_bytes(artifact)).hexdigest() not in targets:
                return callback(artifact, context)
            with isolated_checks(Sandbox()):
                return callback(artifact, context)
        return guarded
    return MappingProxyType({name: wrap(callback) for name, callback in checks.registry().items()})
