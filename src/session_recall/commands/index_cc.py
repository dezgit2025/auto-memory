"""cc-index command — build or update the Claude Code session index."""
import errno
import sqlite3
import sys

from ..util.format_output import output


def run(args) -> int:
    try:
        from ..backends.claude_code.detect import CC_PROJECTS_DIR
        from ..backends.claude_code.index import INDEX_PATH, build_index
    except ImportError as e:
        print(f"error: Claude Code backend unavailable: {e}", file=sys.stderr)
        return 1

    json_mode = getattr(args, "json", False)

    if getattr(args, "status", False):
        data = _status_data(INDEX_PATH, CC_PROJECTS_DIR)
        output(data, json_mode=json_mode)
        return 0

    rebuild = getattr(args, "rebuild", False)
    print(
        f"{'Rebuilding' if rebuild else 'Updating'} Claude Code session index...",
        file=sys.stderr,
    )

    try:
        stats = build_index(rebuild=rebuild, verbose=True)
    except PermissionError as e:
        print(f"error: permission denied writing index — {e}", file=sys.stderr)
        return 1
    except OSError as e:
        if e.errno == errno.ENOSPC:
            print(f"error: disk full — cannot write index to {INDEX_PATH}", file=sys.stderr)
        else:
            print(f"error: I/O error building index — {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: index build failed — {e}", file=sys.stderr)
        return 1

    data = {
        "indexed": stats["indexed"],
        "skipped": stats["skipped"],
        "errors": stats.get("errors", 0),
        "total_files": stats["total"],
        "index_path": str(INDEX_PATH),
    }
    output(data, json_mode=json_mode)
    return 0


def _status_data(index_path, projects_dir) -> dict:
    data = {
        "index_path": str(index_path),
        "index_exists": index_path.exists(),
        "projects_dir": str(projects_dir),
        "projects_dir_exists": projects_dir.exists(),
    }
    if not index_path.exists():
        return data

    conn = None
    try:
        conn = sqlite3.connect(str(index_path))
        row = conn.execute("SELECT COUNT(*) as n FROM cc_sessions").fetchone()
        data["indexed_sessions"] = row[0] if row else 0
    except sqlite3.DatabaseError as e:
        data["indexed_sessions"] = "error"
        data["index_error"] = str(e)
        print(f"warning: could not read index: {e}", file=sys.stderr)
    finally:
        if conn:
            conn.close()
    return data
