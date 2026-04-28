"""Resolve the effective --days default per provider type."""

from __future__ import annotations

from ..config import JSONL_DEFAULT_LOOKBACK_DAYS, SQLITE_DEFAULT_LOOKBACK_DAYS
from ..providers.base import StorageProvider


def resolve_days(user_days: int | None, provider: StorageProvider) -> int | None:
    """Return the effective lookback window for a provider.

    Explicit --days from the user always wins. Otherwise JSONL/file
    providers default to 5 days, SQLite keeps the 30-day default.
    """
    if user_days is not None:
        return user_days
    if provider.uses_jsonl_scan():
        return JSONL_DEFAULT_LOOKBACK_DAYS
    return SQLITE_DEFAULT_LOOKBACK_DAYS
