"""Claude Code file-backed session provider.

Walks ``~/.claude/projects/<slug>/<session-uuid>.jsonl`` — one file per
session, written by the Claude Code CLI as it runs. Each line is a JSON
event with ``type`` (user / assistant / tool_use / tool_result), ``message``,
and ``timestamp`` fields, matching the heuristics in
``_parse_helpers._extract_role`` / ``_extract_text`` already used by the
VS Code / JetBrains / Neovim providers.

Subagent transcripts (``<slug>/subagents/agent-*.jsonl``) are intentionally
skipped — they're per-tool-call children of the parent session, not
recall-worthy in their own right.
"""

from __future__ import annotations

from pathlib import Path

from ._base import _FileSessionProvider


class ClaudeCodeProvider(_FileSessionProvider):
    provider_name = "Claude Code"

    def __init__(self, root_override: str | None = None) -> None:
        home = Path.home()
        if root_override:
            roots = [Path(root_override).expanduser()]
        else:
            roots = [home / ".claude" / "projects"]
        super().__init__("claude_code", roots, ["*/*.jsonl"])
