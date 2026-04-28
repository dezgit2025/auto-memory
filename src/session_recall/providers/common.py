"""Shared helpers for provider implementations."""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path


def utc_iso_from_ts(ts: float) -> str:
    """Convert POSIX timestamp to UTC ISO8601."""
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()


def is_within_days(iso_ts: str | None, days: int | None) -> bool:
    """Check if timestamp string falls inside the requested day window."""
    if days is None:
        return True
    if not iso_ts:
        return False
    try:
        parsed = _dt.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    cutoff = _dt.datetime.now(tz=_dt.timezone.utc) - _dt.timedelta(days=days)
    return parsed >= cutoff


def short_id(sid: str) -> str:
    """Consistent short id representation."""
    return sid[:8]


_MAX_LINE_CHARS = 1_000_000   # 1 MB per line — skip anything larger
_MAX_PARSE_LINES = 5_000      # cap total lines per file


def iter_jsonl_bounded(file_path: Path):
    """Yield parsed dicts from a JSONL file with bounded reads.

    Uses f.readline(max+1) to prevent allocating multi-GB lines.
    Skips oversize lines, malformed JSON, and deeply-nested payloads.
    """
    with file_path.open("r", encoding="utf-8", errors="replace") as f:
        for _ in range(_MAX_PARSE_LINES):
            raw = f.readline(_MAX_LINE_CHARS + 1)
            if not raw:
                return
            if len(raw) > _MAX_LINE_CHARS:
                # Oversize line — drain remainder and skip
                while raw and not raw.endswith("\n"):
                    raw = f.readline(_MAX_LINE_CHARS + 1)
                continue
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, RecursionError, TypeError):
                continue
