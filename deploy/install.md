---
purpose: Agent-runnable guide to install auto-memory and wire it into agent instruction files
audience: AI coding agents (Copilot CLI, Claude Code, Cursor, Aider) acting on behalf of users
requires-user-confirmation: true
read-only-detection: true
mutates-shell-rc: false
mutates-agent-instructions: true
mutates-system-binaries: true
estimated-time: 90 seconds
companion-file: deploy/install-other-backends.md
---

# Deploy auto-memory

**Humans:** skim the TL;DR, then run the snippets — or ask your AI agent to do it.
**Agents:** read sections 1–7 in order. Every mutating step requires user confirmation. Use a reasoning model (Sonnet 4.6, GPT-5.4) — mini models may skip confirmation gates.

```bash
uv tool install auto-memory && session-recall schema-check && session-recall health
# Then append the instruction block from Section 6 to your agent instructions file
```

---

## Section 1 — Detect Environment

All checks here are **read-only**. Do not modify anything.

```bash
python3 --version                # must be 3.10+
copilot --version 2>/dev/null && echo "copilot-cli: detected" || echo "copilot-cli: not found"
command -v code >/dev/null 2>&1 && echo "vscode: detected"
command -v nvim >/dev/null 2>&1 && echo "neovim: detected"
test -d "$HOME/.config/github-copilot" && echo "jetbrains: detected"
```

> **Agent:** If editors detected but no Copilot CLI, note: *"Consider file backends after install — see Section 8."*

### Existing install + version

```bash
INSTALL_PATH=$(command -v session-recall 2>/dev/null)
INSTALLED_VERSION=$(session-recall --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
if [ -z "$INSTALLED_VERSION" ]; then
  INSTALLED_VERSION=$(python3 -c "from session_recall import __version__; print(__version__)" 2>/dev/null)
fi
echo "path=${INSTALL_PATH:-none} version=${INSTALLED_VERSION:-unknown}"
```

### Package manager + shell

```bash
command -v uv   >/dev/null 2>&1 && PKG=uv   || \
command -v pipx >/dev/null 2>&1 && PKG=pipx || \
command -v pip3 >/dev/null 2>&1 && PKG=pip  || \
PKG=none
echo "pkg: $PKG  shell: $(basename "$SHELL")"
```

---

## Section 2 — Choose Install Path

```bash
LATEST="0.3.0"
if [ -z "$INSTALL_PATH" ]; then
  STATE="not-installed"
elif [ -z "$INSTALLED_VERSION" ]; then
  STATE="unknown-version"
elif [ "$INSTALLED_VERSION" = "$LATEST" ]; then
  STATE="current"
elif printf '%s\n' "$INSTALLED_VERSION" "$LATEST" | sort -V | head -1 | grep -qx "$INSTALLED_VERSION"; then
  STATE="outdated"
else
  STATE="current"
fi
# Detect editable/dev install
if [ -n "$INSTALL_PATH" ] && python3 -c "import session_recall; print(session_recall.__file__)" 2>/dev/null | grep -q "auto-memory"; then
  STATE="editable-dev"
fi
echo "state: $STATE"
```

| State | Action |
|-------|--------|
| `not-installed` | → **Section 3** |
| `current` | → **Section 6** (wire instructions) |
| `outdated` | → **Section 4** (upgrade) |
| `unknown-version` | → **Section 4** (treat as upgrade) |
| `editable-dev` | `git pull && pip install -e .` then → **Section 6** |

---

## Section 3 — Fresh Install

### 3a — From PyPI (recommended)

> **Agent:** ask user *"Install auto-memory from PyPI? (Y/n)"*

Run the **first** command that succeeds. Stop after first success.

```bash
uv tool install auto-memory              # preferred
pipx install auto-memory                 # fallback 1
python3 -m pip install --user auto-memory  # fallback 2
```

### 3b — From source (for contributors)

> **Agent:** ask user *"Install auto-memory from source (editable/dev mode)? (Y/n)"*

```bash
git clone https://github.com/dezgit2025/auto-memory.git && cd auto-memory
uv tool install --force --editable .       # or: pipx install --force -e .
```

### Verify

```bash
which session-recall && session-recall schema-check
```

If `which` returns nothing → see **Section 9**.

---

## Section 4 — Upgrade Existing Install

> **Agent:** ask user *"You're on v${INSTALLED_VERSION} — v${LATEST} is available. Upgrade? (Y/n)"*

Detect method and use the **matching** upgrade command (never mix tools):

```bash
if uv tool list 2>/dev/null | grep -q auto-memory; then
  uv tool upgrade auto-memory
elif pipx list 2>/dev/null | grep -q auto-memory; then
  pipx upgrade auto-memory
else
  python3 -m pip install --user --upgrade auto-memory
fi
```

Verify: `session-recall --version`

---

## Section 5 — WSL2 Session Store Prompt

**Skip on macOS and standard Linux.**

```bash
grep -qi microsoft /proc/version 2>/dev/null || { echo "not WSL2 — skip"; }
```

If WSL2 detected and `~/.copilot/session-store.db` does not exist:

> **Agent:** ask user *"WSL2 detected but no session store found. Enable via Copilot CLI /experimental? (Y/n)"*

1. `copilot` → `/experimental` → enable **SESSION_STORE** → exit
2. Verify: `ls ~/.copilot/session-store.db`

> One-time setup. Once enabled, the store persists across all future sessions.

---

## Section 6 — Wire into Agent Instructions

Target: `~/.copilot/copilot-instructions.md`

### 6a — Detect state

```bash
if grep -q '<!-- session-recall:v1 -->' ~/.copilot/copilot-instructions.md 2>/dev/null; then
  echo "current"   # idempotent — skip
elif grep -q 'Progressive Session Recall' ~/.copilot/copilot-instructions.md 2>/dev/null; then
  echo "stale"     # replace legacy block (6c)
else
  echo "missing"   # append new block (6b)
fi
```

### 6b — Append (state = missing)

> **Agent:** ask user *"Append session-recall instructions to copilot-instructions.md? (Y/n)"*

```bash
mkdir -p ~/.copilot
```

Append this exact block:

````markdown
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
````

### 6c — Replace legacy block (state = stale)

> **Agent:** ask user *"Found legacy session-recall block. Replace with current version? (Y/n)"*

Remove everything from `## Progressive Session Recall` through the end of that section, then append the block from 6b. The `<!-- session-recall:v1 -->` markers make future updates idempotent.

---

## Section 7 — Verify Install

```bash
session-recall health
```

| Result | Meaning |
|--------|---------|
| **GREEN** | Done — all systems operational |
| **AMBER** | Some backends not configured (normal for Copilot-CLI-only setups) |
| **RED** | Something broken → see **Section 9** |

```bash
session-recall list --json --limit 1
```

Zero sessions returned is **normal on first use** — complete one Copilot CLI session first.

---

## Section 8 — Optional: Other Backends

> **Agent:** ask user *"Enable VS Code, JetBrains, or Neovim backends? (Y/n)"*

- **Yes** → Read [`deploy/install-other-backends.md`](install-other-backends.md) and execute it end-to-end.
- **No** → Skip. Copilot CLI backend is sufficient for most users.

---

## Section 9 — Troubleshooting

**`command not found: session-recall`** — PATH issue:

```bash
echo "$PATH" | tr ':' '\n' | grep -q '.local/bin' && echo "OK" || echo "MISSING — run: export PATH=\"\$HOME/.local/bin:\$PATH\""
```

**`database not found`** — On WSL2, see **Section 5**. On macOS/Linux: `ls ~/.copilot/session-store.db`

**`schema-check` fails (exit 2)** — Copilot CLI schema drifted. See [UPGRADE-COPILOT-CLI.md](../UPGRADE-COPILOT-CLI.md).

**No sessions found** — Normal on first use. Complete one Copilot CLI session, then retry.

---

## Section 10 — Rollback

### Uninstall

```bash
uv tool uninstall auto-memory    # if installed with uv
pipx uninstall auto-memory       # if installed with pipx
python3 -m pip uninstall auto-memory  # if installed with pip
```

### Revert agent instructions

```bash
sed -i.bak '/<!-- session-recall:v1/,/<!-- \/session-recall:v1 -->/d' ~/.copilot/copilot-instructions.md
```

### Revert shell rc

N/A — this guide does not modify shell config. See [`deploy/install-other-backends.md`](install-other-backends.md) for file-backend rollback.

---

## Section 11 — Maintainers / Lint

### Bash syntax check

```bash
python3 -c "
import re, subprocess, sys
text = open('deploy/install.md').read()
blocks = re.findall(r'\`\`\`bash\n(.*?)\`\`\`', text, re.DOTALL)
errs = 0
for i, b in enumerate(blocks, 1):
    r = subprocess.run(['bash', '-n'], input=b, capture_output=True, text=True)
    if r.returncode != 0:
        print(f'Block {i}: FAIL\n{r.stderr}'); errs += 1
print(f'{len(blocks)} blocks, {errs} errors')
sys.exit(1 if errs else 0)
"
```

### Internal link check

```bash
for f in deploy/install-other-backends.md UPGRADE-COPILOT-CLI.md; do
  test -f "$f" && echo "OK: $f" || echo "MISSING: $f"
done
```
