"""Trust fencing for file-backed provider content."""

_FENCE_OPEN = "<<UNTRUSTED-FILE-BACKED-CONTENT>>"
_FENCE_CLOSE = "<<END-UNTRUSTED-FILE-BACKED-CONTENT>>"


def wrap_untrusted(text: str) -> str:
    """Wrap text in sentinel fence markers for downstream agent safety."""
    if not text:
        return text
    # Strip any embedded fence markers an attacker could inject
    text = text.replace(_FENCE_OPEN, "").replace(_FENCE_CLOSE, "")
    return f"{_FENCE_OPEN}\n{text}\n{_FENCE_CLOSE}"
