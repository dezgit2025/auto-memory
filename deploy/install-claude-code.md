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

**Searching past sessions:**
```
session-recall-cc search "natural language phrase"   # FTS5 full-text
session-recall-cc files                              # files touched recently
session-recall-cc show <session-id>                  # full transcript
```

> **Query tips:** Multi-word natural-language phrases work well. Avoid hyphens / dots in single-token searches — FTS5 splits on them. Prefer `search "session recall"` over `search "session-recall"`. For exact filenames, use `files | grep <name>` instead of `search`.

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

## Section 7 — Optional: Pre-Warm Scheduler

> [!NOTE]
> **Most users can skip this section.** The CLI does on-demand mtime-incremental indexing on every invocation, so cold-start cost is ~50ms after the first run. Pre-warming is only worth setting up if you call recall 20+ times/min or want consistent sub-100ms latency on the very first call after waking your laptop.

### Agent decision tree

> **Agent:** follow this flow to install the sidecar:
>
> 1. **Ask user:** *"Set up a background scheduler to pre-warm the session-recall-cc index? (Y/n)"* — if no, skip this section entirely.
> 2. **Detect OS:** `uname -s` → `Darwin` (macOS), `Linux`, or `MINGW`/`MSYS` (Windows)
> 3. **Check for repo clone:** `test -f scripts/install-claude-sidecar.sh`
>    - **If repo clone exists** → run `bash scripts/install-claude-sidecar.sh --install` (auto-detects OS, idempotent, supports `--dry-run`)
>    - **If pip-only install** → follow the manual snippets below: §7a (macOS), §7b (Linux), or §7c (Windows)
> 4. **Always ask user before writing** any plist, crontab, or scheduled task.
> 5. **Verify:** confirm the scheduler is running with `bash scripts/install-claude-sidecar.sh --status` or the manual verify commands in each section.

Pick **one** of the paths below. All call the same Python module (`session_recall.providers.claude_code.sidecar --once`), which:

1. Scans `~/.claude/projects/*/*.jsonl`
2. Re-parses any file whose mtime is newer than the last index
3. Upserts into `~/.claude/.sr-index.db` (single SQLite transaction)
4. Exits cleanly — no daemon, no long-running process

### §7-quickstart — Automated installer (recommended)

Instead of hand-editing crontab or writing plist files, run the installer script:

```bash
bash scripts/install-claude-sidecar.sh --install        # auto-detects OS
bash scripts/install-claude-sidecar.sh --status         # check state
bash scripts/install-claude-sidecar.sh --uninstall      # remove
```

The script picks **launchd on macOS**, **cron on Linux**, and prints a Windows hint when run on Windows. It is idempotent and supports a `--dry-run` flag for previewing changes.

> **Agent:** if the user has cloned the repo, prefer the installer over §7a/§7b/§7c manual snippets. If they only `pip install`'d (no repo checkout), fall back to the manual sections below.

### §7a — macOS: launchd (recommended for Mac)

The Apple-blessed scheduler. Survives sleep/wake, auto-runs at login, integrates with `launchctl`.

> **Agent:** ask user *"Install launchd agent to pre-warm session-recall-cc every 5 minutes? (Y/n)"*

```bash
PYTHON3="$(command -v python3)"            # capture full path — launchd has no PATH inheritance
USER_HOME="$HOME"
PLIST="$USER_HOME/Library/LaunchAgents/com.session-recall-cc.sidecar.plist"
mkdir -p "$USER_HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.session-recall-cc.sidecar</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>-m</string>
        <string>session_recall.providers.claude_code.sidecar</string>
        <string>--once</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>SESSION_RECALL_ENABLE_CLAUDE_BACKEND</key>
        <string>1</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$USER_HOME/.claude/.sr-sidecar.log</string>
    <key>StandardErrorPath</key>
    <string>$USER_HOME/.claude/.sr-sidecar.err.log</string>
    <key>WorkingDirectory</key>
    <string>$USER_HOME</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST"                          # validate plist syntax
launchctl unload "$PLIST" 2>/dev/null          # idempotent (no-op if not loaded)
launchctl load -w "$PLIST"                     # -w persists across reboots
launchctl list | grep session-recall-cc        # confirm registration
sleep 3 && tail -3 ~/.claude/.sr-sidecar.log   # confirm first run output
```

**Verify it ran:** `tail ~/.claude/.sr-sidecar.log` should show `indexed=N skipped=M errors=0`.

**Uninstall:**
```bash
launchctl unload -w ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist
rm ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist
rm -f ~/.claude/.sr-sidecar.log ~/.claude/.sr-sidecar.err.log
```

> [!TIP]
> The `Label` (`com.session-recall-cc.sidecar`) is the canonical handle. To change the interval, edit `StartInterval` (seconds) and `launchctl unload && launchctl load -w` again.

### §7b — Linux: cron

> **Agent:** ask user *"Add cron job to pre-warm session-recall-cc every 5 minutes? (Y/n)"*

```bash
PYTHON3="$(command -v python3)"
(crontab -l 2>/dev/null; echo "*/5 * * * * env SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 $PYTHON3 -m session_recall.providers.claude_code.sidecar --once >> ~/.claude/.sr-sidecar.log 2>&1") | crontab -
crontab -l | grep session_recall    # confirm
```

**Uninstall:**
```bash
crontab -l | grep -v 'session_recall.providers.claude_code.sidecar' | crontab -
rm -f ~/.claude/.sr-sidecar.log
```

> [!NOTE]
> macOS users **can** use cron instead of launchd — it still ships and works. Apple just won't add features to it. We recommend launchd on Mac for sleep/wake handling and clean `launchctl` integration, but cron is fine if you prefer it.

### §7c — Windows: Task Scheduler (native) or WSL cron

**Native (PowerShell, run as your user — no admin needed):**

> **Agent:** ask user *"Register Windows Scheduled Task to pre-warm session-recall-cc every 5 minutes? (Y/n)"*

```powershell
$python = (Get-Command python).Source
$action = New-ScheduledTaskAction -Execute $python `
  -Argument "-m session_recall.providers.claude_code.sidecar --once"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5)
$env = @{ "SESSION_RECALL_ENABLE_CLAUDE_BACKEND" = "1" }
Register-ScheduledTask -TaskName "session-recall-cc-sidecar" `
  -Action $action -Trigger $trigger -Description "Pre-warm Claude Code session index"
```

**Uninstall:** `Unregister-ScheduledTask -TaskName "session-recall-cc-sidecar" -Confirm:$false`

**WSL2 alternative (if you already use WSL):** follow §7b inside WSL. One gotcha — the cron daemon doesn't auto-start in WSL, so add this to your `~/.bashrc`:
```bash
service cron status >/dev/null 2>&1 || sudo service cron start
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

3. **Remove pre-warm scheduler** (if added — pick the one you installed):
   ```bash
   # macOS launchd:
   launchctl unload -w ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist 2>/dev/null
   rm -f ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist

   # Linux / WSL cron:
   crontab -l 2>/dev/null | grep -v 'session_recall.providers.claude_code.sidecar' | crontab -

   # Windows Task Scheduler (PowerShell):
   #   Unregister-ScheduledTask -TaskName "session-recall-cc-sidecar" -Confirm:$false

   # Logs (any OS):
   rm -f ~/.claude/.sr-sidecar.log ~/.claude/.sr-sidecar.err.log
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
