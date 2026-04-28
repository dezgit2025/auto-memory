"""Text extraction, role detection, and turn parsing for file-backed providers."""

from __future__ import annotations

import json
from pathlib import Path


def _extract_role(obj: object) -> str:
    if not isinstance(obj, dict):
        return "assistant"
    if obj.get("kind") == 1:
        k = obj.get("k")
        if (
            isinstance(k, list)
            and len(k) >= 2
            and k[0] == "inputState"
            and k[1] == "inputText"
        ):
            return "user"
    role = obj.get("role")
    if isinstance(role, str):
        return role.lower()
    kind = obj.get("type")
    if isinstance(kind, str):
        return "user" if "user" in kind.lower() else "assistant"
    return "assistant"


def _extract_text(obj: object) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return " ".join(x for x in (_extract_text(i) for i in obj) if x)
    if not isinstance(obj, dict):
        return ""

    if obj.get("kind") == 1:
        k = obj.get("k")
        v = obj.get("v")
        if (
            isinstance(k, list)
            and len(k) >= 2
            and k[0] == "inputState"
            and k[1] == "inputText"
        ):
            return v if isinstance(v, str) else ""

    if obj.get("kind") == 2 and isinstance(obj.get("v"), list):
        for item in obj.get("v"):
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            if isinstance(message, str) and message.strip():
                return message

    candidates = [
        obj.get("text"),
        obj.get("content"),
        obj.get("message"),
        obj.get("value"),
    ]
    for c in candidates:
        t = _extract_text(c)
        if t:
            return t

    for key in ("messages", "parts", "items", "payload"):
        if key in obj:
            t = _extract_text(obj[key])
            if t:
                return t
    return ""


def _best_summary(turns: list[dict], fallback: str) -> str:
    """Pick the first meaningful user/assistant line for list summaries."""
    for turn in turns:
        for key in ("user", "assistant"):
            raw = str(turn.get(key) or "").strip()
            if not raw:
                continue
            first_line = raw.splitlines()[0].strip()
            if len(first_line) < 4:
                continue
            if first_line in {"@", "```", "---"}:
                continue
            return first_line[:120]
    return fallback


def parse_turns(
    file_path: Path, max_parse_lines: int, max_line_chars: int
) -> list[dict]:
    """Parse JSONL file into turn dicts with deduplication."""
    turns: list[dict] = []
    last_text = None
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if idx >= max_parse_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                if len(line) > max_line_chars:
                    continue
                try:
                    obj = json.loads(line)
                except (
                    json.JSONDecodeError,
                    RecursionError,
                    TypeError,
                    ValueError,
                ):
                    continue
                text = _extract_text(obj)
                if not text:
                    continue
                text = text.strip()
                if not text or text == last_text:
                    continue
                last_text = text
                role = _extract_role(obj)
                turns.append(
                    {
                        "idx": idx,
                        "user": text if role == "user" else "",
                        "assistant": text if role != "user" else "",
                        "timestamp": (
                            obj.get("timestamp") if isinstance(obj, dict) else None
                        ),
                    }
                )
    except OSError:
        return []
    return turns
