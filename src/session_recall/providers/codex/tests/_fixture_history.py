"""Populate synthetic `thread_history_1.sqlite` for paginated fixture threads."""

import json
import sqlite3


def _item(thread_id, turn_id, item_id, ordinal, ts_ms, item_type, payload) -> tuple:
    return (
        thread_id, turn_id, item_id, ordinal, ts_ms,
        json.dumps(payload), item_type, 0,
    )


def _user_msg(text: str) -> dict:
    return {"type": "userMessage", "content": [{"type": "text", "text": text}]}


def _agent_msg(text: str) -> dict:
    return {"type": "agentMessage", "text": text, "phase": "commentary"}


def standard_turn_items(thread_row: dict) -> list:
    """One full turn: user + reasoning + command + agent (+ fileChange for oldband)."""
    tid = thread_row["id"]
    ts = thread_row["created_at_ms"]
    turn_id = f"turn-{tid[:8]}-1"
    user_text = thread_row["first_user_message"] or f"work on {thread_row['title']}"
    items = [
        _item(tid, turn_id, f"{turn_id}-i1", 1, ts + 1000, "userMessage",
              _user_msg(user_text)),
        _item(tid, turn_id, f"{turn_id}-i2", 2, ts + 2000, "reasoning",
              {"type": "reasoning", "text": "SECRET-REASONING must never surface"}),
        _item(tid, turn_id, f"{turn_id}-i3", 3, ts + 3000, "commandExecution",
              {"type": "commandExecution", "command": "rm -rf /tmp/never-shown"}),
        _item(tid, turn_id, f"{turn_id}-i4", 4, ts + 4000, "agentMessage",
              _agent_msg(f"done with {thread_row['title']}")),
    ]
    if "oldband" in thread_row["title"]:
        from ._fixture_state import OLDBAND_FILE
        items.append(
            _item(tid, turn_id, f"{turn_id}-i5", 5, ts + 5000, "fileChange",
                  {"type": "fileChange",
                   "changes": [{"path": OLDBAND_FILE, "kind": "edit"}]})
        )
    return items


def turn_row(thread_row: dict) -> tuple:
    tid = thread_row["id"]
    ts = thread_row["created_at_ms"]
    turn_id = f"turn-{tid[:8]}-1"
    return (
        tid, turn_id, 1, "completed", None,
        ts // 1000, ts // 1000 + 60, 60_000,
        f"{turn_id}-i1", f"{turn_id}-i4", 0, None, None,
    )


def populate_history(history_conn: sqlite3.Connection, thread_rows: list) -> None:
    """Insert items+turns for every paginated thread row."""
    for row in thread_rows:
        if row["history_mode"] != "paginated":
            continue
        for item in standard_turn_items(row):
            history_conn.execute(
                "INSERT INTO thread_items (thread_id, turn_id, item_id, "
                "rollout_ordinal, created_at_ms, item_json, item_type, "
                "updated_at_ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                item,
            )
        history_conn.execute(
            "INSERT INTO thread_turns (thread_id, turn_id, rollout_ordinal, "
            "status, error_json, started_at, completed_at, duration_ms, "
            "first_user_item_id, final_agent_item_id, rollout_byte_offset, "
            "rollout_end_ordinal, rollout_end_byte_offset) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            turn_row(row),
        )
    history_conn.commit()
