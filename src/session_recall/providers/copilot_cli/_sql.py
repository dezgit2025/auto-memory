"""SQLite query helpers for Copilot CLI provider."""

from __future__ import annotations

import sqlite3

from ..common import short_id


def sql_list_sessions(
    conn: sqlite3.Connection,
    provider_id: str,
    repo: str | None,
    limit: int,
    days: int | None,
) -> list[dict]:
    days_arg = f"-{days or 30} days"
    if repo and repo != "all":
        rows = conn.execute(
            """
            SELECT s.id, s.repository, s.branch, s.summary, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) as turns_count,
                   (SELECT COUNT(*) FROM session_files f WHERE f.session_id = s.id) as files_count
            FROM sessions s WHERE s.repository = ? AND s.created_at >= datetime('now', ?)
            ORDER BY s.created_at DESC LIMIT ?
            """,
            (repo, days_arg, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT s.id, s.repository, s.branch, s.summary, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) as turns_count,
                   (SELECT COUNT(*) FROM session_files f WHERE f.session_id = s.id) as files_count
            FROM sessions s WHERE s.created_at >= datetime('now', ?)
            ORDER BY s.created_at DESC LIMIT ?
            """,
            (days_arg, limit),
        ).fetchall()
    return [
        {
            "provider": provider_id,
            "id_short": short_id(r["id"]),
            "id_full": r["id"],
            "repository": r["repository"],
            "branch": r["branch"],
            "summary": r["summary"],
            "date": r["created_at"][:10] if r["created_at"] else None,
            "created_at": r["created_at"],
            "turns_count": r["turns_count"],
            "files_count": r["files_count"],
            "_trust_level": "trusted_first_party",
        }
        for r in rows
    ]


def sql_recent_files(
    conn: sqlite3.Connection,
    provider_id: str,
    repo: str | None,
    limit: int,
    days: int | None,
) -> list[dict]:
    date_filter = " AND sf.first_seen_at >= datetime('now', ?)" if days else ""
    date_param = (f"-{days} days",) if days else ()
    base = """
        SELECT sf.file_path, sf.tool_name, sf.first_seen_at,
               sf.session_id, s.summary
        FROM session_files sf
        JOIN sessions s ON s.id = sf.session_id
    """
    if repo and repo != "all":
        sql = (
            base
            + f" WHERE s.repository = ?{date_filter} ORDER BY sf.first_seen_at DESC LIMIT ?"
        )
        rows = conn.execute(sql, (repo, *date_param, limit)).fetchall()
    else:
        where = f" WHERE 1=1{date_filter}" if days else ""
        sql = base + where + " ORDER BY sf.first_seen_at DESC LIMIT ?"
        rows = conn.execute(sql, (*date_param, limit)).fetchall()
    return [
        {
            "provider": provider_id,
            "file_path": r["file_path"],
            "tool_name": r["tool_name"],
            "date": (r["first_seen_at"] or "")[:10],
            "session_id": short_id(r["session_id"]),
            "session_summary": r["summary"],
            "_trust_level": "trusted_first_party",
        }
        for r in rows
    ]


def sql_list_checkpoints(
    conn: sqlite3.Connection,
    provider_id: str,
    repo: str | None,
    limit: int,
    days: int | None,
) -> list[dict]:
    date_filter = " AND c.created_at >= datetime('now', ?)" if days else ""
    date_param = (f"-{days} days",) if days else ()
    base = """
        SELECT c.checkpoint_number, c.title, c.overview, c.created_at,
               c.session_id, s.summary as session_summary
        FROM checkpoints c
        JOIN sessions s ON s.id = c.session_id
    """
    if repo and repo != "all":
        sql = (
            base
            + f" WHERE s.repository = ?{date_filter} ORDER BY c.created_at DESC LIMIT ?"
        )
        rows = conn.execute(sql, (repo, *date_param, limit)).fetchall()
    else:
        where = f" WHERE 1=1{date_filter}" if days else ""
        sql = base + where + " ORDER BY c.created_at DESC LIMIT ?"
        rows = conn.execute(sql, (*date_param, limit)).fetchall()
    return [
        {
            "provider": provider_id,
            "checkpoint_number": r["checkpoint_number"],
            "title": r["title"],
            "overview": (r["overview"] or "")[:300],
            "date": (r["created_at"] or "")[:10],
            "session_id": short_id(r["session_id"]),
            "session_summary": r["session_summary"],
            "_trust_level": "trusted_first_party",
        }
        for r in rows
    ]


def sql_search(
    conn: sqlite3.Connection,
    provider_id: str,
    fts_query: str,
    repo: str | None,
    limit: int,
    days: int | None,
) -> list[dict]:
    date_clause = " AND s.created_at >= datetime('now', ?)" if days else ""
    date_param = (f"-{days} days",) if days else ()
    if repo and repo != "all":
        sql = (
            """
            SELECT si.content, si.session_id, si.source_type,
                   s.summary, s.created_at, s.repository
            FROM search_index si JOIN sessions s ON s.id = si.session_id
            WHERE search_index MATCH ? AND s.repository = ?
            """
            + date_clause
            + " ORDER BY rank LIMIT ?"
        )
        rows = conn.execute(
            sql, (fts_query, repo, *date_param, limit)
        ).fetchall()
    else:
        sql = (
            """
            SELECT si.content, si.session_id, si.source_type,
                   s.summary, s.created_at, s.repository
            FROM search_index si JOIN sessions s ON s.id = si.session_id
            WHERE search_index MATCH ?
            """
            + date_clause
            + " ORDER BY rank LIMIT ?"
        )
        rows = conn.execute(sql, (fts_query, *date_param, limit)).fetchall()
    return [
        {
            "provider": provider_id,
            "session_id": short_id(r["session_id"]),
            "session_id_full": r["session_id"],
            "source_type": r["source_type"],
            "summary": r["summary"],
            "repository": r["repository"],
            "date": (r["created_at"] or "")[:10],
            "excerpt": (r["content"] or "")[:250]
            + ("..." if len(r["content"] or "") > 250 else ""),
            "_trust_level": "trusted_first_party",
        }
        for r in rows
    ]


# sql_get_session is in _sql_session.py for file-size compliance
