---
requires-user-confirmation: true
mutates-agent-instructions: true
tool: session-recall-cc
version: v1
---

# Deploy session-recall-cc (Claude Code)

**Humans:** skim the overview, then run the snippets — or ask your AI agent to do it.
**Agents:** read sections 1–9 in order. Every mutating step requires user confirmation. Use a reasoning model (Sonnet 4.6, GPT-5.4) — mini models may skip confirmation gates.

```bash
pip install auto-memory[claude]
export SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1
session-recall-cc health
```

---

## Section 1 — Overview

`session-recall-cc` reads Claude Code's local JSONL session files (`~/.claude/projects/`), builds an FTS5 full-text index, and provides structured recall for AI coding agents.

- **Read-only** — never writes to Claude Code's session files
- **FTS5 index** — fast full-text search across all sessions
- **Structured output** — JSON for agent consumption, ~50 tokens per query
- **Self-gating** — instruction blocks are agent-conditional so only Claude Code acts on them

---

## Section 2 — Prerequisites

```bash
python3 --version                # must be 3.10+
command -v pip3 >/dev/null 2>&1 && echo "pip: detected" || echo "pip: not found"
test -d "$HOME/.claude" && echo "claude-code: detected" || echo "claude-code: not found"
```

> [!IMPORTANT]
> You need Python 3.10+ and pip. Claude Code must have been used at least once (so `~/.claude/` exists).

---

## Section 3 — Install

> **Agent:** ask user *"Install auto-memory with Claude Code support? (Y/n)"*

```bash
pip install auto-memory[claude]
export SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1
```

To persist the env var, add it to your shell config:

```bash
echo 'export SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1' >> ~/.zshrc   # or ~/.bashrc
```

---

## Section 4 — Verify

```bash
which session-recall-cc && session-recall-cc health
```

| Result | Meaning |
|--------|---------|
| **GREEN** | Done — Claude Code backend operational |
| **AMBER** | No sessions indexed yet (normal on first use) |
| **RED** | Something broken → see Section 9 |

If `which` returns nothing → ensure `~/.local/bin` is on your `PATH`.

---

## Section 5 — Wire into Claude Code (Per-Repo)

This is the **recommended** install — writes to the repo-local `CLAUDE.md`, safe to commit.

### 5a — Detect state

```bash
AGENT_FILE="CLAUDE.md"   # per-repo default
if grep -q '<!-- session-recall-cc:v1 START -->' "$AGENT_FILE" 2>/dev/null; then
  echo "current"   # idempotent — skip to Section 7
elif grep -q 'session-recall-cc' "$AGENT_FILE" 2>/dev/null; then
  echo "stale"     # upgrade → 5c
else
  echo "missing"   # append → 5b
fi
```

### 5b — Append (state = missing)

> **Agent:** ask user *"Append session-recall-cc instructions to CLAUDE.md? (Y/n)"*

Append this exact block:

````markdown
<!-- session-recall-cc:v1 START -->
**For Claude Code only** — if you are not Claude Code (e.g., Copilot CLI, Cursor, Aider), ignore this section.

When starting a new conversation in this repo, run:
```
session-recall-cc list --json --limit 5
```
Use the output to ground your understanding of recent work.

This requires `auto-memory[claude]` installed and `SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1` set.
<!-- session-recall-cc:v1 END -->
````

### 5c — Upgrade (state = stale)

> **Agent:** ask user *"Found existing session-recall-cc block. Replace with current version? (Y/n)"*

Replace everything between `<!-- session-recall-cc:v1 START -->` and `<!-- session-recall-cc:v1 END -->` (inclusive) with the block from 5b. The sentinel markers make this idempotent.

### 5d — Uninstall

Remove the sentinel block:

```bash
sed -i.bak '/<!-- session-recall-cc:v1 START -->/,/<!-- session-recall-cc:v1 END -->/d' CLAUDE.md
```

---

## Section 6 — Global Install (Optional)

For users who want `session-recall-cc` active in every repo, add the block from 5b to `~/.claude/CLAUDE.md`:

> **Agent:** ask user *"Install session-recall-cc globally to ~/.claude/CLAUDE.md? (Y/n)"*

```bash
mkdir -p "$HOME/.claude"
AGENT_FILE="$HOME/.claude/CLAUDE.md"
```

Then follow 5a–5b using `$AGENT_FILE`.

> [!WARNING]
> If you use a sync script (e.g., `sync-instructions.sh`) that copies `~/.claude/CLAUDE.md` to `~/.copilot/copilot-instructions.md`, the session-recall-cc block will propagate. Add this filter to your sync script:
> ```bash
> sed '/<!-- session-recall-cc:v1 START -->/,/<!-- session-recall-cc:v1 END -->/d'
> ```

---

## Section 7 — Optional: Cron Sidecar

For pre-warming the FTS5 index so queries are instant:

> **Agent:** ask user *"Add cron job to pre-warm the session-recall-cc index every 5 minutes? (Y/n)"*

```cron
*/5 * * * * env SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 python -m session_recall.providers.claude_code.sidecar --once >> ~/.claude/.sr-sidecar.log 2>&1
```

Add with:

```bash
(crontab -l 2>/dev/null; echo '*/5 * * * * env SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 python -m session_recall.providers.claude_code.sidecar --once >> ~/.claude/.sr-sidecar.log 2>&1') | crontab -
```

---

## Section 8 — Uninstall

1. **Remove sentinel block** from CLAUDE.md (per-repo and/or global):
   ```bash
   sed -i.bak '/<!-- session-recall-cc:v1 START -->/,/<!-- session-recall-cc:v1 END -->/d' CLAUDE.md
   sed -i.bak '/<!-- session-recall-cc:v1 START -->/,/<!-- session-recall-cc:v1 END -->/d' ~/.claude/CLAUDE.md
   ```

2. **Remove the FTS5 index:**
   ```bash
   rm ~/.claude/.sr-index.db
   ```

3. **Remove cron entry** (if added):
   ```bash
   crontab -l | grep -v 'session_recall.providers.claude_code.sidecar' | crontab -
   ```

4. **Uninstall the package** (if desired):
   ```bash
   pip uninstall auto-memory
   ```

---

## Section 9 — Cross-CLI Safety

The instruction block is designed to be safe across all AI coding agents:

- **Self-gating text** — "For Claude Code only" tells non-Claude agents to skip the block
- **Clean exit code 2** — if `SESSION_RECALL_ENABLE_CLAUDE_BACKEND` is not set, `session-recall-cc` exits with code 2 and a clear message. Other agents that accidentally invoke it get an informative error, not a crash.
- **Per-repo CLAUDE.md is safe to commit** — it self-gates on agent identity, so Copilot CLI, Cursor, and Aider will ignore it
- **Sync-script filter** — if you sync instruction files across agents, strip the block with:
  ```bash
  sed '/<!-- session-recall-cc:v1 START -->/,/<!-- session-recall-cc:v1 END -->/d'
  ```

> [!TIP]
> The sentinel markers (`<!-- session-recall-cc:v1 START/END -->`) enable idempotent install, upgrade, and uninstall. Never edit the markers manually.
