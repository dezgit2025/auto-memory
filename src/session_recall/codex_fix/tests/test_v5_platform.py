"""Portable fail-closed coverage for the macOS-only candidate sandbox."""

import pytest

from session_recall.codex_fix import sandbox
from session_recall.codex_fix.contracts import ContractError


def test_unsupported_platform_refuses_before_candidate_process(monkeypatch):
    launched = False

    def forbidden_launch(*_args, **_kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("unsupported platform attempted candidate execution")

    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    monkeypatch.setattr(sandbox.subprocess, "Popen", forbidden_launch)

    with pytest.raises(ContractError, match="sandbox_unavailable"):
        sandbox.Sandbox()

    assert launched is False
