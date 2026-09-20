# auto-memory

## Your AI coding agent has amnesia. Here's the fix.

*Zero-dependency session recall for your AI coding tools.*

> Built by [Desi Villanueva](https://github.com/dezgit2025)

[![PyPI](https://img.shields.io/pypi/v/auto-memory)](https://pypi.org/project/auto-memory/)
[![CI](https://github.com/dezgit2025/auto-memory/actions/workflows/test.yml/badge.svg)](https://github.com/dezgit2025/auto-memory/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](pyproject.toml)
[Verification and tests](verify/)
[![Discussions](https://img.shields.io/badge/📢_Updates-Discussions-blue)](https://github.com/dezgit2025/auto-memory/discussions)

<!-- AGENTIC-INSTALL-PROTOCOL: v1
     Files: deploy/install.md, deploy/install-other-backends.md, deploy/install-claude-code.md
     Entry: Read deploy/install.md
-->

## Codex schema repair — v0.6.0 (2026-09-20)

Codex recall now includes a repair companion, `session-recall-codex-fix`, for
schema changes that would otherwise stop session recall. Repair preparation and
testing are automated after you start them; applying a generated fix requires
human approval. Codex session databases remain read-only.

### Install once for all backends

**Install auto-memory once for GitHub Copilot CLI, Claude Code, and Codex.**
Our default is **pipx recommended, uv alternative, and pip only inside a virtual
environment**. Both [pipx](https://pipx.pypa.io/stable/) and
[uv](https://docs.astral.sh/uv/guides/tools/) isolate CLI tools and let you choose
Python explicitly when multiple versions are installed. Choose one method.

We distribute auto-memory through these isolated Python environments; we do not
maintain a Homebrew formula for auto-memory. The Homebrew commands below select
the macOS Python/tooling used by our sandbox tests, not an auto-memory formula.

On macOS with Homebrew, select the Homebrew Python 3.14 build used by our Codex
sandbox tests (verified on Apple silicon):

```bash
brew install pipx python@3.14
pipx install --python "$(brew --prefix python@3.14)/bin/python3.14" \
  "auto-memory @ git+https://github.com/dezgit2025/auto-memory.git@v0.6.0"
```

For Linux/WSL, install pipx and Python 3.14 first, then:

```bash
pipx install --python python3.14 \
  "auto-memory @ git+https://github.com/dezgit2025/auto-memory.git@v0.6.0"
```

**Alternative: uv** (install uv first; do not run both installers):

```bash
uv tool install --python "$(brew --prefix python@3.14)/bin/python3.14" \
  "auto-memory @ git+https://github.com/dezgit2025/auto-memory.git@v0.6.0"
# On Linux/WSL, replace the Homebrew path with --python 3.14.
```

The Linux/WSL commands provide recall; the current Codex AI-repair sandbox
requires macOS. On macOS, use the explicit Homebrew path above for AI repair:
`--python 3.14` alone may select a different Python build. Git is required for
these release-tag installs. If the tool directory is missing from PATH, run
`pipx ensurepath` (or `uv tool update-shell` for uv) and restart your terminal.
To replace an existing install with the same manager or change its Python,
repeat its install command with `--force`. Confirm `command -v session-recall`
resolves to your chosen installation when migrating from another manager.

| Backend | Command after installation | Setup |
| --- | --- | --- |
| GitHub Copilot CLI | `session-recall health` | [Copilot setup](deploy/install.md) |
| Claude Code | `SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 session-recall-cc health` | [Claude setup](deploy/install-claude-code.md) |
| Codex | `session-recall-codex schema-check` | [Codex setup and repair](deploy/install-codex.md) |

Run the check for the backend you actually use; its local session store must
exist. You do not need three installations or the `[claude]` extra to obtain
the commands in 0.6.0. Backend instruction-file wiring remains a separate step.
For a manual virtual-environment alternative, see the [install guide](deploy/install.md#3a--from-github-060).

### How it works

**The problem:** As Codex evolves, OpenAI may change the schema—the structure
of the local databases that store its session state and history. A tool built
for an earlier schema can stop working until its reader is updated.

**The solution:** `auto-memory` checks compatibility before reading sessions.
When it detects an unsupported change, it stops safely. You can then start a
repair: the tool uses a reviewed fix when available, or asks Codex to propose
an update to the recall reader. It tests the repair before you approve and
apply it, keeping Codex’s databases untouched.

```text
          Codex changes its session-state schema
                             |
                   Check compatibility
                             |
                  Can our reader handle it?
                     /               \
                   Yes                No
                    |                  |
             Recall sessions    Stop safely and
                                report the change
                                      |
                             You start a repair
                                      |
                           Reviewed fix available?
                             /                \
                           Yes                 No
                            |                   |
                     Use that fix      Codex proposes a
                                       reader update
                            |                   |
                            +---------+---------+
                                      |
                           Test with synthetic data
                                      |
                                 Tests pass?
                                /           \
                              No             Yes
                               |              |
                       Keep current      Human approval
                       reader unchanged  and explicit apply
                                              |
                                    Recheck repaired reader
                                       /             \
                                     Pass            Fail
                                      |               |
                               Recall sessions     Roll back
```

**Release status:** the deterministic repair path and synthetic end-to-end AI
workflow pass offline verification, including clean installation and rollback.
Live Codex generation is **experimental**: the first live smoke attempt failed
safely, and successful live generation has not yet been verified. AI candidate
testing requires macOS and a working `sandbox-exec`; unavailable isolation stops
the attempt. Ordinary recall and known repairs do not call an AI model.

### Install this Codex update

Use the [shared installation above](#install-once-for-all-backends), then
verify the installed release and your existing Codex session store:

```bash
session-recall --version
session-recall-codex --version
session-recall-codex-fix --version
session-recall-codex schema-check
```

A fresh v0.6.0 install reports version **0.6.0**. Run the check before recalling
sessions; if it reports drift, follow the [Codex setup and repair guide](deploy/install-codex.md).
An existing managed adapter can remain pinned to an earlier version until a
reviewed repair is explicitly applied. GitHub publication does not publish a
new PyPI package; `pip install auto-memory` may install an older release.

After setup, recall with `session-recall-codex list --json --limit 5` or
`session-recall-codex repos`. To investigate a schema change:

```bash
session-recall-codex-fix --json check
# For an unknown, readable schema; starts one experimental AI repair attempt:
session-recall-codex-fix --json assist
# Review the returned diff and test results before approving:
session-recall-codex-fix approve --candidate CANDIDATE_ID
session-recall-codex-fix --json apply-candidate --candidate CANDIDATE_ID
# OPERATION_ID is returned by apply-candidate:
session-recall-codex-fix --json rollback --repair OPERATION_ID
```

For a known repair, follow the guide's `plan` and `apply --plan` workflow. AI
repair uses the installed Codex CLI, its existing login, and GPT-6 Astra at
medium reasoning. It starts with roughly 32K tokens; every additional 32K block
needs explicit approval. Estimates are not hard token or billing caps. Missing
or inaccessible databases are reported without starting AI repair.

**Where the code lives:** [recall reader](src/session_recall/providers/codex/),
[repair controller](src/session_recall/codex_fix/),
[bundled adapters and catalogue](src/session_recall/codex_fix/data/), and
[independent verification](verify/). Everything needed at runtime ships in the
base package. [Full Codex installation guide](deploy/install-codex.md) ·
[Standalone flow diagram and version history](codex-schema-repair-flow.md) ·
[Changelog](CHANGELOG.md)

---

**Also included:** Claude Code support — `session-recall-cc` reads Claude Code JSONL sessions and builds an FTS5 index for structured recall. [Full changelog →](CHANGELOG.md)

**Zero-dependency CLI that turns Copilot CLI's local SQLite into instant recall — no MCP server, no hooks, read-only, schema-checked. ~50 tokens per prompt.**

### Works With

| Backend | Status | How to enable |
|---------|--------|--------------|
| **GitHub Copilot CLI** | ✅ default | Base package — [Install](#quickstart) |
| **Claude Code** | 🟡 opt-in | Same package; enable the backend — [Full setup →](deploy/install-claude-code.md) |
| **Codex CLI** | Recall + reviewed repair; experimental AI repair | Install v0.6.0 from GitHub — [Full setup →](deploy/install-codex.md) |
| **VS Code** | 🟡 opt-in | [Enable in 30 seconds →](deploy/install-other-backends.md#32--vs-code-backend) |
| **JetBrains** | 🟡 opt-in | [Enable →](deploy/install-other-backends.md#33--jetbrains-backend) |
| **Neovim** | 🟡 opt-in | [Enable →](deploy/install-other-backends.md#34--neovim-backend) |

> **Claude Code user?** After installing the package, set `export SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1` and follow [`deploy/install-claude-code.md`](deploy/install-claude-code.md) for full integration.

> **Codex CLI user?** Follow [Install this Codex update](#install-this-codex-update), then [wire session recall into Codex](deploy/install-codex.md#section-5--wire-into-codex-global-recommended).

> **VS Code user?** Ask your agent to read [`deploy/install-other-backends.md`](deploy/install-other-backends.md) — it walks through detection, env var setup, and verification automatically.

**Coming soon:** Cursor

---

### Quickstart

Install once with [pipx or uv](#install-once-for-all-backends), then check
the backend you use:

```bash
session-recall --version # expected: auto-memory 0.6.0
# GitHub Copilot CLI:
session-recall health
# Claude Code:
SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 session-recall-cc health
# Codex:
session-recall-codex schema-check
```

Version 0.6.0 is a [GitHub-only release](https://github.com/dezgit2025/auto-memory/releases/tag/v0.6.0);
an unqualified PyPI install may return an older version. The commands above pin
the published release rather than the moving `main` branch.

Now give your agent a memory. See the **🤖 Agentic Install** section below for agent-driven setup, or follow [`deploy/install.md`](deploy/install.md) manually.

### 📋 Example: Remember Your Last 10 Sessions

Want to recall the last 10 sessions you worked on, which project folder, branch, and what you did? Add this prompt to your agent instructions:

```
Use `session-recall list --json --limit 10` to show my last 10 sessions.
Display: date, time, full session_id, summary, branch, turns count, project folder.
Format as a table.
```

Your agent runs it and gets:

```
 #  │ Date  │ Time  │ Session ID                                 │ Summary                    │ Branch            │ Project                  │ Turns
────┼───────┼───────┼────────────────────────────────────────────┼────────────────────────────┼───────────────────┼──────────────────────────┼──────
 1  │ 05-01 │ 14:32 │ a1b2c3d4-e5f6-7890-abcd-ef1234567890       │ Refactor Auth Module       │ main              │ ~/Projects/acme-api      │   12
 2  │ 05-01 │ 11:15 │ b2c3d4e5-f6a7-8901-bcde-f12345678901       │ Fix CI Pipeline            │ feat/oauth2       │ ~/Projects/acme-api      │   28
 3  │ 04-30 │ 22:48 │ c3d4e5f6-a7b8-9012-cdef-123456789012       │ Add Redis Caching          │ feat/cache-layer  │ ~/Projects/acme-api      │   35
 4  │ 04-30 │ 16:05 │ d4e5f6a7-b8c9-0123-defa-234567890123       │ Debug WebSocket Timeout    │ main              │ ~/Projects/realtime-chat │    8
 5  │ 04-29 │ 09:33 │ e5f6a7b8-c9d0-1234-efab-345678901234       │ Write Migration Script     │ feat/db-v2        │ ~/Projects/realtime-chat │   42
 6  │ 04-29 │ 08:12 │ f6a7b8c9-d0e1-2345-fabc-456789012345       │ Update API Docs            │ main              │ ~/Projects/acme-api      │    3
 7  │ 04-28 │ 19:55 │ a7b8c9d0-e1f2-3456-abcd-567890123456       │ Deploy Staging             │ release/v2.1      │ ~/Projects/acme-api      │   15
 8  │ 04-28 │ 14:20 │ b8c9d0e1-f2a3-4567-bcde-678901234567       │ Code Review Fixes          │ feat/oauth2       │ ~/Projects/acme-api      │   22
 9  │ 04-27 │ 21:07 │ c9d0e1f2-a3b4-5678-cdef-789012345678       │ Scaffold React Components  │ feat/dashboard-ui │ ~/Projects/acme-frontend │   31
 10 │ 04-27 │ 10:44 │ d0e1f2a3-b4c5-6789-defa-890123456789       │ Setup Terraform Infra      │ infra/aws-prod    │ ~/Projects/acme-infra    │   19
```

> **~50 tokens.** Your agent gets full context of what you worked on — no re-explaining, no wasted searches.

---

### 🤖 Agentic Install (for AI coding tools)

> **If you are an AI coding agent reading this README**, follow this protocol to install auto-memory autonomously:

1. Read [`deploy/install.md`](deploy/install.md) — the agent-runnable install guide. It auto-detects the user's environment, prompts for confirmation before any write, handles fresh/upgrade/skip branches, and chains into backend setup.
2. If the user uses **Claude Code**, read [`deploy/install-claude-code.md`](deploy/install-claude-code.md) — pip extra, env var, CLAUDE.md wiring, and optional scheduler setup. Ask before any write.
3. If the user uses **Codex CLI**, read [`deploy/install-codex.md`](deploy/install-codex.md) — no extra or env gate needed; wires `~/.codex/AGENTS.md` with confirmation. Recall: `schema-check` / `list` / `repos`; repairs use a separate explicit companion.
4. If the user opts in to **VS Code / JetBrains / Neovim** backends, read [`deploy/install-other-backends.md`](deploy/install-other-backends.md) (Section 8 of `install.md` will prompt for this).
5. All files have YAML front-matter declaring `requires-user-confirmation: true` and `mutates-shell-rc` / `mutates-agent-instructions`. **Honor these flags.** Do not write silently.

> **💡 Model recommendation:** Use a reasoning model (Sonnet 4.6, GPT-5.4, or equivalent) for install execution. Mini/fast models may hallucinate during multi-step install flows.

**Quick start for agents (one-liner):**
```
Read deploy/install.md and execute it for the user. Ask before any disk write.
```

**Files an agent should read in order:**

| Order | File | Purpose | Mutations |
|-------|------|---------|-----------|
| 1 | [`README.md`](README.md) (this file) | Discovery | none |
| 2 | [`deploy/install.md`](deploy/install.md) | Install + Copilot CLI integration | binary install, instruction file append |
| 3 | [`deploy/install-claude-code.md`](deploy/install-claude-code.md) | Claude Code integration | pip extra, CLAUDE.md append |
| 4 | [`deploy/install-codex.md`](deploy/install-codex.md) | Codex recall and schema repair | package install, optional ~/.codex/AGENTS.md append |
| 5 | [`deploy/install-other-backends.md`](deploy/install-other-backends.md) | Optional VS Code / JetBrains / Neovim setup | shell rc env vars |
| 6 | [`UPGRADE-COPILOT-CLI.md`](UPGRADE-COPILOT-CLI.md) | Run after Copilot CLI version bumps | none (read-only validation) |

---

### 🪟 Windows (WSL2) — Enable the Session Store. (IF MISSING)

> **On Windows 11 + WSL2** (Suggested method of using on Windows install WSL2), IF Copilot CLI doesn't create `session-store.db`   
> You must enable it first — otherwise you'll get `error: database not found`.

### Missing Session Store Error Workaround— Enable the Session Store. 
Inside any Copilot CLI session, run:

```
/experimental
```

Select **SESSION_STORE** to enable it. This turns on the SQLite-based session store for cross-session history, file tracking, and search.

Verify it worked:

```bash
ls ~/.copilot/session-store.db    # should exist after your next session
```

> **Note:** This is a one-time setup. Once enabled, the session store persists across all future sessions.

---

## The Problem

Every AI coding agent ships with a big number on the box. 200K tokens. Sounds massive. Here's what actually happens:

```
200,000  tokens — context window (theoretical max)
120,000  tokens — effective limit before context rot kicks in (~60%)
 -65,000  tokens — MCP tools
 -10,000  tokens — instruction files
=========
 ~45,000  tokens — what you ACTUALLY have before quality degrades
```

LLMs don't degrade gracefully — once you cross roughly **60% of the context window**, the model starts losing coherence. The industry calls it "lost in the middle": attention goes to the beginning (instructions) and the end (recent turns), but your actual working context in the middle gets progressively fuzzier.

I timed it over a week: **68 minutes per day** lost to re-orientation after compactions and new sessions.

> It's a **death spiral of diminishing context** — each compaction leaves the agent slightly dumber, which burns more tokens explaining things, which triggers the next compaction sooner.

### The Compaction Tax

Every 20–30 turns, the context warning hits and you get two bad choices: ignore it and watch the agent hallucinate, or run `/compact` and watch it lobotomize itself into a tidy two-paragraph summary of a 30-minute investigation. Either way you lose five minutes re-narrating your own project back to the agent like it's a new hire. That's not a workflow — that's a hamster wheel.

## The 200x ROI

Here's the cost comparison that made me build this:

| Operation | Tokens | What you get |
|-----------|--------|-------------|
| `grep -r "auth" src/` | ~5,000-10,000 | 500 results, mostly irrelevant |
| `find . -name "*.py"` | ~2,000 | Every Python file, no context |
| Agent re-orientation | ~2,000 | You re-explaining yesterday |
| **`auto-memory files --json --limit 10`** | **~50** | **Exactly the 10 files you touched yesterday** |

**50 tokens vs 10,000 — a 200x improvement.**

## Before & After

**Before auto-memory** — new session on a project:

```
You: Fix the failing test in the auth module

Agent: Let me explore the project structure...
       $ find . -name "*.py" | head -50           ← 2K tokens
       $ grep -r "test.*auth" tests/              ← 5K tokens
       $ cat tests/test_auth.py                    ← 3K tokens
       $ cat src/auth/handler.py                   ← 2K tokens
       I see several test files. Which test is failing?

You: The one we were working on yesterday, the token refresh edge case

Agent: Let me search for that...
       $ grep -r "refresh" tests/                  ← 4K tokens
       ...
```

Total: ~16K tokens burned, 8 minutes elapsed, agent still isn't oriented.

**After auto-memory** — same scenario:

```
You: Fix the failing test in the auth module

Agent: [auto-recall: auto-memory files --json --limit 10]
       → src/auth/refresh.py, tests/test_refresh_edge_cases.py,
         src/auth/token_store.py (last touched 14h ago)

       [auto-recall: auto-memory list --json --limit 3]
       → Yesterday: "Fixed token refresh race condition, one edge case
         test still failing on expired token + network timeout combo"

       I can see from your last session that test_refresh_edge_cases.py
       has a failing test for the expired token + network timeout case.
       Let me look at that specific test...
       $ cat tests/test_refresh_edge_cases.py      ← 1K tokens (targeted)
```

Total: ~1.1K tokens, 30 seconds, agent is immediately productive.

## How it compares

| Approach | Dependencies | Writes to DB | Setup | Agent-native |
|----------|-------------|-------------|-------|-------------|
| **auto-memory** | None (stdlib) | ❌ Read-only | `pipx install` / `uv tool install` | ✅ Instruction-file |
| MCP server | Node.js runtime | Varies | Server config | ❌ Protocol layer |
| Custom hooks | Varies | Often yes | Hook scripts | ❌ Event-driven |
| Manual grep | None | ❌ | None | ❌ Manual |

## Mental Model: RAM vs Disk

- **Context window = RAM.** Fast, limited, clears on restart.
- **session-store.db = Disk.** Persistent, searchable, grows forever.

auto-memory is the **page fault handler** — it pulls exact facts from disk in ~50 tokens when the agent needs them.

**It's not unlimited context. It's unlimited context *recall*.** In practice, same thing.

## Design

```
┌─────────────────────────────────────────────────┐
│  copilot-instructions.md                        │
│  "Run auto-memory FIRST on every prompt"         │
└──────────────────┬──────────────────────────────┘
                   │ agent reads instruction
                   ▼
┌─────────────────────────────────────────────────┐
│  auto-memory CLI                                │
│  (pure Python, zero deps, read-only)            │
└──────────────────┬──────────────────────────────┘
                   │ SELECT ... FROM sessions
                   ▼
┌─────────────────────────────────────────────────┐
│  ~/.copilot/session-store.db                    │
│  (SQLite + FTS5, owned by Copilot CLI binary)   │
└─────────────────────────────────────────────────┘
```

- **Zero dependencies** — stdlib only (sqlite3, json, argparse)
- **Read-only** — never writes to `~/.copilot/session-store.db`
- **WAL-safe** — exponential backoff retry on SQLITE_BUSY (50→150→450ms)
- **Schema-aware** — validates expected schema on every call, fails fast on drift
- **Telemetry** — ring buffer of last 100 invocations for concurrency monitoring

## Works with Claude Code (opt-in)

In addition to GitHub Copilot CLI, `auto-memory` can read [Claude Code](https://docs.anthropic.com/claude-code) session logs from `~/.claude/projects/`. This ships as a separate CLI binary (`session-recall-cc`) that is **off unless explicitly enabled** — Copilot CLI users pay zero cost.

### Enable Claude Code after installation

Install the package once using [Quickstart](#quickstart), then enable Claude
Code recall in that same installation:

```bash
# First install the shared package with pipx (or uv) using the instructions above.
export SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1
session-recall-cc health
```

### Optional: pre-warm scheduler

> Skip this unless you want consistent sub-100ms latency. The CLI already does on-demand indexing (~50ms after the first run).

If you have the repo cloned, the installer auto-detects your OS:

```bash
bash scripts/install-claude-sidecar.sh --install    # auto-detects OS
bash scripts/install-claude-sidecar.sh --status     # check state
bash scripts/install-claude-sidecar.sh --uninstall  # remove
```

Otherwise, pick your OS below:

#### macOS (Intel & Apple Silicon)

Uses `launchd` — Apple's native scheduler. Survives sleep/wake, auto-runs at login.

```bash
PYTHON3="$(command -v python3)"
cat > ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.session-recall-cc.sidecar</string>
  <key>ProgramArguments</key><array>
    <string>$PYTHON3</string><string>-m</string>
    <string>session_recall.providers.claude_code.sidecar</string>
    <string>--once</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>SESSION_RECALL_ENABLE_CLAUDE_BACKEND</key><string>1</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/.claude/.sr-sidecar.log</string>
  <key>StandardErrorPath</key><string>$HOME/.claude/.sr-sidecar.err.log</string>
</dict></plist>
EOF
launchctl load -w ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist
```

**Verify:** `launchctl list | grep session-recall-cc`
**Uninstall:** `launchctl unload -w ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist && rm ~/Library/LaunchAgents/com.session-recall-cc.sidecar.plist`

#### Linux / Windows WSL2

Uses `cron` — works on any distro and WSL2.

```bash
(crontab -l 2>/dev/null; echo "*/5 * * * * env SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 $(command -v python3) -m session_recall.providers.claude_code.sidecar --once >> ~/.claude/.sr-sidecar.log 2>&1") | crontab -
```

**Verify:** `crontab -l | grep session-recall`
**Uninstall:** `crontab -l | grep -v session-recall | crontab -`

> [!TIP]
> Full details (Windows Task Scheduler, interval tuning, troubleshooting) → [`deploy/install-claude-code.md`](deploy/install-claude-code.md) §7

### How it works

- Reads Claude Code's per-conversation `~/.claude/projects/<cwd>/<uuid>.jsonl` files
- Builds an FTS5 index at `~/.claude/.sr-index.db`
- Indexer is **mtime-incremental** — typical update <100ms
- **Read-only** — never modifies Claude Code's session files

### Sample output

> Try: *"What work was done on the API integration in this repo? Check session-recall-cc for recent history."*

**`session-recall-cc list --limit 5`**

| ID | Repo | Summary | Last Seen | Turns |
|----|------|---------|-----------|-------|
| `3b89ff09` | myorg/backend-api | What work was done on the API integration? | 2026-05-02 | 1 |
| `7e63b4b4` | myorg/infra | Where are the session JSON files for Claude Code located? | 2026-05-02 | 1 |
| `78c36e1f` | myorg/infra | How do I update Claude Code? | 2026-05-02 | 2 |
| `aed766c7` | myorg/backend-api | Refactored auth middleware | 2026-04-23 | 1 |
| `0f532ef0` | myorg/dotfiles | ping | 2026-04-18 | 0 |

**`session-recall-cc search "database migration" --limit 3`**

| ID | Repo | Snippet (FTS5 highlights in ⟦⟧) |
|----|------|---------------------------------|
| `bc112c14` | myorg/backend-api | ⟦Database⟧ ⟦migration⟧ for user table — added indexes on email and created_at |
| `01bf810e` | myorg/infra | Check if the staging ⟦database⟧ has pending ⟦migration⟧ scripts |
| `3b89ff09` | myorg/backend-api | What work was done on ⟦database⟧ ⟦migration⟧ in this repo? |

### 🤖 For your AI coding agent

If you'd rather have an agent install this for you, point it at [`deploy/install-claude-code.md`](deploy/install-claude-code.md). The doc has YAML front-matter (`requires-user-confirmation: true`) and per-step "agent: ask user" prompts so a reasoning model walks you through install with confirmation at every mutating step.

## Works with Codex CLI (trial, opt-in)

`auto-memory` can also read [OpenAI Codex CLI](https://github.com/openai/codex)'s local SQLite session store (`~/.codex/`). This ships as a separate binary (`session-recall-codex`) that is **inert unless invoked** — Copilot CLI and Claude Code users pay zero cost, and a Codex storage change can never break the main CLI.

### Install and verify

Use the [v0.6.0 GitHub installation steps above](#install-this-codex-update).
The base package includes both `session-recall-codex` and
`session-recall-codex-fix`; no optional dependency extra is required.

Then wire it into Codex (with confirmation) via [`deploy/install-codex.md`](deploy/install-codex.md), which appends the recall block from [`codex-instructions-template.md`](codex-instructions-template.md) to `~/.codex/AGENTS.md` — Codex reads that file every session, so the block fires only when Codex is the invoker.

### Codex command scope

| Command | Status |
|---------|--------|
| `schema-check` | ✅ fixed-profile validation of both Codex DBs, human + `--json` |
| `list` | ✅ recent sessions (`--repo` `--limit` `--days` `--include-archived` `--json`) |
| `repos` | ✅ repo aggregation (`--include-local` reveals `local:` workspaces) |
| `search` / `show` / `files` / `health` | Not yet available for Codex |
| `session-recall-codex-fix` | Explicit check, plan/apply, experimental assist, approval and rollback |

### How it works

- Reads `~/.codex/state_5.sqlite` + `~/.codex/thread_history_1.sqlite`, **read-only** (`mode=ro` + `PRAGMA query_only`)
- Every data command runs a fixed-schema pre-flight first — if a Codex upgrade changes the storage schema, the CLI refuses cleanly (exit 2/4) instead of returning wrong data
- Sub-agent and archived threads are excluded by default (higher-level context only)
- Synthetic regression and installed-package verification check database hashes before and after the repair lifecycle; [verifier sources](verify/) are included in this repository
- See the [dated repair flow above](#codex-schema-repair--v060-2026-09-20) for schema-change handling, approval, and rollback

> Try (in Codex): *"What did I work on in this repo recently? Run session-recall-codex list --json --limit 5."*

## Usage

The examples below use Copilot CLI's `session-recall` command. For Codex, use
the `list`/`repos` commands and explicit repair workflow documented above;
Codex search and file-level recall are not yet implemented.

### Try these prompts with your agent

 Once wired into your agent's instruction file, session-recall runs on every prompt — giving the agent your recent files and sessions as context before it does anything else.


```
"Search recent sessions about fixing the db connection bug"
"Check past 5 days sessions for latest plans?"
"Pick up where we left off on the API refactor"
"search recent sessions for last 10 files we modified"
"search sessions for the db migration bug"
```

No special syntax. The agent reads your session history and gets oriented in seconds instead of minutes.

### How it works under the hood

Progressive disclosure — most prompts never get past Tier 1.

**Tier 1 — Cheap scan (~50 tokens).** Usually enough.

```bash
session-recall files --json --limit 10
session-recall list --json --limit 5
```

**Tier 2 — Focused recall (~200 tokens).** When Tier 1 isn't enough.

```bash
session-recall search "specific term" --json
```

**Tier 3 — Full session detail (~500 tokens).** Only when investigating something specific.

```bash
session-recall show <session-id> --json
```

**Operational commands:**

```bash
session-recall health          # 9-dimension health dashboard
session-recall schema-check    # validate DB schema after Copilot CLI upgrades
session-recall repos --json     # discovered repositories across providers
```

`session-recall` now supports multi-storage discovery for current Copilot CLI layouts, including session-state sources when legacy `session-store.db` is absent.

## Multi-Storage Recall

By default, session-recall reads only from Copilot CLI's SQLite database. Enable file-backed providers to also recall sessions from VS Code, JetBrains, and Neovim:

```bash
export SESSION_RECALL_ENABLE_FILE_BACKENDS=1
```

### Supported Providers

| Provider | Platforms | Auto-detected paths |
|----------|-----------|-------------------|
| **Copilot CLI** (always on) | All | `~/.copilot/session-store.db`, `~/.copilot/session-state/` |
| **VS Code** (opt-in) | Linux, macOS, WSL | `~/.config/Code/...`, `~/Library/Application Support/Code/...`, `~/.vscode-server/...` |
| **JetBrains** (opt-in) | Linux, macOS | `~/.config/JetBrains/`, `~/.config/github-copilot` |
| **Neovim** (opt-in) | Linux, macOS | `~/.local/share/nvim/`, `~/.config/github-copilot` |

### Lookback Defaults

| Storage type | Default window | Override |
|-------------|---------------|---------|
| SQLite (Copilot CLI) | 30 days | `--days N` |
| JSONL / file backends | 5 days | `--days N` or `SESSION_RECALL_JSONL_DAYS=N` |

### Trust Model

File-backed content is marked `_trust_level: "untrusted_third_party"` and wrapped in sentinel fences (`<<UNTRUSTED-FILE-BACKED-CONTENT>>`). CLI content is `_trust_level: "trusted_first_party"`. Downstream agents can use these markers to fence untrusted content.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_RECALL_ENABLE_FILE_BACKENDS` | `0` | Set to `1` to enable VS Code/JetBrains/Neovim providers |
| `SESSION_RECALL_JSONL_DAYS` | `5` | Default lookback for file-backed providers |
| `SESSION_RECALL_DB` | `~/.copilot/session-store.db` | Override SQLite path |
| `SESSION_RECALL_CLI_STATE_ROOT` | `~/.copilot/session-state` | Override JSONL state dir |
| `SESSION_RECALL_VSCODE_STORAGE` | auto-detected | Override VS Code workspace path |
| `SESSION_RECALL_JETBRAINS_ROOT` | auto-detected | Override JetBrains path |
| `SESSION_RECALL_NEOVIM_ROOT` | auto-detected | Override Neovim path |

## Health Check

`session-recall health` runs a multi-dimensional diagnostic. The core 9 dimensions check your Copilot CLI SQLite database:

```
session-recall health

Dim Name                   Zone     Score  Detail
----------------------------------------------------------------------
 1  DB Freshness           🟢 GREEN   8.0  15.8h old
 2  Schema Integrity       🟢 GREEN  10.0  All tables/columns OK
 3  Query Latency          🟢 GREEN  10.0  1ms
 4  Corpus Size            🟢 GREEN  10.0  399 sessions
 5  Summary Coverage       🟢 GREEN   7.4  92% (367/399)
 6  Repo Coverage          🟢 GREEN  10.0  8 sessions for owner/repo
 7  Concurrency            🟢 GREEN  10.0  busy=0.0%, p95=48ms
 8  E2E Probe              🟢 GREEN  10.0  list→show OK
 9  Progressive Disclosure  ⚪ CALIBRATING  —  Collecting baseline (n=42/200)
```

### Per-Provider Health

Use `--provider` to diagnose a specific backend. Each provider gets 4 sub-dimensions:

| Dimension | What it checks |
|-----------|---------------|
| **Path Discovery** | Are the expected directories/DB files present on this machine? |
| **File Inventory** | How many session files or DB size? Is there data to read? |
| **Recent Activity** | Sessions within the lookback window (5 days JSONL / 30 days SQLite)? |
| **Trust Model** | First-party (Copilot CLI) or third-party (VS Code/JetBrains/Neovim)? |

```
session-recall health --provider cli

 10 Provider:cli
      ├─ Path Discovery     🟢 GREEN  10.0  2 path(s) found
      ├─ File Inventory     🟢 GREEN  10.0  DB 13656064 bytes, 457 state file(s)
      ├─ Recent Activity    🟢 GREEN  10.0  20 session(s) in last 30d
      └─ Trust Model        🟢 GREEN  10.0  Trusted first-party; fences disabled
```

```
session-recall health --provider vscode

 10 Provider:vscode
      ├─ Path Discovery     🟢 GREEN  10.0  1 path(s) found
      ├─ File Inventory     🟢 GREEN  10.0  12 file(s)
      ├─ Recent Activity    🔴 RED     0.0  No sessions in last 5d
      └─ Trust Model        🟢 GREEN  10.0  Untrusted third-party; output fences enabled
```

Available providers: `cli`, `vscode`, `jetbrains`, `neovim`, `all`

**JSON output** for agent parsing:

```bash
session-recall health --provider vscode --json
# Returns structured JSON with providers.vscode.dimensions[] array
```

**Not enabled?** If you see `error: vscode provider is not enabled`, set the env var first:

```bash
export SESSION_RECALL_ENABLE_FILE_BACKENDS=1
# Or follow the full guide: deploy/install-other-backends.md
```

## Agent Integration

auto-memory works with **any agent that supports instruction files** — GitHub Copilot CLI, Claude Code, Cursor, Aider, Windsurf, and more. Installation wires session-recall into your agent's instruction file so it runs context recall automatically.

See [`deploy/install.md`](deploy/install.md) for setup and [`copilot-instructions-template.md`](copilot-instructions-template.md) for integration patterns.

See [`UPGRADE-COPILOT-CLI.md`](UPGRADE-COPILOT-CLI.md) for schema validation after Copilot CLI upgrades.

## What This Isn't

- **Not a vector database** — no embeddings, SQLite FTS5 only.
- **Not cross-machine sync** — local only.
- **Not a replacement for project documentation** — recalls *what you did*, not *how the system works*.

## FAQ

**Is it safe? Does it modify my session data?**
No. auto-memory is strictly read-only. It never writes to `~/.copilot/session-store.db`.

**What happens when Copilot CLI updates its schema?**
Run `session-recall schema-check` to validate. The tool fails fast on schema drift rather than returning bad data. See [UPGRADE-COPILOT-CLI.md](UPGRADE-COPILOT-CLI.md).

## Roadmap

See [ROADMAP.md](ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and guidelines. Issues, PRs, and docs improvements are welcome.

⭐ **If auto-memory saved you time, [star the repo](https://github.com/dezgit2025/auto-memory)** — it's the best way to help others find it.

🔗 **Share it:** *"Zero-dependency CLI that gives your AI coding agent session memory. Read-only, schema-checked, ~50 tokens per prompt."* → [github.com/dezgit2025/auto-memory](https://github.com/dezgit2025/auto-memory)

## Disclaimer

This is an independent open-source project. It is **not** affiliated with, endorsed by, or supported by Microsoft, GitHub, or any other company. There is no official support — use at your own risk. Contributions and issues are welcome on GitHub.

## Contributors

- [@jshessen](https://github.com/jshessen) — Multi-storage provider architecture ([PR #5](https://github.com/dezgit2025/auto-memory/pull/5))
- [@tillig](https://github.com/tillig) — Reported the macOS installation issue and suggested isolated installation with `uv` ([#25](https://github.com/dezgit2025/auto-memory/issues/25)).

## License

MIT
