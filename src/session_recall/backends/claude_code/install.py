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
        try:
            entries = list(vscode_ext_dir.iterdir())
        except OSError:
            entries = []
        for d in entries:
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
        try:
            ide_dirs = list(jb_base.iterdir())
        except OSError:
            ide_dirs = []
        for ide_dir in ide_dirs:
            try:
                plugins_dir = ide_dir / "plugins"
                if plugins_dir.exists():
                    for p in plugins_dir.iterdir():
                        if "claude" in p.name.lower():
                            jb_found = str(p)
                            break
            except OSError:
                pass
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
        try:
            local_entries = list(local_app.iterdir()) if local_app.exists() else []
        except OSError:
            local_entries = []
        for d in local_entries:
            if "claude" in d.name.lower():
                desktop_found = str(d)
                break
    elif sys.platform == "darwin":
        apps = pathlib.Path("/Applications")
        try:
            app_entries = list(apps.iterdir()) if apps.exists() else []
        except OSError:
            app_entries = []
        for d in app_entries:
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
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            try:
                tmp.replace(settings_path)
            except PermissionError as e:
                raise OSError(
                    f"Cannot update {settings_path}: file is locked by another process. "
                    f"Close any tool that has it open and retry.\n  {e}"
                ) from e
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    return {
        "changed": True,
        "path": str(settings_path),
        "action": "dry_run" if dry_run else "wired",
        "hook_command": _HOOK_COMMAND,
    }


_SENTINEL = "<!-- session-recall -->"

_CLAUDE_MD_BLOCK = """{sentinel}
## Session Recall — run on every new conversation

Run `session-recall list --json --limit 5` at the start of every session
to recall recent context for this repository (~50 tokens).

Use `session-recall search "<topic>" --json` to find specific past work.
Use `session-recall show <session-id> --json` for full session detail.

If session-recall is not installed or errors, continue silently.
{sentinel}""".format(sentinel=_SENTINEL)


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

    new_content = existing.rstrip("\n") + ("\n\n" if existing else "") + _CLAUDE_MD_BLOCK + "\n"

    if dry_run:
        return {"action": "dry_run", "path": str(claude_md_path), "block": _CLAUDE_MD_BLOCK}

    tmp = claude_md_path.with_suffix(".tmp")
    try:
        tmp.write_text(new_content, encoding="utf-8")
        try:
            tmp.replace(claude_md_path)
        except PermissionError as e:
            raise OSError(
                f"Cannot update {claude_md_path}: file is locked by another process. "
                f"Close any editor that has it open and retry.\n  {e}"
            ) from e
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    action = "updated" if existing else "written"
    return {"action": action, "path": str(claude_md_path)}
