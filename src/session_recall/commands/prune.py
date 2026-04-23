"""prune command — remove old sessions from the Claude Code index."""
import sys
from ..util.format_output import output


def run(args) -> int:
    try:
        from ..backends.claude_code.index import INDEX_PATH, _open
    except ImportError as e:
        print(f"error: Claude Code backend unavailable: {e}", file=sys.stderr)
        return 1

    if not INDEX_PATH.exists():
        print("error: index not found — run cc-index first", file=sys.stderr)
        return 1

    days = getattr(args, "days", 90) or 90
    dry_run = getattr(args, "dry_run", False)
    cutoff = f"-{days} days"

    conn = _open()
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM cc_sessions WHERE last_seen < datetime('now', ?)", (cutoff,)
        ).fetchone()
        count = count_row[0] if count_row else 0

        if not dry_run and count > 0:
            conn.execute("BEGIN")
            try:
                # delete child rows first (FK-style cleanup)
                conn.execute(
                    "DELETE FROM cc_turns WHERE session_id IN "
                    "(SELECT id FROM cc_sessions WHERE last_seen < datetime('now', ?))", (cutoff,)
                )
                conn.execute(
                    "DELETE FROM cc_files WHERE session_id IN "
                    "(SELECT id FROM cc_sessions WHERE last_seen < datetime('now', ?))", (cutoff,)
                )
                conn.execute(
                    "DELETE FROM cc_search WHERE session_id IN "
                    "(SELECT id FROM cc_sessions WHERE last_seen < datetime('now', ?))", (cutoff,)
                )
                conn.execute(
                    "DELETE FROM cc_sessions WHERE last_seen < datetime('now', ?)", (cutoff,)
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    finally:
        conn.close()

    data = {
        "days": days,
        "removed": 0 if dry_run else count,
        "would_remove": count if dry_run else None,
        "dry_run": dry_run,
    }
    if not getattr(args, "json", False):
        if dry_run:
            print(f"[dry-run] Would remove {count} session(s) older than {days} days")
        elif count == 0:
            print(f"Nothing to prune (no sessions older than {days} days)")
        else:
            print(f"Pruned {count} session(s) older than {days} days")
    output(data, json_mode=getattr(args, "json", False))
    return 0
