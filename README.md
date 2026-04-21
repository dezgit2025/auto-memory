# auto-memory

> **Your AI coding agent never forgets.**
> Built by [Desi Villanueva](https://github.com/dezgit2025)

[![PyPI](https://img.shields.io/pypi/v/auto-memory)](https://pypi.org/project/auto-memory/)
[![CI](https://github.com/dezgit2025/auto-memory/actions/workflows/test.yml/badge.svg)](https://github.com/dezgit2025/auto-memory/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-90%20passed-brightgreen)]()

**Zero-dependency CLI that turns Copilot CLI's local SQLite into instant recall — no MCP server, no hooks, read-only, schema-checked. ~50 tokens per prompt.**

**Works with:** GitHub Copilot CLI · Claude Code · Cursor · Aider · Windsurf · any instruction-file agent

---

### Quickstart

```bash
pip install auto-memory        # or: ./install.sh
session-recall list --json     # see your recent sessions
session-recall health          # 9-dimension health dashboard
```

---

Progressive session disclosure CLI for AI coding agents. Queries your local `~/.copilot/session-store.db` to recall what you worked on across sessions — so your agent always has context.

## Why

Copilot CLI stores session history locally but has no built-in way to query it. `session-recall` gives you (and the agent) structured access to past sessions, files, and checkpoints — enabling progressive context recall without MCP servers or hooks.

## How it compares

| Approach | Dependencies | Writes to DB | Setup | Agent-native |
|----------|-------------|-------------|-------|-------------|
| **auto-memory** | None (stdlib) | ❌ Read-only | `pip install` | ✅ Instruction-file |
| MCP server | Node.js runtime | Varies | Server config | ❌ Protocol layer |
| Custom hooks | Varies | Often yes | Hook scripts | ❌ Event-driven |
| Manual grep | None | ❌ | None | ❌ Manual |

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
 9  Progressive Disclosure  ⚪ CALIBRATING  —  Collecting baseline (n=42/200)
```

## Design

- **Zero dependencies** — stdlib only (sqlite3, json, argparse)
- **Read-only** — never writes to `~/.copilot/session-store.db`
- **WAL-safe** — exponential backoff retry on SQLITE_BUSY (50→150→450ms)
- **Schema-aware** — validates expected schema on every call, fails fast on drift
- **Telemetry** — ring buffer of last 100 invocations for concurrency monitoring

## Agent Integration

auto-memory works with **any agent that supports instruction files** — GitHub Copilot CLI, Claude Code, Cursor, Aider, Windsurf, and more. Installation wires session-recall into your agent's instruction file so it runs context recall automatically.

See [`deploy/install.md`](deploy/install.md) for setup and [`copilot-instructions-template.md`](copilot-instructions-template.md) for integration patterns.

See [`UPGRADE-COPILOT-CLI.md`](UPGRADE-COPILOT-CLI.md) for schema validation after Copilot CLI upgrades.

## FAQ

**Is it safe? Does it modify my session data?**
No. auto-memory is strictly read-only. It never writes to `~/.copilot/session-store.db`.

**Does it work with Claude Code, Cursor, or Aider?**
Yes — any agent that supports instruction files can use session-recall. See `copilot-instructions-template.md` for integration patterns.

**What happens when Copilot CLI updates its schema?**
Run `session-recall schema-check` to validate. The tool fails fast on schema drift rather than returning bad data. See [UPGRADE-COPILOT-CLI.md](UPGRADE-COPILOT-CLI.md).

**Does it need an internet connection?**
No. Everything is local SQLite queries against your existing session store.

## Roadmap

- [ ] PyPI package publishing
- [ ] CI with GitHub Actions (pytest + ruff matrix)
- [ ] Session diffing (what changed between sessions)
- [ ] Export sessions to markdown
- [ ] Optional MCP server wrapper for IDE integration
- [ ] Richer health dimensions (token usage, context efficiency)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and guidelines. Issues, PRs, and docs improvements are welcome.

⭐ **If auto-memory saved you time, [star the repo](https://github.com/dezgit2025/auto-memory)** — it's the best way to help others find it.

🔗 **Share it:** *"Zero-dependency CLI that gives your AI coding agent session memory. Read-only, schema-checked, ~50 tokens per prompt."* → [github.com/dezgit2025/auto-memory](https://github.com/dezgit2025/auto-memory)

## Disclaimer

This is an independent open-source project. It is **not** affiliated with, endorsed by, or supported by Microsoft, GitHub, or any other company. There is no official support — use at your own risk. Contributions and issues are welcome on GitHub.

## License

MIT
