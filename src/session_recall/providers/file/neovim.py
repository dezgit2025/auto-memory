"""Neovim file-backed session provider."""

from __future__ import annotations

from pathlib import Path

from ._base import _FileSessionProvider


class NeovimProvider(_FileSessionProvider):
    provider_name = "Neovim"

    def __init__(self, root_override: str | None = None) -> None:
        home = Path.home()
        if root_override:
            roots = [Path(root_override).expanduser()]
        else:
            roots = [
                home / ".config" / "github-copilot",
                home / ".local" / "share" / "nvim",
            ]
        super().__init__("neovim", roots, ["**/*chat*.json", "**/*chat*.jsonl"])
