# auto-memory

## Your AI coding agent has amnesia. Here's the fix.

*~1,900 lines of Python. Zero dependencies. Saves you an hour a day.*

> Built by [Desi Villanueva](https://github.com/dezgit2025)

[![PyPI](https://img.shields.io/pypi/v/auto-memory)](https://pypi.org/project/auto-memory/)
[![CI](https://github.com/dezgit2025/auto-memory/actions/workflows/test.yml/badge.svg)](https://github.com/dezgit2025/auto-memory/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-90%20passed-brightgreen)]()

**Zero-dependency CLI that turns Copilot CLI's local SQLite into instant recall — no MCP server, no hooks, read-only, schema-checked. ~50 tokens per prompt.**

**Works with:** GitHub Copilot CLI  
**Coming soon:** Claude Code · Cursor · Codex 

---

### Quickstart

```bash
pip install auto-memory        # or: git clone + ./install.sh
session-recall health          # verify it works
```

Point your agent at [`deploy/install.md`](deploy/install.md) and let it cook. 🍳

---

## The Problem

Every AI coding agent ships with a big number on the box. 200K tokens. Sounds massive. Here's what actually happens:

```
200,000  tokens — context window (theoretical max)
120,000  tokens — effective limit before context rot kicks in (~60%)
 -65,000  tokens — MCP tools
 -25,000  tokens — instruction files
=========
 ~30,000  tokens — what you ACTUALLY have before quality degrades
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
| **auto-memory** | None (stdlib) | ❌ Read-only | `pip install` | ✅ Instruction-file |
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

## Usage

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

## License

MIT
