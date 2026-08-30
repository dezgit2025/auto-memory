"""Pure-SQL queries against the Codex state/history databases.

All values are bound parameters — never interpolated. Repository filtering
is NOT done in SQL: `repository` is derived per row (from git_origin_url /
cwd) by normalize, so callers filter by repo label in Python after
normalization. LIMIT is pushed down to SQL only when no repo filter is in
play; otherwise the caller applies the limit after filtering.
"""

import time

from .errors import CodexAmbiguousId, CodexNotFound, CodexUsageError

_DAY_MS = 86_400_000
MIN_ID_CHARS = 8  # UUIDv7 time-prefixes make shorter prefixes ambiguous

_RECENCY = "COALESCE(recency_at_ms, updated_at_ms, created_at_ms)"


def _thread_filters(include_archived: bool) -> tuple[list[str], list]:
    """WHERE fragments + params for the default exclusions.

    Single home for both rules (plan §16 Fix 4 / §19.3):
    - archived rows excluded unless ``include_archived``;
    - sub-agent threads ALWAYS excluded (agent_path set, or a JSON
      ``source`` carrying ``$.subagent`` — the guardian-trap shape).
    """
    clauses = [
        "(agent_path IS NULL OR agent_path = '')",
        "(source IS NULL OR NOT json_valid(source)"
        " OR json_extract(source, '$.subagent') IS NULL)",
    ]
    params: list = []
    if not include_archived:
        clauses.append("(archived IS NULL OR archived = 0)")
    return clauses, params


def select_threads_band(
    state_conn,
    *,
    newest_ms: int,
    oldest_ms: int,
    include_archived: bool = False,
    limit: int | None = None,
):
    """Top-level threads with recency in (oldest_ms, newest_ms], newest first.

    Band form exists so the §20 recency ladder can scan delta bands
    without re-reading earlier ones.
    """
    clauses, params = _thread_filters(include_archived)
    clauses.append(f"{_RECENCY} > ? AND {_RECENCY} <= ?")
    params.extend([oldest_ms, newest_ms])
    sql = (
        f"SELECT * FROM threads WHERE {' AND '.join(clauses)} "
        f"ORDER BY {_RECENCY} DESC"
    )
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return state_conn.execute(sql, params).fetchall()


def select_threads(
    state_conn,
    *,
    repo: str | None = None,
    limit: int,
    days: int,
    include_archived: bool = False,
    now_ms: int | None = None,
):
    """Threads within the lookback window, newest first.

    ``repo`` is accepted only to decide LIMIT pushdown: when a repo filter
    will be applied by the caller (in Python, after normalization), the
    limit must NOT be pushed into SQL or matching rows could be cut off.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    return select_threads_band(
        state_conn,
        newest_ms=now,
        oldest_ms=now - days * _DAY_MS,
        include_archived=include_archived,
        limit=limit if repo is None else None,
    )


def resolve_thread_id(state_conn, raw_sid: str) -> str:
    """Resolve a full id or unique >=8-char prefix to one full thread id.

    Never first-match-wins (plan §16 Fix 3): ambiguity raises with up to
    10 candidate (id, created_at_ms, summary) tuples for display.
    """
    sid = raw_sid.strip().lower()
    if len(sid.replace("-", "")) < MIN_ID_CHARS:
        raise CodexUsageError(
            f"session id must be at least {MIN_ID_CHARS} hex characters: "
            "Codex ids are time-ordered (UUIDv7), so short prefixes match "
            "many sessions instead of one"
        )
    rows = state_conn.execute(
        "SELECT id, created_at_ms, "
        "COALESCE(name, title, preview, first_user_message, '') "
        "FROM threads WHERE id = ? OR id LIKE ? LIMIT 11",
        (sid, sid + "%"),
    ).fetchall()
    if not rows:
        raise CodexNotFound(f"No session found matching '{sid}'")
    if len(rows) > 1:
        raise CodexAmbiguousId(sid, [tuple(r)[:3] for r in rows[:10]])
    return rows[0][0]


def count_turns(history_conn, thread_id: str) -> int:
    """Turn count for a PAGINATED thread. Legacy threads have no rows in
    thread_turns — callers must not call this for legacy (pass None and
    let normalize label it; the Phase 4 rollout reader supplies counts)."""
    row = history_conn.execute(
        "SELECT COUNT(*) FROM thread_turns WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    return row[0]


def count_files(history_conn, thread_id: str) -> int:
    """Distinct explicit fileChange paths for a PAGINATED thread (see
    count_turns for the legacy caveat)."""
    row = history_conn.execute(
        "SELECT COUNT(DISTINCT json_extract(je.value, '$.path')) "
        "FROM thread_items, json_each(thread_items.item_json, '$.changes') je "
        "WHERE thread_id = ? AND item_type = 'fileChange'",
        (thread_id,),
    ).fetchone()
    return row[0]
