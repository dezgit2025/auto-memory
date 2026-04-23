"""Dim 6: Surfaces — detect how many Claude Code installation surfaces are present."""
from __future__ import annotations
import json
import pathlib
from .scoring import zone_for_score

NAME = "dim_surfaces"

_HOME = pathlib.Path.home()
_SETTINGS_PATH = _HOME / ".claude" / "settings.json"
_PROJECTS_DIR = _HOME / ".claude" / "projects"

# Paths that indicate a surface is installed beyond the CLI
_SURFACE_CHECKS: list[tuple[str, list[pathlib.Path]]] = [
    ("cli", [_HOME / ".claude"]),
    ("vscode", [
        _HOME / ".vscode" / "extensions",
        _HOME / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "resources",
        pathlib.Path("/usr/share/code"),
        pathlib.Path("/Applications/Visual Studio Code.app"),
    ]),
    ("jetbrains", [
        _HOME / ".config" / "JetBrains",
        _HOME / "AppData" / "Roaming" / "JetBrains",
        _HOME / "Library" / "Application Support" / "JetBrains",
    ]),
    ("desktop", [
        _HOME / "AppData" / "Local" / "Programs" / "Claude",
        pathlib.Path("/Applications/Claude.app"),
        pathlib.Path("/usr/bin/claude-desktop"),
    ]),
]


def _hook_is_wired() -> bool:
    """Return True if a PostToolUse or Stop hook referencing session_recall is in settings.json."""
    try:
        raw = _SETTINGS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        hooks = data.get("hooks", {})
        if not hooks:
            return False
        hook_text = json.dumps(hooks)
        return "session_recall" in hook_text or "cc-index" in hook_text
    except Exception:
        return False


def check() -> dict:
    try:
        detected: list[str] = []
        for surface, paths in _SURFACE_CHECKS:
            if any(p.exists() for p in paths):
                detected.append(surface)

        hook_wired = _hook_is_wired()
        projects_exist = _PROJECTS_DIR.exists()

        if hook_wired:
            score = 10.0
            hook_label = "hook wired"
        elif detected:
            score = 5.0
            hook_label = "hook not wired"
        elif projects_exist:
            score = 2.0
            hook_label = "hook not wired"
        else:
            score = 0.0
            return {
                "name": NAME, "score": score, "zone": "RED",
                "detail": "no Claude Code installation detected",
            }

        n = len(detected)
        surfaces_label = (", ".join(detected)) if detected else "none"
        detail = f"{hook_label}, {n} surface{'s' if n != 1 else ''} detected: {surfaces_label}"
        return {"name": NAME, "score": score, "zone": zone_for_score(score), "detail": detail}
    except Exception as e:
        return {"name": NAME, "score": 0.0, "zone": "RED", "detail": f"error: {e}"}
