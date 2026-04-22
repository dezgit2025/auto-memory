"""Tests for health/dim_disclosure.py — three-state tier, transitions, sample gates."""
import json
from datetime import datetime, timedelta, timezone
from session_recall.health import dim_disclosure


def _write_entries(tmp_path, entries, monkeypatch):
    p = tmp_path / "stats.json"
    p.write_text(json.dumps({"entries": entries}))
    monkeypatch.setattr(dim_disclosure, "TELEMETRY_PATH", str(p))


def _ts(offset_min=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=offset_min)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_all_legacy_entries_returns_calibrating(tmp_path, monkeypatch):
    entries = [{"cmd": "list", "ts": _ts(i)} for i in range(50)]
    _write_entries(tmp_path, entries, monkeypatch)
    r = dim_disclosure.check()
    assert r["zone"] == "CALIBRATING"
    assert r["score"] is None
    assert r["unknown_entries"] == 50


def test_meta_entries_excluded(tmp_path, monkeypatch):
    entries = ([{"cmd": "health", "tier": 0, "ts": _ts(i)} for i in range(10)] +
               [{"cmd": "list", "tier": 1, "ts": _ts(i+10)} for i in range(5)])
    _write_entries(tmp_path, entries, monkeypatch)
    r = dim_disclosure.check()
    assert r["meta_entries"] == 10
    assert r["scored_entries"] == 5


def test_insufficient_sample_returns_calibrating(tmp_path, monkeypatch):
    entries = [{"cmd": "list", "tier": 1, "ts": _ts(i)} for i in range(5)]
    _write_entries(tmp_path, entries, monkeypatch)
    r = dim_disclosure.check()
    assert r["zone"] == "CALIBRATING"
    assert "Collecting baseline" in r["hint"]


def test_unknown_share_over_50pct_forces_calibrating(tmp_path, monkeypatch):
    entries = ([{"cmd": "list", "ts": _ts(i)} for i in range(300)] +
               [{"cmd": "list", "tier": 1, "ts": _ts(i+300)} for i in range(250)])
    _write_entries(tmp_path, entries, monkeypatch)
    r = dim_disclosure.check()
    assert r["zone"] == "CALIBRATING"
    assert "drain" in r["hint"]


def test_healthy_escalation_t1_to_t2():
    entries = [{"cmd": "list", "tier": 1, "ts": _ts(10)},
               {"cmd": "search", "tier": 2, "ts": _ts(9)}]
    t = dim_disclosure._classify_transitions(entries)
    assert t["healthy"] == 1
    assert t["suspicious"] == 0


def test_cold_start_t3_is_suspicious():
    entries = [{"cmd": "show", "tier": 3, "ts": _ts(5)}]
    t = dim_disclosure._classify_transitions(entries)
    assert t["suspicious"] >= 1


def test_t3_to_t3_within_window_is_neutral():
    entries = [{"cmd": "list", "tier": 1, "ts": _ts(10)},
               {"cmd": "show", "tier": 3, "ts": _ts(9)},
               {"cmd": "show", "tier": 3, "ts": _ts(8)}]
    t = dim_disclosure._classify_transitions(entries)
    assert t["healthy"] == 1
    assert t["neutral"] == 1


def test_repeated_search_with_same_hash_counts_repetition():
    entries = [{"cmd": "search", "tier": 2, "query_hash": "abc12345", "ts": _ts(5)},
               {"cmd": "search", "tier": 2, "query_hash": "abc12345", "ts": _ts(4)}]
    t = dim_disclosure._classify_transitions(entries)
    assert t["repetition"] == 1


def test_scoring_active_gate(tmp_path, monkeypatch):
    """Even with 200+ entries, if SCORING_ACTIVE=False, zone is CALIBRATING."""
    entries = [{"cmd": "list", "tier": 1, "ts": _ts(i)} for i in range(250)]
    _write_entries(tmp_path, entries, monkeypatch)
    monkeypatch.setattr(dim_disclosure, "SCORING_ACTIVE", False)
    r = dim_disclosure.check()
    assert r["score"] is None
    assert r["zone"] == "CALIBRATING"
