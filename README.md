# auto-memory

> **Your AI coding agent never forgets.**

Progressive session disclosure CLI for GitHub Copilot CLI. Queries your local `~/.copilot/session-store.db` to recall what you worked on across sessions — so your agent always has context.

## Why

Copilot CLI stores session history locally but has no built-in way to query it. `auto-memory` gives you (and the agent) structured access to past sessions, files, and checkpoints — enabling progressive context recall without MCP servers or hooks.

## Install

```bash
# Option 1: uv (recommended)
cd auto-memory
uv pip install -e .

# Option 2: pip
pip install -e .

# Option 3: run directly
PYTHONPATH=src python3 -m session_recall <command>
```

## Usage

```bash
# List recent sessions for current repo
auto-memory list --json

# Show details for a session (prefix match)
auto-memory show f662 --json

# Full-text search across turns
auto-memory search "SQLITE_BUSY" --json

# Recently touched files
auto-memory files --json

# Recent checkpoints
auto-memory checkpoints --json

# 8-dimension health check
auto-memory health

# Validate DB schema (run after Copilot CLI upgrades)
auto-memory schema-check
```

## Health Check

```
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
```

## Design

- **Zero dependencies** — stdlib only (sqlite3, json, argparse)
- **Read-only** — never writes to `~/.copilot/session-store.db`
- **WAL-safe** — exponential backoff retry on SQLITE_BUSY (50→150→450ms)
- **Schema-aware** — validates expected schema on every call, fails fast on drift
- **Telemetry** — ring buffer of last 100 invocations for concurrency monitoring

## Agent Integration

To enable your AI agent to automatically recall past sessions, copy the template from [`copilot-instructions-template.md`](copilot-instructions-template.md) into your Copilot CLI instruction file:

```bash
# Create the file if it doesn't exist
mkdir -p ~/.copilot
touch ~/.copilot/copilot-instructions.md

# Append the template
cat copilot-instructions-template.md >> ~/.copilot/copilot-instructions.md
```

### What is `~/.copilot/copilot-instructions.md`?

Copilot CLI reads this file at the start of every session. It tells the agent what tools to use and what context to gather. By adding auto-memory instructions, the agent will automatically check your session history before each prompt — so it always knows what you were working on.

### Verify integration

```bash
# In a Copilot CLI session, ask:
"Run auto-memory health and show me the output"
```

See [`UPGRADE-COPILOT-CLI.md`](UPGRADE-COPILOT-CLI.md) for schema validation after Copilot CLI upgrades.

## License

MIT
