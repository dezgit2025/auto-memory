# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/). Versioning: [SemVer](https://semver.org/).

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
