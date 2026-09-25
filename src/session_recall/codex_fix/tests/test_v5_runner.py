"""Frozen recording-fake tests for the V5 Codex subprocess boundary."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess

import pytest

from session_recall.codex_fix.codex_runner import generate
from session_recall.codex_fix.contracts import canonical_bytes, digest

from ._c_budget_fixtures import model_policy


SOURCE = {
    "path": "session_recall/providers/codex/schema.py",
    "content": "SUPPORTED_STATE = 55\n",
}
SOURCE["sha256"] = "sha256:" + hashlib.sha256(
    SOURCE["content"].encode("utf-8")
).hexdigest()


def candidate_input(**changes):
    value = {
        "format_version": 1,
        "incident_id": "incident-v5",
        "input_fingerprint": "sha256:" + "1" * 64,
        "base_artifact_digest": "sha256:" + "2" * 64,
        "catalogue_digest": "sha256:" + "3" * 64,
        "policy_digest": digest(model_policy()),
        "acceptance_contract_digest": "sha256:" + "4" * 64,
        "allowed_paths": [SOURCE["path"]],
        "schema_diff": {"differences": ["state.user_version: 55 -> 56"]},
        "source_files": [SOURCE],
    }
    value.update(changes)
    return value


def candidate(value=None, **changes):
    request = value or candidate_input()
    patched = {
        "path": SOURCE["path"],
        "content": "SUPPORTED_STATE = 56\n",
    }
    patched["sha256"] = "sha256:" + hashlib.sha256(
        patched["content"].encode("utf-8")
    ).hexdigest()
    result = {
        "format_version": 1,
        "input_digest": digest(request),
        "base_artifact_digest": request["base_artifact_digest"],
        "files": [patched],
    }
    result.update(changes)
    return result


class RecordingRun:
    def __init__(self, payload=None, *, stdout_events=None, returncode=0, error=None):
        self.payload = payload
        self.stdout_events = stdout_events or [
            {"type": "thread.started", "thread_id": "thread-synthetic"},
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "model": "gpt-6-astra",
                "reasoning_effort": "medium",
            },
        ]
        self.returncode = returncode
        self.error = error
        self.calls = []
        self.output_schema = None

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.error is not None:
            raise self.error
        schema_path = Path(argv[argv.index("--output-schema") + 1])
        self.output_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        output_path = Path(argv[argv.index("--output-last-message") + 1])
        if self.payload is not None:
            raw = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
            output_path.write_text(raw, encoding="utf-8")
        stdout = "\n".join(json.dumps(event) for event in self.stdout_events)
        return subprocess.CompletedProcess(argv, self.returncode, stdout, "synthetic error")


def test_generate_uses_one_fixed_isolated_codex_exec_request(tmp_path, monkeypatch):
    request = candidate_input()
    recorder = RecordingRun(candidate(request))
    monkeypatch.chdir(tmp_path)

    result = generate(request, model_policy(), executable="/opt/bin/codex", run=recorder)

    assert result["status"] == "completed"
    assert result["candidate"] == candidate(request)
    assert len(recorder.calls) == 1
    argv, options = recorder.calls[0]
    assert argv[:8] == [
        "/opt/bin/codex", "exec", "--model", "gpt-6-astra", "-c",
        'model_reasoning_effort="medium"', "--sandbox", "read-only",
    ]
    assert argv[8:16] == [
        "--ephemeral", "--ignore-user-config", "--ignore-rules", "--disable",
        "shell_tool", "--skip-git-repo-check", "--json", "--output-last-message",
    ]
    assert argv[-1] == "-"
    assert argv.count("--output-last-message") == 1
    assert argv.count("--output-schema") == 1
    assert options["shell"] is False
    assert options["check"] is False
    assert options["capture_output"] is True
    assert options["text"] is True
    assert options["timeout"] == 300
    assert json.loads(options["input"]) == request
    assert options["input"].encode() == canonical_bytes(request)
    workdir = Path(options["cwd"])
    assert workdir != tmp_path and workdir.is_absolute()
    assert not (workdir / "AGENTS.md").exists()
    assert Path(options["env"]["CODEX_HOME"]).is_relative_to(workdir)
    assert "SESSION_RECALL_CODEX_STATE_DB" not in options["env"]
    assert "SESSION_RECALL_CODEX_HISTORY_DB" not in options["env"]
    assert recorder.output_schema["additionalProperties"] is False
    assert set(recorder.output_schema["required"]) == {
        "format_version", "input_digest", "base_artifact_digest", "files",
    }
    assert recorder.output_schema["properties"]["files"]["maxItems"] == 32

    evidence = result["evidence"]
    assert evidence["requested_model"] == "gpt-6-astra"
    assert evidence["requested_effort"] == "medium"
    assert evidence["reported_model"] == "gpt-6-astra"
    assert evidence["reported_effort"] == "medium"


def test_missing_reported_settings_are_nullable_and_accepted():
    request = candidate_input()
    recorder = RecordingRun(
        candidate(request),
        stdout_events=[{"type": "turn.completed", "usage": {}}],
    )

    result = generate(request, model_policy(), run=recorder)

    assert result["status"] == "completed"
    assert result["evidence"]["reported_model"] is None
    assert result["evidence"]["reported_effort"] is None
    assert len(recorder.calls) == 1


def test_current_codex_usage_fields_are_retained_without_relaxing_event_validation():
    request = candidate_input()
    usage = {
        "input_tokens": 10,
        "cached_input_tokens": 2,
        "cache_write_input_tokens": 3,
        "output_tokens": 4,
        "reasoning_output_tokens": 1,
    }
    recorder = RecordingRun(
        candidate(request),
        stdout_events=[{"type": "turn.completed", "usage": usage}],
    )

    result = generate(request, model_policy(), run=recorder)

    assert result["status"] == "completed"
    assert result["evidence"]["usage"] == usage


@pytest.mark.parametrize(
    ("events", "status"),
    [
        ([{"type": "error", "message": "login required"}], "login_failed"),
        ([{"type": "error", "message": "model is unavailable"}], "model_unavailable"),
        (
            [{"type": "turn.completed", "model": "gpt-5.6-sol",
              "reasoning_effort": "medium"}],
            "reported_settings_mismatch",
        ),
        (
            [{"type": "turn.completed", "model": "gpt-6-astra",
              "reasoning_effort": "high"}],
            "reported_settings_mismatch",
        ),
    ],
)
def test_trusted_process_events_fail_closed_without_retry(events, status):
    recorder = RecordingRun(candidate(), stdout_events=events)
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result["status"] == status
    assert result["candidate"] is None
    assert len(recorder.calls) == 1


@pytest.mark.parametrize(
    ("recorder", "status"),
    [
        (RecordingRun(candidate(), returncode=7), "process_failed"),
        (RecordingRun(None), "missing_output"),
        (RecordingRun("not-json"), "malformed_output"),
        (RecordingRun("{" + '"padding":"' + "x" * (2 * 1024 * 1024) + '"}'),
         "output_too_large"),
        (RecordingRun(error=subprocess.TimeoutExpired("codex", 300)), "timeout"),
    ],
)
def test_process_and_output_failures_are_structured_and_single_attempt(recorder, status):
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result["status"] == status
    assert result["candidate"] is None
    assert len(recorder.calls) == 1


@pytest.mark.parametrize(
    "bad_candidate",
    [
        candidate(input_digest="sha256:" + "9" * 64),
        candidate(base_artifact_digest="sha256:" + "9" * 64),
        candidate(files=[{**SOURCE, "path": "../controller.py"}]),
        {**candidate(), "approved": True},
    ],
)
def test_candidate_binding_shape_and_paths_are_validated_before_acceptance(bad_candidate):
    recorder = RecordingRun(bad_candidate)
    result = generate(candidate_input(), model_policy(), run=recorder)
    assert result["status"] == "invalid_candidate"
    assert result["candidate"] is None
    assert len(recorder.calls) == 1


def test_only_exact_v2_policy_can_start_a_process():
    for changes in (
        {"format_version": 1},
        {"model": "gpt-5.6-sol"},
        {"effort": "high"},
        {"automatic_retries": 1},
        {"timeout_seconds": 301},
    ):
        recorder = RecordingRun(candidate())
        result = generate(candidate_input(), model_policy(**changes), run=recorder)
        assert result["status"] == "invalid_policy"
        assert result["candidate"] is None
        assert recorder.calls == []


@pytest.mark.parametrize(
    "candidate_request",
    [
        candidate_input(format_version=2),
        candidate_input(allowed_paths=[]),
        candidate_input(allowed_paths=[f"allowed/{number}.py" for number in range(33)]),
        candidate_input(source_files=[]),
        candidate_input(source_files=[
            {
                "path": SOURCE["path"],
                "sha256": "sha256:" + "1" * 64,
                "content": "x" * (256 * 1024 + 1),
            }
        ]),
        {**candidate_input(), "session_contents": "must not be accepted"},
    ],
)
def test_invalid_or_oversized_candidate_input_never_starts_codex(candidate_request):
    recorder = RecordingRun(candidate())
    result = generate(candidate_request, model_policy(), run=recorder)
    assert result["status"] == "invalid_input"
    assert result["candidate"] is None
    assert recorder.calls == []
