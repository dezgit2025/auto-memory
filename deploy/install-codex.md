---
requires-user-confirmation: true
mutates-agent-instructions: true
tool: session-recall-codex
version: v1-trial
---

# Deploy session-recall-codex (OpenAI Codex CLI)

**Humans:** skim the overview, then run the snippets — or ask your AI agent to do it.
**Agents:** read sections 1–8 in order. Every mutating step requires user confirmation. Use a reasoning model (Sonnet 4.6, GPT-5.4) — mini models may skip confirmation gates.

```bash
pip install auto-memory        # session-recall-codex ships with the base package
session-recall-codex schema-check
```

> [!NOTE]
> **Trial build.** This build provides `schema-check`, `list`, and `repos`. The `search`, `show`, `files`, and `health` commands arrive in a later phase — the CLI's `--help` says so, and the instruction template below only advertises what exists.

---

## Section 1 — Overview

`session-recall-codex` reads Codex CLI's local SQLite storage (`~/.codex/state_5.sqlite` + `~/.codex/thread_history_1.sqlite`) and provides structured session recall for AI coding agents.

- **Read-only** — opens both databases with `mode=ro` + `PRAGMA query_only`; never writes to anything under `~/.codex/`
- **No env gate** — invoking the dedicated binary is the opt-in. Installing auto-memory never changes Copilot CLI or Claude Code behavior
- **Fixed-schema pre-flight** — every data command validates both databases against captured schema profiles *before* querying. If Codex ships a new storage version, the CLI refuses cleanly (exit 2/4) instead of guessing
- **Structured output** — `--json` on every command, ~50 tokens per query

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | success (a valid empty result is still 0) |
| 1 | session not found |
| 2 | usage error / schema drift / ambiguous id |
| 3 | SQLite busy or read failure after bounded retries |
| 4 | Codex database not found (not installed, or storage version changed) |

---

## Section 2 — Prerequisites

```bash
python3 --version                # must be 3.10+
test -f "$HOME/.codex/state_5.sqlite" && echo "codex store: detected" || echo "codex store: not found"
```

> [!IMPORTANT]
> Codex CLI must have been used at least once so `~/.codex/state_5.sqlite` exists. If the file is missing but other `state_*.sqlite` files exist, Codex changed its storage version — `session-recall-codex` will report `storage_version_changed` (exit 4) and must be updated before use.

---

## Section 3 — Install

> **Agent:** ask user *"Install auto-memory (includes session-recall-codex)? (Y/n)"*

```bash
pip install auto-memory
# or from a clone: ./install.sh   (uses uv/pipx/pip, editable)
```

No extra, no env var: the binary ships with the base package and is inert until invoked.

---

## Section 4 — Verify

```bash
which session-recall-codex && session-recall-codex schema-check
```

| Result | Meaning |
|--------|---------|
| `ok: schema matches fixed profiles (...)` exit 0 | Done — safe to query |
| exit 4, `storage_missing` | Codex not installed / never run |
| exit 4, `storage_version_changed` | Codex upgraded its storage — update auto-memory before use |
| exit 2, schema drift report | Same-file schema change — update auto-memory before use |

Then confirm real data comes back:

```bash
session-recall-codex list --json --limit 3
session-recall-codex repos
```

---

## Section 5 — Wire into Codex (Global, recommended)

Codex reads `~/.codex/AGENTS.md` at the start of **every** session, and only Codex reads it — so a block there fires only when Codex is the invoker, with zero detection logic.

> **Agent:** show the block and ask *"Append the session-recall-codex block to ~/.codex/AGENTS.md? (Y/n)"* — `AGENTS.md` is user-owned configuration; never edit it silently.

### 5a — Detect state

```bash
AGENT_FILE="$HOME/.codex/AGENTS.md"
if grep -q '<!-- session-recall-codex:v1 START -->' "$AGENT_FILE" 2>/dev/null; then
  echo "current"   # idempotent — skip to Section 6
elif grep -q 'session-recall-codex' "$AGENT_FILE" 2>/dev/null; then
  echo "stale"     # remove the old block, then append fresh
else
  echo "missing"   # append → 5b
fi
```

### 5b — Append (state = missing)

Append the **global block** from [`codex-instructions-template.md`](../codex-instructions-template.md) (the section marked "put this in `~/.codex/AGENTS.md`") between its `<!-- session-recall-codex:v1 START -->` / `END -->` markers.

### 5c — Uninstall the block

Delete everything between (and including) the START/END markers.

---

## Section 6 — Per-Repo Wiring (Optional)

A repo-level `AGENTS.md` may be read by several agents (Codex, Copilot CLI, and others honor it). Use the **repo block** from the template — it self-routes by agent identity so Codex runs `session-recall-codex` while Copilot CLI runs `session-recall`. Never place a block in a shared file that names a single CLI unconditionally.

---

## Section 7 — Smoke Test (Optional, recommended)

From a clone of this repo, run the 15-test read-only smoke set against your live store:

```bash
# runner embedded in codex-test/codex-test-set.md — paste the Runner block into bash
# expected: "16 passed, 0 failed ... VERDICT: ALL GREEN"
```

It proves recall correctness and byte-identical SHA-256 hashes of the store before/after (read-only proof).

---

## Section 8 — Safety & Troubleshooting

- **Never write to `~/.codex/`.** Any tool or fix that would modify the store is out of scope by design.
- **Schema drift (exit 2) or version change (exit 4):** report it and continue without recall. Do not attempt to patch the adapter, bypass the pre-flight, or query the database directly.
- **Locked database (exit 3):** Codex was writing at that moment; retry later.
- **Command not found:** ensure your pip/uv tool bin dir (e.g. `~/.local/bin`) is on `PATH`.
