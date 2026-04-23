"""Tests for backends/claude_code/install.py."""
import json
import pathlib
import pytest
from session_recall.backends.claude_code.install import wire_hooks, detect_surfaces, Surface


def test_wire_hooks_new_file(tmp_path):
    settings = tmp_path / "settings.json"
    result = wire_hooks(settings)
    assert result["action"] == "wired"
    data = json.loads(settings.read_text())
    assert "hooks" in data
    assert "SessionStart" in data["hooks"]


def test_wire_hooks_idempotent(tmp_path):
    settings = tmp_path / "settings.json"
    wire_hooks(settings)
    result = wire_hooks(settings)
    assert result["action"] == "already_wired"


def test_wire_hooks_merges_existing(tmp_path):
    settings = tmp_path / "settings.json"
    existing = {"model": "sonnet", "permissions": {"allow": ["Bash(git*)"]}}
    settings.write_text(json.dumps(existing))
    wire_hooks(settings)
    data = json.loads(settings.read_text())
    assert data["model"] == "sonnet"
    assert data["permissions"]["allow"] == ["Bash(git*)"]
    assert "SessionStart" in data["hooks"]


def test_wire_hooks_dry_run_no_write(tmp_path):
    settings = tmp_path / "settings.json"
    result = wire_hooks(settings, dry_run=True)
    assert result["action"] == "dry_run"
    assert not settings.exists()


def test_wire_hooks_corrupt_json_raises(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{ not valid json")
    with pytest.raises(ValueError, match="invalid JSON"):
        wire_hooks(settings)


def test_wire_hooks_atomic_write(tmp_path):
    # After successful write, no .tmp file should remain
    settings = tmp_path / "settings.json"
    wire_hooks(settings)
    tmp_file = settings.with_suffix(".tmp")
    assert not tmp_file.exists()


def test_hook_command_no_backend_flag():
    from session_recall.backends.claude_code.install import _HOOK_COMMAND
    assert "--backend" not in _HOOK_COMMAND


def test_detect_surfaces_returns_list():
    surfaces = detect_surfaces()
    assert isinstance(surfaces, list)
    assert all(isinstance(s, Surface) for s in surfaces)
    names = {s.name for s in surfaces}
    assert {"cli", "vscode", "jetbrains", "desktop"} == names


def test_wire_hooks_returns_hook_command_key(tmp_path):
    settings = tmp_path / "settings.json"
    result = wire_hooks(settings)
    assert "hook_command" in result
    assert result["hook_command"]


def test_wire_hooks_file_written(tmp_path):
    settings = tmp_path / "settings.json"
    wire_hooks(settings)
    assert settings.exists()
    data = json.loads(settings.read_text())
    # Should have a non-empty SessionStart list
    assert len(data["hooks"]["SessionStart"]) >= 1
