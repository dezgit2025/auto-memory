# Changelog

## 2026-04-17 — `--days` Filter Across All Commands

Added `--days N` flag to `search`, `files`, and `checkpoints` commands. `list` already had it — now all four commands support consistent time-range filtering.

### Usage

```bash
session-recall list --days 2        # sessions from last 2 days
session-recall search mcp --days 5  # search only last 5 days
session-recall files --days 7       # files touched in last 7 days
session-recall checkpoints --days 3 # checkpoints from last 3 days
```

### Implementation

- Added `--days` argparse entries for 3 missing subcommands in `__main__.py`
- Wired `AND <timestamp_col> >= datetime('now', '-N days')` filter into SQL of each command
- `None` (no flag) → no filter applied (defaults to behavior pre-change for those commands; `list` still defaults to 30 days)

### Tests

18 new tests in `tests/test_days_filter.py` covering:
- Boundary ages (0d / 3d / 10d / 60d sessions)
- Each command with `--days 1/7/30/None`
- `--repo` + `--days` combinations
- Edge cases: `days=0`, empty search query + `--days`, `days=3650`

Full suite: **49/49 passing** (31 existing + 18 new).

**Commit:** `6c461a8`

---

## 2026-04-17 — FTS5 Query Sanitization

**7 bugs fixed** in `session-recall search`:

### 🔴 Critical — 5 crash bugs

Queries containing FTS5 special characters (`. - () {} [] ^ ~ * : /`) or empty strings crashed with `sqlite3.OperationalError: fts5 syntax error`.

| Query | Before | After |
|-------|--------|-------|
| `CLAUDE.md` | 💥 CRASH | ✅ 2 results |
| `session-recall` | 💥 CRASH | ✅ 2 results |
| `function()` | 💥 CRASH | ✅ 2 results |
| `test.py` | 💥 CRASH | ✅ 2 results |
| `""` (empty) | 💥 CRASH | ✅ 0 results + warning |

**Root cause:** User input passed raw into FTS5 `MATCH` clause. FTS5 interprets `.` `-` `()` as query operators.

**Fix:** New `sanitize_fts5_query()` function in `commands/search.py`:
- Tokens with special chars → wrapped in double quotes for literal matching
- Empty/whitespace queries → graceful return (no crash)

### 🟠 High — No prefix matching

| Query | Before | After |
|-------|--------|-------|
| `OAuth` | 0 results | ✅ 3 results |
| `deploy` | varied | ✅ 2 results |

**Fix:** Normal tokens get `*` suffix for FTS5 prefix matching (`OAuth` → `OAuth*`).

### Tests

13 new tests in `tests/test_search_sanitize.py`. Full suite: 31/31 passing.

**Commit:** `9a9c41c`
