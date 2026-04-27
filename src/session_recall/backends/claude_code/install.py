"""Detect Claude Code installation surfaces and wire session-recall hooks."""
from __future__ import annotations
import copy
import json
import os
import pathlib
import shutil
import sys
from typing import NamedTuple


class Surface(NamedTuple):
    name: str
    detected: bool
    path: str
    note: str


def _safe_iterdir(path: pathlib.Path) -> list[pathlib.Path]:
    """Return entries of a directory, or [] if missing/unreadable."""
    if not path.exists():
        return []
    try:
        return list(path.iterdir())
    except OSError:
        return []


def _find_first(entries: list[pathlib.Path], predicate) -> str | None:
    """Return str(entry) of the first matching entry, or None."""
    for entry in entries:
        if predicate(entry):
            return str(entry)
    return None


def _detect_cli() -> Surface:
    claude_bin = shutil.which("claude")
    return Surface(
        "cli",
        bool(claude_bin),
        claude_bin or "not found",
        "Claude Code CLI" if claude_bin else "Install from https://claude.ai/code",
    )


def _detect_vscode(home: pathlib.Path) -> Surface:
    ext_dir = home / ".vscode" / "extensions"
    found = _find_first(
        _safe_iterdir(ext_dir),
        lambda d: d.name.startswith("anthropic.claude-code"),
    )
    return Surface(
        "vscode",
        bool(found),
        found or str(ext_dir / "anthropic.claude-code-*"),
        "VS Code extension" if found else "Not installed",
    )


def _jetbrains_base(home: pathlib.Path) -> pathlib.Path:
    if sys.platform == "win32":
        appdata = pathlib.Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return appdata / "JetBrains"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "JetBrains"
    return home / ".config" / "JetBrains"


def _detect_jetbrains(home: pathlib.Path) -> Surface:
    base = _jetbrains_base(home)
    found: str | None = None
    for ide_dir in _safe_iterdir(base):
        found = _find_first(
            _safe_iterdir(ide_dir / "plugins"),
            lambda p: "claude" in p.name.lower(),
        )
        if found:
            break
    return Surface(
        "jetbrains",
        bool(found),
        found or str(base),
        "JetBrains plugin" if found else "Not installed",
    )


def _detect_desktop(home: pathlib.Path) -> Surface:
    found: str | None = None
    if sys.platform == "win32":
        local_app = pathlib.Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        found = _find_first(_safe_iterdir(local_app), lambda d: "claude" in d.name.lower())
    elif sys.platform == "darwin":
        found = _find_first(
            _safe_iterdir(pathlib.Path("/Applications")),
            lambda d: "claude" in d.name.lower(),
        )
    return Surface(
        "desktop",
        bool(found),
        found or "not found",
        "Desktop app" if found else "Not installed",
    )


def detect_surfaces() -> list[Surface]:
    """Detect which Claude Code installation surfaces are present."""
    home = pathlib.Path.home()
    return [
        _detect_cli(),
        _detect_vscode(home),
        _detect_jetbrains(home),
        _detect_desktop(home),
    ]


_HOOK_COMMAND = "session-recall list --json --limit 5"
_HOOK_BLOCK = {
    "matcher": "",
    "hooks": [{"type": "command", "command": _HOOK_COMMAND}],
}


def _read_json(path: pathlib.Path) -> dict:
    """Load a JSON file, returning {} if missing. Raises ValueError for bad JSON."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{path} contains invalid JSON — fix it before running --setup.\n"
            f"  Parse error: {e}"
        ) from e
    except OSError as e:
        raise OSError(f"Cannot read {path}: {e}") from e


def _atomic_write(path: pathlib.Path, content: str, *, locked_msg: str) -> None:
    """Write content to path atomically via a .tmp sibling."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        try:
            tmp.replace(path)
        except PermissionError as e:
            raise OSError(f"{locked_msg}\n  {e}") from e
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def wire_hooks(settings_path: pathlib.Path, *, dry_run: bool = False) -> dict:
    """
    Add a SessionStart hook to ~/.claude/settings.json.
    Returns {'changed': bool, 'path': str, 'action': str}.
    """
    data = _read_json(settings_path)
    ss_hooks = data.setdefault("hooks", {}).setdefault("SessionStart", [])

    already_wired = any(
        inner.get("command", "").startswith("session-recall")
        for h in ss_hooks
        for inner in h.get("hooks", [])
    )
    if already_wired:
        return {"changed": False, "path": str(settings_path), "action": "already_wired"}

    ss_hooks.append(_HOOK_BLOCK)

    if not dry_run:
        _atomic_write(
            settings_path,
            json.dumps(data, indent=2),
            locked_msg=(
                f"Cannot update {settings_path}: file is locked by another process. "
                "Close any tool that has it open and retry."
            ),
        )

    return {
        "changed": True,
        "path": str(settings_path),
        "action": "dry_run" if dry_run else "wired",
        "hook_command": _HOOK_COMMAND,
    }


_SENTINEL = "<!-- session-recall -->"

_CLAUDE_MD_BLOCK = f"""{_SENTINEL}
## Session Recall — run on every new conversation

Run `session-recall list --json --limit 5` at the start of every session
to recall recent context for this repository (~50 tokens).

Use `session-recall search "<topic>" --json` to find specific past work.
Use `session-recall show <session-id> --json` for full session detail.

If session-recall is not installed or errors, continue silently.
{_SENTINEL}"""


def write_claude_md(claude_md_path: pathlib.Path, *, dry_run: bool = False) -> dict:
    """
    Append (or update) the session-recall block in a CLAUDE.md file.
    Returns {"action": "written"|"updated"|"already_present"|"dry_run", "path": str}.
    """
    existing = ""
    if claude_md_path.exists():
        try:
            existing = claude_md_path.read_text(encoding="utf-8")
        except OSError as e:
            raise OSError(f"Cannot read {claude_md_path}: {e}") from e

    if _SENTINEL in existing:
        return {"action": "already_present", "path": str(claude_md_path)}

    separator = "\n\n" if existing else ""
    new_content = existing.rstrip("\n") + separator + _CLAUDE_MD_BLOCK + "\n"

    if dry_run:
        return {"action": "dry_run", "path": str(claude_md_path), "block": _CLAUDE_MD_BLOCK}

    _atomic_write(
        claude_md_path,
        new_content,
        locked_msg=(
            f"Cannot update {claude_md_path}: file is locked by another process. "
            "Close any editor that has it open and retry."
        ),
    )
    return {
        "action": "updated" if existing else "written",
        "path": str(claude_md_path),
    }


_MCP_ENTRY = {
    "command": "session-recall",
    "args": ["serve"],
    "env": {},
}


def _default_mcp_config_path() -> pathlib.Path:
    """Platform-specific path to claude_desktop_config.json."""
    home = pathlib.Path.home()
    if sys.platform == "win32":
        appdata = pathlib.Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return appdata / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def wire_mcp_config(config_path: pathlib.Path, *, dry_run: bool = False) -> dict:
    """
    Add session-recall MCP server entry to claude_desktop_config.json.
    Returns {"action": "wired"|"already_wired"|"dry_run", "path": str}.
    """
    data = _read_json(config_path)
    servers = data.setdefault("mcpServers", {})
    if "session-recall" in servers:
        return {"changed": False, "path": str(config_path), "action": "already_wired"}

    servers["session-recall"] = copy.deepcopy(_MCP_ENTRY)

    if dry_run:
        return {"changed": True, "action": "dry_run", "path": str(config_path)}

    _atomic_write(
        config_path,
        json.dumps(data, indent=2),
        locked_msg=f"Cannot update {config_path}: file is locked.",
    )
    return {"changed": True, "path": str(config_path), "action": "wired"}
