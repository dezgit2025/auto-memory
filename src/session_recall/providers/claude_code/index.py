"""Build and query a SQLite FTS5 index over Claude Code session JSONL files."""
from __future__ import annotations

import os
import pathlib
import sqlite3
import sys
import time
from typing import Optional

from ...commands.search import sanitize_fts5_query
from ..file._path_safety import is_under_root

_TRUST_LEVEL = "claude_code_jsonl"

_DDL_TABLES = [
    """CREATE TABLE IF NOT EXISTS cc_sessions (
        id TEXT PRIMARY KEY, cwd TEXT, repository TEXT, branch TEXT,
        summary TEXT, first_seen TEXT, last_seen TEXT,
        turns_count INTEGER, files_count INTEGER, version TEXT)""",
    """CREATE TABLE IF NOT EXISTS cc_turns (
        session_id TEXT, turn_index INTEGER,
        user_msg TEXT, assistant_msg TEXT, timestamp TEXT,
        assistant_summary TEXT,
        PRIMARY KEY (session_id, turn_index))""",
    """CREATE TABLE IF NOT EXISTS cc_files (
        session_id TEXT, file_path TEXT, tool_name TEXT,
        PRIMARY KEY (session_id, file_path))""",
    "CREATE TABLE IF NOT EXISTS cc_meta (key TEXT PRIMARY KEY, value TEXT)",
]

_FTS5_BASE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS cc_search USING fts5("
    "session_id UNINDEXED, user_msg, assistant_msg, summary,"
    " assistant_summary,"
    ' tokenize="porter unicode61 remove_diacritics 2",'
    " prefix='2 3 4'{extra})"
)


def _index_path() -> pathlib.Path:
    custom = os.environ.get("SESSION_RECALL_CC_INDEX_PATH")
    return pathlib.Path(custom) if custom else pathlib.Path.home() / ".claude" / ".sr-index.db"


def _jsonl_days() -> int:
    return int(os.environ.get("SESSION_RECALL_JSONL_DAYS", "5"))


def _prune_days() -> int:
    return int(os.environ.get("SESSION_RECALL_CC_PRUNE_DAYS", "90"))


def _open(path: pathlib.Path | None = None) -> sqlite3.Connection:
    if path is None:
        path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    for stmt in _DDL_TABLES:
        conn.execute(stmt)
    try:
        conn.execute(_FTS5_BASE.format(extra=", contentless_delete=1"))
    except sqlite3.OperationalError:
        conn.execute(_FTS5_BASE.format(extra=""))
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cc_turns)").fetchall()}
    if "assistant_summary" not in cols:
        conn.close()
        raise RuntimeError(
            "Index schema is out of date — run: session-recall cc-index --rebuild"
        )
    return conn


def _get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM cc_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO cc_meta(key,value) VALUES(?,?)", (key, value))


def _repo_filter(repo: Optional[str]) -> Optional[str]:
    return repo if (repo and repo != "all") else None


def build_index(*, rebuild: bool = False, verbose: bool = False) -> dict:
    """Incrementally (or fully) index all Claude Code sessions."""
    from .detect import CC_PROJECTS_DIR, list_session_files
    from .reader import parse_session

    conn = _open()
    indexed = skipped = errors = 0
    jsonl_cutoff = time.time() - _jsonl_days() * 86400
    try:
        conn.execute("BEGIN")
        if rebuild:
            conn.execute("DELETE FROM cc_sessions")
            conn.execute("DELETE FROM cc_turns")
            conn.execute("DELETE FROM cc_files")
            conn.execute("DELETE FROM cc_search")
        last_run = _get_meta(conn, "last_run_epoch")
        cutoff = float(last_run) if (last_run and not rebuild) else 0.0

        for jf in list_session_files():
            if jf.is_symlink():
                continue
            if not is_under_root(jf, CC_PROJECTS_DIR):
                continue
            try:
                mtime = jf.stat().st_mtime
            except OSError:
                continue
            if mtime < jsonl_cutoff:
                skipped += 1
                continue
            if mtime <= cutoff:
                skipped += 1
                continue
            try:
                session = parse_session(jf)
            except OSError as e:
                print(f"warning: cannot read {jf}: {e}", file=sys.stderr)
                errors += 1
                continue
            if not session:
                continue
            _upsert_session(conn, session)
            indexed += 1

        _set_meta(conn, "last_run_epoch", str(time.time()))
        _prune_old_sessions(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "indexed": indexed, "skipped": skipped,
        "errors": errors, "total": indexed + skipped + errors,
    }


def _upsert_session(conn: sqlite3.Connection, session: dict) -> None:
    sid = session["id"]
    conn.execute(
        "INSERT OR REPLACE INTO cc_sessions VALUES(?,?,?,?,?,?,?,?,?,?)",
        (sid, session["cwd"], session["repository"], session["branch"],
         session["summary"], session["first_seen"], session["last_seen"],
         session["turns_count"], session["files_count"], session["version"]))
    conn.execute("DELETE FROM cc_turns WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM cc_files WHERE session_id=?", (sid,))
    conn.execute("DELETE FROM cc_search WHERE session_id=?", (sid,))
    for i, turn in enumerate(session.get("turns", [])):
        conn.execute(
            "INSERT OR REPLACE INTO cc_turns VALUES(?,?,?,?,?,?)",
            (sid, i, turn["user"], turn["assistant"], turn["timestamp"],
             turn["assistant_summary"]),
        )
        conn.execute(
            "INSERT INTO cc_search(session_id, user_msg, assistant_msg,"
            " summary, assistant_summary) VALUES(?,?,?,?,?)",
            (sid, turn["user"], turn["assistant"], session["summary"],
             turn["assistant_summary"]),
        )
    for f in session.get("files", []):
        conn.execute("INSERT OR IGNORE INTO cc_files VALUES(?,?,?)",
                     (sid, f["file_path"], f["tool_name"]))


def _prune_old_sessions(conn: sqlite3.Connection) -> None:
    cutoff = f"-{_prune_days()} days"
    old = conn.execute(
        "SELECT id FROM cc_sessions WHERE last_seen < datetime('now', ?)", (cutoff,),
    ).fetchall()
    for row in old:
        sid = row[0]
        conn.execute("DELETE FROM cc_sessions WHERE id=?", (sid,))
        conn.execute("DELETE FROM cc_turns WHERE session_id=?", (sid,))
        conn.execute("DELETE FROM cc_files WHERE session_id=?", (sid,))
        conn.execute("DELETE FROM cc_search WHERE session_id=?", (sid,))


def query_sessions(
    *, repo: Optional[str] = None, limit: int = 10, days: int = 30,
) -> list[dict]:
    path = _index_path()
    if not path.exists():
        return []
    df, repo_f, conn = f"-{days} days", _repo_filter(repo), _open(path)
    try:
        if repo_f:
            sql = ("SELECT * FROM cc_sessions WHERE repository=?"
                   " AND last_seen >= datetime('now',?) ORDER BY last_seen DESC LIMIT ?")
            params: tuple = (repo_f, df, limit)
        else:
            sql = ("SELECT * FROM cc_sessions WHERE last_seen >= datetime('now',?)"
                   " ORDER BY last_seen DESC LIMIT ?")
            params = (df, limit)
        return [{**dict(r), "_trust_level": _TRUST_LEVEL}
                for r in conn.execute(sql, params)]
    finally:
        conn.close()


def query_files(
    *, repo: Optional[str] = None, limit: int = 20, days: int = 30,
) -> list[dict]:
    path = _index_path()
    if not path.exists():
        return []
    df, repo_f = f"-{days} days", _repo_filter(repo)
    base = ("SELECT f.file_path, f.tool_name, s.last_seen, s.id AS session_id,"
            " s.repository FROM cc_files f JOIN cc_sessions s ON s.id=f.session_id")
    conn = _open(path)
    try:
        if repo_f:
            sql = (f"{base} WHERE s.repository=? AND s.last_seen >= datetime('now',?)"
                   " ORDER BY s.last_seen DESC LIMIT ?")
            params: tuple = (repo_f, df, limit)
        else:
            sql = (f"{base} WHERE s.last_seen >= datetime('now',?)"
                   " ORDER BY s.last_seen DESC LIMIT ?")
            params = (df, limit)
        return [{**dict(r), "_trust_level": _TRUST_LEVEL}
                for r in conn.execute(sql, params)]
    finally:
        conn.close()


def query_search(
    query: str, *, repo: Optional[str] = None, limit: int = 10, days: int = 30,
) -> list[dict]:
    path = _index_path()
    if not path.exists():
        return []
    safe_q = sanitize_fts5_query(query)
    if safe_q is None:
        return []
    df, repo_f = f"-{days} days", _repo_filter(repo)
    base = ("SELECT cs.session_id, cs.user_msg, cs.summary, s.repository, s.branch,"
            " s.last_seen, snippet(cc_search, 1, '⟦', '⟧', '…', 24) AS snippet"
            " FROM cc_search cs JOIN cc_sessions s ON s.id=cs.session_id")
    bm25 = "bm25(cc_search, 0.0, 5.0, 1.0, 1.0, 1.0)"
    conn = _open(path)
    try:
        if repo_f:
            sql = (f"{base} WHERE cc_search MATCH ? AND s.repository=?"
                   f" AND s.last_seen >= datetime('now',?) ORDER BY {bm25} LIMIT ?")
            params: tuple = (safe_q, repo_f, df, limit)
        else:
            sql = (f"{base} WHERE cc_search MATCH ?"
                   f" AND s.last_seen >= datetime('now',?) ORDER BY {bm25} LIMIT ?")
            params = (safe_q, df, limit)
        return [{**dict(r), "_trust_level": _TRUST_LEVEL}
                for r in conn.execute(sql, params)]
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if "fts5" in msg or "syntax" in msg or "no such table" in msg:
            print(f"warning: search error: {e}", file=sys.stderr)
            return []
        raise
    finally:
        conn.close()


def query_show(
    session_id: str, *, turns: Optional[int] = None,
) -> Optional[dict]:
    path = _index_path()
    if not path.exists():
        return None
    conn = _open(path)
    try:
        row = conn.execute(
            "SELECT * FROM cc_sessions WHERE id LIKE ? LIMIT 1",
            (session_id + "%",),
        ).fetchone()
        if not row:
            return None
        sid = row["id"]
        turn_sql = ("SELECT * FROM cc_turns WHERE session_id=? ORDER BY turn_index"
                    + (" LIMIT ?" if turns is not None else ""))
        turn_params = (sid, turns) if turns is not None else (sid,)
        turn_rows = conn.execute(turn_sql, turn_params).fetchall()
        file_rows = conn.execute(
            "SELECT file_path, tool_name FROM cc_files WHERE session_id=?", (sid,),
        ).fetchall()
        return {
            **dict(row), "_trust_level": _TRUST_LEVEL,
            "turns": [dict(t) for t in turn_rows],
            "files": [dict(f) for f in file_rows],
        }
    finally:
        conn.close()
