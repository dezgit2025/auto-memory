"""export command — dump sessions to markdown or JSON."""
import json
import sys

from ..backends import get_backend
from ..util.detect_repo import detect_repo


def run(args) -> int:
    backend_name = getattr(args, "backend", None) or getattr(args, "_global_backend", None)
    backend = get_backend(backend_name)
    repo = getattr(args, "repo", None) or detect_repo()
    session_id = getattr(args, "session", None)
    fmt = getattr(args, "format", "md")
    out_path = getattr(args, "output", None)
    limit = getattr(args, "limit", 20) or 20
    days = getattr(args, "days", 30) or 30

    if session_id:
        session = backend.show_session(session_id)
        if not session:
            print(f"error: session '{session_id}' not found", file=sys.stderr)
            return 1
        sessions = [session]
    else:
        summaries = backend.list_sessions(repo=repo, limit=limit, days=days)
        sessions = [_fetch_full(backend, s) for s in summaries]

    content = json.dumps(sessions, indent=2, default=str) if fmt == "json" else _to_markdown(sessions)

    if not out_path:
        print(content)
        return 0

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"exported {len(sessions)} session(s) to {out_path}", file=sys.stderr)
    return 0


def _fetch_full(backend, summary: dict) -> dict:
    sid = summary.get("id_full") or summary.get("id") or ""
    if not sid:
        return summary
    return backend.show_session(sid) or summary


def _to_markdown(sessions: list[dict]) -> str:
    lines: list[str] = []
    for s in sessions:
        sid = s.get("id", s.get("id_full", "unknown"))
        date = s.get("created_at", s.get("date", ""))
        lines.append(f"# Session: {sid[:8]}")
        lines.append(f"**Repository:** {s.get('repository', 'unknown')}  ")
        lines.append(f"**Branch:** {s.get('branch', '')}  ")
        lines.append(f"**Date:** {date[:10]}  ")
        lines.append(f"**Summary:** {s.get('summary', '')}  ")
        lines.append("")

        for t in s.get("turns", []):
            user = t.get("user") or t.get("user_msg", "")
            assistant = t.get("assistant") or t.get("assistant_msg", "")
            if user:
                lines.append(f"**User:** {user[:300]}")
            if assistant:
                lines.append(f"**Assistant:** {assistant[:300]}")
            lines.append("")

        files = s.get("files", [])
        if files:
            lines.append(f"**Files touched ({len(files)}):**")
            for f in files[:10]:
                fp = f.get("file_path", "")
                tn = f.get("tool_name", "")
                lines.append(f"- `{fp}` ({tn})" if tn else f"- `{fp}`")
            lines.append("")

        lines.append("---")
        lines.append("")
    return "\n".join(lines)
