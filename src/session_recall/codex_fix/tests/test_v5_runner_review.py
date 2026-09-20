"""Adversarial review cases for the V5 subprocess boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from session_recall.codex_fix.codex_runner import (
    _bounded_subprocess,
    _production_executable,
    generate,
)
from session_recall.codex_fix.contracts import ContractError

from ._c_budget_fixtures import model_policy
from .test_v5_runner import RecordingRun, candidate, candidate_input


def test_historical_v1_policy_is_rejected_before_process_launch():
    legacy = {
        **model_policy(),
        "format_version": 1,
        "policy_id": "sol-medium-budget-v1",
        "model": "gpt-5.6-sol",
    }
    recorder = RecordingRun(candidate())
    result = generate(candidate_input(), legacy, run=recorder)
    assert result["status"] == "invalid_policy"
    assert recorder.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"format_version": True},
        {"allowed_paths": [[]]},
        {"allowed_paths": ["session_recall/providers/codex/schema.py", []]},
        {"schema_diff": {"differences": [None]}},
        {"source_files": [{"path": [], "sha256": [], "content": []}]},
    ],
)
def test_malformed_input_types_return_invalid_without_launch(changes):
    recorder = RecordingRun(candidate())
    result = generate(candidate_input(**changes), model_policy(), run=recorder)
    assert result["status"] == "invalid_input"
    assert recorder.calls == []


def test_any_explicit_reported_mismatch_rejects_even_if_last_event_matches():
    recorder = RecordingRun(
        candidate(),
        stdout_events=[
            {"type": "turn.completed", "model": "wrong-model"},
            {"type": "turn.completed", "model": "gpt-6-astra",
             "reasoning_effort": "medium"},
        ],
    )
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result["status"] == "reported_settings_mismatch"
    assert len(recorder.calls) == 1


@pytest.mark.parametrize("reported", [{"name": "gpt-6-astra"}, [], 6])
def test_nonscalar_reported_model_is_a_mismatch_not_typeerror(reported):
    recorder = RecordingRun(
        candidate(),
        stdout_events=[{"type": "turn.completed", "model": reported}],
    )
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result["status"] == "reported_settings_mismatch"


@pytest.mark.parametrize(
    ("message", "status"),
    [("Login required", "login_failed"), ("Model unavailable", "model_unavailable")],
)
def test_nonzero_process_still_classifies_trusted_jsonl_error(message, status):
    recorder = RecordingRun(
        None, returncode=1,
        stdout_events=[{"type": "error", "message": message}],
    )
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result["status"] == status
    assert result["candidate"] is None


def test_duplicate_candidate_json_key_is_rejected():
    value = candidate()
    pairs = json.dumps(value)[1:-1]
    recorder = RecordingRun('{"format_version":1,"format_version":1,' + pairs + "}")
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result["status"] == "invalid_candidate"


def test_fixed_argv_is_strict_and_contains_no_alternate_transport_flags():
    recorder = RecordingRun(candidate())
    generate(candidate_input(), model_policy(), executable="/fixed/codex", run=recorder)
    argv = recorder.calls[0][0]
    assert argv.count("--strict-config") == 1
    assert argv.count("--model") == 1
    assert argv[argv.index("--model") + 1] == "gpt-6-astra"
    assert argv.count("shell_tool") == 1
    assert not ({"--search", "--oss", "--local-provider", "resume", "fork",
                 "--dangerously-bypass-approvals-and-sandbox"} & set(argv))


def test_malformed_usage_event_is_rejected():
    recorder = RecordingRun(
        candidate(),
        stdout_events=[{"type": "turn.completed", "usage": {"surprise": 1}}],
    )
    assert generate(candidate_input(), model_policy(), run=recorder)["status"] == "malformed_events"


def _actual_run(argv, *, timeout, cwd):
    return _bounded_subprocess(
        argv, input="", cwd=str(cwd), env={}, shell=False, check=False,
        capture_output=True, text=True, timeout=timeout, start_new_session=True,
    )


def test_real_subprocess_output_flood_is_killed_and_bounded(tmp_path):
    with pytest.raises(ContractError, match="process_output_too_large"):
        _actual_run(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 3000000)"],
            timeout=10,
            cwd=tmp_path,
        )


def test_real_subprocess_timeout_kills_child_process_group(tmp_path):
    sentinel = tmp_path / "child-survived"
    child = "import time; from pathlib import Path; time.sleep(1); Path(%r).write_text('bad')" % str(sentinel)
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(30)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        _actual_run([sys.executable, "-c", parent], timeout=1, cwd=tmp_path)
    time.sleep(1.2)
    assert not sentinel.exists()


def test_production_runner_rejects_missing_or_symlinked_executable(tmp_path):
    missing = str(tmp_path / "missing-codex")
    assert generate(candidate_input(), model_policy(), executable=missing)["status"] == "process_failed"
    target = tmp_path / "codex-target"
    target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    target.chmod(0o700)
    link = tmp_path / "codex"
    link.symlink_to(target)
    assert generate(candidate_input(), model_policy(), executable=str(link))["status"] == "process_failed"


def test_production_executable_resolves_once_from_parent_path(tmp_path, monkeypatch):
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert _production_executable("codex") == str(executable)


def test_installed_path_shim_is_resolved_to_a_fixed_canonical_binary(tmp_path, monkeypatch):
    installed = tmp_path / 'installed-codex'
    installed.write_text('#!/bin/sh\nexit 0\n')
    installed.chmod(0o700)
    (tmp_path / 'codex').symlink_to(installed)
    monkeypatch.setenv('PATH', str(tmp_path))
    assert _production_executable('codex') == str(installed)


@pytest.mark.parametrize(('message', 'status'), [
    ('Invalid schema: format_version requires type', 'invalid_output_schema'),
    ('The model is not supported for this account', 'model_unavailable'),
    ('Authentication required, please login', 'login_failed'),
])
def test_failed_turn_has_sanitized_specific_status_without_leaking_raw_error(message, status):
    recorder = RecordingRun(candidate(), returncode=1, stdout_events=[
        {'type': 'turn.failed', 'error': {'message': message}},
    ])
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result['status'] == status
    assert result['candidate'] is None
    assert message not in str(result)
    assert len(recorder.calls) == 1
