"""Detect Claude Code projects and decode path-encoded directory names."""
from __future__ import annotations
import os
import pathlib
import re


CC_PROJECTS_DIR = pathlib.Path.home() / ".claude" / "projects"

_WIN_ENCODED_RE = re.compile(r'^([A-Za-z])--(.+)$')


def decode_project_path(encoded: str) -> str:
    """Decode 'C--Users-foo-repo' back to 'C:\\Users\\foo\\repo' (Windows) or '/Users/foo/repo' (Unix)."""
    m = _WIN_ENCODED_RE.match(encoded)
    if m:
        drive, rest = m.group(1), m.group(2)
        return drive + ":\\" + rest.replace("-", "\\")
    return "/" + encoded.replace("-", "/")


def encode_project_path(path: str) -> str:
    """Encode 'C:\\Users\\foo\\repo' to 'C--Users-foo-repo'."""
    if os.name == 'nt' and len(path) >= 2 and path[1] == ':':
        drive = path[0]
        rest = path[2:].lstrip('\\/').replace('\\', '-').replace('/', '-')
        return f"{drive}--{rest}"
    return path.lstrip('/').replace('/', '-').replace('\\', '-')


def list_projects() -> list[dict]:
    """Return list of {encoded, decoded, path, session_count} for all CC projects."""
    if not CC_PROJECTS_DIR.exists():
        return []
    results = [
        {
            "encoded": d.name,
            "decoded": decode_project_path(d.name),
            "path": d,
            "session_count": sum(1 for _ in d.glob("*.jsonl")),
        }
        for d in CC_PROJECTS_DIR.iterdir() if d.is_dir()
    ]
    return sorted(results, key=lambda x: x["session_count"], reverse=True)


def find_project_dir(cwd: str) -> pathlib.Path | None:
    """Find the Claude Code project dir for a given working directory path."""
    candidate = CC_PROJECTS_DIR / encode_project_path(cwd)
    return candidate if candidate.exists() else None


def _safe_mtime(p: pathlib.Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def list_session_files(project_dir: pathlib.Path | None = None) -> list[pathlib.Path]:
    """List all .jsonl session files, optionally filtered to one project."""
    if project_dir:
        return sorted(project_dir.glob("*.jsonl"), key=_safe_mtime, reverse=True)
    if not CC_PROJECTS_DIR.exists():
        return []
    files = [
        jf
        for d in CC_PROJECTS_DIR.iterdir() if d.is_dir()
        for jf in d.glob("*.jsonl")
    ]
    return sorted(files, key=_safe_mtime, reverse=True)
