"""Fail-closed macOS SBPL sandbox for untrusted adapter candidates."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import importlib.util
from typing import Mapping, Sequence

from .contracts import ContractError


_SAFE_ENVIRONMENT = {
    "CANDIDATE_MARKER",
    "LANG",
    "LC_ALL",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "SESSION_RECALL_CODEX_STATE_DB",
    "SESSION_RECALL_CODEX_HISTORY_DB",
    "SESSION_RECALL_CODEX_SESSIONS_ROOT",
}
_SECRET_MARKERS = ("AUTH", "CREDENTIAL", "KEY", "SECRET", "TOKEN")
MAX_OUTPUT_BYTES = 256 * 1024


def _quote(value: Path) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _canonical(path: Path, *, directory: bool | None = None) -> Path:
    if not isinstance(path, Path) or path.is_symlink():
        raise ContractError("sandbox_path_unsafe")
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise ContractError("sandbox_path_unsafe") from exc
    cursor = resolved
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise ContractError("sandbox_path_unsafe")
        cursor = cursor.parent
    if directory is True and not resolved.is_dir():
        raise ContractError("sandbox_path_unsafe")
    if directory is False and not resolved.is_file():
        raise ContractError("sandbox_path_unsafe")
    if not (metadata.st_mode & 0o400):
        raise ContractError("sandbox_path_unsafe")
    return resolved


def _contains(root: Path, child: Path) -> bool:
    try:
        child.relative_to(root)
    except ValueError:
        return False
    return True


def _ancestors(paths: Sequence[Path]) -> list[Path]:
    result: set[Path] = set()
    for path in paths:
        cursor = path if path.is_dir() else path.parent
        while True:
            result.add(cursor)
            if cursor == cursor.parent:
                break
            cursor = cursor.parent
    return sorted(result, key=str)


def _sqlite_dependencies() -> tuple[Path, ...]:
    """Return exact non-system dylibs used by trusted stdlib extensions."""
    try:
        runtime = Path(sys.base_prefix).resolve(strict=True)
        extensions = []
        for name in ("_sqlite3", "_lzma", "_zstd", "_bz2"):
            spec = importlib.util.find_spec(name)
            if spec is not None and spec.origin is not None:
                path = Path(spec.origin).resolve(strict=True)
                if not path.is_relative_to(runtime):
                    raise ContractError("sandbox_unavailable")
                extensions.append(path)
    except OSError as exc:
        raise ContractError("sandbox_unavailable") from exc
    if not extensions or len(extensions) > 256:
        raise ContractError("sandbox_unavailable")
    pending = [path.resolve(strict=True) for path in extensions]
    inspected: set[Path] = set()
    allowed: set[Path] = set()
    while pending:
        item = pending.pop()
        if item in inspected:
            continue
        inspected.add(item)
        if len(inspected) > 512:
            raise ContractError("sandbox_unavailable")
        try:
            completed = subprocess.run(
                ["/usr/bin/otool", "-L", str(item)],
                env={"PATH": os.defpath},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ContractError("sandbox_unavailable") from exc
        if completed.returncode != 0 or len(completed.stdout.encode("utf-8")) > 64 * 1024:
            raise ContractError("sandbox_unavailable")
        for line in completed.stdout.splitlines()[1:]:
            raw = line.strip().split(" (", 1)[0]
            if not raw:
                continue
            dependency = Path(raw)
            if not dependency.is_absolute():
                raise ContractError("sandbox_unavailable")
            if raw.startswith(("/usr/lib/", "/System/Library/")):
                continue
            homebrew = raw.startswith(("/opt/homebrew/opt/", "/opt/homebrew/Cellar/"))
            if not homebrew or dependency.suffix != ".dylib":
                raise ContractError("sandbox_unavailable")
            try:
                resolved = dependency.resolve(strict=True)
            except OSError as exc:
                raise ContractError("sandbox_unavailable") from exc
            if not resolved.is_file() or not str(resolved).startswith("/opt/homebrew/Cellar/"):
                raise ContractError("sandbox_unavailable")
            allowed.update((dependency, resolved))
            if resolved not in inspected:
                pending.append(resolved)
    return tuple(sorted(allowed, key=str))


class Sandbox:
    """Execute Python candidates with explicit read roots and one scratch root."""

    def __init__(
        self,
        python_executable: Path | None = None,
        sandbox_executable: Path = Path("/usr/bin/sandbox-exec"),
    ) -> None:
        if sys.platform != "darwin":
            raise ContractError("sandbox_unavailable")
        selected_python = Path(sys.executable) if python_executable is None else python_executable
        self.executable = _canonical(sandbox_executable, directory=False)
        self.runtime = _canonical(Path(sys.base_prefix).resolve(strict=True), directory=True)
        framework_python = self.runtime / "Resources/Python.app/Contents/MacOS/Python"
        launch_python = framework_python if framework_python.is_file() else selected_python
        self.python = _canonical(launch_python.resolve(strict=True), directory=False)
        self.dependencies = _sqlite_dependencies()

    def _environment(
        self, supplied: Mapping[str, str], home: Path
    ) -> dict[str, str]:
        result = {
            "HOME": str(home),
            "TMPDIR": str(home),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        for name, value in supplied.items():
            if not isinstance(name, str) or not isinstance(value, str) or "\x00" in value:
                raise ContractError("sandbox_environment")
            if name in {"HOME", "TMPDIR", "PATH"}:
                continue
            if any(marker in name.upper() for marker in _SECRET_MARKERS):
                raise ContractError("sandbox_environment")
            if name not in _SAFE_ENVIRONMENT:
                raise ContractError("sandbox_environment")
            result[name] = value
        return result

    def _profile(
        self, readable: Sequence[Path], writable: Path | None
    ) -> str:
        rules = [
            "(version 1)",
            "(deny default)",
            f"(allow process-exec (literal {_quote(self.python)}))",
            "(allow signal (target self))",
            "(allow sysctl-read)",
            '(allow file-read* (subpath "/System/Library"))',
            '(allow file-read* (subpath "/usr/lib"))',
            '(allow file-read* (subpath "/usr/share/locale"))',
            '(allow file-read* (literal "/dev/null") (literal "/dev/urandom"))',
            f"(allow file-read* (literal {_quote(self.python)}) (subpath {_quote(self.runtime)}))",
        ]
        ancestry = [self.python, self.runtime, *self.dependencies, *readable]
        if writable is not None:
            ancestry.append(writable)
        for path in _ancestors(ancestry):
            rules.append(f"(allow file-read* (literal {_quote(path)}))")
        for path in self.dependencies:
            rules.append(f"(allow file-read* (literal {_quote(path)}))")
            rules.append(f"(allow file-map-executable (literal {_quote(path)}))")
        for parent in sorted({path.parent for path in self.dependencies}, key=str):
            rules.append(f"(allow file-read* (subpath {_quote(parent)}))")
            rules.append(f"(allow file-map-executable (subpath {_quote(parent)}))")
        for path in readable:
            selector = "subpath" if path.is_dir() else "literal"
            rules.append(f"(allow file-read* ({selector} {_quote(path)}))")
        if writable is not None:
            rules.append(
                f"(allow file-read* (subpath {_quote(writable)}))\n"
                f"(allow file-write* (literal {_quote(writable)}) (subpath {_quote(writable)}))"
            )
        return "\n".join(rules) + "\n"

    def run(
        self,
        argv: Sequence[Path | str],
        *,
        readable: list[Path],
        writable: Path | None,
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        if not argv or type(timeout) is not int or not 1 <= timeout <= 300:
            raise ContractError("sandbox_arguments")
        read_roots = [_canonical(path) for path in readable]
        if len(read_roots) != len(set(read_roots)) or len(read_roots) > 32:
            raise ContractError("sandbox_arguments")
        write_root = None if writable is None else _canonical(writable, directory=True)
        working = _canonical(cwd, directory=True)
        if not any(_contains(root, working) for root in read_roots) and not (
            write_root is not None and _contains(write_root, working)
        ):
            raise ContractError("sandbox_cwd_denied")
        arguments = [str(item) for item in argv]
        if any(not item or "\x00" in item for item in arguments):
            raise ContractError("sandbox_arguments")
        script = _canonical(Path(arguments[0]), directory=False)
        if not any(_contains(root, script) for root in read_roots):
            raise ContractError("sandbox_path_denied")
        arguments[0] = str(script)
        home = write_root if write_root is not None else working
        normalized_env = dict(env)
        for name in (
            "SESSION_RECALL_CODEX_STATE_DB",
            "SESSION_RECALL_CODEX_HISTORY_DB",
            "SESSION_RECALL_CODEX_SESSIONS_ROOT",
        ):
            if name not in normalized_env:
                continue
            try:
                value = Path(normalized_env[name]).resolve(strict=True)
            except OSError as exc:
                raise ContractError("sandbox_path_denied") from exc
            if not any(_contains(root, value) for root in read_roots):
                if name == "SESSION_RECALL_CODEX_SESSIONS_ROOT":
                    normalized_env.pop(name)
                    continue
                raise ContractError("sandbox_path_denied")
            normalized_env[name] = str(value)
        environment = self._environment(normalized_env, home)
        profile = self._profile(read_roots, write_root)
        command = [
            str(self.executable), "-p", profile, str(self.python), *arguments
        ]
        try:
            process = subprocess.Popen(
                command,
                cwd=working,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            raise ContractError("sandbox_unavailable") from exc
        chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
        overflow = threading.Event()
        output_lock = threading.Lock()

        def drain(name: str, stream: object) -> None:
            while True:
                data = stream.read(8192)  # type: ignore[attr-defined]
                if not data:
                    return
                with output_lock:
                    remaining = MAX_OUTPUT_BYTES - sum(
                        len(item) for item in chunks.values()
                    )
                    if remaining > 0:
                        chunks[name].extend(data[:remaining])
                    exceeded = len(data) > remaining
                if exceeded:
                    overflow.set()
                    try:
                        os.killpg(process.pid, 9)
                    except ProcessLookupError:
                        pass
                    return

        readers = [
            threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, 9)
            except ProcessLookupError:
                pass
            process.wait()
            raise ContractError("sandbox_timeout") from exc
        finally:
            for reader in readers:
                reader.join(timeout=1)
            for stream in (process.stdout, process.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
        if overflow.is_set():
            raise ContractError("sandbox_output_limit")
        return subprocess.CompletedProcess(
            command,
            returncode,
            chunks["stdout"].decode("utf-8", errors="replace"),
            chunks["stderr"].decode("utf-8", errors="replace"),
        )

    def probe(self, workspace: Path) -> subprocess.CompletedProcess[str]:
        root = _canonical(workspace, directory=True)
        run_root = Path(tempfile.mkdtemp(prefix="sandbox-capability-", dir=root))
        probe_root = run_root / "candidate"
        scratch = run_root / "scratch"
        protected = run_root / "protected"
        for path in (probe_root, scratch, protected):
            path.mkdir(mode=0o700)
        credential = protected / "credential"
        credential.write_text("secret", encoding="utf-8")
        escape = probe_root / "escape"
        escape.symlink_to(credential)
        source = r'''import json, socket, subprocess, sys
from pathlib import Path
readable, scratch, protected, escape, child = map(Path, sys.argv[1:])
result = {}
def attempt(name, callback):
    try: callback()
    except BaseException: result[name] = "denied"
    else: result[name] = "allowed"
attempt("readable", lambda: readable.read_text())
attempt("scratch_write", lambda: (scratch / "ok").write_text("ok"))
attempt("protected_read", lambda: protected.read_text())
attempt("protected_write", lambda: protected.write_text("bad"))
attempt("symlink_escape", lambda: escape.read_text())
attempt("network", lambda: socket.socket().bind(("127.0.0.1", 0)))
attempt("child_exec", lambda: subprocess.run([str(child)], check=True))
print(json.dumps(result, sort_keys=True))
expected = {"child_exec":"denied","network":"denied","protected_read":"denied",
 "protected_write":"denied","readable":"allowed","scratch_write":"allowed",
 "symlink_escape":"denied"}
raise SystemExit(0 if result == expected else 5)
'''
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix="sandbox-probe-", suffix=".py", dir=probe_root
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(source)
                handle.flush()
                os.fsync(handle.fileno())
            script = Path(raw_path)
            readable = probe_root / "input"
            readable.write_text("synthetic", encoding="utf-8")
            return self.run(
                [script, readable, scratch, credential, escape, Path("/usr/bin/true")],
                readable=[probe_root],
                writable=scratch,
                cwd=probe_root,
                env={},
                timeout=10,
            )
        finally:
            try:
                if "raw_path" in locals():
                    Path(raw_path).unlink()
            except OSError:
                pass
