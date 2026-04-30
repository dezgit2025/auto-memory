"""Per-provider health diagnostics (4 sub-dimensions per provider)."""

from __future__ import annotations

from pathlib import Path

from ..config import JSONL_DEFAULT_LOOKBACK_DAYS, SQLITE_DEFAULT_LOOKBACK_DAYS


def _is_file_provider(provider: object) -> bool:
    return hasattr(provider, "_roots")


def check_path_discovery(provider: object) -> dict:
    """Check which root paths exist for this provider."""
    name = "Path Discovery"
    matched: list[str] = []

    if _is_file_provider(provider):
        for root in getattr(provider, "_roots", []):
            try:
                if Path(root).exists():
                    matched.append(str(root))
            except OSError:
                pass
    else:
        # CLI provider
        try:
            db = Path(getattr(provider, "db_path", ""))
            if db.is_file():
                matched.append(str(db))
        except OSError:
            pass
        try:
            sr = getattr(provider, "state_root", None)
            if sr is not None and Path(sr).is_dir():
                matched.append(str(sr))
        except OSError:
            pass

    if matched:
        zone, score = "GREEN", 10.0
        detail = f"{len(matched)} path(s) found"
    else:
        zone, score = "RED", 0.0
        detail = "No paths found"

    return {
        "name": name,
        "zone": zone,
        "score": score,
        "detail": detail,
        "matched_paths": matched,
    }


def check_file_inventory(provider: object) -> dict:
    """Count files and detect parse issues for file-backed providers."""
    name = "File Inventory"
    file_count = 0

    if _is_file_provider(provider):
        try:
            files = provider._iter_files(days=None)  # type: ignore[union-attr]
            file_count = len(files)
        except OSError:
            file_count = 0

        if file_count >= 1:
            zone, score = "GREEN", 10.0
            detail = f"{file_count} file(s)"
        else:
            zone, score = "RED", 0.0
            detail = "0 files found"
    else:
        # CLI provider
        db_exists = False
        db_bytes = 0
        state_count = 0

        try:
            db_path = Path(getattr(provider, "db_path", ""))
            if db_path.is_file():
                db_exists = True
                db_bytes = db_path.stat().st_size
        except OSError:
            pass

        try:
            state_files = provider._state_files()  # type: ignore[union-attr]
            state_count = len(state_files)
        except (OSError, AttributeError):
            pass

        file_count = state_count + (1 if db_exists else 0)

        if db_exists and db_bytes > 0:
            zone, score = "GREEN", 10.0
            detail = f"DB {db_bytes} bytes, {state_count} state file(s)"
        elif state_count > 0:
            zone, score = "AMBER", 5.0
            detail = f"No DB; {state_count} state file(s) only"
        else:
            zone, score = "RED", 0.0
            detail = "No DB and no state files"

    return {
        "name": name,
        "zone": zone,
        "score": score,
        "detail": detail,
        "file_count": file_count,
    }


def check_recent_activity(provider: object, lookback_days: int) -> dict:
    """Check if there are recent sessions within the lookback window."""
    name = "Recent Activity"
    sessions_found = 0

    try:
        sessions = provider.list_sessions(  # type: ignore[union-attr]
            repo="all", limit=20, days=lookback_days,
        )
        sessions_found = len(sessions)
    except Exception:
        sessions_found = 0

    if sessions_found > 0:
        zone, score = "GREEN", 10.0
        detail = f"{sessions_found} session(s) in last {lookback_days}d"
    else:
        zone, score = "RED", 0.0
        detail = f"No sessions in last {lookback_days}d"

    return {
        "name": name,
        "zone": zone,
        "score": score,
        "detail": detail,
        "sessions_found": sessions_found,
        "lookback_days": lookback_days,
    }


def check_trust_model(provider: object) -> dict:
    """Report the trust level applied to this provider."""
    name = "Trust Model"

    if _is_file_provider(provider):
        trust_level = "untrusted_third_party"
        fences_enabled = True
        detail = "Untrusted third-party; output fences enabled"
    else:
        trust_level = "trusted_first_party"
        fences_enabled = False
        detail = "Trusted first-party; fences disabled"

    return {
        "name": name,
        "zone": "GREEN",
        "score": 10.0,
        "detail": detail,
        "trust_level": trust_level,
        "fences_enabled": fences_enabled,
    }


def check_provider_health(provider: object) -> list[dict]:
    """Run all 4 checks for a provider and return list of dim dicts."""
    if _is_file_provider(provider):
        lookback = JSONL_DEFAULT_LOOKBACK_DAYS
    else:
        lookback = SQLITE_DEFAULT_LOOKBACK_DAYS

    return [
        check_path_discovery(provider),
        check_file_inventory(provider),
        check_recent_activity(provider, lookback),
        check_trust_model(provider),
    ]
