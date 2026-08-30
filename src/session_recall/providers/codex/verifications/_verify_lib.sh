# _verify_lib.sh — shared machinery for codex verifiers (sourced, not executed)
# Builds synthetic fixtures FROM captured-profiles.json (never hand-typed columns),
# produces drift mutations, hashes stores, detects the implementation.
# shellcheck shell=bash

VLIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CODEX_PROFILES_JSON="$VLIB_DIR/captured-profiles.json"

vlib_impl_present() {
  command -v session-recall-codex >/dev/null 2>&1 || return 1
  python3 -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('session_recall.providers.codex.cli') else 1)" 2>/dev/null
}

# vlib_build_fixture DIR — exact synthetic store built from the captured profiles.
# Env in: HELD_OUT_LITERAL (search term), BAND_TERM (15-30d term). Both optional.
vlib_build_fixture() {
  local dir="$1"
  mkdir -p "$dir/sessions/2026/08/10"
  FIXTURE_DIR="$dir" python3 - <<'PYEOF'
import json, os, sqlite3, time
with open(os.environ["CODEX_PROFILES_JSON"]) as _f:
    prof = json.load(_f)
dirp = os.environ["FIXTURE_DIR"]
held = os.environ.get("HELD_OUT_LITERAL", "zebra-held-out")
band = os.environ.get("BAND_TERM", "band-term-oldweek")
NOW = int(time.time() * 1000)
D = 86400_000

def create_from_profile(db, side):
    for tbl, cols in prof[side]["tables"].items():
        defs, pks = [], [c for c in cols if c[5]]
        for cid, name, ctype, notnull, dflt, pk in cols:
            d = f'"{name}" {ctype}'
            if pk and len(pks) == 1: d += " PRIMARY KEY"
            if notnull: d += " NOT NULL"
            if dflt is not None: d += f" DEFAULT {dflt}"
            defs.append(d)
        if len(pks) > 1:
            names = ", ".join(f'"{c[1]}"' for c in sorted(pks, key=lambda c: c[5]))
            defs.append(f"PRIMARY KEY ({names})")
        db.execute(f'CREATE TABLE "{tbl}" ({", ".join(defs)})')
    ceil, desc = prof[side]["migration_ceiling"], prof[side]["migration_description"]
    for v in range(1, ceil + 1):
        db.execute("INSERT INTO _sqlx_migrations VALUES (?,?,?,?,?,?)",
                   (v, desc if v == ceil else f"migration {v}", "2026-01-01T00:00:00Z", 1, b"x", 1))

def thread_row(cols, **over):
    vals = []
    for cid, name, ctype, notnull, dflt, pk in cols:
        if name in over: vals.append(over[name])
        elif ctype == "INTEGER": vals.append(0)
        else: vals.append("")
    return vals

state = sqlite3.connect(os.path.join(dirp, "state_5.sqlite"))
create_from_profile(state, "state")
tc = prof["state"]["tables"]["threads"]
rows = [
    # newest, paginated, has held-out literal in history
    dict(id="01aa1111-2222-7333-8444-555566667777", history_mode="paginated", source="cli",
         title="alpha paginated session", name="alpha", preview="alpha preview",
         first_user_message="alpha first", cwd="/tmp/repo-a", git_branch="main",
         git_origin_url="https://github.com/o/repo-a.git", agent_path=None,
         created_at=(NOW - 2 * D) // 1000, created_at_ms=NOW - 2 * D,
         updated_at=(NOW - 2 * D) // 1000, updated_at_ms=NOW - 2 * D,
         recency_at_ms=NOW - 2 * D, rollout_path=os.path.join(dirp, "sessions/2026/08/10/rollout-a.jsonl")),
    # older paginated in the 15-30d band, carries BAND_TERM
    dict(id="01aa2222-3333-7444-8555-666677778888", history_mode="paginated", source="cli",
         title="band session " + band, name="band", preview=band,
         first_user_message=band, cwd="/tmp/repo-a", git_branch="main",
         git_origin_url="https://github.com/o/repo-a.git", agent_path=None,
         created_at=(NOW - 20 * D) // 1000, created_at_ms=NOW - 20 * D,
         updated_at=(NOW - 20 * D) // 1000, updated_at_ms=NOW - 20 * D,
         recency_at_ms=NOW - 20 * D, rollout_path=os.path.join(dirp, "sessions/2026/08/10/rollout-b.jsonl")),
    # legacy thread with real rollout
    dict(id="01aa3333-4444-7555-8666-777788889999", history_mode="legacy", source="cli",
         title="legacy session", name="legacy", preview="legacy preview",
         first_user_message="legacy first", cwd="/tmp/repo-b", git_branch="dev",
         git_origin_url=None, agent_path=None,
         created_at=(NOW - 3 * D) // 1000, created_at_ms=NOW - 3 * D,
         updated_at=(NOW - 3 * D) // 1000, updated_at_ms=NOW - 3 * D,
         recency_at_ms=NOW - 3 * D, rollout_path=os.path.join(dirp, "sessions/2026/08/10/rollout-c.jsonl")),
    # guardian-shaped subagent: agent_path NULL but source JSON subagent
    dict(id="01aa4444-5555-7666-8777-88889999aaaa", history_mode="paginated",
         source='{"subagent":{"other":"guardian"}}', title="guardian worker", name="guardian",
         preview="guardian", first_user_message="guardian", cwd="/tmp/repo-a",
         git_branch="main", git_origin_url="https://github.com/o/repo-a.git", agent_path=None,
         created_at=(NOW - 1 * D) // 1000, created_at_ms=NOW - 1 * D,
         updated_at=(NOW - 1 * D) // 1000, updated_at_ms=NOW - 1 * D,
         recency_at_ms=NOW - 1 * D, rollout_path=os.path.join(dirp, "sessions/2026/08/10/rollout-d.jsonl")),
    # archived thread
    dict(id="01aa5555-6666-7777-8888-9999aaaabbbb", history_mode="paginated", source="cli",
         title="archived session", name="archived", preview="archived", archived=1,
         first_user_message="archived", cwd="/tmp/repo-a", git_branch="main",
         git_origin_url="https://github.com/o/repo-a.git", agent_path=None,
         created_at=(NOW - 4 * D) // 1000, created_at_ms=NOW - 4 * D,
         updated_at=(NOW - 4 * D) // 1000, updated_at_ms=NOW - 4 * D,
         recency_at_ms=NOW - 4 * D, rollout_path=os.path.join(dirp, "sessions/2026/08/10/rollout-e.jsonl")),
]
q = f"INSERT INTO threads VALUES ({','.join('?' * len(tc))})"
for r in rows:
    state.execute(q, thread_row(tc, **r))
state.commit(); state.close()

hist = sqlite3.connect(os.path.join(dirp, "thread_history_1.sqlite"))
create_from_profile(hist, "history")
t1 = "01aa1111-2222-7333-8444-555566667777"
t2 = "01aa2222-3333-7444-8555-666677778888"
hist.execute("INSERT INTO thread_turns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (t1, "turn-1", 1, "completed", None, NOW - 2 * D, NOW - 2 * D + 5000, 5000,
              "item-1", "item-2", 0, 3, 100))
items = [
    (t1, "turn-1", "item-1", 1, NOW - 2 * D,
     json.dumps({"type": "userMessage", "id": "item-1",
                 "content": [{"type": "text", "text": f"please find {held} in the code"}]}),
     "userMessage", 1),
    (t1, "turn-1", "item-2", 2, NOW - 2 * D + 1000,
     json.dumps({"type": "agentMessage", "id": "item-2", "text": "done, found it", "phase": "commentary"}),
     "agentMessage", 2),
    (t1, "turn-1", "item-3", 3, NOW - 2 * D + 2000,
     json.dumps({"type": "fileChange", "id": "item-3",
                 "changes": [{"path": "/tmp/repo-a/src/target.py", "kind": "edit"}]}),
     "fileChange", 3),
    (t2, "turn-1", "item-1", 1, NOW - 20 * D,
     json.dumps({"type": "userMessage", "id": "item-1",
                 "content": [{"type": "text", "text": f"old work about {band}"}]}),
     "userMessage", 1),
]
hist.executemany("INSERT INTO thread_items VALUES (?,?,?,?,?,?,?,?)", items)
hist.commit(); hist.close()

roll = os.path.join(dirp, "sessions/2026/08/10/rollout-c.jsonl")
with open(roll, "w") as f:
    f.write(json.dumps({"type": "event_msg",
                        "payload": {"type": "user_message", "message": "legacy hello from rollout"}}) + "\n")
    f.write(json.dumps({"type": "event_msg",
                        "payload": {"type": "agent_message", "message": "legacy answer"}}) + "\n")
print("fixture-built")
PYEOF
}

# vlib_mutate MUTATION DIR — schema-only bad copies built from a mutated profile.
vlib_mutate() {
  local mutation="$1" dir="$2"
  mkdir -p "$dir"
  MUTATION="$mutation" MUT_DIR="$dir" python3 - <<'PYEOF'
import copy, json, os, sqlite3
with open(os.environ["CODEX_PROFILES_JSON"]) as _f:
    prof = copy.deepcopy(json.load(_f))
mut, dirp = os.environ["MUTATION"], os.environ["MUT_DIR"]

def apply(prof, mut):
    st, hi = prof["state"], prof["history"]
    tcols = st["tables"]["threads"]
    if mut == "drop_preview":
        st["tables"]["threads"] = [c for c in tcols if c[1] != "preview"]
    elif mut == "rename_history_mode":
        for c in tcols:
            if c[1] == "history_mode": c[1] = "history_mode_x"
    elif mut == "add_threads_column":
        tcols.append([len(tcols), "example_column", "TEXT", 0, None, 0])
    elif mut == "change_item_json_decl":
        for c in hi["tables"]["thread_items"]:
            if c[1] == "item_json": c[2] = "BLOB"
    elif mut == "drop_thread_turns":
        del hi["tables"]["thread_turns"]
    elif mut == "state_migration_52":
        st["migration_ceiling"] = 52; st["migration_description"] = "mystery"
    elif mut == "history_migration_7":
        hi["migration_ceiling"] = 7; hi["migration_description"] = "mystery"
    elif mut == "failed_migration":
        st["failed_migration"] = True
    elif mut == "extra_unrelated_table":
        pass  # handled at build time
    else:
        raise SystemExit(f"unknown mutation {mut}")

apply(prof, mut)
for side, fname in (("state", "state_5.sqlite"), ("history", "thread_history_1.sqlite")):
    db = sqlite3.connect(os.path.join(dirp, fname))
    for tbl, cols in prof[side]["tables"].items():
        defs, pks = [], [c for c in cols if c[5]]
        for cid, name, ctype, notnull, dflt, pk in cols:
            d = f'"{name}" {ctype}'
            if pk and len(pks) == 1: d += " PRIMARY KEY"
            if notnull: d += " NOT NULL"
            if dflt is not None: d += f" DEFAULT {dflt}"
            defs.append(d)
        if len(pks) > 1:
            names = ", ".join(f'"{c[1]}"' for c in sorted(pks, key=lambda c: c[5]))
            defs.append(f"PRIMARY KEY ({names})")
        db.execute(f'CREATE TABLE "{tbl}" ({", ".join(defs)})')
    ceil, desc = prof[side]["migration_ceiling"], prof[side]["migration_description"]
    failed = prof[side].get("failed_migration") and side == "state"
    for v in range(1, ceil + 1):
        ok = 0 if (failed and v == ceil) else 1
        db.execute("INSERT INTO _sqlx_migrations VALUES (?,?,?,?,?,?)",
                   (v, desc if v == ceil else f"migration {v}", "2026-01-01T00:00:00Z", ok, b"x", 1))
    if mut == "extra_unrelated_table" and side == "state":
        db.execute("CREATE TABLE totally_unrelated (x TEXT)")
    db.commit(); db.close()
print(f"mutated:{mut}")
PYEOF
}

# vlib_assert_drift MUTATION DIR — prove the mutation is physically present (self-test).
vlib_assert_drift() {
  local mutation="$1" dir="$2"
  MUTATION="$mutation" MUT_DIR="$dir" python3 - <<'PYEOF'
import os, sqlite3, sys
mut, dirp = os.environ["MUTATION"], os.environ["MUT_DIR"]
s = sqlite3.connect(f"file:{os.path.join(dirp, 'state_5.sqlite')}?mode=ro", uri=True)
h = sqlite3.connect(f"file:{os.path.join(dirp, 'thread_history_1.sqlite')}?mode=ro", uri=True)
cols = lambda db, t: [r[1] for r in db.execute(f"PRAGMA table_info({t})")]
types = lambda db, t: {r[1]: r[2] for r in db.execute(f"PRAGMA table_info({t})")}
checks = {
    "drop_preview": lambda: "preview" not in cols(s, "threads"),
    "rename_history_mode": lambda: "history_mode_x" in cols(s, "threads") and "history_mode" not in cols(s, "threads"),
    "add_threads_column": lambda: "example_column" in cols(s, "threads"),
    "change_item_json_decl": lambda: types(h, "thread_items")["item_json"] == "BLOB",
    "drop_thread_turns": lambda: not cols(h, "thread_turns"),
    "state_migration_52": lambda: s.execute("SELECT MAX(version) FROM _sqlx_migrations").fetchone()[0] == 52,
    "history_migration_7": lambda: h.execute("SELECT MAX(version) FROM _sqlx_migrations").fetchone()[0] == 7,
    "failed_migration": lambda: s.execute("SELECT COUNT(*) FROM _sqlx_migrations WHERE success=0").fetchone()[0] == 1,
    "extra_unrelated_table": lambda: s.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='totally_unrelated'").fetchone()[0] == 1,
}
ok = checks[mut]()
s.close(); h.close()
print(f"drift-{'present' if ok else 'MISSING'}:{mut}")
sys.exit(0 if ok else 3)
PYEOF
}

# vlib_assert_exact DIR — prove an unmutated fixture matches the captured profile.
vlib_assert_exact() {
  local dir="$1"
  FIX_DIR="$dir" python3 - <<'PYEOF'
import json, os, sqlite3, sys
with open(os.environ["CODEX_PROFILES_JSON"]) as _f:
    prof = json.load(_f)
dirp = os.environ["FIX_DIR"]
for side, fname in (("state", "state_5.sqlite"), ("history", "thread_history_1.sqlite")):
    db = sqlite3.connect(f"file:{os.path.join(dirp, fname)}?mode=ro", uri=True)
    for tbl, expected in prof[side]["tables"].items():
        got = [list(r) for r in db.execute(f"PRAGMA table_info({tbl})")]
        exp = [list(map(lambda v: v, e)) for e in expected]
        if got != exp:
            print(f"MISMATCH {side}.{tbl}"); sys.exit(3)
    ceil = db.execute("SELECT MAX(version) FROM _sqlx_migrations WHERE success=1").fetchone()[0]
    db.close()
    if ceil != prof[side]["migration_ceiling"]:
        print(f"MISMATCH {side} ceiling {ceil}"); sys.exit(3)
print("exact-match")
PYEOF
}

vlib_hash_dir() {  # stable hash listing of every file under DIR
  (cd "$1" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256)
}

# vlib_run CMD... — subprocess with hard timeout; prints exit code as last line "RC:<n>"
vlib_run() {
  RUN_TIMEOUT="${RUN_TIMEOUT:-30}" python3 - "$@" <<'PYEOF'
import os, subprocess, sys
try:
    r = subprocess.run(sys.argv[1:], capture_output=True, text=True,
                       timeout=int(os.environ.get("RUN_TIMEOUT", "30")))
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    print(f"RC:{r.returncode}")
except subprocess.TimeoutExpired:
    print("RC:124")
PYEOF
}
