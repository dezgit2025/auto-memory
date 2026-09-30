"""Strict JSON envelopes and canonical hashing for the Codex fixer."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ._contract_schema import MAX_INT, VALIDATORS as _BASE_VALIDATORS
from ._controller_config import controller_config

VALIDATORS = {**_BASE_VALIDATORS, "ControllerConfig": controller_config}

MAX_DECODED_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 16


class ContractError(ValueError):
    """A stable contract refusal with a machine-readable code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _reject_float(_value: str) -> None:
    raise ContractError("invalid_json", "floating-point values are not allowed")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate_key", f"duplicate object key: {key}")
        result[key] = value
    return result


def _json_shape(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ContractError("invalid_contract", "JSON nesting exceeds 16 levels")
    if value is None or type(value) is bool or isinstance(value, str):
        return
    if type(value) is int:
        if not 0 <= value <= MAX_INT:
            raise ContractError("invalid_contract", "integer is outside the allowed range")
        return
    if isinstance(value, list):
        for item in value:
            _json_shape(item, depth + 1)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ContractError("invalid_contract", "object keys must be strings")
        for item in value.values():
            _json_shape(item, depth + 1)
        return
    raise ContractError("invalid_contract", "value is not permitted in JSON envelopes")


def canonical_bytes(value: Any) -> bytes:
    """Return compact sorted UTF-8 JSON without Unicode normalization."""
    _json_shape(value)
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise ContractError("invalid_contract", "value is not canonical JSON") from exc
    if len(encoded) > MAX_DECODED_BYTES:
        raise ContractError("too_large", "JSON envelope exceeds 2 MiB")
    return encoded


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate(value: Any, kind: str) -> Any:
    """Validate an exact v1 envelope and return the original object."""
    _json_shape(value)
    if len(canonical_bytes(value)) > MAX_DECODED_BYTES:
        raise ContractError("too_large")
    validator = VALIDATORS.get(kind)
    if validator is None:
        raise ContractError("unknown_kind", f"unknown envelope kind: {kind}")
    validator(value)
    if kind == "SchemaSnapshot":
        semantic = {
            "storage_family": value["storage_family"],
            "state": value["state"],
            "history": value["history"],
        }
        if value["schema_fingerprint"] != digest(semantic):
            raise ContractError("digest_mismatch", "schema fingerprint does not match")
    elif kind == "Observation":
        validate(value["snapshot"], "SchemaSnapshot")
        semantic = {
            "schema_fingerprint": value["snapshot"]["schema_fingerprint"],
            "adapter": value["adapter"],
            "catalogue_digest": value["catalogue_digest"],
            "policy_digest": value["policy_digest"],
        }
        if value["input_fingerprint"] != digest(semantic):
            raise ContractError("digest_mismatch", "input fingerprint does not match")
    return value


def parse(text: str, kind: str) -> Any:
    if not isinstance(text, str):
        raise ContractError("invalid_json", "JSON input must be text")
    try:
        encoded_size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ContractError("invalid_json", "JSON input is not valid Unicode") from exc
    if encoded_size > MAX_DECODED_BYTES:
        raise ContractError("too_large", "JSON envelope exceeds 2 MiB")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_int=int,
            parse_constant=_reject_float,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError) as exc:
        raise ContractError("invalid_json", "invalid JSON") from exc
    return validate(value, kind)
