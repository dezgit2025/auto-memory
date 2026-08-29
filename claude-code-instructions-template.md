# auto-memory — Claude Code Instructions Template

> **Note:** For installation, use [`deploy/install-claude-code.md`](deploy/install-claude-code.md) — it handles everything including appending this template automatically.

This file contains the raw instruction block for manual reference. Copy the block below into `~/.claude/CLAUDE.md` (global) or your project's `CLAUDE.md` (per-repo) if you prefer manual setup.

**This is the Claude Code–specific block.** It uses `session-recall-cc`, which reads Claude Code's own JSONL session transcripts (`~/.claude/projects/`) via a dedicated SQLite+FTS5 index — not the plain `session-recall` command, which reads Copilot CLI's session store instead. If your `CLAUDE.md` also contains the generic `session-recall` block (e.g. from [`copilot-instructions-template.md`](copilot-instructions-template.md) or `deploy/install.md`), make sure that block is gated to skip itself for Claude Code — see [`deploy/install-claude-code.md`](deploy/install-claude-code.md) for details.

Requires `auto-memory[claude]` installed and `SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1` set.

---

<!-- session-recall-cc:v1 START -->
**For Claude Code only** — if you are not Claude Code (e.g., Copilot CLI, Cursor, Aider), ignore this section.

When starting a new conversation in this repo, run:
```
session-recall-cc list --json --limit 5
```
Use the output to ground your understanding of recent work.

**Searching past sessions:**
```
session-recall-cc search "natural language phrase"   # FTS5 full-text
session-recall-cc files                              # files touched recently
session-recall-cc show <session-id>                  # full transcript
```

> **Query tips:** Multi-word natural-language phrases work well. Avoid hyphens / dots in single-token searches — FTS5 splits on them. Prefer `search "session recall"` over `search "session-recall"`. For exact filenames, use `files | grep <name>` instead of `search`.

This requires `auto-memory[claude]` installed and `SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1` set.
<!-- session-recall-cc:v1 END -->
