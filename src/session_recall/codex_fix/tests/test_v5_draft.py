"""Transport-only null hashes never survive into a trusted Candidate."""
from copy import deepcopy
import hashlib
import json

import pytest

from session_recall.codex_fix._candidate_contracts import CANDIDATE_DRAFT_SCHEMA, parse_draft
from session_recall.codex_fix.contracts import ContractError, digest
from .test_v5_runner import candidate, candidate_input


def test_transport_schema_declares_explicit_type_for_constant_version():
    assert CANDIDATE_DRAFT_SCHEMA['properties']['format_version'] == {'type': 'integer', 'const': 1}


def test_null_hash_is_computed_for_novel_code_and_fully_hashed_candidate_identity():
    request = candidate_input()
    draft = candidate(request)
    draft['files'][0].update(content='a = "new arbitrary code"\n', sha256=None)
    result = parse_draft(json.dumps(draft), request)
    expected = deepcopy(draft)
    expected['files'][0]['sha256'] = 'sha256:' + hashlib.sha256(draft['files'][0]['content'].encode()).hexdigest()
    assert result == expected
    assert digest(result) == digest(expected)
    assert digest(result) != digest(draft)


@pytest.mark.parametrize('mutation', ['wrong_hash', 'duplicate', 'forbidden', 'input', 'base', 'extra', 'oversize'])
def test_null_hash_does_not_relax_any_candidate_authority(mutation):
    request = candidate_input()
    draft = candidate(request)
    draft['files'][0]['sha256'] = None
    if mutation == 'wrong_hash':
        draft['files'][0]['sha256'] = 'sha256:' + '0' * 64
    elif mutation == 'duplicate':
        draft['files'].append(deepcopy(draft['files'][0]))
    elif mutation == 'forbidden':
        draft['files'][0]['path'] = 'session_recall/codex_fix/approval.py'
    elif mutation == 'input':
        draft['input_digest'] = 'sha256:' + '0' * 64
    elif mutation == 'base':
        draft['base_artifact_digest'] = 'sha256:' + '0' * 64
    elif mutation == 'extra':
        draft['approved'] = True
    else:
        draft['files'][0]['content'] = 'x' * (256 * 1024 + 1)
    with pytest.raises(ContractError):
        parse_draft(json.dumps(draft), request)
