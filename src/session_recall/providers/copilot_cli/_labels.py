"""Workspace label and repo detection helpers."""

from __future__ import annotations

from pathlib import Path

from ...util.detect_repo import detect_repo_for_cwd


def _detect_repo_for_path(path_str: str) -> str | None:
    path = Path(path_str).expanduser()
    candidate = path if path.is_dir() else path.parent
    return detect_repo_for_cwd(str(candidate))


def _local_workspace_label(path_str: str | None) -> str | None:
    if not path_str:
        return None
    expanded = Path(path_str).expanduser()
    return f"local:{expanded}"
