"""Workspace label and repo detection helpers."""

from __future__ import annotations

import ntpath
import posixpath
from pathlib import Path

from ...util.detect_repo import detect_repo_for_cwd


def _is_posixish_path(path_str: str) -> bool:
    """Return True for POSIX/WSL-style paths even when running on Windows."""
    return path_str.startswith(("/", "~/"))


def _detect_repo_for_path(path_str: str) -> str | None:
    """Detect a repository for a path without rewriting POSIX paths on Windows.

    Copilot CLI state can contain Linux/WSL-style paths even when this package is
    executed by Windows Python. Passing those strings through pathlib.Path on
    Windows rewrites separators (``/work`` -> ``\\work``), which breaks repo
    detection and changes user-facing local workspace labels.
    """
    if _is_posixish_path(path_str):
        expanded = posixpath.expanduser(path_str)
        for candidate in (expanded, posixpath.dirname(expanded)):
            if not candidate:
                continue
            repo = detect_repo_for_cwd(candidate)
            if repo:
                return repo
        return None

    path = Path(path_str).expanduser()
    candidate = path if path.is_dir() else path.parent
    return detect_repo_for_cwd(str(candidate))


def _local_workspace_label(path_str: str | None) -> str | None:
    if not path_str:
        return None
    if _is_posixish_path(path_str):
        return f"local:{posixpath.expanduser(path_str)}"
    return f"local:{ntpath.normpath(str(Path(path_str).expanduser()))}"
