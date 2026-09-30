# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/). Versioning: [SemVer](https://semver.org/).

## [0.6.0] — 2026-09-20

Available from the GitHub repository. This change does not itself publish a PyPI
release. AI-assisted generation remains experimental: synthetic lifecycle and
sandbox gates pass, but a successful live model repair has not yet been verified.

### Added

- Deterministic `session-recall-codex-fix` checker/planner and reviewed local
  profile-52-to-55 repair recipe, with explicit apply and digest-bound rollback.
- Stable Codex adapter launcher, reproducible pinned adapter artifacts, atomic
  activation journals, single-writer locking and interruption recovery.
- Synthetic smoke, crash, trust-boundary and isolated-wheel end-to-end tests.
  Unknown schemas still refuse in normal recall; explicit maintenance can stage a repair.
- Internal AI-repair budget contracts and durable ledger: approximate 32K blocks,
  explicit +32K human grants, truthful usage/overshoot reconciliation, single-use
  approvals and crash-safe recovery.
- Foreground `assist`, `approve`, `apply-candidate` and `budget-approve` commands:
  one Codex GPT-6 Astra medium job, strict candidate contracts, macOS sandbox
  verification, durable human review and existing managed activation/rollback.
  No automatic model retry, provider switch or startup integration.
- Versioned GPT-6 policy and requested/reported usage evidence, preserving legacy
  receipts and blocking new spending while legacy usage remains outstanding.
- V5 adversarial, mutation and clean-installed-wheel lifecycle verification,
  including damaged-candidate rollback and conflicting-approval rejection.
- Dated Codex repair explanation and ASCII flow near the top of README, with
  standalone version history, repository installation steps and source locations.
- Rebuilt 0.6.0 adapter bundles and a reviewed upgrade from the prior 0.5.1
  profile-55 adapter; old bundles remain available for explicit rollback.
- `session-recall-codex-fix --version` for checking the installed companion.

### Fixed

- Updated the Codex state schema profile to migration 52 (`projects recency`)
  after verifying that the adapter's used table definitions are unchanged.
- Advanced the reviewed Codex profile from state migration 52 to 55, including
  nullable `originator` and `daybreak_enabled` columns; history remains at 6.
  Unknown schemas still fail before session queries.
- Fixed calendar-dependent Codex CLI tests and added independent profile,
  query-blocking, boundary, output-invariance, and trial smoke verification.

## [0.5.1] — Packaging fix

### Fixed
- Wheel now ships `providers/codex/verifications/captured-profiles.json`
  (schema pre-flight data). v0.5.0's wheel omitted it, so every
  `session-recall-codex` data command crashed on a PyPI install
  (editable installs masked the gap). v0.5.0 should not be used.

## [0.5.0] — Codex CLI Support (trial)

### Added
- **Codex CLI provider** (`session-recall-codex`) — standalone read-only CLI over
  Codex CLI's SQLite storage (`~/.codex/state_5.sqlite` + `thread_history_1.sqlite`)
  - Trial build commands: `schema-check`, `list`, `repos` (search/show/files/health next phase)
  - Fixed-schema pre-flight on every data command: captured profiles
    `codex-state-v5-migration-52` / `codex-thread-history-v1-migration-6`;
    any drift refuses cleanly (exit 2/4) before any query
  - Sub-agent and archived threads excluded by default; `local:` workspaces
    hidden in `repos` unless `--include-local`
  - Exit-code contract: 0 ok / 1 not found / 2 usage-drift / 3 busy / 4 storage missing
  - Acceptance frozen before code: spec.yaml, synthetic fixtures, hashed verifiers,
    15-test read-only smoke set (`codex-test/codex-test-set.md`)
- **Docs** — `deploy/install-codex.md` (agent-runnable) + `codex-instructions-template.md`
  (global `~/.codex/AGENTS.md` block + self-routing repo block)

### Fixed
- `schema-check` human output collapses extra tables/indexes/triggers to per-side counts
- `repos` tie-break now newest-first on equal session counts
- CLI maps mid-query `sqlite3.Error` to clean exit 3 (no traceback)
- CI: pinned `ruff==0.15.12` in dev deps — unpinned ruff 0.16.x broke the lint
  gate on CI and blocked the v0.3.0/v0.4.0 PyPI publishes; removed unused imports

## [0.4.0] — Claude Code Support

### Added
- **Claude Code provider** (`session-recall-cc`) — separate CLI for Claude Code session recall
  - FTS5 full-text search over Claude Code JSONL sessions
  - Porter stemming, unicode61, prefix queries, bm25 column weighting
  - Incremental on-demand indexing with mtime cutoff
  - Symlink guard and bounded JSONL reads (security hardened)
  - WAL mode + busy_timeout for concurrent access
  - Auto-prune (configurable via `SESSION_RECALL_CC_PRUNE_DAYS`, default 90)
  - `session-recall-claude` alias
- **Sidecar entry point** — optional cron-based index pre-warming
  - `python -m session_recall.providers.claude_code.sidecar --once`
- **Agent-runnable install doc** — `deploy/install-claude-code.md`
  - Sentinel-bracketed CLAUDE.md instructions with cross-CLI safety
  - Per-repo default install (not global)
- **Token budget tests** for Claude Code provider output
- **`[claude]` pip extra** — decorative marker for discoverability

### Security
- FTS5 query injection prevention (reuses upstream `sanitize_fts5_query`)
- Symlink traversal guard on all filesystem operations
- Bounded JSONL reads (1MB line cap, 5000 line cap)
- No writes to user-owned config files (`~/.claude/settings.json`, `CLAUDE.md`, MCP config)

### Design
- **Process-level isolation** — `session-recall-cc` is a separate binary; bugs cannot affect `session-recall`
- **Env var gate** — requires `SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1`
- **Agent-driven recall** — no hooks, no auto-mutation; agent reads instruction file and decides
- **Cherry-picked from PR #8** (@osamarehman) with security hardening and architectural alignment

## [0.3.0] — 2026-04-30

### Added
- **Per-provider health dimensions** — `session-recall health --provider <name>` now shows 4 sub-dimensions per backend (Path Discovery, File Inventory, Recent Activity, Trust Model) instead of a single session-count check
- **Structured JSON health output** — `providers` dict in `--json` mode with per-provider dimensions for agent parsing (backward-compat: `dims` array preserved)
- **Helpful error messages** — requesting a disabled backend now shows how to enable it (`export SESSION_RECALL_ENABLE_FILE_BACKENDS=1`) instead of a cryptic "unavailable" error
- **Agent-runnable backend install guide** — `deploy/install-other-backends.md` walks agents through VS Code/JetBrains/Neovim setup with detection, confirmation prompts, idempotent shell snippets, troubleshooting, and rollback
- **"Works With" matrix in README** — all 4 backends visible above Quickstart with direct links to setup guides
- 26 new tests (13 unit + 7 integration + 6 E2E) — 197 total

### Changed
- README Health Check section expanded with per-provider examples, dimension table, JSON usage, and error guidance
- `deploy/install.md` prerequisites no longer require Copilot CLI — VS Code/JetBrains/Neovim are listed as alternatives
- `deploy/install-other-backends.md` verification steps use `health --provider` instead of `list --provider`

## [0.2.0] — 2026-04-28

### Added
- **Multi-storage provider architecture** — pluggable backends for VS Code, JetBrains, Neovim session recall (opt-in via `SESSION_RECALL_ENABLE_FILE_BACKENDS=1`)
- **Asymmetric lookback** — JSONL/file providers default to 5-day window, SQLite keeps 30-day. Override with `--days N` or `SESSION_RECALL_JSONL_DAYS=N`
- **`repos` command** — summarize discovered repositories across all providers
- **WSL/Linux support** — VS Code Server paths, XDG directory support
- **Security hardening:**
  - Symlink escape protection (`is_under_root` guard at all glob sites)
  - Trust level tagging (`_trust_level: trusted_first_party | untrusted_third_party`)
  - Sentinel fence wrapping for untrusted file-backed content
  - Bounded JSONL reader (`iter_jsonl_bounded`) — caps line size and count
  - mtime prefilter skips stale files before opening
- **Token budget regression tests** — list/search/files byte budgets enforced in CI
- **Adversarial security tests** — symlink escape, JSONL bomb, prompt injection, nested JSON
- **PyPI publish workflow** — tag `v*` triggers test → build → publish → GitHub Release (Trusted Publisher OIDC)
- **`--provider` flag** on all commands to select specific storage backend

### Changed
- `list` default `--limit` reverted from 50 to **10** (preserves ~50 token Tier-1 budget)
- Search results use `excerpt` field (250-char truncation) instead of `content` (500-char) — restores Tier-2 ~200 token budget
- Provider field shortened (`cli`/`vsc`/`jb`/`nv`) and omitted when single provider active — reduces per-row token overhead
- File-backed providers split into `providers/file/` subpackage (one file per provider, ≤200 LOC each)
- Copilot CLI provider split into `providers/copilot_cli/` subpackage
- `repos` command now calls `schema_problems()` before querying (matches all other commands)

### Fixed
- `_local_workspace_label` now deterministic — removed filesystem-dependent `is_dir()` branch (F1)
- macOS VS Code workspace path added to root candidates (F21)

## [0.1.0] — 2026-04-17

### Added
- Initial release — progressive session recall for GitHub Copilot CLI
- Commands: `list`, `search`, `show`, `files`, `checkpoints`, `health`, `schema-check`
- `--days N` filter on all query commands
- FTS5 query sanitization (7 crash bugs fixed)
- Zero runtime dependencies (stdlib only)
- WAL-safe SQLite with exponential backoff
- Schema validation on every CLI entry point
