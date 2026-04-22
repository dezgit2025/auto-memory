"""Schema validation against expected Copilot CLI session store structure."""

EXPECTED_SCHEMA: dict[str, set[str]] = {
    "sessions": {"id", "repository", "branch", "summary", "created_at", "updated_at"},
    "turns": {"session_id", "turn_index", "user_message", "assistant_response", "timestamp"},
    "session_files": {"session_id", "file_path", "tool_name", "turn_index", "first_seen_at"},
    "session_refs": {"session_id", "ref_type", "ref_value", "turn_index", "created_at"},
    "checkpoints": {"session_id", "checkpoint_number", "title", "overview", "created_at"},
}


def schema_check(conn) -> list[str]:
    """Validate schema. Returns list of problems (empty = OK).

    Works with both SQLite Connection and JSONLStoreAdapter.
    """
    problems: list[str] = []

    # Check if this is a JSONL store adapter
    if hasattr(conn, 'store'):
        return _schema_check_jsonl(conn.store)

    # Otherwise assume SQLite
    return _schema_check_sqlite(conn)


def _schema_check_sqlite(conn) -> list[str]:
    """Validate SQLite schema."""
    problems: list[str] = []
    for table, expected_cols in EXPECTED_SCHEMA.items():
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            problems.append(f"MISSING TABLE: {table}")
            continue
        actual = {r[1] if isinstance(r, tuple) else r["name"] for r in rows}
        missing = expected_cols - actual
        if missing:
            problems.append(f"{table}: missing columns {missing}")
    return problems


def _schema_check_jsonl(store) -> list[str]:
    """Validate JSONL store schema."""
    problems: list[str] = []

    # Check if tables have data and expected columns
    if not store.sessions:
        problems.append("No sessions found in event logs")
    else:
        # Sample first session to check columns
        sample = next(iter(store.sessions.values()))
        expected = EXPECTED_SCHEMA["sessions"]
        missing = expected - set(sample.keys())
        if missing:
            problems.append(f"sessions: missing columns {missing}")

    if not store.turns:
        problems.append("No turns found in event logs")
    elif store.turns:
        sample = store.turns[0]
        expected = EXPECTED_SCHEMA["turns"]
        missing = expected - set(sample.keys())
        if missing:
            problems.append(f"turns: missing columns {missing}")

    if not store.session_files:
        problems.append("No session_files found in event logs")
    elif store.session_files:
        sample = store.session_files[0]
        expected = EXPECTED_SCHEMA["session_files"]
        missing = expected - set(sample.keys())
        if missing:
            problems.append(f"session_files: missing columns {missing}")

    return problems
