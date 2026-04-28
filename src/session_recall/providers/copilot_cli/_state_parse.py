"""JSONL state session parsing for Copilot CLI."""

from __future__ import annotations

import json
from pathlib import Path

from ..common import short_id, utc_iso_from_ts
from ._labels import _detect_repo_for_path, _local_workspace_label


_PATH_HINT_KEYS = {
    "path",
    "cwd",
    "filePath",
    "workspaceFolder",
    "dirPath",
    "resourcePath",
    "includePattern",
}


def _extract_path_candidates(obj: object) -> list[str]:
    paths: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if (
                key in _PATH_HINT_KEYS
                and isinstance(value, str)
                and value.strip().startswith(("/", "~"))
            ):
                paths.append(value.strip())
            paths.extend(_extract_path_candidates(value))
    elif isinstance(obj, list):
        for item in obj:
            paths.extend(_extract_path_candidates(item))
    return paths


def _dedupe_paths(paths: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def parse_state_session(provider_id: str, file_path: Path) -> dict:
    """Parse an events.jsonl state file into a session dict."""
    session_id = file_path.parent.name
    created_at = None
    cwd = None
    git_root = None
    repo_from_context = None
    candidate_paths: list[str] = []
    turns: list[dict] = []
    last_text = None
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type")
                data = event.get("data") or {}
                ts = event.get("timestamp")

                if etype == "session.start":
                    session_id = data.get("sessionId") or session_id
                    created_at = created_at or ts
                    context = data.get("context") or {}
                    if isinstance(context, dict):
                        cwd = context.get("cwd") or cwd
                        git_root = context.get("gitRoot") or git_root
                        if isinstance(context.get("repository"), str):
                            repo_from_context = (
                                context.get("repository") or repo_from_context
                            )
                elif etype == "tool.execution_start":
                    candidate_paths.extend(
                        _extract_path_candidates(data.get("arguments"))
                    )

                text = None
                role = None
                if etype == "user.message":
                    text = data.get("content") or data.get("transformedContent")
                    role = "user"
                elif etype == "assistant.message":
                    text = data.get("content")
                    role = "assistant"

                if not text:
                    continue
                text = str(text).strip()
                if not text or text == last_text:
                    continue
                last_text = text
                turns.append(
                    {
                        "idx": len(turns),
                        "user": text if role == "user" else "",
                        "assistant": text if role == "assistant" else "",
                        "timestamp": ts,
                    }
                )
    except OSError:
        pass

    summary = ""
    for t in turns:
        if t.get("user"):
            summary = t["user"].splitlines()[0][:120]
            break
    if not summary:
        summary = file_path.name

    created_str = ""
    if isinstance(created_at, str) and created_at:
        created_str = created_at
    else:
        created_str = utc_iso_from_ts(file_path.stat().st_mtime)

    repository = repo_from_context
    if not repository:
        for maybe_repo_path in (git_root, cwd, *_dedupe_paths(candidate_paths)):
            if not isinstance(maybe_repo_path, str) or not maybe_repo_path:
                continue
            repository = _detect_repo_for_path(maybe_repo_path)
            if repository:
                break
    if not repository:
        repository = _local_workspace_label(
            git_root or cwd or next(iter(_dedupe_paths(candidate_paths)), None)
        )

    return {
        "provider": provider_id,
        "id_short": short_id(session_id),
        "id_full": session_id,
        "repository": repository or "unknown",
        "branch": "unknown",
        "summary": summary,
        "date": created_str[:10] if created_str else "",
        "created_at": created_str,
        "turns_count": len(turns),
        "files_count": 0,
        "_trust_level": "trusted_first_party",
        "_turns": turns,
        "_path": str(file_path),
    }
