"""Compiled trust anchor for the bundled, local-only repair catalogue."""

from __future__ import annotations

import hashlib
import importlib.resources
from typing import Any

from .contracts import ContractError, canonical_bytes, parse


TRUSTED_CATALOGUE_SHA256 = (
    "4e48e3a6c4216299fe5a28f61c41f0979348263a4de6930d3f404103d507e2cc"
)
MAX_CATALOGUE_BYTES = 2 * 1024 * 1024


def _catalogue_resource() -> Any:
    """Return only the package-owned catalogue resource (test seam is private)."""
    return (
        importlib.resources.files("session_recall.codex_fix")
        .joinpath("data")
        .joinpath("catalogue-v1.json")
    )


def load_catalogue() -> dict[str, Any]:
    """Load and authenticate the one bundled catalogue against compiled trust."""
    try:
        raw = _catalogue_resource().read_bytes()
    except OSError as exc:
        raise ContractError("catalogue_untrusted", "bundled catalogue unavailable") from exc
    if len(raw) > MAX_CATALOGUE_BYTES:
        raise ContractError("catalogue_untrusted", "bundled catalogue is too large")
    try:
        value = parse(raw.decode("utf-8"), "Catalogue")
    except (UnicodeDecodeError, ContractError) as exc:
        raise ContractError("catalogue_untrusted", "bundled catalogue is invalid") from exc
    actual = hashlib.sha256(canonical_bytes(value)).hexdigest()
    if actual != TRUSTED_CATALOGUE_SHA256:
        raise ContractError("catalogue_untrusted", "bundled catalogue digest mismatch")
    return value
