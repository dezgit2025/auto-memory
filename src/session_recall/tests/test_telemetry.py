"""Tests for util/telemetry.py — new tier/query_hash/window fields + backward compat."""
import json
import pytest
from session_recall.util import telemetry


@pytest.fixture
def tmp_telemetry(tmp_path):
    p = tmp_path / "stats.json"
    telemetry.init(str(p))
    yield p
    telemetry.init(None)  # reset


def test_record_with_tier(tmp_telemetry):
    telemetry.record("list", 42, tier=1)
    e = json.loads(tmp_telemetry.read_text())["entries"][-1]
    assert e["tier"] == 1
    assert e["cmd"] == "list"
    assert "query_hash" not in e  # only set when provided


def test_record_search_with_query_hash(tmp_telemetry):
    qh = telemetry.query_hash("hello world")
    assert len(qh) == 8
    assert qh == telemetry.query_hash("HELLO   WORLD")  # normalize
    telemetry.record("search", 12, tier=2, query_hash=qh)
    e = json.loads(tmp_telemetry.read_text())["entries"][-1]
    assert e["query_hash"] == qh


def test_record_show_with_session_prefix(tmp_telemetry):
    telemetry.record("show", 12, tier=3, session_id_prefix="abcd1234")
    e = json.loads(tmp_telemetry.read_text())["entries"][-1]
    assert e["session_id_prefix"] == "abcd1234"


def test_record_without_tier_no_field(tmp_telemetry):
    """Legacy-style call must not inject tier=None into entry (keeps 3-state semantics)."""
    telemetry.record("list", 10)
    e = json.loads(tmp_telemetry.read_text())["entries"][-1]
    assert "tier" not in e
    assert "query_hash" not in e


def test_ring_buffer_500(tmp_telemetry):
    for i in range(600):
        telemetry.record("list", i, tier=1)
    entries = json.loads(tmp_telemetry.read_text())["entries"]
    assert len(entries) == 500
    # Oldest entry dropped — first remaining has duration_ms=100
    assert entries[0]["duration_ms"] == 100


def test_no_raw_query_stored(tmp_telemetry):
    """Privacy guardrail: sensitive text must NEVER land in telemetry."""
    secret = "SELECT user_password FROM users"
    telemetry.record("search", 12, tier=2, query_hash=telemetry.query_hash(secret))
    raw = tmp_telemetry.read_text()
    assert "user_password" not in raw
    assert "SELECT" not in raw


def test_query_hash_deterministic():
    assert telemetry.query_hash("foo") == telemetry.query_hash("foo")
    assert telemetry.query_hash("foo") != telemetry.query_hash("bar")
