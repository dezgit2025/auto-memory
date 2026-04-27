"""Tests for wire_mcp_config() in backends/claude_code/install.py."""
from __future__ import annotations
import json
import pytest
from session_recall.backends.claude_code.install import wire_mcp_config


def test_wire_mcp_config_new_file(tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    result = wire_mcp_config(config)
    assert result["action"] == "wired"
    assert config.exists()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "session-recall" in data["mcpServers"]


def test_wire_mcp_config_idempotent(tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    wire_mcp_config(config)
    result = wire_mcp_config(config)
    assert result["action"] == "already_wired"
    assert result["changed"] is False


def test_wire_mcp_config_merges_existing_keys(tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    existing = {"globalShortcut": "Ctrl+Space", "theme": "dark"}
    config.write_text(json.dumps(existing), encoding="utf-8")
    wire_mcp_config(config)
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["globalShortcut"] == "Ctrl+Space"
    assert data["theme"] == "dark"
    assert "session-recall" in data["mcpServers"]


def test_wire_mcp_config_dry_run(tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    result = wire_mcp_config(config, dry_run=True)
    assert result["action"] == "dry_run"
    assert not config.exists()


def test_wire_mcp_config_corrupt_json_raises(tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    config.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        wire_mcp_config(config)


def test_wire_mcp_config_atomic_write(tmp_path):
    config = tmp_path / "claude_desktop_config.json"
    wire_mcp_config(config)
    assert not config.with_suffix(".tmp").exists()
