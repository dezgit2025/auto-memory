"""JSONL state fallback query methods for Copilot CLI provider."""

from __future__ import annotations

from pathlib import Path

from ..common import is_within_days, short_id
from ._state_parse import parse_state_session


def state_list_sessions(
    provider_id: str, state_files: list[Path], repo: str | None, limit: int, days: int | None
) -> list[dict]:
    rows = []
    for fp in state_files:
        parsed = parse_state_session(provider_id, fp)
        if repo and repo != "all" and parsed.get("repository") != repo:
            continue
        if not is_within_days(parsed.get("created_at"), days):
            continue
        record = {k: v for k, v in parsed.items() if not k.startswith("_")}
        record["_trust_level"] = "trusted_first_party"
        rows.append(record)
        if len(rows) >= limit:
            break
    return rows


def state_search(
    provider_id: str, state_files: list[Path], query: str, repo: str | None, limit: int, days: int | None
) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return []
    out = []
    for fp in state_files:
        parsed = parse_state_session(provider_id, fp)
        if repo and repo != "all" and parsed.get("repository") != repo:
            continue
        if not is_within_days(parsed.get("created_at"), days):
            continue
        for t in parsed.get("_turns", []):
            content = f"{t.get('user', '')}\n{t.get('assistant', '')}".strip()
            if q not in content.lower():
                continue
            out.append(
                {
                    "provider": provider_id,
                    "session_id": short_id(parsed["id_full"]),
                    "session_id_full": parsed["id_full"],
                    "source_type": "turn",
                    "summary": parsed["summary"],
                    "repository": parsed["repository"],
                    "date": parsed["date"],
                    "excerpt": content[:250]
                    + ("..." if len(content) > 250 else ""),
                    "_trust_level": "trusted_first_party",
                }
            )
            if len(out) >= limit:
                return out
    return out


def state_get_session(
    provider_id: str, state_files: list[Path], session_id: str, turns: int | None, full: bool
) -> dict | None:
    sid = session_id.strip().lower()
    for fp in state_files:
        parsed = parse_state_session(provider_id, fp)
        full_id = str(parsed["id_full"]).lower()
        if not (full_id == sid or full_id.startswith(sid)):
            continue
        turn_rows = parsed.get("_turns", [])
        if turns is not None:
            turn_rows = turn_rows[:turns]
        if not full:
            turn_rows = [
                {
                    "idx": t["idx"],
                    "user": (t.get("user") or "")[:500],
                    "assistant": (t.get("assistant") or "")[:500],
                    "timestamp": t.get("timestamp"),
                }
                for t in turn_rows
            ]
        return {
            "provider": provider_id,
            "id": parsed["id_full"],
            "repository": parsed["repository"],
            "branch": parsed["branch"],
            "summary": parsed["summary"],
            "created_at": parsed["created_at"],
            "turns_count": len(turn_rows),
            "turns": turn_rows,
            "files": [],
            "refs": [],
            "checkpoints": [],
            "_trust_level": "trusted_first_party",
        }
    return None
