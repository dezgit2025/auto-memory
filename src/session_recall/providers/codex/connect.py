"""Read-only connections to both Codex databases (plan §5.2, §16 Fix 2).

One open per database per command: ``open_codex_ro`` is the ONLY place Codex
databases are opened.  Pre-flight validation and the data query share the
connections it yields — never close-and-reopen between check and use (TOCTOU).
"""

from contextlib import contextmanager

from ...db.connect import DatabaseBusyError, connect_ro_raising
from .errors import CodexBusy, CodexStorageMissing
from .paths import CodexPaths, classify_missing_storage


def _open_one(db_path):
    """Open one Codex DB read-only, mapping failures to codex errors."""
    try:
        return connect_ro_raising(str(db_path))
    except FileNotFoundError:
        code, message = classify_missing_storage(db_path.parent, db_path.name)
        raise CodexStorageMissing(message, code=code) from None
    except DatabaseBusyError:
        raise CodexBusy(
            f"database is locked after bounded retries: {db_path}"
        ) from None


@contextmanager
def open_codex_ro(paths: CodexPaths):
    """Yield ``(state_conn, history_conn)`` for the lifetime of ONE command.

    Both connections are read-only (URI mode=ro + PRAGMA query_only).  Both
    are guaranteed closed on exit; if the history DB fails to open after the
    state DB succeeded, the state connection is closed before the error
    propagates.
    """
    state = _open_one(paths.state_db)
    try:
        history = _open_one(paths.history_db)
    except BaseException:
        state.close()
        raise
    try:
        yield state, history
    finally:
        history.close()
        state.close()
