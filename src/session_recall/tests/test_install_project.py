"""Tests for write_claude_md()."""
import json, pathlib
import pytest
from session_recall.backends.claude_code.install import write_claude_md, _SENTINEL

def test_write_to_new_file(tmp_path):
    p = tmp_path / "CLAUDE.md"
    result = write_claude_md(p)
    assert result["action"] == "written"
    assert p.exists()
    assert _SENTINEL in p.read_text()

def test_write_appends_to_existing(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# My Project\n\nExisting content.\n")
    result = write_claude_md(p)
    assert result["action"] == "updated"
    text = p.read_text()
    assert "# My Project" in text
    assert _SENTINEL in text

def test_idempotent(tmp_path):
    p = tmp_path / "CLAUDE.md"
    write_claude_md(p)
    result = write_claude_md(p)
    assert result["action"] == "already_present"
    # block appears exactly once
    assert p.read_text().count(_SENTINEL) == 2  # opening + closing sentinel

def test_dry_run_no_write(tmp_path):
    p = tmp_path / "CLAUDE.md"
    result = write_claude_md(p, dry_run=True)
    assert result["action"] == "dry_run"
    assert not p.exists()

def test_atomic_no_tmp_remaining(tmp_path):
    p = tmp_path / "CLAUDE.md"
    write_claude_md(p)
    assert not p.with_suffix(".tmp").exists()
