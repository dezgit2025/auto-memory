"""File-backed session providers (lazy-loaded)."""


def __getattr__(name):
    if name == "VSCodeProvider":
        from .vscode import VSCodeProvider

        return VSCodeProvider
    if name == "JetBrainsProvider":
        from .jetbrains import JetBrainsProvider

        return JetBrainsProvider
    if name == "NeovimProvider":
        from .neovim import NeovimProvider

        return NeovimProvider
    if name == "_extract_role":
        from ._parse_helpers import _extract_role

        return _extract_role
    if name == "_extract_text":
        from ._parse_helpers import _extract_text

        return _extract_text
    if name == "_is_wsl":
        from .vscode import _is_wsl

        return _is_wsl
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
