"""VS Code file-backed session provider."""

from __future__ import annotations

from pathlib import Path

from ._base import _FileSessionProvider


def _is_wsl() -> bool:
    """Detect Windows Subsystem for Linux via /proc/version."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


class VSCodeProvider(_FileSessionProvider):
    provider_name = "VS Code"

    def __init__(self, root_override: str | None = None) -> None:
        home = Path.home()
        if root_override:
            roots = [Path(root_override).expanduser()]
        else:
            roots = [
                home / ".config" / "Code" / "User" / "workspaceStorage",
                home
                / "Library"
                / "Application Support"
                / "Code"
                / "User"
                / "workspaceStorage",
                home
                / ".var"
                / "app"
                / "com.visualstudio.code"
                / "config"
                / "Code"
                / "User"
                / "workspaceStorage",
                home
                / "snap"
                / "code"
                / "current"
                / ".config"
                / "Code"
                / "User"
                / "workspaceStorage",
                home / ".vscode-server" / "data" / "User" / "workspaceStorage",
            ]
        super().__init__("vscode", roots, ["**/chatSessions/*.jsonl"])
