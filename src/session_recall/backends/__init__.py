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
    # fallback
    return CopilotBackend()


__all__ = ["SessionBackend", "CopilotBackend", "get_backend", "AllBackend"]
