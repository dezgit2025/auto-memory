"""Tests for the sidecar CLI entry point."""
from __future__ import annotations

import pytest


@pytest.fixture()
def _mock_build_index(monkeypatch: pytest.MonkeyPatch):
    """Patch build_index so no real JSONL files or DB are needed."""
    fake_stats = {"indexed": 3, "skipped": 7, "errors": 0}

    def _fake(*, rebuild: bool = False, verbose: bool = False) -> dict:
        _fake.calls.append({"rebuild": rebuild, "verbose": verbose})
        return fake_stats

    _fake.calls = []
    monkeypatch.setattr(
        "session_recall.providers.claude_code.index.build_index", _fake
    )
    return _fake


def test_once_mode_exits_zero(_mock_build_index):
    from session_recall.providers.claude_code.sidecar import main

    rc = main(["--once"])
    assert rc == 0
    assert len(_mock_build_index.calls) == 1
    assert _mock_build_index.calls[0]["rebuild"] is False


def test_rebuild_flag_passed(_mock_build_index):
    from session_recall.providers.claude_code.sidecar import main

    rc = main(["--once", "--rebuild"])
    assert rc == 0
    assert _mock_build_index.calls[0]["rebuild"] is True


def test_verbose_prints_stats(_mock_build_index, capsys):
    from session_recall.providers.claude_code.sidecar import main

    rc = main(["--once", "--verbose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "indexed=3" in out
    assert "skipped=7" in out
    assert "errors=0" in out


def test_missing_required_flag():
    from session_recall.providers.claude_code.sidecar import main

    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
