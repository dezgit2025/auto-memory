# auto-memory — Pre-Public-Release Findings

_Generated: 2026-04-21 from parallel fleet review (security, viral-readiness, code-quality sub-agents)._

---

## 🚨 BLOCKERS — Fix before going public

### 1. ~~Real identity in git history~~ ✅ DONE
~~Git history contains real name/email on every commit.~~
**Fixed:** Used `git filter-repo --mailmap` to unify all 13 commits under `Desi Villanueva <217994822+dezgit2025@users.noreply.github.com>`. The 2 commits using `desi <desi4k@gmail.com>` were rewritten.

### 2. ~~README says "8-dimension health check" but code has 9~~ ✅ DONE
**Fixed:** Updated README.md line 43 to "9-dimension health check".

### 3. `CHANGELOG.md` is in `.gitignore` but exists in repo — ✅ NO ACTION NEEDED
**Verified:** `CHANGELOG.md` is in `.gitignore` and is NOT tracked by git. The `.gitignore` rule is working correctly.

---

## ⚠️ WARNINGS — Should fix

| # | Item | Fix |
|---|------|-----|
| 1 | ~~Owner's name not in README~~ | ✅ Added byline `> Built by [Desi Villanueva](https://github.com/dezgit2025)` |
| 2 | ~~`SECURITY.md` says "Email:"~~ | ✅ Reworded to "**Report via** GitHub Security Advisory" |
| 3 | ~~Silent DB lock failure~~ | ✅ Added stderr message before `sys.exit(3)` in `db/connect.py` |
| 4 | ~~Nested fenced code blocks~~ | ✅ Fixed with 4-backtick outer fence in `deploy/install.md` |
| 5 | ~~`pyproject.toml` metadata minimal~~ | ✅ Added authors, readme, urls, keywords, classifiers |
| 6 | No CI workflow | 🔲 TODO: Add `.github/workflows/test.yml` — matrix Python 3.10/3.11/3.12, pytest + ruff |
| 7 | ~~Unpinned dev deps~~ | ✅ Pinned `pytest>=8`, `ruff>=0.6` |
| 8 | ~~881 pytest deprecation warnings~~ | ✅ Fixed `utcnow()` in source + test files — 0 warnings now |
| 9 | ~~`.gitignore` missing patterns~~ | ✅ Added `*.sqlite-wal`, `*.sqlite-shm`, `.envrc`, `.python-version`, `.pypirc` |
| 10 | CHANGELOG uses dates not semver | 🔲 TODO: Switch to `## [0.1.0] - YYYY-MM-DD` + `## [Unreleased]` sections |

**Good news — no leaked secrets.** Scanned for `sk-`, `ghp_`, `AKIA`, `xoxb-`, `Bearer`, `password=`, `api_key`, `SAS=`, etc. — clean across working tree AND git history. No unsafe SQL or path traversal. 90/90 tests passing. Zero-deps claim verified.

---

## 🚀 VIRAL GROWTH — High-impact additions

### README hero section (paste near top)

```md
# auto-memory

> **Your AI coding agent never forgets.**
> Built by [Desi Villanueva](https://github.com/dezgit2025)

[![PyPI](https://img.shields.io/pypi/v/auto-memory)](https://pypi.org/project/auto-memory/)
[![CI](https://github.com/OWNER/auto-memory/actions/workflows/test.yml/badge.svg)](...)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)

Zero-dependency CLI that turns Copilot CLI's local SQLite session store into
instant recall — no MCP server, no hooks, read-only, schema-checked.
```

### GitHub "About" description (paste in repo settings)

> Zero-dependency Python CLI that gives AI coding agents instant recall of Copilot CLI sessions, files, and checkpoints from local SQLite — read-only, schema-checked, MCP-free.

### Suggested GitHub topics (repo settings → topics)

`python` `cli` `copilot-cli` `github-copilot` `ai-tools` `developer-tools` `agentic-ai` `sqlite` `fts5` `session-management` `context-window` `llm` `zero-dependency` `memory` `recall` `productivity` `prompt-engineering` `claude-code` `cursor` `aider`

### Missing files for serious OSS

- `CODE_OF_CONDUCT.md` (Contributor Covenant)
- `.github/workflows/test.yml` (CI)
- `.github/ISSUE_TEMPLATE/bug_report.md` + `feature_request.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/dependabot.yml`
- `.github/FUNDING.yml` (optional — for sponsors)

### High-impact README additions

1. **Comparison table** vs MCP servers / hooks / manual grep / auto-memory (key differentiator)
2. **asciinema cast or animated GIF** of `session-recall health` — the colored health dashboard is the strongest visual
3. **FAQ**: Is it read-only? Does it work with Claude Code/Cursor/Aider? What if Copilot's schema changes?
4. **Roadmap** section (shows momentum)
5. **Call to action** at bottom: ⭐ star + share
6. **Broaden integration story** — ship templates for Claude Code, Cursor, Aider, not Copilot-only. Triples the addressable audience.

### Launch blurb (HN / Reddit / X)

> Copilot CLI already remembers everything locally in SQLite. **auto-memory** gives it a ~50-token recall layer — no MCP server, no hooks, no deps, read-only, schema-checked. 9 health dimensions, 90 tests, stdlib-only.

### CONTRIBUTING.md is too restrictive

The "one function per file / ≤80 lines" rules are internal style, but will scare off casual contributors. Soften it: keep them as "preferred style" not mandate, and add a PR checklist + "good first issue" note.

---

## 📋 Prioritized Top-10 Checklist

1. ~~Rewrite git history to unify identity~~ ✅
2. ~~Add "Built by Desi Villanueva" byline to README~~ ✅
3. ~~Fix README "8 → 9" health dimension mismatch~~ ✅
4. ~~`CHANGELOG.md` `.gitignore` status~~ ✅ (verified — working correctly)
5. Add badges + GIF/asciinema to README hero 🔲
6. ~~Fix `deploy/install.md` nested code fence~~ ✅
7. ~~Flesh out `pyproject.toml` metadata~~ ✅
8. Add `.github/workflows/test.yml` for CI 🔲
9. ~~Fix `datetime.utcnow()` deprecation~~ ✅
10. Add CODE_OF_CONDUCT, ISSUE_TEMPLATE, PR template, dependabot 🔲

---

## Raw Agent Reports

### Security audit
- No leaked secrets in working tree or git history (all common patterns scanned)
- No unsafe SQL / path traversal in `search.py:73-90`, `show_session.py:30-63`, `files.py:27-33`, `db/schema_check.py:16`
- `install.sh:8-16` safe: no `curl | bash`, no `sudo`, local editable install only
- Git history identity leak (see Blocker #1)
- `.gitignore` gaps: `*.sqlite-wal`, `*.sqlite-shm`, `.envrc`, `.python-version`, `.pypirc`

### Code quality
- 90/90 tests passing, 881 deprecation warnings (datetime.utcnow)
- Zero-deps claim verified (`pyproject.toml:12` `dependencies = []`)
- Console script `session-recall` resolves correctly
- `python3 -m session_recall` fails from checkout (src layout not on PYTHONPATH unless installed)
- No CI, no lint/type config, minimal packaging metadata

### Viral readiness
- README hero weak, no byline, no badges, no visual
- Quickstart not obvious in <30s (pushes to `deploy/install.md`)
- Missing FAQ, roadmap, comparison table, CTA, credits
- Integration story Copilot-only — broaden to Claude Code / Cursor / Aider for 3x reach
- CONTRIBUTING.md too restrictive for casual contributors
- CHANGELOG should use semver sections, not pure dates
