#!/usr/bin/env python3
"""Installed-wheel, synthetic-store V5 workflow probe (no live Codex or user data)."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import secrets


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode()


def create_db(path: Path, profile: dict, *, migration56: bool = False,
              private_column: str = "") -> None:
    tables = {name: list(rows) for name, rows in profile["tables"].items()}
    if migration56:
        tables["threads"] = [
            *tables["threads"],
            [len(tables["threads"]), private_column, "TEXT", 0, None, 0],
        ]
    connection = sqlite3.connect(path)
    try:
        for name, rows in tables.items():
            columns = []
            primary = sorted((row for row in rows if row[5]), key=lambda row: row[5])
            for row in rows:
                part = f'"{row[1]}" {row[2]}'
                if len(primary) == 1 and row[5]:
                    part += " PRIMARY KEY"
                if row[3]:
                    part += " NOT NULL"
                if row[4] is not None:
                    part += f" DEFAULT {row[4]}"
                columns.append(part)
            if len(primary) > 1:
                columns.append("PRIMARY KEY (" + ",".join(f'"{row[1]}"' for row in primary) + ")")
            connection.execute(f'CREATE TABLE "{name}" ({",".join(columns)})')
        ceiling = 56 if migration56 else profile["migration_ceiling"]
        for version in range(1, ceiling + 1):
            description = "synthetic schema repair" if version == ceiling else f"migration {version}"
            connection.execute(
                'INSERT INTO "_sqlx_migrations" '
                '(version,description,installed_on,success,checksum,execution_time) '
                "VALUES (?,?,'2026-09-20 00:00:00',1,?,0)",
                (version, description, b""),
            )
        connection.commit()
    finally:
        connection.close()


def fake_codex(path: Path, counter: Path) -> None:
    source = r'''#!/usr/bin/env python3
import hashlib,json,sys
def canon(v): return json.dumps(v,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(",",":")).encode()
expected=["exec","--model","gpt-6-astra","-c",'model_reasoning_effort="medium"',"--sandbox","read-only","--ephemeral","--ignore-user-config","--ignore-rules","--disable","shell_tool","--skip-git-repo-check","--json"]
if sys.argv[1:1+len(expected)] != expected: raise SystemExit("unexpected argv prefix")
required=["--output-last-message","--output-schema","--strict-config","multi_agent","unbounded_connection_retries","hooks","apps","browser_use","code_mode_host","skill_search","tool_suggest"]
if any(item not in sys.argv for item in required) or sys.argv[-1] != "-": raise SystemExit("missing fixed runner arguments")
request=json.load(sys.stdin)
parts=[]
for item in request["schema_diff"]["differences"]:
    if item.startswith("target_profiles_part_"): parts.append(item.split(":",1)[1])
content="".join(parts)
profile="session_recall/providers/codex/verifications/captured-profiles.json"
candidate={"format_version":1,"input_digest":"sha256:"+hashlib.sha256(canon(request)).hexdigest(),"base_artifact_digest":request["base_artifact_digest"],"files":[{"path":profile,"sha256":"sha256:"+hashlib.sha256(content.encode()).hexdigest(),"content":content}]}
output=sys.argv[sys.argv.index("--output-last-message")+1]
open(output,"wb").write(canon(candidate))
with open(COUNTER,"a",encoding="utf-8") as handle: handle.write(hashlib.sha256(canon(request)).hexdigest()+"\n")
print(json.dumps({"type":"turn.completed","model":"gpt-6-astra","reasoning_effort":"medium","usage":{"input_tokens":100,"output_tokens":50,"reasoning_tokens":10,"total_tokens":150}}))
'''.replace("COUNTER", repr(str(counter)))
    path.write_text(source, encoding="utf-8")
    path.chmod(0o700)


def command(executable: Path, common: list[str], *args: str, env: dict[str, str], expected=(0,)) -> dict:
    process = subprocess.run([str(executable), "--json", *common, *args], env=env,
                             text=True, capture_output=True, timeout=360)
    if process.returncode not in expected:
        raise RuntimeError(f"command failed {args}: rc={process.returncode} out={process.stdout!r} err={process.stderr!r}")
    return json.loads(process.stdout)


def main() -> int:
    root = Path(os.environ["VERIFY_ROOT"]).resolve()
    wheel_root = Path(os.environ["VERIFY_WHEEL_ROOT"]).resolve()
    import session_recall
    from session_recall.codex_fix.trust import load_catalogue
    installed = Path(session_recall.__file__).resolve()
    if wheel_root in installed.parents or (wheel_root / "src") in installed.parents:
        raise RuntimeError(f"source-tree import forbidden: {installed}")
    profile_path = importlib.resources.files("session_recall.providers.codex").joinpath(
        "verifications", "captured-profiles.json"
    )
    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    state = root / "state_5.sqlite"
    history = root / "thread_history_1.sqlite"
    sessions = root / "sessions"
    managed = root / "managed"
    sessions.mkdir()
    managed.mkdir(mode=0o700)
    private_column = "private_56_" + secrets.token_hex(8)
    create_db(state, profiles["state"], migration56=True, private_column=private_column)
    create_db(history, profiles["history"])
    fake_dir = root / "fake-bin"
    fake_dir.mkdir()
    fake = fake_dir / "codex"
    counter = root / "fake-codex-requests.log"
    fake_codex(fake, counter)
    home = root / "home"
    codex_home = root / "codex-home"
    home.mkdir()
    codex_home.mkdir()
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update({
        "HOME": str(home),
        "CODEX_HOME": str(codex_home),
        "PATH": str(fake_dir) + os.pathsep + os.environ.get("PATH", ""),
        "SESSION_RECALL_CODEX_FIX_ROOT": str(managed),
        "SESSION_RECALL_CODEX_STATE_DB": str(state),
        "SESSION_RECALL_CODEX_HISTORY_DB": str(history),
        "SESSION_RECALL_CODEX_SESSIONS_ROOT": str(sessions),
    })
    cli = Path(sys.executable).parent / "session-recall-codex-fix"
    public = Path(sys.executable).parent / "session-recall-codex"
    common = ["--root", str(managed), "--state-db", str(state), "--history-db", str(history),
              "--sessions-root", str(sessions)]
    before_hashes = {"state": hashlib.sha256(state.read_bytes()).hexdigest(),
                     "history": hashlib.sha256(history.read_bytes()).hexdigest()}

    def unchanged(label: str) -> None:
        after = {"state": hashlib.sha256(state.read_bytes()).hexdigest(),
                 "history": hashlib.sha256(history.read_bytes()).hexdigest()}
        if after != before_hashes:
            raise RuntimeError(f"database changed after {label}")

    assisted = command(cli, common, "assist", env=env, expected=(2,))
    if assisted["status"] == "sandbox_unavailable":
        print(canonical({"status": "infrastructure", "reason": "sandbox_unavailable"}).decode())
        return 2
    if assisted["status"] != "action_needed":
        raise RuntimeError(f"assist did not reach review: {assisted}")
    unchanged("assist")
    if not counter.exists() or len(counter.read_text(encoding="utf-8").splitlines()) != 1:
        raise RuntimeError("fake Codex request count was not exactly one")
    candidate_id = assisted["detail"]["candidate_id"]
    command(cli, common, "approve", "--candidate", candidate_id, "--yes", env=env)
    unchanged("approve")
    applied = command(cli, common, "apply-candidate", "--candidate", candidate_id, env=env)
    unchanged("apply-candidate")
    operation = applied["detail"]["operation_id"]
    selector = managed / "selection/current.json"
    active_selector = selector.read_bytes()
    for args in (("schema-check",), ("list",), ("repos",)):
        process = subprocess.run([str(public), *args], env=env, text=True, capture_output=True, timeout=120)
        if process.returncode != 0:
            raise RuntimeError(f"public command failed {args}: {process.stderr}")
        unchanged("public-" + args[0])
    repeated = command(cli, common, "apply-candidate", "--candidate", candidate_id, env=env)
    if repeated["status"] != "no_op":
        raise RuntimeError("fresh-process candidate apply was not idempotent")
    unchanged("repeat-apply")
    rolled = command(cli, common, "rollback", "--repair", operation, env=env)
    unchanged("rollback")
    if rolled["status"] != "rolled_back_incompatible":
        raise RuntimeError(f"rollback did not report incompatibility: {rolled['status']}")
    if selector.read_bytes() == active_selector:
        raise RuntimeError("rollback did not restore the prior selector")
    restored = json.loads(selector.read_text(encoding="utf-8"))
    if restored["artifact_digest"] != load_catalogue()["seed_artifact_digest"]:
        raise RuntimeError("rollback selector is not the prior bundled seed")
    if len(counter.read_text(encoding="utf-8").splitlines()) != 1:
        raise RuntimeError("workflow performed more than one model request")
    print(canonical({"status": "pass", "candidate_id": candidate_id,
                     "private_column_sha256": hashlib.sha256(private_column.encode()).hexdigest(),
                     "database_sha256": before_hashes}).decode())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(canonical({"status": "fail", "reason": str(exc)}).decode())
        raise SystemExit(1)
