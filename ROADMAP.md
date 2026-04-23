# Roadmap

Planned work for auto-memory. Contributions welcome.

Current version: **0.1.0**

---

## Current State (v0.1.0)

`session-recall` is a zero-dependency Python CLI that gives AI agents instant recall of past sessions — ~50 tokens per context injection vs 10,000+ for blind re-exploration.

**Backends shipped:**
- **Copilot CLI** — reads `~/.copilot/session-store.db` (SQLite, read-only)
- **Claude Code** — scans `~/.claude/projects/` JSONL files, builds a local FTS5 index at `~/.claude/.sr-index.db`

**Commands:** `list`, `files`, `search`, `show`, `checkpoints`, `health`, `schema-check`, `cc-index`, `install-mode`

**Flags:** `--backend {copilot,claude}`, `--json`, `--limit`, `--days`, `--repo`

**Integration:** `SessionStart` hook in `~/.claude/settings.json` for Claude Code; `copilot-instructions.md` block for Copilot CLI.

**Backend abstraction:** `SessionBackend` ABC with six methods — adding a new backend requires implementing `list_sessions`, `list_files`, `search`, `show_session`, `health`, `is_available`.

---

## Planned Features

### HIGH Priority

#### 1. `--backend all` — unified multi-backend query

Merge results from every available backend in a single command invocation.

**Why:** Users running both Copilot CLI and Claude Code run two separate commands and mentally merge the output. A unified view is the natural evolution once two backends exist.

**Approach:**
- Add `"all"` to `--backend` choices; implement `backends/all.py` `AllBackend` that fans out to each available backend
- Deduplicate results by `(repository, summary_hash, created_at_minute)` then re-sort by recency
- `show` excluded from `all` mode — session IDs are backend-scoped; direct user to specify `--backend`
- `health` in `all` mode reports a dimension block per backend

**~120 LOC** (`backends/all.py` ~80, `__main__.py` ~40)

---

#### 2. `install-mode --project` — per-project `CLAUDE.md` block

Write a `CLAUDE.md` instruction block into the current repo so the integration is version-controlled and visible to all contributors.

**Why:** A global `settings.json` hook is invisible; a `CLAUDE.md` block is self-documenting and ships with the repo.

**Approach:**
- Add `--project` flag to `install-mode`; append a fenced block to `./CLAUDE.md`
- Block instructs Claude: "At the start of every session run `session-recall list --limit 5 --json`…"
- Guard with a sentinel comment (`<!-- session-recall -->`) to prevent duplicate writes on re-runs
- Add `--dry-run` to preview the diff without writing

**~90 LOC** (additions to `commands/install_mode.py` and `backends/claude_code/install.py`)

---

### MEDIUM Priority

#### 3. Cursor IDE backend

Read Cursor's per-workspace conversation history from its application data SQLite database.

**Why:** Cursor is the second most common AI-native editor. Users with large Cursor histories get nothing from the current backends.

**Approach:**
- `backends/cursor.py` implementing `SessionBackend`; `is_available()` checks for `~/Library/Application Support/Cursor/` (macOS), `%APPDATA%\Cursor\` (Windows), `~/.config/Cursor/` (Linux)
- Parse workspace storage SQLite key `workbench.panel.aichat.view.aichat.chatdata` (JSON conversation turns)
- Map Cursor schema to `SessionRecord`/`TurnRecord`; `repository` derived from workspace folder path

**~180 LOC** (`backends/cursor.py` + tests + `__init__.py` wiring)

---

#### 4. Aider backend

Parse `.aider.chat.history.md` files written by Aider into each project root.

**Why:** Aider is widely used for terminal-based AI coding. Its sessions are pure markdown — easy to parse — and contain high-signal file-edit history.

**Approach:**
- `backends/aider.py` implementing `SessionBackend`; `is_available()` returns True if any `.aider.chat.history.md` exists under a configurable root
- Parse with a simple state machine: `#### human` / `#### assistant` headings with timestamps
- In-memory index cached by file mtime (`functools.lru_cache`); `search` does case-insensitive substring scan — no FTS needed at this scale

**~160 LOC** (`backends/aider.py` + tests)

---

#### 5. MCP server mode

Expose `session-recall` as an MCP tool server so any MCP-compatible agent can query it without shell access.

**Why:** MCP is becoming the standard integration layer. An MCP server works in contexts where a `SessionStart` hook is not available (e.g. Claude Desktop, headless CI).

**Approach:**
- New `session-recall serve` subcommand; stdio-based MCP server via the `mcp` SDK (optional dep, guarded by `ImportError`)
- Three MCP tools: `session_list`, `session_search`, `session_show` — all accept a `backend` parameter
- `install-mode --mcp` appends the server entry to `~/.claude/claude_desktop_config.json`
- Packaged as `auto-memory[mcp]` optional extra on PyPI

**~200 LOC** (`commands/serve.py`, install helper additions, `__main__.py` wiring)

---

### LOW Priority

#### 6. `session-recall export` — archive sessions to markdown or JSON

Dump one or more sessions to a portable file for sharing or archiving.

**Approach:**
- `export` subcommand with `--format {md,json}`, `--output <file>`, `--session <id>`, `--repo`, `--days`, `--limit`
- Batch export all sessions matching filters as a multi-document file
- Reuses `show_session` from the active backend — no new backend methods

**~110 LOC**

---

#### 7. `session-recall prune` — expire old index entries

Remove sessions older than N days from `~/.claude/.sr-index.db`. Does not touch source JSONL files.

**Approach:**
- `prune` subcommand with `--days <N>` (default 90) and `--dry-run`
- `DELETE FROM cc_sessions WHERE last_seen < ?`; prints count of removed rows
- Claude Code backend only — Copilot backend is read-only

**~60 LOC**

---

#### 8. CI with GitHub Actions

pytest matrix across Python 3.10–3.13 on macOS, Linux, and Windows.

---

### FUTURE

#### 9. Cross-machine sync

Optional sync of the Claude Code index to a remote store (S3, GitHub Gist, HTTPS endpoint) so session context follows the user across machines.

**Design notes:**
- Index is a SQLite file — `litestream`-style replication or periodic upload/download are both viable
- Conflict resolution is append-only (newer `last_seen` wins per session row)
- Must be explicitly opt-in; transport must be user-controlled (privacy)
- Out of scope for v1

---

## Version Milestones

### v0.2 — Multi-backend + project integration
- [ ] `--backend all` aggregator with deduplication (`backends/all.py`)
- [ ] `install-mode --project` writes `CLAUDE.md` block
- [ ] `health` reports across all detected backends in `all` mode
- [ ] Full test coverage for new paths

### v0.3 — Ecosystem backends + MCP
- [ ] Cursor IDE backend (`backends/cursor.py`)
- [ ] Aider backend (`backends/aider.py`)
- [ ] MCP server mode (`session-recall serve`, `install-mode --mcp`)
- [ ] `--backend all` includes cursor and aider when detected

### v1.0 — Stable API + polish
- [ ] `export` command (markdown + JSON)
- [ ] `prune` command for index hygiene
- [ ] Stable `--json` output shapes documented and semver-committed
- [ ] Full CI matrix (Python 3.10–3.13, macOS + Linux + Windows)
- [ ] PyPI release with optional extras: `auto-memory[mcp]`
