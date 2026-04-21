# auto-memory

> **Your AI coding agent never forgets.**
> Built by [Desi Villanueva](https://github.com/dezgit2025)

Progressive session disclosure CLI for GitHub Copilot CLI. Queries your local `~/.copilot/session-store.db` to recall what you worked on across sessions — so your agent always has context.

## Why

Copilot CLI stores session history locally but has no built-in way to query it. `session-recall` gives you (and the agent) structured access to past sessions, files, and checkpoints — enabling progressive context recall without MCP servers or hooks.

## Install

Tell your AI agent:

> Read `deploy/install.md` and follow every step.

Or run manually:

```bash
./install.sh
```

See [`deploy/install.md`](deploy/install.md) for full instructions, agent integration, and troubleshooting.

## Usage

```bash
# List recent sessions for current repo
session-recall list --json

# Show details for a session (prefix match)
session-recall show f662 --json

# Full-text search across turns
session-recall search "SQLITE_BUSY" --json

# Recently touched files
session-recall files --json

# Recent checkpoints
session-recall checkpoints --json

# 9-dimension health check
session-recall health

# Validate DB schema (run after Copilot CLI upgrades)
session-recall schema-check
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

Installation includes wiring auto-memory into `~/.copilot/copilot-instructions.md` so your agent runs session recall automatically. See [`deploy/install.md`](deploy/install.md) for setup.

See [`UPGRADE-COPILOT-CLI.md`](UPGRADE-COPILOT-CLI.md) for schema validation after Copilot CLI upgrades.

## Disclaimer

This is an independent open-source project. It is **not** affiliated with, endorsed by, or supported by Microsoft, GitHub, or any other company. There is no official support — use at your own risk. Contributions and issues are welcome on GitHub.

## License

MIT
