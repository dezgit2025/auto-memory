"""Parse Claude Code JSONL session files into normalized records."""
from __future__ import annotations

import pathlib

from ..common import iter_jsonl_bounded
from ..file._path_safety import is_under_root

_CLAUDE_PROJECTS_ROOT = pathlib.Path.home() / ".claude" / "projects"


def _extract_text(content) -> str:
    """Extract plain text from message content (str or list of blocks)."""
    if isinstance(content, str):
        return content[:500]
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", "")[:300])
        elif btype == "tool_use":
            parts.append(f"[{block.get('name', 'tool')}]")
        elif btype == "tool_result":
            c = block.get("content", "")
            text = c if isinstance(c, str) else str(c)
            parts.append(text[:200])
    return " ".join(parts)[:500]


def _is_tool_result_message(content) -> bool:
    """True if a user message content is actually a tool_result (not a real prompt)."""
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result"
        for b in content
    )


def _collect_tool_files(content, files: dict[str, str]) -> None:
    """Collect file paths referenced by tool_use blocks into the files dict."""
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        inp = block.get("input", {})
        fp = inp.get("file_path") or inp.get("path")
        if fp and isinstance(fp, str):
            files.setdefault(fp, block.get("name", ""))


def _cwd_to_repo(cwd: str) -> str:
    """Extract owner/repo-style identifier from a cwd path."""
    p = pathlib.Path(cwd)
    parts = p.parts
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return p.name


def parse_session(
    path: pathlib.Path,
    *,
    root: pathlib.Path | None = None,
) -> dict | None:
    """Parse a JSONL file into a normalized session dict.

    Returns None when the file is unreadable, resolves outside the
    allowed *root* (default ``~/.claude/projects/``), or contains no
    meaningful data.
    """
    allowed_root = root if root is not None else _CLAUDE_PROJECTS_ROOT
    if not is_under_root(path, allowed_root):
        return None

    session_id = path.stem
    cwd: str | None = None
    branch: str | None = None
    version: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None
    turns: list[dict] = []
    files: dict[str, str] = {}
    last_prompt: str | None = None
    pending_user: str | None = None

    try:
        records = iter_jsonl_bounded(path)
    except OSError:
        return None

    for rec in records:
        rtype = rec.get("type")
        ts = rec.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        if cwd is None:
            cwd = rec.get("cwd")
        if branch is None:
            branch = rec.get("gitBranch")
        if version is None:
            version = rec.get("version")

        if rtype == "last-prompt":
            last_prompt = rec.get("lastPrompt", "")
        elif rtype == "user":
            content = rec.get("message", {}).get("content", "")
            if _is_tool_result_message(content):
                continue
            pending_user = _extract_text(content)
        elif rtype == "assistant":
            content = rec.get("message", {}).get("content", [])
            assistant_text = _extract_text(content)
            _collect_tool_files(content, files)
            if pending_user is not None:
                turns.append({
                    "user": pending_user,
                    "assistant": assistant_text,
                    "assistant_summary": assistant_text[:300],
                    "timestamp": ts or "",
                })
                pending_user = None

    if not cwd and not first_ts:
        return None

    repository = _cwd_to_repo(cwd) if cwd else ""
    summary = last_prompt or (turns[0]["user"][:120] if turns else "")

    return {
        "id": session_id,
        "cwd": cwd or "",
        "repository": repository,
        "branch": branch or "",
        "version": version or "",
        "first_seen": first_ts or "",
        "last_seen": last_ts or "",
        "turns_count": len(turns),
        "files_count": len(files),
        "summary": summary[:200],
        "turns": turns,
        "files": [{"file_path": fp, "tool_name": tn} for fp, tn in files.items()],
    }
