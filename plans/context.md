# Session Context — auto-memory

> Overwrite this before /clear. Keep it tight.

## What This Project Is
Zero-dependency Python CLI (`session-recall`) that gives AI coding agents persistent memory by querying Copilot CLI's session store. v0.2.0 adds multi-storage provider support (VS Code, JetBrains, Neovim) with security hardening.

## Last 5 Tasks Completed
1. **All 6 phases of PR #5 remediation** — 21 findings addressed, 26 todos completed across foundation fixes, restructure, security, regression tests, conventions, and documentation
2. **WSL/Linux compatibility** — VS Code Server paths, XDG dirs, WSL detection helper
3. **PyPI publish workflow** — `.github/workflows/publish.yml` with Trusted Publisher OIDC, auto-publish on tag push
4. **CI verified green** — Python 3.10/3.11/3.12 all passing on GitHub Actions (PR #11)
5. **Version bumped to 0.2.0** — pyproject.toml, `__version__`, CHANGELOG.md reformatted to Keep a Changelog

## Current Verified State
- 171 tests passing locally ✅
- CI green on all 3 Python versions ✅
- Lint clean (ruff) ✅
- PR #11 open and ready for merge ✅
- PyPI Trusted Publisher configured ✅
- CHANGELOG.md tracked (removed from .gitignore) ✅
- docs/pr5-docs.md generated (local-only, gitignored) ✅

## What's Next
1. **Merge PR #11** to main
2. **Tag v0.2.0** → `git tag v0.2.0 && git push origin v0.2.0` → auto-publishes to PyPI + creates GitHub Release
3. **Verify PyPI publish** succeeded: `pip install --upgrade auto-memory` should get 0.2.0
4. Post MS Teams + LinkedIn announcements (drafts ready)

## Key Files
| Purpose | Path |
|---------|------|
| Package config | `pyproject.toml` (v0.2.0) |
| Main entry | `src/session_recall/__main__.py` |
| Provider discovery | `src/session_recall/providers/discovery.py` |
| CLI provider | `src/session_recall/providers/copilot_cli/` |
| File backends | `src/session_recall/providers/file/` |
| Config (env vars) | `src/session_recall/config.py` |
| PR review plan | `plans/pr5-plan.md` |
| Progress tracker | `plans/progress.md` |
| Install guide | `deploy/install.md` |
| CI publish | `.github/workflows/publish.yml` |
| CHANGELOG | `CHANGELOG.md` |

## Run Before Release (in order)
```bash
pytest src/ -q              # 171 tests
ruff check src/             # lint clean
session-recall health       # local sanity
git tag v0.2.0 && git push origin v0.2.0  # triggers PyPI publish
```
