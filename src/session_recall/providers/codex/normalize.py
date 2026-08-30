"""Normalization: Codex thread rows -> Auto Memory session dicts (plan §6.1/§6.5)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from ...util.detect_repo import parse_repo_url
from ...util.format_output import sanitize_for_terminal
from ..common import short_id, utc_iso_from_ts

TRUST_LEVEL = "codex_local_first_party"
NO_SUMMARY = "(no summary)"
_SUMMARY_FIELDS = ("name", "title", "preview", "first_user_message")


def _get(row, key):
    """Mapping-style access that works for dicts and sqlite3.Row alike."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def ts_ms_to_iso(ms: float) -> str:
    """Epoch milliseconds -> UTC ISO8601 (reuses shared utc_iso_from_ts)."""
    return utc_iso_from_ts(ms / 1000.0)


def thread_timestamp(row) -> str:
    """ISO timestamp for a thread: created_at_ms, else created_at seconds."""
    ms = _get(row, "created_at_ms")
    if ms is not None:
        return ts_ms_to_iso(float(ms))
    secs = _get(row, "created_at")
    if secs is not None:
        return utc_iso_from_ts(float(secs))
    return ""


def date10(iso: str) -> str:
    """First 10 chars of an ISO timestamp (YYYY-MM-DD)."""
    return iso[:10]


def thread_summary(row) -> str:
    """First non-empty of name/title/preview/first_user_message, sanitized.

    Sanitization happens before the emptiness check so an all-control-chars
    value falls through to the next field instead of yielding "".
    """
    for field in _SUMMARY_FIELDS:
        val = _get(row, field)
        if val is None:
            continue
        clean = sanitize_for_terminal(str(val)).strip()
        if clean:
            return clean
    return NO_SUMMARY


def repo_label(git_origin_url: str | None, cwd: str | None) -> str:
    """Repository label: parsed origin slug, else deterministic local:<cwd>.

    The local: form is copied/adapted from copilot_cli/_labels.py
    (_local_workspace_label is private; plan §2 forbids cross-provider import).
    """
    parsed = parse_repo_url(git_origin_url) if git_origin_url else None
    if parsed:
        return parsed
    if not cwd:
        return "local:unknown"
    return f"local:{Path(cwd).expanduser()}"


def repo_matches(row_label: str, repo_filter: str | None) -> bool:
    """Exact-match repo filter; None or "all" disables (§16 Fix 5, no substrings)."""
    if not repo_filter or repo_filter == "all":
        return True
    return row_label == repo_filter


def normalize_change_path(path_str: str, thread_cwd: str | None) -> str:
    """Absolute, cwd-joined, case-preserved path for files dedup (§16 Fix 5).

    Deliberately does NOT call resolve()/realpath(): the file may no longer
    exist, and resolving symlinks would make dedup depend on today's
    filesystem state. A relative path with no cwd stays relative.
    """
    p = PurePosixPath(path_str)
    if not p.is_absolute() and thread_cwd:
        p = PurePosixPath(thread_cwd) / p
    return str(p)


def normalize_thread_row(row, turns_count=None, files_count=None) -> dict:
    """Assemble the spec-pinned output row for one thread.

    turns_count/files_count of None mean "not computed" (legacy threads get
    real counts from the Phase 4 rollout reader).
    """
    iso = thread_timestamp(row)
    tid = str(_get(row, "id") or "")
    return {
        "id_full": tid,
        "id_short": short_id(tid),
        "summary": thread_summary(row),
        "created_at": iso,
        "date": date10(iso),
        "branch": _get(row, "git_branch") or "unknown",
        "repository": repo_label(_get(row, "git_origin_url"), _get(row, "cwd")),
        "turns_count": turns_count,
        "files_count": files_count,
        "_trust_level": TRUST_LEVEL,
    }
