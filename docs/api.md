# session-recall JSON API Reference

All `--json` output shapes are stable as of v1.0. Fields marked `[new in vX.Y]` may be
added in minor versions; no fields will be removed or renamed in a minor version.

This document describes the exact JSON emitted by every command that supports machine-readable
output. Use it as a contract when building tools, scripts, or integrations on top of
`session-recall`.

---

## Table of Contents

1. [list --json](#list---json)
2. [files --json](#files---json)
3. [search --json](#search---json)
4. [show --json](#show---json)
5. [health --json](#health---json)
6. [cc-index --status](#cc-index---status)
7. [install-mode --json](#install-mode---json)
8. [export --format json](#export---format-json)
9. [prune --json](#prune---json)

---

## list --json

List recent sessions, optionally scoped to a repository.

**Usage:**
```
session-recall list --json [--repo REPO] [--limit N] [--days N]
```

**Top-level envelope:**

```jsonc
{
  "repo":     "string",   // repo filter used, or "all" when no --repo flag
  "count":    "integer",  // number of sessions in the array
  "sessions": [ ... ]     // array of SessionSummary objects (see below)
}
```

**SessionSummary object:**

```jsonc
{
  "id_short":    "string",           // first 8 characters of the full session UUID
  "id_full":     "string",           // full session UUID (UUID v4)
  "repository":  "string | null",    // git remote origin / repo identifier
  "branch":      "string | null",    // git branch active during the session
  "summary":     "string | null",    // auto-generated one-line session summary
  "date":        "string",           // ISO date of last activity, YYYY-MM-DD
  "created_at":  "string",           // ISO datetime of session start (from index)
  "turns_count": "integer",          // number of conversation turns
  "files_count": "integer"           // number of distinct files touched
}
```

**Example:**

```json
{
  "repo": "all",
  "count": 2,
  "sessions": [
    {
      "id_short": "a1b2c3d4",
      "id_full": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "repository": "auto-memory",
      "branch": "main",
      "summary": "Added JSON output to prune command",
      "date": "2026-04-23",
      "created_at": "2026-04-23T14:05:01",
      "turns_count": 12,
      "files_count": 4
    },
    {
      "id_short": "b2c3d4e5",
      "id_full": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "repository": "auto-memory",
      "branch": "feature/health",
      "summary": "Implemented health check dimensions",
      "date": "2026-04-22",
      "created_at": "2026-04-22T09:30:00",
      "turns_count": 8,
      "files_count": 6
    }
  ]
}
```

---

## files --json

List recently touched files across sessions, optionally scoped to a repository.

**Usage:**
```
session-recall files --json [--repo REPO] [--limit N] [--days N]
```

**Top-level envelope:**

```jsonc
{
  "repo":  "string",   // repo filter used, or "all" when no --repo flag
  "count": "integer",  // number of file records in the array
  "files": [ ... ]     // array of FileRecord objects (see below)
}
```

**FileRecord object:**

```jsonc
{
  "file_path":  "string",   // absolute or repo-relative file path
  "tool_name":  "string",   // Claude Code tool that touched the file (e.g. "Write", "Edit", "Read"), or "unknown"
  "date":       "string",   // ISO date of the session that last touched this file, YYYY-MM-DD
  "session_id": "string"    // first 8 characters of the session UUID that last touched this file
}
```

**Example:**

```json
{
  "repo": "auto-memory",
  "count": 3,
  "files": [
    {
      "file_path": "src/session_recall/commands/prune.py",
      "tool_name": "Edit",
      "date": "2026-04-23",
      "session_id": "a1b2c3d4"
    },
    {
      "file_path": "src/session_recall/util/format_output.py",
      "tool_name": "Write",
      "date": "2026-04-22",
      "session_id": "b2c3d4e5"
    },
    {
      "file_path": "README.md",
      "tool_name": "Read",
      "date": "2026-04-21",
      "session_id": "c3d4e5f6"
    }
  ]
}
```

---

## search --json

Full-text search across all indexed session turns and summaries.

**Usage:**
```
session-recall search "<query>" --json [--repo REPO] [--limit N] [--days N]
```

**Top-level envelope:**

```jsonc
{
  "query":   "string",   // the search query as passed on the command line
  "count":   "integer",  // number of result rows
  "results": [ ... ]     // array of SearchResult objects (see below)
}
```

**SearchResult object:**

The fields come directly from the FTS5 index join and reflect the matched turn plus its
parent session metadata:

```jsonc
{
  "session_id":  "string",        // full session UUID of the matching turn
  "user_msg":    "string | null", // the user message text of the matching turn
  "summary":     "string | null", // the session-level summary
  "repository":  "string | null", // repository identifier of the session
  "branch":      "string | null", // git branch of the session
  "last_seen":   "string"         // ISO datetime of the session's last activity
}
```

**Example:**

```json
{
  "query": "health check",
  "count": 2,
  "results": [
    {
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "user_msg": "implement the health check command with 9 dimensions",
      "summary": "Implemented health check dimensions",
      "repository": "auto-memory",
      "branch": "feature/health",
      "last_seen": "2026-04-22T11:45:00"
    },
    {
      "session_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "user_msg": "add --json flag to health command",
      "summary": "Added JSON output to health command",
      "repository": "auto-memory",
      "branch": "main",
      "last_seen": "2026-04-21T09:00:00"
    }
  ]
}
```

---

## show --json

Show full detail for a single session, including all turns and files touched.

**Usage:**
```
session-recall show <session-id> --json [--turns N]
```

`<session-id>` may be a full UUID or any unambiguous prefix (minimum 8 characters).

**Output object:**

The top level is a single session detail object (not wrapped in an envelope).

```jsonc
{
  // --- session-level fields (from cc_sessions table) ---
  "id":          "string",          // full session UUID
  "cwd":         "string | null",   // working directory at session start
  "repository":  "string | null",   // git repository identifier
  "branch":      "string | null",   // git branch
  "summary":     "string | null",   // auto-generated one-line summary
  "first_seen":  "string",          // ISO datetime of first indexed activity
  "last_seen":   "string",          // ISO datetime of last indexed activity
  "turns_count": "integer",         // total turns in the session
  "files_count": "integer",         // total distinct files touched
  "version":     "string | null",   // Claude Code version that produced the JSONL file

  // --- turn array ---
  "turns": [
    {
      "session_id":        "string",        // parent session UUID (same as top-level id)
      "turn_index":        "integer",       // 0-based turn position
      "user_msg":          "string | null", // user message text
      "assistant_msg":     "string | null", // assistant response text
      "timestamp":         "string | null", // ISO datetime of the turn
      "assistant_summary": "string | null"  // per-turn assistant summary (if present)
    }
  ],

  // --- files array ---
  "files": [
    {
      "file_path": "string",  // path of the file that was touched
      "tool_name": "string"   // Claude Code tool used (e.g. "Write", "Edit", "Read")
    }
  ]
}
```

**Example:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "cwd": "/home/user/projects/auto-memory",
  "repository": "auto-memory",
  "branch": "main",
  "summary": "Added JSON output to prune command",
  "first_seen": "2026-04-23T14:05:01",
  "last_seen": "2026-04-23T14:32:10",
  "turns_count": 3,
  "files_count": 2,
  "version": "1.2.3",
  "turns": [
    {
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "turn_index": 0,
      "user_msg": "add --json flag to prune command",
      "assistant_msg": "I'll add the --json flag to the prune command now.",
      "timestamp": "2026-04-23T14:05:05",
      "assistant_summary": "Added --json flag"
    }
  ],
  "files": [
    {
      "file_path": "src/session_recall/commands/prune.py",
      "tool_name": "Edit"
    },
    {
      "file_path": "src/session_recall/__main__.py",
      "tool_name": "Read"
    }
  ]
}
```

---

## health --json

Run all 9 health-check dimensions and report an overall score.

**Usage:**
```
session-recall health --json
```

**Output object:**

```jsonc
{
  "overall_score": "number",  // minimum score across all scored dimensions (0.0–10.0)
  "dims": [ ... ],            // array of DimensionResult objects (see below), one per dimension
  "top_hints": [ "string" ]   // up to 3 actionable hint strings for non-GREEN dimensions
}
```

**DimensionResult object:**

```jsonc
{
  "name":   "string",          // human-readable dimension name (e.g. "DB Freshness")
  "score":  "number | null",   // dimension score (0.0–10.0); null if not applicable
  "zone":   "string",          // "GREEN", "AMBER", "RED", or "CALIBRATING"
  "detail": "string",          // short human-readable detail (e.g. "2.3h old")
  "hint":   "string | null"    // actionable fix hint; null when zone is GREEN
}
```

The 9 dimensions checked are, in order: DB Freshness, Schema, Latency, Corpus, Summary
Coverage, Repo Coverage, Concurrency, E2E, and Disclosure.

**Example:**

```json
{
  "overall_score": 7.0,
  "dims": [
    {
      "name": "DB Freshness",
      "score": 9.2,
      "zone": "GREEN",
      "detail": "2.3h old",
      "hint": "Use Copilot CLI — DB only updates from active sessions"
    },
    {
      "name": "Latency",
      "score": 7.0,
      "zone": "AMBER",
      "detail": "120ms p95",
      "hint": "Run cc-index --rebuild to compact the index"
    }
  ],
  "top_hints": [
    "Run cc-index --rebuild to compact the index"
  ]
}
```

---

## cc-index --status

Report the current state of the Claude Code session index without rebuilding it.

**Usage:**
```
session-recall cc-index --status
```

Note: `cc-index --status` does not accept a `--json` flag; it always emits JSON to stdout
via the same `output()` helper (which prints JSON when the value is not a list or
sessions-keyed dict).

**Output object:**

```jsonc
{
  "index_path":         "string",           // absolute path to the SQLite index file (~/.claude/.sr-index.db)
  "index_exists":       "boolean",          // whether the index file exists on disk
  "projects_dir":       "string",           // absolute path to the Claude Code projects directory (~/.claude/projects)
  "projects_dir_exists":"boolean",          // whether the projects directory exists

  // Only present when index_exists is true:
  "indexed_sessions":   "integer | string", // count of sessions in the index, or "error" if the DB is unreadable

  // Only present when indexed_sessions is "error":
  "index_error":        "string"            // SQLite error message
}
```

**Example (index exists):**

```json
{
  "index_path": "/home/user/.claude/.sr-index.db",
  "index_exists": true,
  "projects_dir": "/home/user/.claude/projects",
  "projects_dir_exists": true,
  "indexed_sessions": 47
}
```

**Example (index not yet built):**

```json
{
  "index_path": "/home/user/.claude/.sr-index.db",
  "index_exists": false,
  "projects_dir": "/home/user/.claude/projects",
  "projects_dir_exists": true
}
```

---

## install-mode --json

Detect Claude Code installation surfaces and optionally wire hooks or MCP config.

**Usage:**
```
session-recall install-mode --json [--setup] [--dry-run] [--project] [--project-path PATH] [--mcp]
```

**Output object:**

The base object is always present. Additional keys appear only when the corresponding
flag is supplied.

```jsonc
{
  // Always present
  "surfaces": [ ... ],   // array of SurfaceResult objects (see below)
  "detected": [ "string" ], // names of surfaces where detected=true

  // Present only when --setup or --dry-run is passed
  "hook_setup": {
    "changed":       "boolean",        // true when the settings file was modified
    "path":          "string",         // absolute path to ~/.claude/settings.json
    "action":        "string",         // "wired" | "already_wired" | "dry_run"
    "hook_command":  "string"          // the hook command string (only when action != "already_wired")
  },

  // Present only when --project or --project-path is passed
  "claude_md": {
    "action": "string",  // "written" | "updated" | "already_present" | "dry_run"
    "path":   "string",  // absolute path to the CLAUDE.md file
    "block":  "string"   // the block that would be written (only when action = "dry_run")
  },

  // Present only when --mcp is passed
  "mcp_config": {
    "changed": "boolean",  // true when the config file was modified
    "path":    "string",   // absolute path to claude_desktop_config.json
    "action":  "string"    // "wired" | "already_wired" | "dry_run"
  }
}
```

**SurfaceResult object:**

```jsonc
{
  "surface":  "string",   // surface identifier: "cli" | "vscode" | "jetbrains" | "desktop"
  "detected": "boolean",  // true if the surface was found on the current machine
  "path":     "string",   // path where the surface was found, or a "not found" description
  "note":     "string"    // human-readable description or install hint
}
```

**Example (detect only, no flags):**

```json
{
  "surfaces": [
    {
      "surface": "cli",
      "detected": true,
      "path": "/usr/local/bin/claude",
      "note": "Claude Code CLI"
    },
    {
      "surface": "vscode",
      "detected": true,
      "path": "/home/user/.vscode/extensions/anthropic.claude-code-1.0.0",
      "note": "VS Code extension"
    },
    {
      "surface": "jetbrains",
      "detected": false,
      "path": "/home/user/.config/JetBrains",
      "note": "Not installed"
    },
    {
      "surface": "desktop",
      "detected": false,
      "path": "not found",
      "note": "Not installed"
    }
  ],
  "detected": ["cli", "vscode"]
}
```

**Example (with --setup --dry-run):**

```json
{
  "surfaces": [ "... (same as above) ..." ],
  "detected": ["cli", "vscode"],
  "hook_setup": {
    "changed": true,
    "path": "/home/user/.claude/settings.json",
    "action": "dry_run",
    "hook_command": "session-recall list --json --limit 5"
  }
}
```

---

## export --format json

Export full session details (all turns and files) as a JSON array.

**Usage:**
```
session-recall export --format json [--session SESSION_ID] [--repo REPO] [--days N] [--limit N] [--output FILE]
```

When `--output` is provided the JSON is written to the file; otherwise it is printed to
stdout. The exit code is 0 on success.

**Output:**

A top-level JSON **array** where each element is a full session detail object identical in
shape to the object returned by [`show --json`](#show---json).

```jsonc
[
  {
    "id":          "string",
    "cwd":         "string | null",
    "repository":  "string | null",
    "branch":      "string | null",
    "summary":     "string | null",
    "first_seen":  "string",
    "last_seen":   "string",
    "turns_count": "integer",
    "files_count": "integer",
    "version":     "string | null",
    "turns": [
      {
        "session_id":        "string",
        "turn_index":        "integer",
        "user_msg":          "string | null",
        "assistant_msg":     "string | null",
        "timestamp":         "string | null",
        "assistant_summary": "string | null"
      }
    ],
    "files": [
      {
        "file_path": "string",
        "tool_name": "string"
      }
    ]
  }
]
```

**Example:**

```json
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "cwd": "/home/user/projects/auto-memory",
    "repository": "auto-memory",
    "branch": "main",
    "summary": "Added JSON output to prune command",
    "first_seen": "2026-04-23T14:05:01",
    "last_seen": "2026-04-23T14:32:10",
    "turns_count": 1,
    "files_count": 1,
    "version": "1.2.3",
    "turns": [
      {
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "turn_index": 0,
        "user_msg": "add --json flag to prune command",
        "assistant_msg": "Done — prune now emits JSON when --json is passed.",
        "timestamp": "2026-04-23T14:05:05",
        "assistant_summary": "Added --json flag"
      }
    ],
    "files": [
      {
        "file_path": "src/session_recall/commands/prune.py",
        "tool_name": "Edit"
      }
    ]
  }
]
```

---

## prune --json

Remove (or preview removal of) sessions from the Claude Code index that have not been
seen within the specified number of days.

**Usage:**
```
session-recall prune --json [--days N] [--dry-run]
```

**Output object:**

```jsonc
{
  "days":         "integer",        // the --days threshold used (default: 90)
  "removed":      "integer | null", // sessions actually deleted; 0 when --dry-run is set
  "would_remove": "integer | null", // sessions that would be deleted; null when not a dry run
  "dry_run":      "boolean"         // true when --dry-run was passed
}
```

**Example (live run):**

```json
{
  "days": 90,
  "removed": 5,
  "would_remove": null,
  "dry_run": false
}
```

**Example (dry run):**

```json
{
  "days": 90,
  "removed": 0,
  "would_remove": 5,
  "dry_run": true
}
```
