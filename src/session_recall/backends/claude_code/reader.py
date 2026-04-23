"""Parse Claude Code JSONL session files into normalized records."""
from __future__ import annotations
import json
import pathlib
from typing import Iterator


def _extract_text(content) -> str:
    """Extract plain text from message content (str or list of blocks)."""
    if isinstance(content, str):
        return content[:500]
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", "")[:300])
                elif block.get("type") == "tool_use":
                    parts.append(f"[{block.get('name', 'tool')}]")
                elif block.get("type") == "tool_result":
                    c = block.get("content", "")
                    parts.append((c[:200] if isinstance(c, str) else str(c)[:200]))
        return " ".join(parts)[:500]
    return ""


def iter_records(path: pathlib.Path) -> Iterator[dict]:
    """Yield parsed JSON objects from a JSONL file, skipping malformed lines."""
    # OSError propagates to caller so build_index can count and warn about unreadable files
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def parse_session(path: pathlib.Path) -> dict | None:
    """
    Parse a JSONL file into a normalized session dict:
    {
      id, cwd, repository, branch, version,
      first_seen, last_seen,
      turns: [{user, assistant, timestamp}],
      files: [{file_path, tool_name}],
      summary (first user message, truncated)
    }
    """
    session_id = path.stem
    cwd = None
    branch = None
    version = None
    first_ts = None
    last_ts = None
    turns = []
    files: dict[str, str] = {}  # file_path -> tool_name
    last_prompt = None

    pending_user: str | None = None

    for rec in iter_records(path):
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
            msg = rec.get("message", {})
            content = msg.get("content", "")
            # skip tool result records for turn pairing
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            ):
                # extract file paths from tool results
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        # heuristic: look for file paths in stdout
                        tr = rec.get("toolUseResult", {})
                        continue
                continue
            pending_user = _extract_text(content)

        elif rtype == "assistant":
            msg = rec.get("message", {})
            content = msg.get("content", [])
            assistant_text = _extract_text(content)
            # collect tool calls as file references
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        inp = block.get("input", {})
                        # Read/Write/Edit tools have file_path or path
                        fp = inp.get("file_path") or inp.get("path")
                        tool_name = block.get("name", "")
                        if fp and isinstance(fp, str):
                            files.setdefault(fp, tool_name)
            if pending_user is not None:
                turns.append({
                    "user": pending_user,
                    "assistant": assistant_text,
                    "timestamp": ts or "",
                })
                pending_user = None

    if not cwd and not first_ts:
        return None

    # derive repository from cwd (owner/repo from last two path segments)
    repository = _cwd_to_repo(cwd) if cwd else None
    summary = last_prompt or (turns[0]["user"][:120] if turns else "")

    return {
        "id": session_id,
        "cwd": cwd or "",
        "repository": repository or "",
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


def _cwd_to_repo(cwd: str) -> str:
    """Extract owner/repo-style identifier from a cwd path."""
    import pathlib
    p = pathlib.Path(cwd)
    parts = p.parts
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return p.name
