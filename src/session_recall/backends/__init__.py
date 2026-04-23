"""Backend registry — auto-detect or select by name."""
from .base import SessionBackend
from .copilot import CopilotBackend

_BACKENDS = {
    "copilot": CopilotBackend,
}

# Lazy import for claude_code to avoid import errors if its deps aren't present
def _get_claude_backend():
    try:
        from .claude_code import ClaudeCodeBackend
        return ClaudeCodeBackend
    except ImportError:
        return None


def get_backend(name: str | None = None) -> SessionBackend:
    """Return a backend instance. name=None → auto-detect."""
    if name == "all":
        from .all import AllBackend
        return AllBackend()
    if name == "copilot" or name is None:
        b = CopilotBackend()
        if b.is_available() or name == "copilot":
            return b
    if name == "claude" or name is None:
        cls = _get_claude_backend()
        if cls:
            b = cls()
            if b.is_available() or name == "claude":
                return b
    if name == "aider" or name is None:
        from .aider import AiderBackend
        b = AiderBackend()
        if b.is_available() or name == "aider":
            return b
    if name == "cursor" or name is None:
        try:
            from .cursor import CursorBackend
            b = CursorBackend()
            if b.is_available() or name == "cursor":
                return b
        except ImportError:
            pass
    # fallback
    return CopilotBackend()


__all__ = ["SessionBackend", "CopilotBackend", "get_backend", "AllBackend"]
