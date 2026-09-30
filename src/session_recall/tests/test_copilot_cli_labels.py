"""Tests for Copilot CLI workspace labels and repo detection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from session_recall.providers.copilot_cli import _labels

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX path rendering"
)


@pytest.mark.parametrize("value", [None, ""])
def test_label_empty_path_returns_none(value) -> None:
    assert _labels._local_workspace_label(value) is None


@posix_only
def test_label_absolute_path_is_unchanged() -> None:
    assert _labels._local_workspace_label("/work/app") == "local:/work/app"


@posix_only
def test_label_relative_path_keeps_forward_slashes() -> None:
    assert _labels._local_workspace_label("projects/app") == "local:projects/app"


@posix_only
def test_label_expands_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _labels._local_workspace_label("~/app") == f"local:{tmp_path}/app"


def test_detect_repo_from_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        _labels, "detect_repo_for_cwd", lambda p: "o/r" if p == str(tmp_path) else None
    )
    assert _labels._detect_repo_for_path(str(tmp_path)) == "o/r"


def test_detect_repo_from_file_uses_its_directory(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "notes.md"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        _labels, "detect_repo_for_cwd", lambda p: "o/r" if p == str(tmp_path) else None
    )
    assert _labels._detect_repo_for_path(str(target)) == "o/r"
