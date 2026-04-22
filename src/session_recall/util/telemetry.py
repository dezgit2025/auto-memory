"""Telemetry ring buffer for session-recall invocations."""
import hashlib
import json
import time
from pathlib import Path

_TELEMETRY_PATH = None

def query_hash(q: str) -> str:
    """8-char sha256 hash of whitespace-normalized, lowercased query.
    Collision-tolerant, not reversible. Use for repetition detection without logging raw query."""
    normalized = " ".join(q.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:8]

def init(path: str) -> None:
    global _TELEMETRY_PATH
    _TELEMETRY_PATH = path

def record(cmd: str, duration_ms: int, busy_hits: int = 0,
           attempts: int = 1, rows: int = 0, exit_code: int = 0,
           schema_ok: bool = True, tier: int | None = None,
           query_hash: str | None = None, session_id_prefix: str | None = None,
           window_tier: str | None = None) -> None:
    """Append entry to ring buffer. Silent fail on any error.

    New optional fields (Phase 1):
      tier: 0=meta, 1=scan, 2=search, 3=deep. None = pre-instrumentation legacy.
      query_hash: 8-char sha256 prefix of normalized search query (search only).
      session_id_prefix: 8-char prefix of session ID (show only).
      window_tier: one of W1..W6 or "W?" — set by --days-from/--days-to (Phase 4).
    """
    if not _TELEMETRY_PATH:
        return
    try:
        path = Path(_TELEMETRY_PATH)
        entries = json.loads(path.read_text()).get("entries", []) if path.exists() else []
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cmd": cmd, "duration_ms": duration_ms, "busy_hits": busy_hits,
            "attempts": attempts, "rows_returned": rows,
            "exit_code": exit_code, "schema_ok": schema_ok,
        }
        # Only include non-None optional fields — keeps legacy schema clean
        if tier is not None: entry["tier"] = tier
        if query_hash is not None: entry["query_hash"] = query_hash
        if session_id_prefix is not None: entry["session_id_prefix"] = session_id_prefix
        if window_tier is not None: entry["window_tier"] = window_tier
        entries.append(entry)
        entries = entries[-500:]  # Ring buffer: 100 → 500
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"entries": entries}, indent=2))
    except Exception:
        pass  # Silent fail — telemetry must never crash the CLI
