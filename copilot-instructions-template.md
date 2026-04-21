# auto-memory — Copilot CLI Integration Template

Copy the block below into your Copilot CLI instruction file:

- **User-level (recommended):** `~/.copilot/copilot-instructions.md`
- **Repo-level:** `.github/copilot-instructions.md`

---

## Progressive Session Recall — RUN FIRST ON EVERY PROMPT

**Run `auto-memory` FIRST on every prompt before doing anything else.** It costs ~50 tokens and prevents expensive blind searches.

```bash
auto-memory files --json --limit 10  # recently touched files
auto-memory files --days 7 --json    # files touched in last 7 days
auto-memory list --json --limit 5    # recent sessions
auto-memory list --days 2 --json     # sessions from last 2 days
auto-memory search '<term>' --json   # full-text search
auto-memory search '<term>' --days 5 # search last 5 days only
auto-memory checkpoints --days 3     # checkpoints from last 3 days
auto-memory show <id> --json         # drill into one session
auto-memory health --json            # 8-dimension health check
auto-memory schema-check             # validate DB schema (run after Copilot CLI upgrade)
```

**`--days N` works on all 4 query commands** (`list`, `files`, `checkpoints`, `search`) — filters to sessions/files/checkpoints from the last N days.

Only use filesystem tools (grep, glob, find) if auto-memory returns nothing useful.
If `auto-memory` errors, continue silently — it's a convenience, not a blocker.
