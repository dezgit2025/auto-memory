"""One-shot Codex CLI runner for V5 candidate generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import shutil
import stat
import subprocess
import tempfile
import threading
from typing import Any, Callable

from ._candidate_contracts import (
    CANDIDATE_DRAFT_SCHEMA,
    parse_draft,
    validate_input,
)
from .c_contracts import validate_c
from .contracts import ContractError, canonical_bytes, digest


MAX_PROCESS_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_USAGE_VALUE = 2**63 - 1
DEVELOPER_INSTRUCTIONS = (
    "Return exactly one Candidate JSON object matching the output schema. "
    "Use no tools, shell, network, nested agents, approvals, or activation claims. "
    "Change only allowed paths and preserve input/base digest bindings."
)


def _result(status: str, candidate=None, evidence=None) -> dict[str, Any]:
    return {"status": status, "candidate": candidate, "evidence": evidence}


def _read_auth() -> bytes | None:
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    path = home / "auth.json"
    descriptor = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024 * 1024:
            return None
        content = os.read(descriptor, 1024 * 1024 + 1)
        return content if len(content) == metadata.st_size else None
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _isolated_environment(workdir: Path) -> dict[str, str]:
    allowed = ("LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment.update(
        {
            "PATH": os.defpath,
            "HOME": str(workdir / "home"),
            "CODEX_HOME": str(workdir / "codex-home"),
            "XDG_CONFIG_HOME": str(workdir / "xdg-config"),
            "XDG_DATA_HOME": str(workdir / "xdg-data"),
            "XDG_STATE_HOME": str(workdir / "xdg-state"),
            "XDG_CACHE_HOME": str(workdir / "xdg-cache"),
        }
    )
    for value in environment.values():
        Path(value).mkdir(parents=True, exist_ok=True) if value.startswith(str(workdir)) else None
    auth = _read_auth()
    if auth is not None:
        target = Path(environment["CODEX_HOME"]) / "auth.json"
        try:
            target.write_bytes(auth)
            target.chmod(0o600)
        except OSError:
            target.unlink(missing_ok=True)
    return environment


def _events(raw: str) -> tuple[list[dict[str, Any]], str | None]:
    if len(raw.encode("utf-8")) > MAX_PROCESS_OUTPUT_BYTES:
        return [], "process_output_too_large"
    parsed = []
    try:
        for line in raw.splitlines():
            if line.strip():
                event = json.loads(line)
                if not isinstance(event, dict):
                    return [], "malformed_events"
                parsed.append(event)
    except (json.JSONDecodeError, UnicodeError):
        return [], "malformed_events"
    return parsed, None


def _failure_category(message: str) -> str:
    message = message.lower()
    if 'invalid schema' in message or 'invalid_json_schema' in message:
        return 'invalid_output_schema'
    if 'unknown field' in message or 'unknown feature' in message:
        return 'configuration_rejected'
    if 'login' in message or 'auth' in message:
        return 'login_failed'
    if 'model' in message and any(term in message for term in ('unavailable', 'not available', 'not supported', 'does not exist')):
        return 'model_unavailable'
    return 'process_failed'


def _event_failure(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") not in {"error", "turn.failed"}:
            continue
        error = event.get('error')
        message = error.get('message', '') if isinstance(error, dict) else event.get('message', '')
        return _failure_category(str(message))
    return None


def _usage(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    allowed = {
        "input_tokens", "cached_input_tokens", "output_tokens",
        "reasoning_tokens", "total_tokens",
    }
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise ContractError("malformed_events")
    result: dict[str, int] = {}
    for key, item in value.items():
        if type(item) is not int or not 0 <= item <= MAX_USAGE_VALUE:
            raise ContractError("malformed_events")
        result[key] = item
    return result


def _reported(events: list[dict[str, Any]]) -> tuple[Any, Any, dict[str, int] | None]:
    for event in reversed(events):
        if event.get("type") == "turn.completed":
            return (
                event.get("model"), event.get("reasoning_effort"),
                _usage(event.get("usage")),
            )
    return None, None, None


def _settings_mismatch(events: list[dict[str, Any]], policy: dict[str, Any]) -> bool:
    for event in events:
        if event.get("type") != "turn.completed":
            continue
        model = event.get("model")
        effort = event.get("reasoning_effort")
        if model is not None and (not isinstance(model, str) or model != policy["model"]):
            return True
        if effort is not None and (not isinstance(effort, str) or effort != policy["effort"]):
            return True
    return False


def _bounded_subprocess(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    """Drain bounded pipes concurrently and kill the process group on failure."""
    input_text = kwargs.pop("input")
    kwargs.pop("capture_output")
    kwargs.pop("check")
    kwargs.pop("text")
    timeout = kwargs.pop("timeout")
    process = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        **kwargs,
    )
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    output_lock = threading.Lock()
    overflow = threading.Event()

    def kill_group() -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass

    def drain(name: str, stream: Any) -> None:
        while True:
            data = stream.read(8192)
            if not data:
                return
            with output_lock:
                remaining = MAX_PROCESS_OUTPUT_BYTES - sum(
                    len(item) for item in chunks.values()
                )
                if remaining > 0:
                    chunks[name].extend(data[:remaining])
                exceeded = len(data) > remaining
            if exceeded:
                overflow.set()
                kill_group()
                return

    def write_input() -> None:
        try:
            process.stdin.write(input_text.encode("utf-8"))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    workers = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
        threading.Thread(target=write_input, daemon=True),
    ]
    for worker in workers:
        worker.start()
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group()
        process.wait()
        raise
    finally:
        for worker in workers:
            worker.join(timeout=1)
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
    if overflow.is_set():
        raise ContractError("process_output_too_large")
    try:
        stdout = chunks["stdout"].decode("utf-8")
        stderr = chunks["stderr"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("malformed_events") from exc
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def _read_candidate(path: Path, candidate_input: dict[str, Any]) -> tuple[Any, str | None]:
    descriptor = -1
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            return None, "missing_output"
        if before.st_size > MAX_PROCESS_OUTPUT_BYTES:
            return None, "output_too_large"
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        opened = os.fstat(descriptor)
        identities = {
            (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
            for item in (before, opened)
        }
        if len(identities) != 1 or not stat.S_ISREG(opened.st_mode):
            return None, "invalid_candidate"
        raw = os.read(descriptor, MAX_PROCESS_OUTPUT_BYTES + 1)
        after = os.fstat(descriptor)
        identities.add((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns))
        if len(raw) > MAX_PROCESS_OUTPUT_BYTES or len(identities) != 1 or len(raw) != opened.st_size:
            return None, "output_too_large" if len(raw) > MAX_PROCESS_OUTPUT_BYTES else "invalid_candidate"
        text = raw.decode("utf-8")
        return parse_draft(text, candidate_input), None
    except FileNotFoundError:
        return None, "missing_output"
    except ContractError as exc:
        if exc.code == "malformed_candidate":
            return None, "malformed_output"
        return None, "invalid_candidate"
    except (OSError, UnicodeError):
        return None, "malformed_output"
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _production_executable(value: str) -> str:
    selected = Path(value)
    if not selected.is_absolute():
        found = shutil.which(value)
        if found is None:
            raise ContractError("runner_unavailable")
        try:
            # Installed CLI shims are commonly symlinks. Resolve discovery once;
            # all validation and execution below use the canonical binary.
            selected = Path(found).resolve(strict=True)
        except OSError as exc:
            raise ContractError("runner_unavailable") from exc
    try:
        metadata = selected.lstat()
        resolved = selected.resolve(strict=True)
    except OSError as exc:
        raise ContractError("runner_unavailable") from exc
    if selected.is_symlink() or resolved != selected or not stat.S_ISREG(metadata.st_mode):
        raise ContractError("runner_unavailable")
    cursor = selected.parent
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise ContractError("runner_unavailable")
        cursor = cursor.parent
    if not os.access(selected, os.X_OK):
        raise ContractError("runner_unavailable")
    return str(selected)


def generate(
    candidate_input: dict[str, Any],
    policy: dict[str, Any],
    *,
    executable: str = "codex",
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Generate one validated candidate with one fixed Codex CLI request."""
    try:
        validate_c(policy, "ModelPolicy")
        if (
            type(policy["format_version"]) is not int
            or policy["format_version"] != 2
            or policy["policy_id"] != "astra-medium-budget-v2"
            or policy["model"] != "gpt-6-astra"
            or policy["effort"] != "medium"
        ):
            raise ContractError("invalid_policy")
    except ContractError:
        return _result("invalid_policy")
    try:
        validate_input(candidate_input)
        if candidate_input["policy_digest"] != digest(policy):
            raise ContractError("policy_digest_mismatch")
    except ContractError:
        return _result("invalid_input")
    if run is subprocess.run:
        try:
            executable = _production_executable(executable)
        except ContractError:
            return _result("process_failed")

    with tempfile.TemporaryDirectory(prefix="session-recall-codex-") as raw_workdir:
        workdir = Path(raw_workdir)
        output_path = workdir / "candidate.json"
        schema_path = workdir / "candidate-schema.json"
        schema_path.write_bytes(canonical_bytes(CANDIDATE_DRAFT_SCHEMA))
        environment = _isolated_environment(workdir)
        instructions = (
            f"{DEVELOPER_INSTRUCTIONS} The exact input_digest is "
            f"{digest(candidate_input)}; copy it without modification. Copy the exact "
            "base_artifact_digest from the input. Set each generated file sha256 to null; "
            "the trusted controller computes content hashes before validation and storage."
        )
        argv = [
            executable, "exec", "--model", "gpt-6-astra", "-c",
            'model_reasoning_effort="medium"', "--sandbox", "read-only",
            "--ephemeral", "--ignore-user-config", "--ignore-rules", "--disable",
            "shell_tool", "--skip-git-repo-check", "--json",
            "--output-last-message", str(output_path), "--output-schema",
            str(schema_path), "--strict-config", "--disable", "multi_agent", "--disable",
            "unbounded_connection_retries", "--disable", "hooks", "--disable",
            "apps", "--disable", "browser_use", "--disable", "code_mode_host",
            "--disable", "skill_search", "--disable", "tool_suggest", "-c",
            f"developer_instructions={json.dumps(instructions)}",
            "-",
        ]
        try:
            invoke = _bounded_subprocess if run is subprocess.run else run
            completed = invoke(
                argv,
                input=canonical_bytes(candidate_input).decode("utf-8"),
                cwd=str(workdir),
                env=environment,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=policy["timeout_seconds"],
                start_new_session=True,
            )
        except subprocess.TimeoutExpired:
            return _result("timeout")
        except ContractError as exc:
            return _result(exc.code)
        except (OSError, UnicodeError, ValueError):
            return _result("process_failed")

        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        stderr = completed.stderr if isinstance(completed.stderr, str) else ""
        if len(stderr.encode("utf-8")) > MAX_PROCESS_OUTPUT_BYTES:
            return _result("process_output_too_large")
        events, event_error = _events(stdout)
        if event_error:
            return _result(event_error)
        failure = _event_failure(events)
        if failure:
            return _result(failure)
        if completed.returncode != 0:
            return _result(_failure_category(stderr))
        try:
            reported_model, reported_effort, usage = _reported(events)
        except ContractError as exc:
            return _result(exc.code)
        evidence = {
            "requested_model": policy["model"],
            "requested_effort": policy["effort"],
            "reported_model": reported_model,
            "reported_effort": reported_effort,
            "usage": usage,
        }
        if _settings_mismatch(events, policy):
            return _result("reported_settings_mismatch", evidence=evidence)
        raw_candidate, output_error = _read_candidate(output_path, candidate_input)
        if output_error:
            return _result(output_error, evidence=evidence)
        return _result("completed", raw_candidate, evidence)
