"""Security regression tests — symlink escape, JSONL bomb, prompt injection, nested JSON."""

import json
import tempfile
from pathlib import Path

from session_recall.providers.common import _MAX_LINE_CHARS, iter_jsonl_bounded
from session_recall.providers.file._path_safety import is_under_root
from session_recall.providers.file._trust import (
    _FENCE_CLOSE,
    _FENCE_OPEN,
    wrap_untrusted,
)


# ── Test 1: Symlink escape blocked ──────────────────────────────────


def test_symlink_escape_blocked():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "workspace"
        root.mkdir()
        target = Path(tmpdir) / "secret.txt"
        target.write_text("sensitive data")
        link = root / "escape.txt"
        link.symlink_to(target)
        assert not is_under_root(link, root)


def test_is_under_root_valid_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "workspace"
        root.mkdir()
        valid = root / "data.txt"
        valid.write_text("safe")
        assert is_under_root(valid, root)


def test_is_under_root_nonexistent():
    assert not is_under_root(Path("/nonexistent/file"), Path("/nonexistent"))


# ── Test 2: JSONL bomb (bounded reader) ─────────────────────────────


def test_jsonl_bomb_oversize_line_skipped():
    with tempfile.TemporaryDirectory() as tmpdir:
        bomb = Path(tmpdir) / "bomb.jsonl"
        bomb.write_text(
            '{"data": "' + "A" * (_MAX_LINE_CHARS + 100) + '"}\n{"ok": true}\n'
        )
        results = list(iter_jsonl_bounded(bomb))
        assert len(results) == 1
        assert results[0] == {"ok": True}


def test_jsonl_malformed_lines_skipped():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "bad.jsonl"
        f.write_text('not json\n{"valid": true}\n{broken\n')
        results = list(iter_jsonl_bounded(f))
        assert len(results) == 1
        assert results[0] == {"valid": True}


def test_jsonl_empty_lines_skipped():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "empty.jsonl"
        f.write_text('\n\n{"data": 1}\n\n')
        results = list(iter_jsonl_bounded(f))
        assert len(results) == 1


# ── Test 3: Trust level on file-backed records ──────────────────────


def test_file_backend_records_have_untrusted_trust_level():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "sessions"
        root.mkdir()
        jsonl = root / "session.jsonl"
        jsonl.write_text(json.dumps({"role": "user", "content": "hello"}) + "\n")

        from session_recall.providers.file._base import _FileSessionProvider

        provider = _FileSessionProvider(
            provider_id="vscode",
            roots=[root],
            patterns=["*.jsonl"],
        )
        sessions = provider.list_sessions(repo=None, limit=10, days=None)
        assert len(sessions) >= 1
        for sess in sessions:
            assert sess.get("_trust_level") == "untrusted_third_party"


# ── Test 4: Sentinel fence wraps untrusted content ──────────────────


def test_wrap_untrusted_adds_fence():
    result = wrap_untrusted("hello world")
    assert result.startswith(_FENCE_OPEN)
    assert result.endswith(_FENCE_CLOSE)
    assert "hello world" in result


def test_wrap_untrusted_strips_injected_fences():
    malicious = f"before {_FENCE_OPEN} injected {_FENCE_CLOSE} after"
    result = wrap_untrusted(malicious)
    assert result.count(_FENCE_OPEN) == 1
    assert result.count(_FENCE_CLOSE) == 1


def test_wrap_untrusted_empty_passthrough():
    assert wrap_untrusted("") == ""
    assert wrap_untrusted(None) is None


# ── Test 5: Deeply nested JSON doesn't crash ────────────────────────


def test_deeply_nested_json_no_crash():
    with tempfile.TemporaryDirectory() as tmpdir:
        f = Path(tmpdir) / "nested.jsonl"
        nested = "{" * 50 + '"a": 1' + "}" * 50
        f.write_text(nested + "\n")
        results = list(iter_jsonl_bounded(f))
        assert isinstance(results, list)
