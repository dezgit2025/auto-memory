"""Tests for codex normalize helpers (Phase 2 Step 2)."""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

import yaml

from session_recall.providers.codex import normalize as nz

SPEC = (
    Path(__file__).resolve().parents[1] / "verifications" / "spec.yaml"
)


def test_ts_ms_to_iso_known_epoch():
    assert nz.ts_ms_to_iso(0) == "1970-01-01T00:00:00+00:00"
    ms = 1788042010551
    expected = dt.datetime.fromtimestamp(
        ms / 1000.0, tz=dt.timezone.utc
    ).isoformat()
    assert nz.ts_ms_to_iso(ms) == expected


def test_thread_timestamp_prefers_ms_then_seconds():
    assert nz.thread_timestamp({"created_at_ms": 0}) == "1970-01-01T00:00:00+00:00"
    row = {"created_at_ms": None, "created_at": 86400}
    assert nz.thread_timestamp(row) == "1970-01-02T00:00:00+00:00"
    assert nz.thread_timestamp({}) == ""


def test_date10():
    assert nz.date10("2026-08-30T12:00:00+00:00") == "2026-08-30"
    assert nz.date10("") == ""


def test_summary_priority_order():
    row = {"name": "N", "title": "T", "preview": "P", "first_user_message": "F"}
    assert nz.thread_summary(row) == "N"
    row["name"] = ""
    assert nz.thread_summary(row) == "T"
    row["title"] = None
    assert nz.thread_summary(row) == "P"
    row["preview"] = "   "
    assert nz.thread_summary(row) == "F"
    row["first_user_message"] = ""
    assert nz.thread_summary(row) == nz.NO_SUMMARY


def test_summary_sanitizes_and_falls_through_control_only():
    row = {"name": "\x1b[31mred\x1b[0m alert", "title": "t"}
    assert nz.thread_summary(row) == "red alert"
    # all-control name falls through to title instead of returning ""
    row = {"name": "\x1b[31m\x07", "title": "safe"}
    assert nz.thread_summary(row) == "safe"


def test_repo_label_origins():
    assert nz.repo_label("git@github.com:acme/widget.git", None) == "acme/widget"
    assert (
        nz.repo_label("https://github.com/acme/widget.git", "/x") == "acme/widget"
    )
    assert nz.repo_label(None, "/Users/synthetic/scratch") == (
        "local:/Users/synthetic/scratch"
    )
    home = str(Path("~/proj").expanduser())
    assert nz.repo_label(None, "~/proj") == f"local:{home}"
    assert nz.repo_label(None, None) == "local:unknown"


def test_repo_matches_exact_only():
    assert nz.repo_matches("acme/widget", None)
    assert nz.repo_matches("acme/widget", "all")
    assert nz.repo_matches("acme/widget", "acme/widget")
    assert not nz.repo_matches("acme/widget", "acme")
    assert not nz.repo_matches("acme/widget", "widget")
    assert not nz.repo_matches("local:/a/b", "local:/a")


def test_normalize_change_path(tmp_path):
    assert nz.normalize_change_path("/abs/f.py", "/cwd") == "/abs/f.py"
    assert nz.normalize_change_path("src/f.py", "/cwd") == "/cwd/src/f.py"
    assert nz.normalize_change_path("SRC/F.py", "/cwd") == "/cwd/SRC/F.py"
    assert nz.normalize_change_path("f.py", None) == "f.py"
    # symlinked cwd stays literal — no resolve()/realpath()
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    out = nz.normalize_change_path("f.py", str(link))
    assert out == f"{link}/f.py"
    assert "real" not in out


def _spec_pinned_keys() -> list[str]:
    spec = yaml.safe_load(SPEC.read_text())
    for crit in spec["acceptance_criteria"]:
        if "pin key sets:" in crit:
            body = crit.split("pin key sets:", 1)[1]
            body = body.split(";", 1)[0]
            body = re.sub(r"\(=[^)]*\)", "", body)
            return [k.strip() for k in body.split(",") if k.strip()]
    raise AssertionError("pinned key list not found in spec.yaml")


def test_row_assembly_matches_spec_pinned_keys():
    row = {
        "id": "01a04f9bdeadbeef",
        "created_at_ms": 0,
        "title": "t",
        "git_branch": None,
        "git_origin_url": None,
        "cwd": "/w",
    }
    out = nz.normalize_thread_row(row)
    assert list(out.keys()) == _spec_pinned_keys()
    assert out["id_short"] == "01a04f9b"
    assert out["branch"] == "unknown"
    assert out["repository"] == "local:/w"
    assert out["turns_count"] is None and out["files_count"] is None
    assert out["_trust_level"] == "codex_local_first_party"


def test_row_assembly_from_sqlite_row(codex_store):
    conn = sqlite3.connect(f"file:{codex_store.state_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM threads WHERE git_origin_url IS NOT NULL LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    out = nz.normalize_thread_row(row, turns_count=2, files_count=1)
    assert out["repository"] == "acme/widget"
    assert out["branch"] == "main"
    assert out["turns_count"] == 2 and out["files_count"] == 1
    assert out["date"] == out["created_at"][:10]
