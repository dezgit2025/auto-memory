# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Claude Code provider** — recall sessions from Anthropic Claude Code's
  per-session JSONL files at `~/.claude/projects/<slug>/<session-uuid>.jsonl`.
  Mirrors the existing VS Code / JetBrains / Neovim file-backed provider
  pattern (~30-line subclass of `_FileSessionProvider`). Closes the
  "Coming soon: Claude Code" gap in the v0.2.0 README.
  - Provider id: `claude_code` (output short code: `cc`)
  - Default root: `~/.claude/projects` (override via
    `SESSION_RECALL_CLAUDE_CODE_ROOT`)
  - Opt-in via `SESSION_RECALL_ENABLE_FILE_BACKENDS=1` (consistent with
    the other file providers)
  - Subagent transcripts (`<slug>/subagents/agent-*.jsonl`) are
    intentionally excluded — they're tool-call children of the parent
    session, not recall-worthy in their own right
  - Compatible with CC's actual JSONL schema: events with `type`,
    `message`, `timestamp`, `cwd`, `gitBranch`, `sessionId`, `uuid` keys.
    The shared `_extract_role` / `_extract_text` helpers recurse through
    both flat-string `message` and nested `message: {role, content: [...]}`
    shapes without modification
- 13 unit tests covering provider id / short-code, availability detection,
  top-level vs subagent globbing, turn counting, default-root resolution
  (via `monkeypatch.setattr` on `Path.home`), nested-message text
  extraction, empty file handling, and malformed JSONL line skipping
- `claude_code` added to the `--provider` argparse choices on all 8
  CLI subcommands (`list`, `files`, `search`, `show`, `checkpoints`,
  `repos`, `health`, `schema-check`)

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
