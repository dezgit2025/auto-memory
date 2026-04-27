"""Copilot CLI backend — delegates to existing SQLite command modules."""
from __future__ import annotations
import pathlib
import sys
from typing import Optional

from .base import SessionBackend
from ..config import DB_PATH
from ..db.connect import connect_ro
from ..db.schema_check import schema_check


class CopilotBackend(SessionBackend):
    @property
    def name(self) -> str:
        return "copilot"

    def is_available(self) -> bool:
        return pathlib.Path(DB_PATH).exists()

    def _check_schema(self, conn) -> bool:
        """Return True if schema is broken (log problems). False means OK to proceed."""
        problems = schema_check(conn)
        if problems:
            print("schema drift detected:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return True
        return False

    def list_sessions(self, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        from ..commands.list_sessions import _QUERY_REPO, _QUERY_ALL
        conn = connect_ro(DB_PATH)
        try:
            if self._check_schema(conn):
                return []
            days_arg = f"-{days} days"
            if repo and repo != "all":
                rows = conn.execute(_QUERY_REPO, (repo, days_arg, limit)).fetchall()
            else:
                rows = conn.execute(_QUERY_ALL, (days_arg, limit)).fetchall()
            return [
                {
                    "id": r["id"],
                    "id_short": r["id"][:8],
                    "repository": r["repository"],
                    "branch": r["branch"],
                    "summary": r["summary"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "turns_count": r["turns_count"],
                    "files_count": r["files_count"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def list_files(self, *, repo: Optional[str] = None, limit: int = 20, days: int = 30) -> list[dict]:
        from ..commands.files import _BASE
        conn = connect_ro(DB_PATH)
        try:
            if self._check_schema(conn):
                return []
            date_filter = " AND sf.first_seen_at >= datetime('now', ?)"
            date_param = (f"-{days} days",)
            if repo and repo != "all":
                sql = _BASE + f" WHERE s.repository = ?{date_filter} ORDER BY sf.first_seen_at DESC LIMIT ?"
                rows = conn.execute(sql, (repo, *date_param, limit)).fetchall()
            else:
                sql = _BASE + f" WHERE 1=1{date_filter} ORDER BY sf.first_seen_at DESC LIMIT ?"
                rows = conn.execute(sql, (*date_param, limit)).fetchall()
            return [
                {
                    "file_path": r["file_path"],
                    "tool_name": r["tool_name"],
                    "date": (r["first_seen_at"] or "")[:10],
                    "session_id": r["session_id"][:8],
                    "session_summary": r["summary"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def search(self, query: str, *, repo: Optional[str] = None, limit: int = 10, days: int = 30) -> list[dict]:
        from ..commands.search import sanitize_fts5_query, _SQL, _FILE_SQL
        conn = connect_ro(DB_PATH)
        try:
            if schema_check(conn):
                return []
            fts_query = sanitize_fts5_query(query)
            if fts_query is None:
                return []
            has_repo = repo and repo != "all"
            date_clause = " AND s.created_at >= datetime('now', ?)"
            date_param = (f"-{days} days",)

            if has_repo:
                sql = _SQL.format(repo_filter=" AND s.repository = ?" + date_clause)
                rows = conn.execute(sql, (fts_query, repo, *date_param, limit)).fetchall()
            else:
                sql = _SQL.format(repo_filter=date_clause)
                rows = conn.execute(sql, (fts_query, *date_param, limit)).fetchall()

            results = [
                {
                    "session_id": r["session_id"][:8],
                    "session_id_full": r["session_id"],
                    "source_type": r["source_type"],
                    "summary": r["summary"],
                    "date": (r["created_at"] or "")[:10],
                    "excerpt": (r["content"] or "")[:200],
                }
                for r in rows
            ]
            seen = {(r["session_id_full"], r["source_type"]) for r in results}
            like_pat = f"%{query}%"
            if has_repo:
                fsql = _FILE_SQL.format(repo_filter=" AND s.repository = ?" + date_clause)
                frows = conn.execute(fsql, (like_pat, repo, *date_param, limit)).fetchall()
            else:
                fsql = _FILE_SQL.format(repo_filter=date_clause)
                frows = conn.execute(fsql, (like_pat, *date_param, limit)).fetchall()
            for r in frows:
                if (r["session_id"], "file") in seen:
                    continue
                seen.add((r["session_id"], "file"))
                results.append({
                    "session_id": r["session_id"][:8],
                    "session_id_full": r["session_id"],
                    "source_type": "file",
                    "summary": r["summary"],
                    "date": (r["created_at"] or "")[:10],
                    "excerpt": f"{r['file_path']} ({r['tool_name']})",
                })
            return results[:limit]
        finally:
            conn.close()

    def show_session(self, session_id: str, *, turns: Optional[int] = None) -> Optional[dict]:
        conn = connect_ro(DB_PATH)
        try:
            if schema_check(conn):
                return None
            sid = session_id.strip().lower()
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ? OR id LIKE ?", (sid, f"{sid}%"),
            ).fetchone()
            if not row:
                return None
            full_id = row["id"]
            turns_sql = (
                "SELECT turn_index, user_message, assistant_response, timestamp "
                "FROM turns WHERE session_id = ? ORDER BY turn_index"
            )
            if turns is not None:
                turns_rows = conn.execute(turns_sql + " LIMIT ?", (full_id, turns)).fetchall()
            else:
                turns_rows = conn.execute(turns_sql, (full_id,)).fetchall()
            mx = 500
            turn_list = [
                {
                    "idx": t["turn_index"],
                    "user": (t["user_message"] or "")[:mx],
                    "assistant": (t["assistant_response"] or "")[:mx],
                    "timestamp": t["timestamp"],
                }
                for t in turns_rows
            ]
            files = [dict(f) for f in conn.execute(
                "SELECT file_path, tool_name, turn_index FROM session_files WHERE session_id = ?",
                (full_id,),
            ).fetchall()]
            refs = [dict(r) for r in conn.execute(
                "SELECT ref_type, ref_value, turn_index FROM session_refs WHERE session_id = ?",
                (full_id,),
            ).fetchall()]
            cps = [
                {"n": c["checkpoint_number"], "title": c["title"], "overview": (c["overview"] or "")[:300]}
                for c in conn.execute(
                    "SELECT checkpoint_number, title, overview FROM checkpoints "
                    "WHERE session_id = ? ORDER BY checkpoint_number",
                    (full_id,),
                ).fetchall()
            ]
            return {
                "id": full_id,
                "repository": row["repository"],
                "branch": row["branch"],
                "summary": row["summary"],
                "created_at": row["created_at"],
                "turns_count": len(turns_rows),
                "turns": turn_list,
                "files": files,
                "refs": refs,
                "checkpoints": cps,
            }
        finally:
            conn.close()

    def health(self) -> dict:
        from ..health.scoring import overall_score
        from ..health import (dim_freshness, dim_schema, dim_latency, dim_corpus,
                              dim_summary_coverage, dim_repo_coverage, dim_concurrency,
                              dim_e2e, dim_disclosure)
        dims = [dim_freshness, dim_schema, dim_latency, dim_corpus,
                dim_summary_coverage, dim_repo_coverage, dim_concurrency,
                dim_e2e, dim_disclosure]
        results = [d.check() for d in dims]
        score = overall_score(results)
        zones = [r["zone"] for r in results]
        if "RED" in zones:
            zone = "RED"
        elif "AMBER" in zones:
            zone = "AMBER"
        else:
            zone = "GREEN"
        return {"score": score, "zone": zone, "dimensions": results}
