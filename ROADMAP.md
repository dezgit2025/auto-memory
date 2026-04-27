# Roadmap

Planned work for auto-memory. Contributions welcome.

Current version: **0.1.0**

---

## Current State (v0.1.0)

`session-recall` is a zero-dependency Python CLI that gives AI agents instant recall of past sessions — ~50 tokens per context injection vs 10,000+ for blind re-exploration.

**Backends shipped:**
- **Copilot CLI** — reads `~/.copilot/session-store.db` (SQLite, read-only)
- **Claude Code** — scans `~/.claude/projects/` JSONL files, builds a local FTS5 index at `~/.claude/.sr-index.db`
- **Cursor IDE** — reads per-workspace `state.vscdb` SQLite files
- **Aider** — parses `.aider.chat.history.md` files

**Commands:** `list`, `files`, `search`, `show`, `checkpoints`, `health`, `schema-check`, `cc-index`, `install-mode`, `export`, `prune`

**Flags:** `--backend {copilot,claude,cursor,aider,all}`, `--json`, `--limit`, `--days`, `--repo`

**Integration:** `SessionStart` hook in `~/.claude/settings.json` for Claude Code; `CLAUDE.md` block via `install-mode --project`.

**Backend abstraction:** `SessionBackend` ABC with six methods — adding a new backend requires implementing `list_sessions`, `list_files`, `search`, `show_session`, `health`, `is_available`.

---

## Planned Features

### HIGH Priority

#### 1. Assistant message indexing (FTS search gap)

The FTS5 index currently stores only user messages. Technical terms introduced in assistant responses (e.g. "backend abstraction", "atomic write", "FTS5 index") are not searchable.

**Why:** `search "backend abstraction"` returns 0 results even though the concept was central to a session — because the phrase lived in assistant turns, not user turns.

**Approach:**
- Index a truncated summary of `assistant_msg` alongside `user_msg` in `cc_turns` (≤300 chars)
- Alternatively: extract file paths and tool names touched in that turn as a synthetic text field
- Keeps index size reasonable while covering the most useful technical terms
- Schema migration: add `assistant_summary TEXT` column; rebuild index via `cc-index --rebuild`

**~60 LOC** (changes to `reader.py`, `index.py` DDL + build loop)

---

#### 2. MCP server mode

Expose `session-recall` as an MCP tool server so any MCP-compatible agent can query it without shell access.

**Why:** MCP is becoming the standard integration layer. An MCP server works in contexts where a `SessionStart` hook is not available (e.g. Claude Desktop, headless CI).

**Approach:**
- New `session-recall serve` subcommand; stdio-based MCP server via the `mcp` SDK (optional dep, guarded by `ImportError`)
- Three MCP tools: `session_list`, `session_search`, `session_show` — all accept a `backend` parameter
- `install-mode --mcp` appends the server entry to `~/.claude/claude_desktop_config.json`
- Packaged as `auto-memory[mcp]` optional extra on PyPI

**~200 LOC** (`commands/serve.py`, install helper additions, `__main__.py` wiring)

---

### MEDIUM Priority

#### 3. CI with GitHub Actions

pytest matrix across Python 3.10–3.13 on macOS, Linux, and Windows.

---

### LOW Priority

#### 4. Stable API documentation

Document and semver-commit all `--json` output shapes.

---

### FUTURE

#### 5. Cross-machine sync

Optional sync of the Claude Code index to a remote store (S3, GitHub Gist, HTTPS endpoint) so session context follows the user across machines.

**Design notes:**
- Index is a SQLite file — `litestream`-style replication or periodic upload/download are both viable
- Conflict resolution is append-only (newer `last_seen` wins per session row)
- Must be explicitly opt-in; transport must be user-controlled (privacy)
- Out of scope for v1

---

## Version Milestones

### v0.2 ✅ — Multi-backend + project integration
- [x] `--backend all` aggregator with deduplication (`backends/all.py`)
- [x] `install-mode --project` writes `CLAUDE.md` block
- [x] `health` reports across all detected backends in `all` mode
- [x] Full test coverage for new paths

### v0.3 ✅ — Ecosystem backends
- [x] Cursor IDE backend (`backends/cursor.py`)
- [x] Aider backend (`backends/aider.py`)
- [x] `--backend all` includes cursor and aider when detected
- [x] `export` command (markdown + JSON)
- [x] `prune` command for index hygiene
- [ ] MCP server mode (`session-recall serve`, `install-mode --mcp`)

### v1.0 — Stable API + polish
- [ ] Assistant message indexing (FTS search gap fix)
- [ ] Stable `--json` output shapes documented and semver-committed
- [ ] Full CI matrix (Python 3.10–3.13, macOS + Linux + Windows)
- [ ] PyPI release with optional extras: `auto-memory[mcp]`
