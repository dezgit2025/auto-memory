"""JetBrains file-backed session provider."""

from __future__ import annotations

from pathlib import Path

from ._base import _FileSessionProvider


class JetBrainsProvider(_FileSessionProvider):
    provider_name = "JetBrains"

    def __init__(self, root_override: str | None = None) -> None:
        home = Path.home()
        roots = (
            [Path(root_override).expanduser()]
            if root_override
            else [home / ".config" / "github-copilot"]
        )
        super().__init__(
            "jetbrains",
            roots,
            ["chat-sessions/*", "chat-agent-sessions/*", "chat-edit-sessions/*"],
        )
