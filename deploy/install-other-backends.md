---
purpose: Agent-runnable guide to enable session-recall file-backed backends (VS Code, JetBrains, Neovim)
audience: AI coding agents (Copilot CLI, Claude Code, Cursor, Aider) acting on behalf of users
requires-user-confirmation: true
read-only-detection: true
mutates-shell-rc: true
estimated-time: 2 minutes
---

# Enable Other Backends for session-recall

By default, `session-recall` reads only from Copilot CLI's SQLite database. This guide enables **file-backed providers** so it can also recall sessions from **VS Code**, **JetBrains**, and **Neovim**.

**Humans:** skim the decision table below, then run the shell snippets manually — or ask your AI agent to do it for you.

**Agents:** read this file top-to-bottom and execute each section in order. Every write to the user's shell config **requires explicit user confirmation** — never write silently.

---

## Section 1 — Detect Available Editors

Run these read-only checks to discover which editors the user has. Do NOT modify anything.

### macOS

```bash
# VS Code (macOS)
test -d "$HOME/Library/Application Support/Code/User/workspaceStorage" && echo "vscode: detected (macOS standard)"

# JetBrains (macOS)
test -d "$HOME/.config/github-copilot" && echo "jetbrains: detected"

# Neovim (macOS)
test -d "$HOME/.local/share/nvim" && echo "neovim: detected"
```

### Linux (standard)

```bash
# VS Code (Linux standard)
test -d "$HOME/.config/Code/User/workspaceStorage" && echo "vscode: detected (Linux standard)"

# VS Code (Flatpak)
test -d "$HOME/.var/app/com.visualstudio.code/config/Code/User/workspaceStorage" && echo "vscode: detected (Flatpak)"

# VS Code (Snap)
test -d "$HOME/snap/code/current/.config/Code/User/workspaceStorage" && echo "vscode: detected (Snap)"

# JetBrains (Linux)
test -d "$HOME/.config/github-copilot" && echo "jetbrains: detected"

# Neovim (Linux)
test -d "$HOME/.local/share/nvim" && echo "neovim: detected"
```

### WSL2

```bash
# VS Code (WSL2 remote server)
test -d "$HOME/.vscode-server/data/User/workspaceStorage" && echo "vscode: detected (WSL2)"
```

### After detection

> **Agent:** Report findings to the user: *"I detected [list]. Would you like to enable session-recall for these backends? [Y/n]"*
>
> If the user declines all, stop here. If the user wants a subset, skip the unwanted backends in Section 3.

---

## Section 2 — Detect User's Shell

Determine which shell config file to write environment variables to.

```bash
basename "$SHELL"
```

| Shell | Config file | Export syntax |
|-------|------------|-------------|
| `zsh` | `~/.zshenv` | `export VAR=value` |
| `bash` | `~/.bashrc` | `export VAR=value` |
| `fish` | `~/.config/fish/config.fish` | `set -gx VAR value` |

**Why `~/.zshenv` instead of `~/.zshrc`?** `.zshenv` is loaded for ALL zsh invocations — including non-interactive shells (cron, launchd, scripts). `.zshrc` only loads for interactive terminals. Since `session-recall` may be called from agent hooks or automation, `.zshenv` ensures the env vars are always available.

> **Agent:** Tell the user: *"Your shell is [detected shell]. I'll write environment variables to [config file]. OK? [Y/n]"*
>
> If the user prefers a different file, use their choice.

Store the detected config file path — you'll reference it as `SHELL_RC` in Section 3.

---

## Section 3 — Enable Backends

### Important: Trust Warning (show BEFORE any backend enable)

> ⚠️ **Trust model notice**
>
> Sessions from VS Code, JetBrains, and Neovim are marked `_trust_level: "untrusted_third_party"`. Their content is wrapped in `<<UNTRUSTED-FILE-BACKED-CONTENT>>` sentinel fences. This means:
> - Downstream agents should treat this content as third-party data
> - The fences help agents distinguish first-party (Copilot CLI) from third-party sessions
> - This is a security feature, not a limitation
>
> Copilot CLI sessions remain `_trust_level: "trusted_first_party"` (no fences).

> **Agent:** Display the trust warning above verbatim. Then ask: *"Understood — proceed with enabling file backends? [Y/n]"*

---

### 3.1 — Master Enable Flag

This single flag activates ALL file-backed providers. It only needs to be set once regardless of how many backends you enable.

> **Agent:** Ask the user: *"I'll add `SESSION_RECALL_ENABLE_FILE_BACKENDS=1` to [SHELL_RC]. This enables session-recall to discover VS Code, JetBrains, and Neovim sessions. OK? [Y/n]"*

#### zsh (`~/.zshenv`)

```bash
LINE='export SESSION_RECALL_ENABLE_FILE_BACKENDS=1  # session-recall: file backends'
grep -qF 'SESSION_RECALL_ENABLE_FILE_BACKENDS' ~/.zshenv 2>/dev/null || echo "$LINE" >> ~/.zshenv
```

#### bash (`~/.bashrc`)

```bash
LINE='export SESSION_RECALL_ENABLE_FILE_BACKENDS=1  # session-recall: file backends'
grep -qF 'SESSION_RECALL_ENABLE_FILE_BACKENDS' ~/.bashrc 2>/dev/null || echo "$LINE" >> ~/.bashrc
```

#### fish (`~/.config/fish/config.fish`)

```bash
grep -qF 'SESSION_RECALL_ENABLE_FILE_BACKENDS' ~/.config/fish/config.fish 2>/dev/null || echo 'set -gx SESSION_RECALL_ENABLE_FILE_BACKENDS 1  # session-recall: file backends' >> ~/.config/fish/config.fish
```

After writing, source the config:

```bash
# zsh
source ~/.zshenv

# bash
source ~/.bashrc

# fish
source ~/.config/fish/config.fish
```

---

### 3.2 — VS Code Backend

**What this does:** Enables session-recall to read Copilot chat sessions stored by VS Code at `**/chatSessions/*.jsonl` under the workspace storage directory.

#### Verify VS Code sessions exist

```bash
# macOS
ls "$HOME/Library/Application Support/Code/User/workspaceStorage/"*/chatSessions/*.jsonl 2>/dev/null | head -3

# Linux
ls "$HOME/.config/Code/User/workspaceStorage/"*/chatSessions/*.jsonl 2>/dev/null | head -3

# WSL2
ls "$HOME/.vscode-server/data/User/workspaceStorage/"*/chatSessions/*.jsonl 2>/dev/null | head -3
```

- ✅ Files listed → VS Code sessions exist. Continue to verification.
- ❌ No files found → check these possibilities:
  1. **No Copilot chat sessions yet.** Open VS Code, start a Copilot chat, then retry.
  2. **Non-standard install (Flatpak/Snap/custom).** Ask user for their VS Code data path and set the override below.

#### Optional: Custom path override

Only needed if auto-detection fails (Flatpak, Snap, portable installs, VS Code Insiders).

> **Agent:** Ask: *"VS Code auto-detection didn't find sessions. What's your VS Code workspace storage path? (e.g., `~/.var/app/com.visualstudio.code/config/Code/User/workspaceStorage`)"*

##### zsh

```bash
LINE='export SESSION_RECALL_VSCODE_STORAGE="/path/to/workspaceStorage"  # session-recall: vscode override'
grep -qF 'SESSION_RECALL_VSCODE_STORAGE' ~/.zshenv 2>/dev/null || echo "$LINE" >> ~/.zshenv
```

##### bash

```bash
LINE='export SESSION_RECALL_VSCODE_STORAGE="/path/to/workspaceStorage"  # session-recall: vscode override'
grep -qF 'SESSION_RECALL_VSCODE_STORAGE' ~/.bashrc 2>/dev/null || echo "$LINE" >> ~/.bashrc
```

##### fish

```bash
grep -qF 'SESSION_RECALL_VSCODE_STORAGE' ~/.config/fish/config.fish 2>/dev/null || echo 'set -gx SESSION_RECALL_VSCODE_STORAGE "/path/to/workspaceStorage"  # session-recall: vscode override' >> ~/.config/fish/config.fish
```

> **Agent:** Replace `/path/to/workspaceStorage` with the user's actual path before writing.

#### Verify VS Code backend

```bash
session-recall health --provider vscode --json
```

- ✅ JSON with `providers.vscode.dimensions` showing 4 sub-checks → VS Code backend is working
- ❌ Error or all RED zones → see [Troubleshooting](#section-4--troubleshooting)

---

### 3.3 — JetBrains Backend

**What this does:** Enables session-recall to read Copilot chat sessions from JetBrains IDEs (IntelliJ, PyCharm, WebStorm, etc.) stored under `~/.config/github-copilot/`.

#### Verify JetBrains sessions exist

```bash
ls "$HOME/.config/github-copilot/chat-sessions/"* 2>/dev/null | head -3
ls "$HOME/.config/github-copilot/chat-agent-sessions/"* 2>/dev/null | head -3
```

- ✅ Files listed → JetBrains sessions exist. Continue to verification.
- ❌ No files → open a JetBrains IDE, use Copilot chat, then retry.

#### Optional: Custom path override

> **Agent:** Only if auto-detection fails. Ask: *"What's your JetBrains Copilot config path?"*

##### zsh

```bash
LINE='export SESSION_RECALL_JETBRAINS_ROOT="/path/to/github-copilot"  # session-recall: jetbrains override'
grep -qF 'SESSION_RECALL_JETBRAINS_ROOT' ~/.zshenv 2>/dev/null || echo "$LINE" >> ~/.zshenv
```

##### bash

```bash
LINE='export SESSION_RECALL_JETBRAINS_ROOT="/path/to/github-copilot"  # session-recall: jetbrains override'
grep -qF 'SESSION_RECALL_JETBRAINS_ROOT' ~/.bashrc 2>/dev/null || echo "$LINE" >> ~/.bashrc
```

##### fish

```bash
grep -qF 'SESSION_RECALL_JETBRAINS_ROOT' ~/.config/fish/config.fish 2>/dev/null || echo 'set -gx SESSION_RECALL_JETBRAINS_ROOT "/path/to/github-copilot"  # session-recall: jetbrains override' >> ~/.config/fish/config.fish
```

#### Verify JetBrains backend

```bash
session-recall health --provider jetbrains --json
```

---

### 3.4 — Neovim Backend

**What this does:** Enables session-recall to read Copilot chat sessions from Neovim stored under `~/.config/github-copilot/` and `~/.local/share/nvim/`.

#### Verify Neovim sessions exist

```bash
find "$HOME/.local/share/nvim" -name "*chat*.json" -o -name "*chat*.jsonl" 2>/dev/null | head -3
find "$HOME/.config/github-copilot" -name "*chat*.json" -o -name "*chat*.jsonl" 2>/dev/null | head -3
```

- ✅ Files listed → Neovim sessions exist. Continue to verification.
- ❌ No files → open Neovim, use Copilot chat, then retry.

#### Optional: Custom path override

##### zsh

```bash
LINE='export SESSION_RECALL_NEOVIM_ROOT="/path/to/nvim-data"  # session-recall: neovim override'
grep -qF 'SESSION_RECALL_NEOVIM_ROOT' ~/.zshenv 2>/dev/null || echo "$LINE" >> ~/.zshenv
```

##### bash

```bash
LINE='export SESSION_RECALL_NEOVIM_ROOT="/path/to/nvim-data"  # session-recall: neovim override'
grep -qF 'SESSION_RECALL_NEOVIM_ROOT' ~/.bashrc 2>/dev/null || echo "$LINE" >> ~/.bashrc
```

##### fish

```bash
grep -qF 'SESSION_RECALL_NEOVIM_ROOT' ~/.config/fish/config.fish 2>/dev/null || echo 'set -gx SESSION_RECALL_NEOVIM_ROOT "/path/to/nvim-data"  # session-recall: neovim override' >> ~/.config/fish/config.fish
```

#### Verify Neovim backend

```bash
session-recall health --provider neovim --json
```

---

### 3.5 — Optional: Change Lookback Window

File-backed providers default to a **5-day lookback** (vs 30 days for Copilot CLI SQLite). To increase it:

> **Agent:** Ask: *"File backends default to 5-day lookback. Would you like to change it? (e.g., 14 for two weeks, or keep default)"*

If the user wants a custom value:

#### zsh

```bash
LINE='export SESSION_RECALL_JSONL_DAYS=14  # session-recall: file backend lookback days'
grep -qF 'SESSION_RECALL_JSONL_DAYS' ~/.zshenv 2>/dev/null || echo "$LINE" >> ~/.zshenv
```

#### bash

```bash
LINE='export SESSION_RECALL_JSONL_DAYS=14  # session-recall: file backend lookback days'
grep -qF 'SESSION_RECALL_JSONL_DAYS' ~/.bashrc 2>/dev/null || echo "$LINE" >> ~/.bashrc
```

#### fish

```bash
grep -qF 'SESSION_RECALL_JSONL_DAYS' ~/.config/fish/config.fish 2>/dev/null || echo 'set -gx SESSION_RECALL_JSONL_DAYS 14  # session-recall: file backend lookback days' >> ~/.config/fish/config.fish
```

> **Agent:** Replace `14` with the user's chosen value.

---

## Section 4 — Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `session-recall list --provider vscode` returns 0 sessions | No Copilot chat sessions created yet | Open VS Code → start a Copilot chat conversation → retry |
| Provider not listed in `session-recall list --provider all` | `SESSION_RECALL_ENABLE_FILE_BACKENDS` not set or not sourced | Verify: `echo $SESSION_RECALL_ENABLE_FILE_BACKENDS` should print `1`. If blank, source your shell rc or open a new terminal. |
| VS Code sessions not found (macOS) | VS Code installed but no chat history at expected path | Run: `find "$HOME/Library/Application Support/Code" -name "*.jsonl" -path "*/chatSessions/*" 2>/dev/null \| head -3` — if empty, no chat sessions exist yet |
| VS Code Flatpak/Snap not auto-detected | Auto-detect only checks standard paths | Set `SESSION_RECALL_VSCODE_STORAGE` to the actual path (see §3.2) |
| JetBrains and Neovim show the same sessions | Both read from `~/.config/github-copilot/` | Expected behavior — use `--provider jetbrains` or `--provider neovim` to isolate |
| Sessions appear but content is empty | Permission denied on JSONL files | Check: `ls -la` on the session files. Ensure your user owns them. |
| Env var set but not picked up | Shell rc not sourced in current session | Run `exec $SHELL -l` or open a new terminal window |
| `session-recall` command not found | Tool not installed or not on PATH | Run: `pip install auto-memory` (or `pipx install auto-memory`) |

---

## Section 5 — Rollback

To disable file backends and remove all env vars added by this guide:

### zsh

```bash
sed -i.bak '/# session-recall: file backends/d' ~/.zshenv
sed -i.bak '/# session-recall: vscode override/d' ~/.zshenv
sed -i.bak '/# session-recall: jetbrains override/d' ~/.zshenv
sed -i.bak '/# session-recall: neovim override/d' ~/.zshenv
sed -i.bak '/# session-recall: file backend lookback days/d' ~/.zshenv
source ~/.zshenv
```

### bash

```bash
sed -i.bak '/# session-recall: file backends/d' ~/.bashrc
sed -i.bak '/# session-recall: vscode override/d' ~/.bashrc
sed -i.bak '/# session-recall: jetbrains override/d' ~/.bashrc
sed -i.bak '/# session-recall: neovim override/d' ~/.bashrc
sed -i.bak '/# session-recall: file backend lookback days/d' ~/.bashrc
source ~/.bashrc
```

### fish

```bash
sed -i.bak '/# session-recall: file backends/d' ~/.config/fish/config.fish
sed -i.bak '/# session-recall: vscode override/d' ~/.config/fish/config.fish
sed -i.bak '/# session-recall: jetbrains override/d' ~/.config/fish/config.fish
sed -i.bak '/# session-recall: neovim override/d' ~/.config/fish/config.fish
sed -i.bak '/# session-recall: file backend lookback days/d' ~/.config/fish/config.fish
source ~/.config/fish/config.fish
```

### Verify rollback

```bash
session-recall list --provider all --json --limit 1
```

Only the `cli` provider should appear in results. If VS Code/JetBrains/Neovim still show, open a new terminal and retry.

Clean up backup files:

```bash
rm -f ~/.zshenv.bak ~/.bashrc.bak ~/.config/fish/config.fish.bak
```

---

## Environment Variable Reference

Complete list of env vars used by session-recall backends.

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_RECALL_ENABLE_FILE_BACKENDS` | `0` (disabled) | Set to `1` to enable VS Code, JetBrains, and Neovim providers |
| `SESSION_RECALL_JSONL_DAYS` | `5` | Lookback window in days for file-backed providers |
| `SESSION_RECALL_VSCODE_STORAGE` | auto-detected | Override VS Code workspace storage path |
| `SESSION_RECALL_JETBRAINS_ROOT` | auto-detected | Override JetBrains Copilot config path |
| `SESSION_RECALL_NEOVIM_ROOT` | auto-detected | Override Neovim data path |
| `SESSION_RECALL_DB` | `~/.copilot/session-store.db` | Override Copilot CLI SQLite path (not file-backend specific) |
| `SESSION_RECALL_CLI_STATE_ROOT` | `~/.copilot/session-state` | Override Copilot CLI JSONL state dir (not file-backend specific) |

### Auto-detected Paths

These are the paths session-recall checks automatically when `SESSION_RECALL_ENABLE_FILE_BACKENDS=1`:

**VS Code:**

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/Code/User/workspaceStorage/` |
| Linux | `~/.config/Code/User/workspaceStorage/` |
| Linux (Flatpak) | `~/.var/app/com.visualstudio.code/config/Code/User/workspaceStorage/` |
| Linux (Snap) | `~/snap/code/current/.config/Code/User/workspaceStorage/` |
| WSL2 | `~/.vscode-server/data/User/workspaceStorage/` |

**JetBrains:**

| Platform | Path |
|----------|------|
| All | `~/.config/github-copilot/` |

**Neovim:**

| Platform | Path |
|----------|------|
| All (primary) | `~/.config/github-copilot/` |
| All (secondary) | `~/.local/share/nvim/` |

---

## Backend Capability Comparison

Not all backends provide the same data. Copilot CLI's SQLite database is the richest source.

| Feature | Copilot CLI (SQLite) | VS Code | JetBrains | Neovim |
|---------|---------------------|---------|-----------|--------|
| Session listing | ✅ | ✅ | ✅ | ✅ |
| Full-text search | ✅ FTS5 | ✅ line scan | ✅ line scan | ✅ line scan |
| Recent files | ✅ | ❌ | ❌ | ❌ |
| Checkpoints | ✅ | ❌ | ❌ | ❌ |
| Default lookback | 30 days | 5 days | 5 days | 5 days |
| Trust level | ✅ first-party | ⚠️ third-party | ⚠️ third-party | ⚠️ third-party |
| Always enabled | ✅ | 🟡 opt-in | 🟡 opt-in | 🟡 opt-in |
