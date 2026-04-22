"""Provider discovery and selection."""

from __future__ import annotations

from ..config import (
    CLI_SESSION_STATE_ROOT,
    JETBRAINS_SESSIONS_ROOT,
    NEOVIM_SESSIONS_ROOT,
    VSCODE_WORKSPACE_STORAGE,
)
from .base import StorageProvider
from .copilot_cli import CopilotCliProvider
from .file_backends import JetBrainsProvider, NeovimProvider, VSCodeProvider


def discover_providers(db_path: str) -> list[StorageProvider]:
    """Build the provider list and keep only available ones."""
    candidates: list[StorageProvider] = [
        CopilotCliProvider(db_path=db_path, state_root=CLI_SESSION_STATE_ROOT),
        VSCodeProvider(root_override=VSCODE_WORKSPACE_STORAGE),
        JetBrainsProvider(root_override=JETBRAINS_SESSIONS_ROOT),
        NeovimProvider(root_override=NEOVIM_SESSIONS_ROOT),
    ]
    return [p for p in candidates if p.is_available()]


def get_active_providers(selected: str | None, db_path: str) -> list[StorageProvider]:
    """Resolve user-selected provider scope from discovered backends."""
    providers = discover_providers(db_path)
    if not selected or selected == "all":
        return providers
    selected = selected.lower()
    filtered = [p for p in providers if p.provider_id == selected]
    if not filtered:
        known = ", ".join(sorted({p.provider_id for p in providers})) or "none"
        raise ValueError(f"provider '{selected}' is unavailable (available: {known})")
    return filtered
