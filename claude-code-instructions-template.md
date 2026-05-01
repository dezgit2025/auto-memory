# auto-memory — Claude Code Instructions Template

> **Note:** For installation, use [`deploy/install.md`](deploy/install.md) — it handles everything including appending this template automatically.

This file contains the raw instruction block for manual reference. Copy the block below into `~/.claude/CLAUDE.md` or your project's `.claude/CLAUDE.md` if you prefer manual setup.

---

<!-- session-recall:v1 — DO NOT EDIT MANUALLY -->
## Progressive Session Recall — RUN FIRST ON EVERY PROMPT

**Run `session-recall` FIRST on every prompt before doing anything else.** It costs ~50 tokens and prevents expensive blind searches.

```bash
session-recall files --json --limit 10  # recently touched files
session-recall files --days 7 --json    # files touched in last 7 days
session-recall list --json --limit 5    # recent sessions
session-recall list --days 2 --json     # sessions from last 2 days
session-recall search '<term>' --json   # full-text search
session-recall search '<term>' --days 5 # search last 5 days only
session-recall checkpoints --days 3     # checkpoints from last 3 days
session-recall repos --json             # discovered repositories across providers
session-recall show <id> --json         # drill into one session
session-recall health --json            # 8-dimension health check
session-recall schema-check             # validate DB schema (run after Copilot CLI upgrade)
```

**`--days N` works on all 4 query commands** (`list`, `files`, `checkpoints`, `search`) — filters to sessions/files/checkpoints from the last N days.

Only use filesystem tools (grep, glob, find) if session-recall returns nothing useful.
If `session-recall` errors, continue silently — it's a convenience, not a blocker.
<!-- /session-recall:v1 -->
