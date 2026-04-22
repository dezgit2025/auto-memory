"""Session store connection abstraction.

Supports both SQLite (for older Copilot CLI) and JSONL (for 1.0.34+).
Automatically detects available storage format.
"""
import pathlib
import sqlite3
import sys
from typing import Union

from .jsonl_store import JSONLStore


def connect_ro(db_path: str) -> Union[sqlite3.Connection, "JSONLStoreAdapter"]:
    """Open read-only connection to session store.

    Tries SQLite first, falls back to JSONL if database doesn't exist.
    """
    db_file = pathlib.Path(db_path)

    # Try SQLite if database file exists
    if db_file.exists():
        return _connect_sqlite(db_path)

    # Fall back to JSONL from ~/.copilot/session-state
    session_dir = pathlib.Path.home() / ".copilot" / "session-state"
    if session_dir.exists():
        return JSONLStoreAdapter()

    # Neither format found
    print("error: no session data found", file=sys.stderr)
    print(f"  tried: {db_path}", file=sys.stderr)
    print(f"  tried: {session_dir}", file=sys.stderr)
    sys.exit(4)


def _connect_sqlite(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite database."""
    RETRY_DELAYS_MS = [50, 150, 450]

    for delay in [0] + RETRY_DELAYS_MS:
        if delay:
            import random
            import time
            time.sleep(delay * random.uniform(0.8, 1.2) / 1000)
        try:
            conn = sqlite3.connect(
                f"file:{db_path}?mode=ro",
                uri=True,
                timeout=0.5,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 500")
            conn.execute("PRAGMA query_only = ON")
            return conn
        except sqlite3.OperationalError as e:
            if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                raise

    print("error: database is locked — another session-recall process may be running", file=sys.stderr)
    raise SystemExit(3)


class JSONLStoreAdapter:
    """Adapter to make JSONLStore look like sqlite3.Connection."""

    def __init__(self):
        """Initialize store."""
        self.store = JSONLStore()

    def execute(self, sql: str, params: tuple = ()) -> "QueryResultAdapter":
        """Execute query."""
        result = self.store.query(sql, params)
        return QueryResultAdapter(result)

    def close(self) -> None:
        """Close (no-op for in-memory store)."""
        pass


class QueryResultAdapter:
    """Adapter to make QueryResult look like sqlite3.Cursor."""

    def __init__(self, result):
        """Initialize with query result."""
        self.result = result

    def fetchall(self) -> list:
        """Return all rows."""
        rows = self.result.fetchall()
        # Convert dicts to Row-like objects
        return [_DictRow(r) for r in rows]

    def fetchone(self):
        """Return first row."""
        row = self.result.fetchone()
        if row is None:
            return None
        dict_row = _DictRow(row)
        # For COUNT queries, try to return the count value
        # This is a hack but necessary for compatibility
        return dict_row


class _DictRow:
    """Dict wrapper that supports both dict and Row-like access."""

    def __init__(self, data: dict):
        """Initialize with dict data."""
        self._data = data

    def __getitem__(self, key):
        """Support row[key] access."""
        # Support both dict-style keys and index-based access
        if isinstance(key, int):
            # Index-based access (e.g., row[0])
            if key < len(self._data):
                return list(self._data.values())[key]
            raise IndexError(f"Index {key} out of range")
        return self._data.get(key)

    def get(self, key, default=None):
        """Support row.get(key) access."""
        return self._data.get(key, default)

    def keys(self):
        """Support dict(row) conversion."""
        return self._data.keys()

    def values(self):
        """Support dict(row) conversion."""
        return self._data.values()

    def items(self):
        """Support dict(row) conversion."""
        return self._data.items()

    def __iter__(self):
        """Support dict(row) conversion."""
        return iter(self._data)
