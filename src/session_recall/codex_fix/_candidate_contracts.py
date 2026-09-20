"""Strict V5 candidate input and output contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

from .contracts import ContractError, canonical_bytes, digest


MAX_SOURCE_BYTES = 256 * 1024
MAX_TOTAL_SOURCE_BYTES = 1024 * 1024
MAX_FILES = 32
ALLOWED_PROVIDER_PATHS = frozenset(
    {
        "session_recall/providers/codex/schema.py",
        "session_recall/providers/codex/__init__.py",
        "session_recall/providers/codex/_schema_report.py",
        "session_recall/providers/codex/cli.py",
        "session_recall/providers/codex/connect.py",
        "session_recall/providers/codex/errors.py",
        "session_recall/providers/codex/provider.py",
        "session_recall/providers/codex/normalize.py",
        "session_recall/providers/codex/paths.py",
        "session_recall/providers/codex/state_queries.py",
        "session_recall/providers/codex/util_out.py",
        "session_recall/providers/codex/verifications/captured-profiles.json",
    }
)


def _fail(code: str) -> None:
    raise ContractError(code)


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(f"invalid_{label}")
    return value


def _string(value: Any, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        _fail(f"invalid_{label}")
    return value


def _digest(value: Any, label: str) -> str:
    value = _string(value, label, maximum=71)
    if (
        len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        _fail(f"invalid_{label}")
    return value


def _path(value: Any) -> str:
    value = _string(value, "path")
    parsed = PurePosixPath(value)
    if (
        value != parsed.as_posix()
        or parsed.is_absolute()
        or "." in parsed.parts
        or ".." in parsed.parts
        or value not in ALLOWED_PROVIDER_PATHS
    ):
        _fail("invalid_path")
    return value


def _source(value: Any) -> dict[str, Any]:
    source = _exact(value, {"path", "sha256", "content"}, "source")
    _path(source["path"])
    expected = _digest(source["sha256"], "source_digest")
    content = source['content']
    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_SOURCE_BYTES:
        _fail('invalid_source_content')
    actual = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    if actual != expected:
        _fail("source_digest_mismatch")
    return source


def _sources(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_FILES:
        _fail(f"invalid_{label}")
    paths: set[str] = set()
    total = 0
    for source in value:
        _source(source)
        if source["path"] in paths:
            _fail("duplicate_source_path")
        paths.add(source["path"])
        total += len(source["content"].encode("utf-8"))
    if total > MAX_TOTAL_SOURCE_BYTES:
        _fail("source_total_too_large")
    return value


def validate_input(value: Any) -> dict[str, Any]:
    fields = {
        "format_version", "incident_id", "input_fingerprint",
        "base_artifact_digest", "catalogue_digest", "policy_digest",
        "acceptance_contract_digest", "allowed_paths", "schema_diff",
        "source_files",
    }
    candidate_input = _exact(value, fields, "input")
    if type(candidate_input["format_version"]) is not int or candidate_input["format_version"] != 1:
        _fail("invalid_input")
    _string(candidate_input["incident_id"], "incident_id", maximum=128)
    for field in (
        "input_fingerprint", "base_artifact_digest", "catalogue_digest",
        "policy_digest", "acceptance_contract_digest",
    ):
        _digest(candidate_input[field], field)
    paths = candidate_input["allowed_paths"]
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FILES:
        _fail("invalid_allowed_paths")
    seen: set[str] = set()
    for path in paths:
        _path(path)
        if path in seen:
            _fail("duplicate_allowed_path")
        seen.add(path)
    schema_diff = _exact(candidate_input["schema_diff"], {"differences"}, "schema_diff")
    differences = schema_diff["differences"]
    if not isinstance(differences, list) or not 1 <= len(differences) <= 256:
        _fail("invalid_schema_diff")
    for difference in differences:
        _string(difference, "schema_difference", maximum=4096)
    sources = _sources(candidate_input["source_files"], "source_files")
    if any(source["path"] not in paths for source in sources):
        _fail("source_not_allowed")
    canonical_bytes(candidate_input)
    return candidate_input


def validate_candidate(value: Any, candidate_input: dict[str, Any]) -> dict[str, Any]:
    fields = {"format_version", "input_digest", "base_artifact_digest", "files"}
    candidate = _exact(value, fields, "candidate")
    if type(candidate["format_version"]) is not int or candidate["format_version"] != 1:
        _fail("invalid_candidate")
    _digest(candidate["input_digest"], "input_digest")
    _digest(candidate["base_artifact_digest"], "base_artifact_digest")
    if candidate["input_digest"] != digest(candidate_input):
        _fail("candidate_input_mismatch")
    if candidate["base_artifact_digest"] != candidate_input["base_artifact_digest"]:
        _fail("candidate_base_mismatch")
    files = _sources(candidate["files"], "candidate_files")
    if any(source["path"] not in candidate_input["allowed_paths"] for source in files):
        _fail("candidate_path_not_allowed")
    canonical_bytes(candidate)
    return candidate


def parse_candidate(text: str, candidate_input: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 2 * 1024 * 1024:
        _fail("invalid_candidate")
    try:
        def reject_duplicates(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    _fail("duplicate_candidate_key")
                value[key] = item
            return value

        value = json.loads(text, object_pairs_hook=reject_duplicates)
    except (json.JSONDecodeError, UnicodeError):
        _fail("malformed_candidate")
    return validate_candidate(value, candidate_input)


def candidate_output_schema() -> dict[str, Any]:
    digest_schema = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    source_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "sha256", "content"],
        "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 4096},
            "sha256": digest_schema,
            "content": {"type": "string", "maxLength": MAX_SOURCE_BYTES},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["format_version", "input_digest", "base_artifact_digest", "files"],
        "properties": {
            "format_version": {"type": "integer", "const": 1},
            "input_digest": digest_schema,
            "base_artifact_digest": digest_schema,
            "files": {"type": "array", "minItems": 1, "maxItems": MAX_FILES,
                      "items": source_schema},
        },
    }


CANDIDATE_SCHEMA = candidate_output_schema()


def parse_draft(text: str, candidate_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize transport null hashes; all stored candidates retain strict hashes."""
    from .contracts import _pairs, _reject_float
    if not isinstance(text, str) or len(text.encode('utf-8')) > 2 * 1024 * 1024:
        _fail('invalid_candidate')
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_float=_reject_float)
    except (json.JSONDecodeError, UnicodeError):
        _fail('malformed_candidate')
    canonical_bytes(value)
    validate_input(candidate_input)
    _exact(value, {'format_version', 'input_digest', 'base_artifact_digest', 'files'}, 'candidate')
    files = value['files']
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        _fail('invalid_candidate_files')
    total = 0
    paths = set()
    normalized = []
    for item in files:
        _exact(item, {'path', 'sha256', 'content'}, 'source')
        path = _path(item['path'])
        if path in paths or path not in candidate_input['allowed_paths']:
            _fail('invalid_candidate_path')
        paths.add(path)
        content = item['content']
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_SOURCE_BYTES:
            _fail('invalid_source_content')
        total += len(content.encode('utf-8'))
        if total > MAX_TOTAL_SOURCE_BYTES:
            _fail('source_total_too_large')
        source = dict(item)
        if source['sha256'] is None:
            source['sha256'] = 'sha256:' + hashlib.sha256(content.encode('utf-8')).hexdigest()
        _source(source)
        normalized.append(source)
    return validate_candidate({**value, 'files': normalized}, candidate_input)


def draft_output_schema() -> dict[str, Any]:
    schema = candidate_output_schema()
    schema['properties']['files']['items']['properties']['sha256'] = {
        'anyOf': [{'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}, {'type': 'null'}],
    }
    return schema


CANDIDATE_DRAFT_SCHEMA = draft_output_schema()
