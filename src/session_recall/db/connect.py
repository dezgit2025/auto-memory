"""Read-only SQLite connection with exponential backoff retry."""
import sqlite3
import pathlib
import random
import sys
import time

RETRY_DELAYS_MS = [50, 150, 450]


class DatabaseBusyError(Exception):
    """Database remained locked/busy after bounded retries."""


def connect_ro_raising(db_path: str) -> sqlite3.Connection:
    """Open read-only connection; raise instead of exiting on failure.

    Raises FileNotFoundError if the database file is missing, and
    DatabaseBusyError if it stays locked after bounded retries.
    """
    if not pathlib.Path(db_path).exists():
        raise FileNotFoundError(db_path)
    for delay in [0] + RETRY_DELAYS_MS:
        if delay:
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
    raise DatabaseBusyError(db_path)


def connect_ro(db_path: str) -> sqlite3.Connection:
    """Open read-only connection with busy timeout and retry on SQLITE_BUSY."""
    try:
        return connect_ro_raising(db_path)
    except FileNotFoundError:
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(4)
    except DatabaseBusyError:
        print("error: database is locked — another session-recall process may be running", file=sys.stderr)
        raise SystemExit(3)
