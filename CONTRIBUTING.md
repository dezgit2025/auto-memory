# Contributing to auto-memory

Thanks for your interest in contributing! Whether it's a bug fix, docs improvement, or new feature — all contributions are welcome.

## Quick Start

```bash
git clone https://github.com/dezgit2025/auto-memory.git
cd auto-memory
pip install -e ".[dev]"
pytest src/session_recall/tests/ -q
```

## Good First Issues

Look for issues labeled [`good first issue`](https://github.com/dezgit2025/auto-memory/labels/good%20first%20issue) — these are scoped and beginner-friendly. Documentation fixes and typo corrections are always welcome too.

## Code Style (preferred, not enforced)

We prefer small, focused files:

- **≤80 lines per file** when practical
- **One function per file** (or a tightly coupled group of 2-3)
- **stdlib only** — no external runtime dependencies
- **Relative imports** within the package

These are guidelines, not gates. Don't let style concerns stop you from submitting a PR — we'll work through it together in review.

## Adding a Subcommand

1. Create `src/session_recall/commands/your_command.py` with `def run(args) -> int`
2. Add argparse subparser in `__main__.py`
3. Add dispatch `elif` in `__main__.py`
4. Add tests in `tests/test_your_command.py`

## Adding a Health Dimension

1. Create `src/session_recall/health/dim_your_dim.py` with `def check() -> dict`
2. Return `{"name", "score", "zone", "detail", "hint"}`
3. Import and add to `DIMS` list in `commands/health.py`

## PR Checklist

Before submitting:

- [ ] Tests pass: `pytest src/session_recall/tests/ -q`
- [ ] Lint passes: `ruff check src/`
- [ ] No new runtime dependencies added
- [ ] Docs updated if behavior changed

## Questions?

Open an issue or start a discussion — happy to help.
