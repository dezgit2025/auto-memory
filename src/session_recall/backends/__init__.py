"""Backend registry — auto-detect or select by name."""
from .base import SessionBackend
from .copilot import CopilotBackend


def _load_claude():
    try:
        from .claude_code import ClaudeCodeBackend
        return ClaudeCodeBackend
    except ImportError:
        return None


def _load_aider():
    from .aider import AiderBackend
    return AiderBackend


def _load_cursor():
    try:
        from .cursor import CursorBackend
        return CursorBackend
    except ImportError:
        return None


# Ordered (name, loader) pairs — order controls auto-detect precedence.
_BACKEND_LOADERS = [
    ("copilot", lambda: CopilotBackend),
    ("claude",  _load_claude),
    ("aider",   _load_aider),
    ("cursor",  _load_cursor),
]


def get_backend(name: str | None = None) -> SessionBackend:
    """Return a backend instance. name=None → auto-detect."""
    if name == "all":
        from .all import AllBackend
        return AllBackend()

    for backend_name, loader in _BACKEND_LOADERS:
        if name is not None and name != backend_name:
            continue
        cls = loader()
        if cls is None:
            continue
        instance = cls()
        # When explicitly requested, return even if unavailable; otherwise require availability.
        if name == backend_name or instance.is_available():
            return instance

    # fallback
    return CopilotBackend()


__all__ = ["SessionBackend", "CopilotBackend", "AllBackend", "get_backend"]


def __getattr__(name):
    # Lazy-export AllBackend to avoid importing optional backends at module load.
    if name == "AllBackend":
        from .all import AllBackend
        return AllBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
