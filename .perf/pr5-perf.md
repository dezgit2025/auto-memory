# PR #5 — Token & Latency Regression Review

**Branch:** `bug/issue-3-multistorage-recall` vs `origin/main`
**DB:** real `~/.copilot/session-store.db` on this Mac
**Note:** Report written to `.perf/pr5-perf.md` (the user asked for `/tmp/pr5-perf.md` but `/tmp` writes are forbidden by the runtime).

---

## 1. Token / byte cost — main vs PR

Token estimates use `bytes / 4` (cl100k_base proxy).

| command | main bytes | PR bytes | Δ bytes | main ~tok | PR ~tok | main med ms | PR med ms | Δ ms | PR max ms |
|---------|-----------:|---------:|--------:|----------:|--------:|------------:|----------:|-----:|----------:|
| `list --json --limit 10`     | 2,403 | 3,278 | **+36.4%** | 600 | 819   | 83.9 | 91.4 | +8.9% | 119.3 |
| `files --json --limit 10`    | 1,524 | 1,649 | +8.2%      | 381 | 412   | 79.1 | 81.2 | +2.7% | 83.4  |
| `search 'test' --limit 5`    | 3,226 | 5,933 | **+83.9%** | 806 | 1,483 | 83.3 | 85.3 | +2.4% | 102.3 |
| `repos --json` (PR-only)     | —     | 3,620 | new        | —   | 905   | —    | n/m  | —    | —     |

Median of 5 runs each, single-process startup included.

### Schema diff per row

* **list / files / search**: every row in PR has a new `"provider": "cli"` field.
* **search**: also adds `"repository"` to every row, **and renames `excerpt` → `content` while doubling its length** (`[:500]` chars vs the previous `[:250]`-style excerpt). This is the source of the +84% search bloat — not the new field.

Findings:

* `[HIGH]` token-bloat-search: `search` output is **+83.9%** (3.2 KB → 5.9 KB, ~806 → ~1,483 tokens). Tier-2 budget is "~200 tokens" — PR drives it to ~1.5K. Root cause: `excerpt` field replaced with `content` containing 500 chars instead of ~250. — `src/session_recall/providers/copilot_cli.py:175-…` (search), `src/session_recall/providers/file_backends.py:182` (`blob[:500]`).
* `[MED]` token-bloat-list: `list` output is **+36.4%** (~600 → ~819 tokens) — exceeds the 10% regression threshold. Cause: new `provider` field on every row + rename of `provider_name` strings on output. The Tier-1 "~50 tokens" promise is per-call and per-row; for 10 rows the absolute increase is +22 tokens/row of pure protocol metadata. — `src/session_recall/providers/copilot_cli.py:80`, `file_backends.py:57`.
* `[INFO]` token-files: `files` only +8.2% (under 10% threshold). Same `provider` field but smaller rows so relative impact is smaller.
* `[INFO]` token-repos: new `repos` command emits **905 tokens** for 20 rows — about **18× the Tier-1 budget**. Acceptable as a utility; problematic if any agent integration calls it on every prompt.

---

## 2. New `repos` command — placement

* README line 204 lists `repos` under utilities alongside `health` / `schema-check`, **not** the 3-tier ladder (lines 178-194). So docs-wise it is net-new surface, not a violation of the 3-tier promise.
* But the implementation (`src/session_recall/commands/repos.py:42-43`) calls `provider.list_sessions(repo="all", limit=500, days=30)` on **every active provider**. On the SQLite backend that's one indexed query (cheap). On any **file backend** it triggers parsing of up to 500 JSONL files via `_session_from_file` (see §4) — potentially seconds. On this Mac no file backend is available so we couldn't time it; on a real VS Code user's machine it will be the most expensive command in the suite.

Findings:

* `[INFO]` repos-doc: documented as a utility, not part of the 3-tier ladder. — `README.md:204`.
* `[MED]` repos-cost: `repos` runs `list_sessions(limit=500, days=30)` against every provider with **no early termination** and parses every JSONL file via the file backend. — `src/session_recall/commands/repos.py:42-43`.

---

## 3. Latency

(See table above.) On this machine **no file-backend was available** (see §4) so the latency delta only reflects added Python work in the CLI provider + arg-parsing for the new `--provider` flag.

* `[INFO]` latency-list: median +7.5 ms (+8.9%); max went 96 → 119 ms. Within noise but trending up.
* `[INFO]` latency-files / search: <3% delta on this machine. **Numbers will be very different on a Linux machine where `~/.config/Code/User/workspaceStorage` exists** — see §5.

---

## 4. Provider-discovery cost analysis (static)

### Discovery is run on every CLI invocation

`src/session_recall/providers/discovery.py:16-24` builds a fresh list of 4 candidate providers on every call and calls `is_available()` on each. There is **no module-level cache, no on-disk TTL cache, and no reuse across calls** (and there can't be — the CLI is a fresh process per invocation).

`is_available()` is cheap for all 4 providers — just `Path.exists()` checks. So discovery itself is not the problem.

### What IS expensive: `_FileSessionProvider._iter_files()` + `_session_from_file()`

`src/session_recall/providers/file_backends.py:28-44`:

```python
for root in self._roots:
    for pattern in self._patterns:
        for file_path in root.glob(pattern):       # rglob via "**/" patterns
            ...
files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
```

* **VSCodeProvider** uses pattern `**/chatSessions/*.jsonl` → recursive walk of the entire `workspaceStorage/` directory. No depth limit, no mtime cutoff before opening. — `file_backends.py:260`.
* **NeovimProvider** uses `**/*chat*.json` and `**/*chat*.jsonl` against `~/.config/github-copilot` AND `~/.local/share/nvim` — also recursive globs. — `file_backends.py:288-292`.
* **JetBrainsProvider** uses `chat-sessions/*` etc — single-level, OK.

After enumeration, every relevant call path (`list_sessions`, `search`, `repos`) calls `_session_from_file(fp)` which calls `_parse_turns(fp)` → opens, reads up to 5,000 lines, JSON-parses each line.

Worst-case for `list_sessions(limit=10)`:
* `_iter_files()` enumerates **all** matching files (not just 10), stats every one of them for sort, then `_session_from_file` is called on each until 10 pass the date filter.
* Because `_session_from_file` is invoked **before** the limit check in the loop (`file_backends.py:120-126`), even early termination still pays for full-parse of the first 10 files.
* For `search`, every file is parsed exhaustively until `limit` matches are found — worst case all of them.

### Parallelization

* `_iter_files()` iterates roots and patterns serially.
* Discovery iterates the 4 providers serially in `commands/*/run`.
* No `concurrent.futures`, `asyncio`, or threading anywhere in the new code.

### `Path.rglob` / `os.walk` / unbounded glob check

* `os.walk`: 0 occurrences (verified).
* `Path.rglob`: 0 occurrences.
* `Path.glob("**/...")` (functionally equivalent to `rglob`): **2 instances** — `file_backends.py:260` (VSCode) and `file_backends.py:292` (Neovim).
* `*` glob without recursion: 1 instance (`copilot_cli.py:32`, bounded by `state_root`, OK).

Findings:

* `[HIGH]` recursive-glob-vscode: `**/chatSessions/*.jsonl` walks entire `workspaceStorage/` on every call, no cache. — `src/session_recall/providers/file_backends.py:260`.
* `[HIGH]` recursive-glob-neovim: two `**/*chat*.json{,l}` patterns walk `~/.config/github-copilot` + `~/.local/share/nvim` on every call. — `src/session_recall/providers/file_backends.py:292`.
* `[HIGH]` parse-before-limit: file backend `list_sessions` parses up to 5,000 lines of every file before checking if it needs more results, defeating the `--limit 10` cost contract. — `src/session_recall/providers/file_backends.py:118-127`.
* `[MED]` no-mtime-prefilter: `_iter_files` stats every match for sort but never prunes by `--days` before opening files. A 30-day cutoff could skip 99% of historical workspaces cheaply. — `src/session_recall/providers/file_backends.py:43`.
* `[MED]` serial-providers: 4 providers iterated serially even for `list`/`search`/`repos`. With file backends present, total time = sum, not max. — `src/session_recall/commands/{list_sessions,search,repos,files}.py`.
* `[INFO]` no-discovery-cache: providers re-instantiated and re-checked every CLI call. Cheap today (only `exists()`), but not a place to add expensive checks later. — `src/session_recall/providers/discovery.py:16-24`.

---

## 5. Worst-case walkthrough — `list --json --limit 10`

Machine: Copilot CLI + 50 VS Code workspaces × 200 chat sessions + 1,000 JetBrains sessions + Neovim copilot history.

Step-by-step on PR branch:

1. `discover_providers` — 4 × `Path.exists()` ≈ <1 ms.
2. **CopilotCliProvider.list_sessions** — single SQLite query, ~5-30 ms (existing behaviour).
3. **VSCodeProvider.list_sessions** — `_iter_files()` does a recursive glob over 50 workspace dirs looking for `**/chatSessions/*.jsonl`. With 50 × 200 = 10,000 jsonl files, plus arbitrary subtrees of state/cache binaries, the **glob enumeration alone is ~200-2,000 ms**. Then `stat()` × 10,000 for sort: **~50-200 ms**. Then `_session_from_file` is invoked per file in mtime order until 10 pass the `--days 30` filter — but `_parse_turns` reads up to 5,000 lines × JSON-parses each, even for the first 10. JSONL parse for a 1 MB chat file is ~10-30 ms × 10 files ≈ **100-300 ms**.
4. **JetBrainsProvider.list_sessions** — similar pattern but flat-glob over 1,000 files. ~50-100 ms enumeration + 100-300 ms parse.
5. **NeovimProvider.list_sessions** — recursive glob over `~/.config/github-copilot` AND `~/.local/share/nvim`. Variable, often hundreds of ms.

Estimated total wall-time on that machine: **~600 ms – 3 s** for what was an ~80 ms call on `main`. **7-40× slowdown.**

Output token cost: still bounded by `--limit 10` so the **JSON payload stays around 800-900 tokens** (slightly higher because each row also carries `provider`). Token bloat is modest; **latency bloat is severe**.

Findings:

* `[HIGH]` worst-case-latency: on a real VS Code user's machine, `list --json --limit 10` can balloon from ~80 ms to **600-3,000 ms** — destroying the "instant recall" promise. — file-backed providers; see §4.
* `[INFO]` worst-case-tokens: token output stays bounded by `--limit`; the 200-token Tier-1 contract holds. Bloat is from per-row `provider` field only.

---

## 6. Caching opportunities

There is **no TTL cache** anywhere in the providers layer. Recommendations (for the author, not for this review):

* **Per-call memoization** for `_iter_files()` — at minimum, share the file list across `list_sessions` and `search` within a single CLI invocation.
* **On-disk index** (e.g. `~/.cache/session-recall/file-index.json`) keyed by `(root, pattern, mtime-of-root)` with a 5-minute TTL. Recursive glob over `workspaceStorage` is the perfect candidate.
* **mtime prefilter**: refuse to open files whose `stat().st_mtime` is older than `--days` cutoff. Removes 90%+ of work on a long-lived VS Code install.
* **Early termination**: in `list_sessions`, parse only the first `limit + small_buffer` files, not everything `_iter_files()` returned.
* **Parallelism**: `concurrent.futures.ThreadPoolExecutor(max_workers=4)` over providers would convert serial-sum to max-of-4.

Findings:

* `[MED]` no-cache: provider discovery and file enumeration have no caching layer. Worth adding a per-invocation memo + on-disk TTL index for file backends. — `src/session_recall/providers/{discovery,file_backends}.py`.

---

## Summary findings list

```
[HIGH] token-bloat-search:    search payload +83.9% (3.2KB → 5.9KB, ~806→~1,483 tok), violates Tier-2 ~200-tok budget — file_backends.py:182, copilot_cli.py:175+
[HIGH] recursive-glob-vscode: **/chatSessions/*.jsonl walks entire workspaceStorage/ every call — file_backends.py:260
[HIGH] recursive-glob-neovim: two **/*chat*.json{,l} patterns walk multiple roots every call — file_backends.py:292
[HIGH] parse-before-limit:    list_sessions parses up to 5,000 lines/file before --limit check — file_backends.py:118-127
[HIGH] worst-case-latency:    50-workspace VS Code user pays 600-3,000 ms for list --limit 10 (was ~80 ms) — file_backends.py
[MED]  token-bloat-list:      list payload +36.4% from new "provider" field on every row — copilot_cli.py:80, file_backends.py:57
[MED]  repos-cost:            repos command runs list_sessions(limit=500) on every provider with no early termination — repos.py:42-43
[MED]  no-mtime-prefilter:    _iter_files never prunes by --days before opening files — file_backends.py:43
[MED]  serial-providers:      4 providers iterated serially in every command — commands/*.py
[MED]  no-cache:              no TTL/memo cache for discovery or file enumeration — providers/{discovery,file_backends}.py
[INFO] token-files:           files payload +8.2%, under threshold — copilot_cli.py recent_files
[INFO] token-repos:           repos emits ~905 tokens — 18× Tier-1 budget; OK as utility
[INFO] repos-doc:             repos documented as utility, not part of 3-tier ladder — README.md:204
[INFO] latency-on-this-mac:   list +8.9%, files/search +<3% — Mac has no active file backends so file-walk cost is invisible
[INFO] no-discovery-cache:    providers rebuilt every call — discovery.py:16-24
[INFO] worst-case-tokens:     output stays ~800-900 tok regardless of file count; bloat is latency, not tokens
```

## Verdict

**Token regression: confirmed and material on `search` (+84%) and `list` (+36%).** Both exceed the 10% regression threshold. The added `provider` field is defensible; the doubled `content` field in search is not.

**Latency regression on this Mac: ~9% on `list`, negligible elsewhere.** But the Mac doesn't have any of the new file backends active — VS Code's macOS path is `~/Library/Application Support/Code/User/workspaceStorage` and the code only checks the Linux `~/.config/Code/...` path, so on macOS the multi-storage feature silently degrades to "Copilot CLI only". On Linux machines with real VS Code workspaceStorage, the recursive glob + per-file JSONL parse will inflate `list --limit 10` by **7-40×** and break the "instant recall" promise. That's the worst regression in the PR even though it's not visible from this machine's measurements.
