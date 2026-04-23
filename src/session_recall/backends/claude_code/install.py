"""Detect Claude Code installation surfaces and wire session-recall hooks."""
from __future__ import annotations
import json
import os
import pathlib
import sys
from typing import NamedTuple


class Surface(NamedTuple):
    name: str
    detected: bool
    path: str
    note: str


def detect_surfaces() -> list[Surface]:
    """Detect which Claude Code installation surfaces are present."""
    surfaces = []

    # CLI — check if 'claude' binary is in PATH
    import shutil
    claude_bin = shutil.which("claude")
    surfaces.append(Surface(
        "cli", bool(claude_bin),
        claude_bin or "not found",
        "Claude Code CLI" if claude_bin else "Install from https://claude.ai/code"
    ))

    home = pathlib.Path.home()

    # VS Code extension
    vscode_ext_dir = home / ".vscode" / "extensions"
    vscode_found = None
    if vscode_ext_dir.exists():
        for d in vscode_ext_dir.iterdir():
            if d.name.startswith("anthropics.claude-code"):
                vscode_found = str(d)
                break
    surfaces.append(Surface(
        "vscode", bool(vscode_found),
        vscode_found or str(vscode_ext_dir / "anthropics.claude-code-*"),
        "VS Code extension" if vscode_found else "Not installed"
    ))

    # JetBrains
    jb_base = None
    if sys.platform == "win32":
        appdata = pathlib.Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        jb_base = appdata / "JetBrains"
    elif sys.platform == "darwin":
        jb_base = home / "Library" / "Application Support" / "JetBrains"
    else:
        jb_base = home / ".config" / "JetBrains"
    jb_found = None
    if jb_base and jb_base.exists():
        for ide_dir in jb_base.iterdir():
            plugins_dir = ide_dir / "plugins"
            if plugins_dir.exists():
                for p in plugins_dir.iterdir():
                    if "claude" in p.name.lower():
                        jb_found = str(p)
                        break
            if jb_found:
                break
    surfaces.append(Surface(
        "jetbrains", bool(jb_found),
        jb_found or (str(jb_base) if jb_base else "n/a"),
        "JetBrains plugin" if jb_found else "Not installed"
    ))

    # Desktop app (Windows)
    desktop_found = None
    if sys.platform == "win32":
        local_app = pathlib.Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        for d in local_app.iterdir() if local_app.exists() else []:
            if "claude" in d.name.lower():
                desktop_found = str(d)
                break
    elif sys.platform == "darwin":
        apps = pathlib.Path("/Applications")
        for d in (apps.iterdir() if apps.exists() else []):
            if "claude" in d.name.lower():
                desktop_found = str(d)
                break
    surfaces.append(Surface(
        "desktop", bool(desktop_found),
        desktop_found or "not found",
        "Desktop app" if desktop_found else "Not installed"
    ))

    return surfaces


_HOOK_COMMAND = "session-recall list --json --limit 5"
_HOOK_BLOCK = {
    "matcher": "",
    "hooks": [{"type": "command", "command": _HOOK_COMMAND}]
}


def wire_hooks(settings_path: pathlib.Path, *, dry_run: bool = False) -> dict:
    """
    Add a SessionStart hook to ~/.claude/settings.json.
    Returns {'changed': bool, 'path': str, 'action': str}.
    """
    data = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(
                f"{settings_path} contains invalid JSON — fix it before running --setup.\n"
                f"  Parse error: {e}"
            ) from e
        except OSError as e:
            raise OSError(f"Cannot read {settings_path}: {e}") from e

    hooks = data.setdefault("hooks", {})
    ss_hooks = hooks.setdefault("SessionStart", [])

    # Check if already wired
    for h in ss_hooks:
        for inner in h.get("hooks", []):
            if inner.get("command", "").startswith("session-recall"):
                return {"changed": False, "path": str(settings_path), "action": "already_wired"}

    ss_hooks.append(_HOOK_BLOCK)

    if not dry_run:
        tmp = settings_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(settings_path)

    return {
        "changed": True,
        "path": str(settings_path),
        "action": "dry_run" if dry_run else "wired",
        "hook_command": _HOOK_COMMAND,
    }
