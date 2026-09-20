"""Strict Stage C budget envelopes, separate from the accepted B registry."""

from __future__ import annotations

from typing import Any

from ._c_validators import VALIDATORS
from .contracts import ContractError, canonical_bytes


def validate_c(value: Any, kind: str) -> Any:
    """Validate one exact C budget envelope and return the original value."""
    canonical_bytes(value)
    validator = VALIDATORS.get(kind)
    if validator is None:
        raise ContractError("unknown_kind", f"unknown C envelope kind: {kind}")
    validator(value)
    return value
