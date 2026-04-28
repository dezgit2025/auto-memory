# Deploy auto-memory

auto-memory is a zero-dependency Python CLI that queries `~/.copilot/session-store.db` for progressive session recall. Install it once, wire it into Copilot CLI instructions, and every future agent session starts with full context.

> **This guide installs auto-memory v0.2.0+**

## Prerequisites

Verify these before proceeding. Stop and report if any fail.

```bash
python3 --version   # must be 3.10+
copilot --version   # Copilot CLI must be installed
```

One of these package managers must be available (checked in priority order):

```bash
uv --version     # preferred
pipx --version   # fallback 1
pip --version     # fallback 2
```

### Windows (WSL2) — Enable the Session Store

On Windows 11 + WSL2, Copilot CLI does not create `session-store.db` by default. You must enable the experimental session store first.

1. Start a Copilot CLI session:

```bash
copilot
```

2. Inside the session, run the slash command:

```
/experimental
```

3. Select **SESSION_STORE** to enable it. This turns on:
   - SQLite-based session store for cross-session history
   - File tracking and full-text search

4. Exit and verify:

```bash
ls ~/.copilot/session-store.db
```

The file should now exist. If not, start and complete one full Copilot CLI session, then check again.

> **This is a one-time setup.** Once enabled, the session store persists across all future sessions.

## Install

### Step 1 — Clone or navigate to the repo

If the repo is not already local, clone it:

```bash
git clone <auto-memory-repo-url>
cd auto-memory
```

If already local, `cd` into the repo root.

### Step 2 — Install the CLI

Run the first command that succeeds. Stop after one succeeds.

```bash
# Preferred — uv
uv tool install --force --editable .

# Fallback 1 — pipx
pipx install --force -e .

# Fallback 2 — pip
python3 -m pip install --user --force-reinstall -e .
```

### Step 3 — Verify install

Run both commands. Both must succeed.

```bash
which session-recall
session-recall schema-check
```

If `which session-recall` returns nothing, see Troubleshooting below.

## Upgrading from v0.1.0

If already installed, upgrade with the same tool you used to install:

```bash
# PyPI install
pip install --upgrade auto-memory

# Editable install (from repo root)
git pull origin main
pip install -e .

# Or re-run install.sh
./install.sh
```

Verify upgrade:
```bash
python3 -c "from session_recall import __version__; print(__version__)"
# Should print: 0.2.0
```

## Agent Integration — Add to Copilot Instructions

This step wires auto-memory into every future agent session by appending instructions to `~/.copilot/copilot-instructions.md`.

### Step 1 — Ensure the file exists

```bash
mkdir -p ~/.copilot
touch ~/.copilot/copilot-instructions.md
```

### Step 2 — Check for duplicates

Search `~/.copilot/copilot-instructions.md` for the string `Progressive Session Recall`. If it already exists, **skip Step 3 entirely** — the block is already present.

### Step 3 — Append the instruction block

Append this exact block to the end of `~/.copilot/copilot-instructions.md`:

````markdown
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
````

## Verify Installation

Run all three checks. All must pass.

```bash
session-recall health          # all dimensions should show GREEN
session-recall list --json     # should return at least one session
session-recall schema-check    # must exit 0
```

If `session-recall list --json` returns zero sessions, that is normal on a fresh install — Copilot CLI needs at least one completed session first.

## Multi-Storage Configuration (Optional)

By default, session-recall only reads from Copilot CLI's SQLite database. To also recall sessions from VS Code, JetBrains, or Neovim:

```bash
export SESSION_RECALL_ENABLE_FILE_BACKENDS=1
```

Add this to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.) to persist it.

### Provider paths (auto-detected)

| Provider | Platform | Path |
|----------|----------|------|
| VS Code | Linux | `~/.config/Code/User/workspaceStorage` |
| VS Code | macOS | `~/Library/Application Support/Code/User/workspaceStorage` |
| VS Code | WSL | `~/.vscode-server/data/User/workspaceStorage` |
| JetBrains | Linux/macOS | `~/.config/JetBrains/` + `~/.config/github-copilot` |
| Neovim | Linux/macOS | `~/.local/share/nvim/` + `~/.config/github-copilot` |

Override any path: `SESSION_RECALL_VSCODE_STORAGE=/custom/path`

### Lookback defaults

| Provider type | Default lookback | Override |
|--------------|-----------------|---------|
| SQLite (Copilot CLI) | 30 days | `--days N` |
| JSONL/file backends | 5 days | `--days N` or `SESSION_RECALL_JSONL_DAYS=N` |

### Trust model

File-backed content is marked `_trust_level: "untrusted_third_party"` and wrapped in sentinel fences. Copilot CLI content is `_trust_level: "trusted_first_party"`.

## Troubleshooting

### `error: database not found` (Windows/WSL2)

Copilot CLI has not created the session store database yet. On WSL2, this requires enabling an experimental feature:

1. Run `copilot` to start a session
2. Run `/experimental` inside the session
3. Enable **SESSION_STORE**
4. Complete at least one session, then verify:

```bash
ls ~/.copilot/session-store.db
```

If the file still doesn't exist after enabling, try starting a new Copilot CLI session — the database is created on first use after enabling.

### `command not found: session-recall`

PATH issue. Check that `~/.local/bin` is on PATH:

```bash
echo "$PATH" | tr ':' '\n' | grep -q '.local/bin' && echo "OK" || echo "MISSING"
```

If missing, add it and retry:

```bash
export PATH="$HOME/.local/bin:$PATH"
which session-recall
```

If still not found, re-run install with `uv tool install --force --editable .` from the repo root.

### `schema-check` fails (exit code 2)

The Copilot CLI DB schema has drifted from what session-recall expects. This usually happens after a Copilot CLI upgrade. See [UPGRADE-COPILOT-CLI.md](../UPGRADE-COPILOT-CLI.md) for the full procedure.

### No sessions found

Normal on first use. Copilot CLI needs at least one completed session before session-recall has anything to query. Run a Copilot CLI session, then retry.

## Upgrading Copilot CLI

After any Copilot CLI upgrade, run:

```bash
session-recall schema-check
```

If it exits 0, no action needed. If it fails, follow the full upgrade procedure in [UPGRADE-COPILOT-CLI.md](../UPGRADE-COPILOT-CLI.md).
