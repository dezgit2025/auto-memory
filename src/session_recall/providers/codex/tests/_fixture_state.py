"""Synthetic `state_5.sqlite` thread rows for the small store fixture.

All timestamps derive from REF_NOW_MS (2026-08-23T12:00:00Z) — deterministic,
no wall-clock reads. Thread ids are UUIDv7-style: leading 48 bits encode the
creation timestamp, so short-prefix collision behavior matches real Codex.
"""

import sqlite3
from pathlib import Path

from ._fixture_schema import column_names

# 2026-08-23T12:00:00Z as epoch milliseconds (fixed reference "now").
REF_NOW_MS = 1787486400000
_DAY_MS = 86_400_000

REPO_URL = "https://github.com/acme/widget.git"
SEARCH_TOKEN = "XERXES_PLUM_7Q"  # lives only in the 15-30d band thread
OLDBAND_FILE = "src/widget/alpha.py"


def make_uuid7(ts_ms: int, seq: int) -> str:
    """Deterministic UUIDv7-style id whose first 12 hex chars are ts_ms."""
    h = f"{ts_ms & 0xFFFFFFFFFFFF:012x}"
    return f"{h[:8]}-{h[8:12]}-7{seq & 0xFFF:03x}-8000-{seq & 0xFFFFFFFFFFFF:012x}"


def _base_row(tid: str, ts_ms: int) -> dict:
    """A full 40-column threads row with realistic defaults."""
    return {
        "id": tid,
        "rollout_path": "",
        "created_at": ts_ms // 1000,
        "updated_at": ts_ms // 1000,
        "source": "cli",
        "model_provider": "openai",
        "cwd": "/Users/synthetic/projects/widget",
        "title": "",
        "sandbox_policy": "workspace-write",
        "approval_mode": "on-request",
        "tokens_used": 0,
        "has_user_event": 1,
        "archived": 0,
        "archived_at": None,
        "git_sha": None,
        "git_branch": "main",
        "git_origin_url": REPO_URL,
        "cli_version": "0.99.0",
        "first_user_message": "",
        "agent_nickname": None,
        "agent_role": None,
        "memory_mode": "enabled",
        "model": "synthetic-model",
        "reasoning_effort": None,
        "agent_path": None,
        "created_at_ms": ts_ms,
        "updated_at_ms": ts_ms,
        "thread_source": None,
        "preview": "",
        "recency_at": ts_ms // 1000,
        "recency_at_ms": ts_ms,
        "history_mode": "paginated",
        "name": None,
        "is_pinned": 0,
        "thread_section_id": None,
        "section_position": None,
        "section_entered_at_ms": None,
        "project_id": None,
        "originator": None,
        "daybreak_enabled": None,
    }


def small_store_threads(sessions_root: Path) -> list:
    """The designed inventory. Collision pair = recent-a / recent-b."""
    # Aligned base so recent-a and recent-b share the top 32 id bits
    # (same 65.536s window => identical first 8 hex chars).
    pair_base = (REF_NOW_MS - 2 * 3_600_000) & ~0xFFFF
    rows = []

    r = _base_row(make_uuid7(pair_base + 1_000, 1), pair_base + 1_000)
    r.update(title="recent-a widget refactor", preview="refactor the widget core")
    rows.append(r)

    r = _base_row(make_uuid7(pair_base + 31_000, 2), pair_base + 31_000)
    r.update(title="recent-b widget tests", preview="add widget tests")
    rows.append(r)

    r = _base_row(make_uuid7(REF_NOW_MS - 6 * _DAY_MS, 3), REF_NOW_MS - 6 * _DAY_MS)
    r.update(title="recent-c local scratch", git_origin_url=None, git_branch=None,
             cwd="/Users/synthetic/scratch")
    rows.append(r)

    old_ts = REF_NOW_MS - 20 * _DAY_MS
    r = _base_row(make_uuid7(old_ts, 4), old_ts)
    r.update(title="oldband alpha work",
             first_user_message=f"please fix {SEARCH_TOKEN} in alpha")
    rows.append(r)

    leg_ts = REF_NOW_MS - 3 * _DAY_MS
    r = _base_row(make_uuid7(leg_ts, 5), leg_ts)
    r.update(title="legacy-recent session", history_mode="legacy",
             rollout_path=str(sessions_root / "2026/08/27/rollout-legacy-recent.jsonl"))
    rows.append(r)

    arc_ts = REF_NOW_MS - 5 * _DAY_MS
    r = _base_row(make_uuid7(arc_ts, 6), arc_ts)
    r.update(title="archived experiment", archived=1, archived_at=arc_ts // 1000)
    rows.append(r)

    trap_ts = REF_NOW_MS - 1 * _DAY_MS
    r = _base_row(make_uuid7(trap_ts, 7), trap_ts)
    r.update(title="guardian trap", agent_path=None,
             source='{"subagent":{"other":"guardian"}}')
    rows.append(r)

    sub_ts = REF_NOW_MS - 1 * _DAY_MS + 60_000
    r = _base_row(make_uuid7(sub_ts, 8), sub_ts)
    r.update(title="explicit subagent", agent_path="/root/security_testing",
             source='{"subagent":{"thread_spawn":{"agent_path":"/root/security_testing"}}}')
    rows.append(r)

    return rows


def insert_threads(conn: sqlite3.Connection, rows: list) -> None:
    cols = column_names("state", "threads")
    placeholders = ", ".join("?" for _ in cols)
    sql = f'INSERT INTO threads ({", ".join(cols)}) VALUES ({placeholders})'
    for row in rows:
        conn.execute(sql, [row[c] for c in cols])
    conn.commit()
