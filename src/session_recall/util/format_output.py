"""Output formatting for human-readable and JSON modes."""

import json
import re

_CONTROL_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"  # CSI sequences (colors, cursor moves)
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC sequences (title, clipboard, hyperlinks)
    r"|\x1b[@-Z\\-_]"  # other ESC-prefixed (Fp, Fe, Fs)
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"  # C0 controls (except TAB \x09, LF \x0a, CR \x0d) + DEL
    r"|[\x80-\x9f]"  # C1 controls
)


def sanitize_for_terminal(s: str | None) -> str:
    """Strip ANSI/OSC/control sequences so session content can't hijack the terminal."""
    if not s:
        return ""
    return _CONTROL_RE.sub("", s)


def fmt_json(data: dict | list) -> str:
    """Return compact JSON string."""
    return json.dumps(data, indent=2, default=str)


def fmt_human_sessions(sessions: list[dict]) -> str:
    """Format session list as human-readable table."""
    if not sessions:
        return "No sessions found."
    lines = []
    lines.append(
        f"{'ID':8s}  {'Date':10s}  {'Repository/Workspace':28s}  {'Turns':>5s}  {'Summary'}"
    )
    lines.append("-" * 100)
    for s in sessions:
        sid = sanitize_for_terminal(s.get("id_short", s.get("id", "?")[:8]))
        date = sanitize_for_terminal(s.get("date", s.get("created_at", "?"))[:10])
        repo = sanitize_for_terminal((s.get("repository") or "unknown")[:28])
        turns = str(s.get("turns_count", s.get("turns", "?")))
        summary = sanitize_for_terminal((s.get("summary") or "(untitled)")[:40])
        lines.append(f"{sid:8s}  {date:10s}  {repo:28s}  {turns:>5s}  {summary}")
    return "\n".join(lines)


def output(data, json_mode: bool = False) -> None:
    """Print data in requested format to stdout."""
    if json_mode:
        print(fmt_json(data))
    elif isinstance(data, list):
        print(fmt_human_sessions(data))
    elif isinstance(data, dict) and "sessions" in data:
        print(fmt_human_sessions(data["sessions"]))
    else:
        print(fmt_json(data))
