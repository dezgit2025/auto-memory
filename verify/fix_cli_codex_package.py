"""Isolated wheel provenance probe for the Stage A verifier."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fix_cli_codex_common import ROOT, InfraFailure, VerifyFailure, require, run


def _project_version() -> str:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > 262_144:
        raise InfraFailure("pyproject.toml exceeds bounded metadata size")
    in_project = False
    versions: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project and line.startswith("version") and "=" in line:
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                versions.append(value[1:-1])
    if len(versions) != 1 or not versions[0]:
        raise InfraFailure(f"expected one literal [project] version, found {versions!r}")
    return versions[0]


def verify_packaged_install() -> list[str]:
    expected_version = _project_version()
    with tempfile.TemporaryDirectory(prefix="fix-cli-codex-wheel-") as temp:
        root = Path(temp)
        source = root / "source"
        source.mkdir()
        shutil.copytree(ROOT / "src", source / "src")
        shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
        shutil.copy2(ROOT / "README.md", source / "README.md")
        wheels = root / "wheels"
        wheels.mkdir()
        require(run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps",
             "--no-build-isolation", "--wheel-dir", str(wheels), str(source)],
            cwd=root, timeout=120,
        ))
        built = list(wheels.glob("*.whl"))
        if len(built) != 1:
            raise InfraFailure(f"expected one wheel, found {[p.name for p in built]}")
        venv = root / "venv"
        require(run([sys.executable, "-m", "venv", str(venv)], cwd=root, timeout=60))
        bindir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        cli = bindir / ("session-recall-codex.exe" if os.name == "nt" else "session-recall-codex")
        require(run([str(python), "-m", "pip", "install", "--no-deps", str(built[0])],
                    cwd=root, timeout=120))
        if not cli.is_file():
            raise InfraFailure(f"wheel did not install CLI entry point: {cli}")
        version = require(run([str(cli), "--version"], cwd=root)).stdout.strip()
        if version != expected_version:
            raise VerifyFailure(f"wheel CLI {version!r} != project {expected_version!r}")
        code = (
            "import importlib.metadata as m,json,session_recall as s;"
            "from session_recall.providers.codex import schema;"
            "print(json.dumps({'source':s.__version__,'dist':m.version('auto-memory'),"
            "'state':schema.STATE_PROFILE_NAME,'history':schema.HISTORY_PROFILE_NAME}))"
        )
        result = require(run([str(python), "-c", code], cwd=root))
        data = json.loads(result.stdout)
        wanted = {"source": expected_version, "dist": expected_version,
                  "state": "codex-state-v5-migration-55",
                  "history": "codex-thread-history-v1-migration-6"}
        if data != wanted:
            raise VerifyFailure(f"wheel provenance mismatch: {data!r}")
        smoke = ROOT / "src/session_recall/providers/codex/verifications/smoke.sh"
        path = str(bindir) + os.pathsep + os.environ.get("PATH", "")
        require(run(["bash", str(smoke), "--trial"], env={"PATH": path}, timeout=120),
                contains='"verdict":"PASS"')
    return ["isolated-wheel-version=pass", "isolated-wheel-profile=55",
            "isolated-wheel-trial-smoke=pass"]
