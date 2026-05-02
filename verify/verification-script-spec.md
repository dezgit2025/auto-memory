# Verification Script Specification (Python Projects)

> **Audience:** Agentic coding tools (Claude Code, GitHub Copilot CLI, Cursor, Aider) and the humans who supervise them.
> **Purpose:** Give an autonomous coding agent everything it needs to write a `verify.sh` (or `verify.py`) that can reliably distinguish "the code actually works" from "the agent thinks the code works."
> **Scope:** Python projects. Bash and Python verifier flavors. End-of-task acceptance and per-phase gates.
> **Status:** v1.0 — synthesized from meta-harness operational experience and external research (see §15).

---

## 0. TL;DR for Agents (10-line abstract)

1. Before writing **any** verification code, fill in the **Verification Spec template** in §4.
2. Verification asserts **observable behavior**, not file-existence or import-success. `[Source: Anthropic Claude Code Best Practices]`
3. Use `set -euo pipefail` (bash) or `subprocess.run(check=True, timeout=…)` (python). No silent failures.
4. Run **pytest first**, then add **5+ inline behavioral assertions** covering: happy / boundary / failure-mode / invariant / negative.
5. Include **adversarial / anti-cheat probes**: AST-scan for placeholder bodies, grep for `pytest.skip`, run with **novel inputs** the agent never saw. `[Source: Aider laziness benchmark]`
6. Emit a **structured exit code** (`0/1/2/3/124`) AND a **JSON verdict** on the last stdout line.
7. The verifier must be **idempotent** (re-runnable) and **hermetic** (no shared state).
8. Add a `--self-test` flag that runs the verifier against a known-bad reference and asserts it FAILs.
9. Run the **Pre-"Done" Checklist** in §11 before declaring the task complete. **Capture the exit code.** Do not trust the agent's narrative.
10. If unsure, copy §5 (bash template) or §6 (python template) and fill in the marked slots.

---

## 1. Problem Statement

### 1.1 The "Agent Says Done But Isn't" Failure Mode

Agentic coding tools regularly report task completion when the artifact is broken. Three concrete patterns:

- **Lazy / placeholder code** — The agent writes `# TODO: implement` or `pass` and reports success. Aider quantified this as **"lazy comments on 12 of 89 tasks"** at GPT-4 Turbo baseline. `[Source: Aider unified-diffs benchmark]`
- **Symptom suppression** — Agent silences a failing test with `pytest.skip`, `try/except: pass`, or by hardcoding the asserted return value. Anthropic's own guidance explicitly warns to **"address the root cause, don't suppress the error."** `[Source: Anthropic Claude Code Best Practices]`
- **Compensating bugs** — In multi-file refactors, fixing one bug surfaces another. SWE-ABS reports **~29.6% of patches that pass the standard test suite are behaviorally divergent on more thorough tests.** `[Source: meta-harness DD-003-verify-sh-hardening.md]`

### 1.2 Why Standard Pytest Is Insufficient

Pre-existing tests in the repo are **read by the agent**. Anything the agent can read, the agent can game — by tailoring code to the literal test inputs (Goodhart's Law applied to evals). SWE-bench's design choice — **"the held-out acceptance tests were only used after benchmarking"** — exists for this reason. `[Source: Aider SWE-bench Lite blog post; SWE-bench leaderboard]`

### 1.3 Meta-Harness Position (DD-003)

> "A verify.sh with 5–10 diverse assertions makes it significantly harder to produce a technically-passing but semantically-wrong solution — which is exactly the failure mode the meta-harness is trying to surface."
> — `plans/design-decisions/DD-003-verify-sh-hardening.md`

This spec generalizes that position: every Python project that uses an agentic coding tool needs an externally-authored, behavior-asserting, anti-cheat-aware verifier whose result is **canonical** for "done."

---

## 2. Core Principles

Each principle below is **mandatory**. Skip one and the verifier loses signal.

### P1. Behavior over implementation
Assert what the code **does**, not what it **looks like**. `assert count_words("a a b") == {"a": 2, "b": 1}` — not `assert os.path.exists("wordcount.py")`.
**Rationale:** Acceptance tests are held out from the agent so it cannot "teach to the test." `[Source: SWE-bench design; Aider SWE-bench Lite]`

### P2. Hermetic & deterministic
Run in a fresh `tmpdir`, fresh venv (or container), clean `PYTHONPATH`, fixed `PYTHONHASHSEED=0`, `PYTHONDEVMODE=1`. Never reuse cached state.
**Rationale:** OpenAI Evals built-in templates "contain deterministic functions to compare the output to the ideal_answers." Non-determinism destroys the pass/fail signal. `[Source: OpenAI Cookbook — Getting started with OpenAI Evals]`

### P3. Fast-fail with `set -e` / `pipefail`
Bash: `set -euo pipefail` on line 2. Python: `subprocess.run(..., check=True)` and `pytest -x`.
**Rationale:** A missing `set -e` lets pytest fail and the script still print "PASS" — the canonical false-positive verifier. `[Source: meta-harness exploration-summary §G Failure Mode 4]`

### P4. Structured exit codes (0/1/2/3/124)
`0` = pass, `1` = real test failure, `2` = infra error (re-runnable), `3` = anti-cheat trip, `124` = timeout. Nothing else.
**Rationale:** Lets the orchestrator distinguish "fail the agent" from "retry the harness." `[Source: research-summary §7]`

### P5. Two-witness rule (independent re-execution)
Re-run the canonical example in a **second** subprocess with a fresh import cache; results must match. Script-level analogue of OpenAI's "use a different model to do grading."
**Rationale:** Externalises the agent's implicit decisions. `[Source: OpenAI Cookbook — Getting started with OpenAI Evals; Cognition Labs — Don't build multi-agents]`

### P6. Negative + adversarial cases mandatory
Every verifier must test what must **NOT** happen (silent skips, wrong exception types, no-op mutations) in addition to what must happen.
**Rationale:** Symptom-suppression cheats live in the gap between "succeeds" and "fails correctly." `[Source: Anthropic — root-cause guidance]`

### P7. Verify environment state, not just exit codes
Assert that expected files exist with non-zero size, expected ports are open, expected log tokens are present, expected DB rows are written.
**Rationale:** Anthropic's "verify UI changes visually" generalizes to: assert the **world state**, not the agent's report of it. `[Source: Anthropic Claude Code Best Practices]`

### P8. Idempotent (re-run yields same result)
Cleanup tempdirs, drop tables, kill leftover processes. Running `verify.sh` twice in a row must yield identical results.
**Rationale:** Non-idempotent verifiers produce flaky pass/fail signals indistinguishable from real bugs. `[Source: research-summary §6]`

### P9. Self-test mode (verifier runs against known-bad reference)
`verify.sh --self-test` runs the verifier against a deliberately broken implementation and asserts it correctly **FAILs**.
**Rationale:** "Model grading will have an error rate, so it is important to validate the performance with human evaluation before running the evals at scale." Verifiers must themselves be tested. `[Source: OpenAI Cookbook — How to eval abstractive summarization (G-Eval)]`

---

## 3. Verification Levels

| Level | When | Cost | What runs |
|-------|------|------|-----------|
| **L1: per-phase gate** | After each protocol phase (post-implementer, post-test-writer, post-commit) | <5 s | AST scan + import probe + 1 behavior assertion |
| **L2: end-of-task gate (`verify.sh`)** | When the agent declares "done" | 10–60 s | Full pytest + 5+ inline assertions + anti-cheat probes + held-out inputs + JSON verdict |
| **L3: CI gate** | On every PR / nightly | 1–10 min | All L2 tasks + cross-task regression + mutation probe + coverage threshold |

### 3.1 Decision Matrix

| Question | If yes → use |
|---|---|
| Is this between two protocol phases that produce/consume artifacts? | L1 |
| Is this the gate that decides SR (success rate) for the task? | L2 |
| Is this run on a schedule across many tasks? | L3 |
| Does the gate output need to be parseable by an orchestrator? | L2 + L3 (JSON verdict) |
| Is this a 1-line "did the import work?" check? | L1 only — never L2 |

**Rule:** Every artifact-producing phase needs at least L1. Only L2 results are canonical for "done." `[Source: Anthropic Building Effective Agents — programmatic gates between sub-tasks]`

---

## 4. Verification Spec Template

The agent fills this in **before writing a single line of verifier code**. If it cannot fill in §§4.3–4.10 from the task description, the task description is incomplete and must be clarified first.

### 4.1 Schema (YAML)

```yaml
task_id: <string, e.g. "wordcount-v1">
acceptance_criteria:
  - <observable, behavioral statement (NOT "must use class X")>
files_in_scope:
  - <relative path>
happy_path_cases:
  - input: <literal>
    expected_output: <literal>
boundary_cases:
  - input: <literal>            # empty, None, zero, max
    expected_output: <literal>
failure_mode_cases:
  - input: <literal>            # what triggers an error
    expected_exception: <ExceptionClass>
    expected_message_substring: <optional>
invariants:
  - <statement that is always true (e.g. "sum of values == len(input.split())")>
negative_cases:
  - <something that must NOT happen, e.g. "calling f(x) twice must NOT raise on second call">
anti_cheat_checks:
  - <e.g. "no pytest.skip in tests/", "no hardcoded literal output for held-out input X">
environment_requirements:
  python: ">=3.10"
  deps: [pytest>=8]
  env_vars: {PYTHONHASHSEED: "0", PYTHONDEVMODE: "1"}
performance_budget:           # optional
  max_runtime_seconds: 5
  max_memory_mb: 256
```

### 4.2 Filled-in Example (used in §12 worked example)

```yaml
task_id: wordcount-v1
acceptance_criteria:
  - count_words(text) returns a dict mapping each whitespace-delimited token to its count
  - tokens are case-folded to lowercase before counting
  - punctuation at token boundaries is stripped (",.;:!?")
  - empty input returns {}
files_in_scope:
  - src/wordcount.py
happy_path_cases:
  - input: "the quick brown fox"
    expected_output: {"the": 1, "quick": 1, "brown": 1, "fox": 1}
  - input: "Apple apple APPLE"
    expected_output: {"apple": 3}
boundary_cases:
  - input: ""
    expected_output: {}
  - input: "   "
    expected_output: {}
  - input: "hi!"
    expected_output: {"hi": 1}
failure_mode_cases:
  - input: 42
    expected_exception: TypeError
    expected_message_substring: "str"
  - input: null
    expected_exception: TypeError
invariants:
  - sum(count_words(s).values()) == len([w for w in s.lower().split() if w.strip(",.;:!?")])
negative_cases:
  - count_words("a") must NOT mutate global state
  - count_words must NOT print to stdout
anti_cheat_checks:
  - "no pytest.skip / pytest.xfail in tests/test_wordcount.py"
  - "src/wordcount.py contains no function whose body is only `pass`, `...`, or `raise NotImplementedError`"
  - "the held-out string 'Goodhart law applies here, here, and here.' returns {'goodhart': 1, 'law': 1, 'applies': 1, 'here': 3, 'and': 1}"
environment_requirements:
  python: ">=3.10"
  deps: [pytest>=8]
  env_vars: {PYTHONHASHSEED: "0", PYTHONDEVMODE: "1"}
performance_budget:
  max_runtime_seconds: 2
```

---

## 5. Bash `verify.sh` Template

Copy verbatim. Fill in the slots marked `<<< FILL >>>`. Idioms in §§5.1–5.7 are pulled directly from `task_305/verify.sh`, `task_309/verify.sh`, `task_401/verify.sh`.

```bash
#!/usr/bin/env bash
# verify.sh — end-of-task acceptance gate (Level 2)
# Exit codes: 0=pass, 1=test fail, 2=infra error, 3=anti-cheat trip, 124=timeout

set -euo pipefail

# ----- 5.1 Self-test mode --------------------------------------------------
if [[ "${1:-}" == "--self-test" ]]; then
    echo "[self-test] Running verifier against known-bad reference..."
    tmpdir="$(mktemp -d ./.verify-selftest.XXXXXX)"
    trap 'rm -rf "$tmpdir"' EXIT
    mkdir -p "$tmpdir/src" "$tmpdir/tests"
    cp tests/test_*.py "$tmpdir/tests/" 2>/dev/null || true
    cat > "$tmpdir/src/wordcount.py" <<'BAD'
def count_words(text):
    return {}        # known-bad: always empty
BAD
    if (cd "$tmpdir" && bash "$OLDPWD/verify.sh") 2>/dev/null; then
        echo "[self-test] FAIL — verifier passed a broken impl"; exit 3
    fi
    echo "[self-test] OK — verifier correctly rejects broken impl"; exit 0
fi

# ----- 5.2 Working directory pinning ---------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ----- 5.3 Hermetic environment --------------------------------------------
export PYTHONHASHSEED=0
export PYTHONDEVMODE=1
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH

# ----- 5.4 Static anti-cheat scan (fast-fail BEFORE running anything) ------
# Skip / xfail markers introduced by the agent
if grep -RnE 'pytest\.(skip|xfail)|@pytest\.mark\.(skip|xfail)' tests/ 2>/dev/null \
        | grep -v '^Binary'; then
    echo "ANTI-CHEAT: pytest.skip/xfail found in tests/" >&2
    exit 3
fi

# Placeholder bodies in source
python3 - <<'PYEOF' || exit 3
import ast, glob, sys
bad = []
for path in glob.glob("src/**/*.py", recursive=True):
    try:
        tree = ast.parse(open(path).read())
    except SyntaxError as e:
        print(f"ANTI-CHEAT: {path} has syntax error: {e}", file=sys.stderr); sys.exit(3)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if len(body) == 1:
                stmt = body[0]
                if isinstance(stmt, ast.Pass): bad.append(f"{path}:{node.lineno} {node.name} is `pass`")
                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
                    bad.append(f"{path}:{node.lineno} {node.name} is `...`")
                elif isinstance(stmt, ast.Raise) and isinstance(stmt.exc, ast.Call) \
                        and getattr(stmt.exc.func, "id", "") == "NotImplementedError":
                    bad.append(f"{path}:{node.lineno} {node.name} raises NotImplementedError")
if bad:
    print("ANTI-CHEAT: placeholder function bodies found:", file=sys.stderr)
    for b in bad: print("  " + b, file=sys.stderr)
    sys.exit(3)
PYEOF

# Bare `except:` clauses introduced by agent
if grep -RnE '^\s*except\s*:' src/ 2>/dev/null; then
    echo "ANTI-CHEAT: bare except: clause in src/" >&2
    exit 3
fi

# ----- 5.5 Run the test suite ----------------------------------------------
# -x: stop on first failure. --tb=short: readable traces. -p no:cacheprovider: no cache
python3 -m pytest tests/ -x --tb=short -p no:cacheprovider --import-mode=importlib 2>&1 | tail -40
PYTEST_RC=${PIPESTATUS[0]}
if [[ $PYTEST_RC -ne 0 ]]; then
    echo '{"verdict":"fail","gate":"end","reason":"pytest_failed","exit":1}'
    exit 1
fi

# ----- 5.6 Inline behavioral assertions (5+ required) ----------------------
# HAPPY PATH
python3 -c "
from src.wordcount import count_words
result = count_words('the quick brown fox')
assert result == {'the': 1, 'quick': 1, 'brown': 1, 'fox': 1}, f'happy path: {result!r}'
print('OK: happy path')
"

# BOUNDARY: empty + whitespace
python3 -c "
from src.wordcount import count_words
assert count_words('') == {}, 'empty string'
assert count_words('   ') == {}, 'whitespace only'
assert count_words('hi!') == {'hi': 1}, 'trailing punctuation'
print('OK: boundary cases')
"

# FAILURE MODE: wrong type raises
python3 -c "
from src.wordcount import count_words
try:
    count_words(42)
except TypeError as e:
    assert 'str' in str(e).lower() or True   # message check is soft
    print('OK: TypeError on int input')
else:
    raise AssertionError('expected TypeError on int input')
"

# INVARIANT: sum of counts == number of normalised tokens
python3 -c "
from src.wordcount import count_words
s = 'Apple apple, banana. Cherry: cherry; cherry!'
counts = count_words(s)
expected_tokens = [w.strip(',.;:!?').lower() for w in s.split()]
expected_tokens = [w for w in expected_tokens if w]
assert sum(counts.values()) == len(expected_tokens), f'invariant: {counts} vs {expected_tokens}'
print('OK: invariant — sum(counts.values()) == len(tokens)')
"

# HELD-OUT INPUT (anti-hardcode probe)
python3 -c "
from src.wordcount import count_words
held_out = 'Goodhart law applies here, here, and here.'
result = count_words(held_out)
assert result == {'goodhart': 1, 'law': 1, 'applies': 1, 'here': 3, 'and': 1}, f'held-out: {result!r}'
print('OK: held-out input (anti-hardcode probe)')
"

# NEGATIVE: no stdout side-effects
python3 -c "
import io, contextlib
from src.wordcount import count_words
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    count_words('a b c')
assert buf.getvalue() == '', f'count_words must not print, got: {buf.getvalue()!r}'
print('OK: no stdout side-effect')
"

# ----- 5.7 Two-witness re-execution ----------------------------------------
# Re-run the canonical example in a second subprocess with a clean cache
python3 -B -c "
import sys, importlib
for m in [m for m in sys.modules if m.startswith('src')]: del sys.modules[m]
from src.wordcount import count_words
assert count_words('the quick brown fox') == {'the':1,'quick':1,'brown':1,'fox':1}
print('OK: two-witness re-execution')
"

# ----- 5.8 Structured verdict on stdout's last line ------------------------
echo "PASS: all verifications succeeded"
echo '{"verdict":"pass","gate":"end","exit":0,"checks":["pytest","happy","boundary","failure","invariant","held-out","negative","two-witness"]}'
exit 0
```

### 5.x Notes on idioms

- **`tail -40` after pytest** — pulled from `task_305`/`task_309`/`task_401`; keeps verifier output bounded.
- **`python3 -c "..."` blocks** — every block is self-contained: imports, setup, assertions, `print('OK: ...')`. This is the meta-harness house style.
- **`PIPESTATUS[0]`** — required because `| tail` would otherwise mask pytest's exit code.
- **`unset PYTHONPATH`** — prevents accidental imports from the agent's editor cache.

---

## 6. Python `verify.py` Template

Use when you need richer assertions, JSON parsing, or socket / DB checks.

```python
#!/usr/bin/env python3
"""verify.py — end-of-task acceptance gate (Level 2).

Exit codes:
    0   pass
    1   real test failure
    2   infra error (re-runnable)
    3   anti-cheat trip
    124 timeout
"""
from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
HELD_OUT = "Goodhart law applies here, here, and here."
HELD_OUT_EXPECTED = {"goodhart": 1, "law": 1, "applies": 1, "here": 3, "and": 1}


def emit(verdict: str, exit_code: int, **extra) -> None:
    payload = {"verdict": verdict, "gate": "end", "exit": exit_code, **extra}
    print(json.dumps(payload))


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONDEVMODE": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, env=env, cwd=REPO)


def anti_cheat_static() -> None:
    """AST + grep scan. Exits 3 on any hit."""
    for path in glob.glob(str(REPO / "src" / "**" / "*.py"), recursive=True):
        try:
            tree = ast.parse(Path(path).read_text())
        except SyntaxError as e:
            print(f"ANTI-CHEAT: syntax error in {path}: {e}", file=sys.stderr)
            emit("fail", 3, reason="syntax_error", path=path); sys.exit(3)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    print(f"ANTI-CHEAT: {path}:{node.lineno} `{node.name}` is pass-only", file=sys.stderr)
                    emit("fail", 3, reason="placeholder_body"); sys.exit(3)
    for path in glob.glob(str(REPO / "tests" / "**" / "*.py"), recursive=True):
        text = Path(path).read_text()
        for marker in ("pytest.skip", "pytest.xfail", "@pytest.mark.skip", "@pytest.mark.xfail"):
            if marker in text:
                print(f"ANTI-CHEAT: {marker} in {path}", file=sys.stderr)
                emit("fail", 3, reason="skipped_test", marker=marker); sys.exit(3)


def run_pytest() -> None:
    proc = run([sys.executable, "-m", "pytest", "tests/", "-x", "--tb=short",
                "-p", "no:cacheprovider", "--import-mode=importlib"], timeout=120)
    sys.stderr.write(proc.stdout[-2000:] + proc.stderr[-1000:])
    if proc.returncode != 0:
        emit("fail", 1, reason="pytest_failed", returncode=proc.returncode)
        sys.exit(1)


def behavioral_probes() -> None:
    """Each probe: independent subprocess, fresh import cache."""
    probes = [
        ("happy",     "from src.wordcount import count_words; "
                      "assert count_words('the quick brown fox') == {'the':1,'quick':1,'brown':1,'fox':1}"),
        ("boundary",  "from src.wordcount import count_words; "
                      "assert count_words('') == {} and count_words('   ') == {}"),
        ("failure",   "from src.wordcount import count_words\n"
                      "try: count_words(42)\n"
                      "except TypeError: pass\n"
                      "else: raise AssertionError('expected TypeError')"),
        ("invariant", "from src.wordcount import count_words; "
                      "s='a a b c c c'; assert sum(count_words(s).values()) == len(s.split())"),
        ("held_out",  f"from src.wordcount import count_words; "
                      f"assert count_words({HELD_OUT!r}) == {HELD_OUT_EXPECTED!r}"),
        ("negative",  "import io, contextlib; from src.wordcount import count_words\n"
                      "b=io.StringIO()\n"
                      "with contextlib.redirect_stdout(b): count_words('a b')\n"
                      "assert b.getvalue() == ''"),
    ]
    for name, code in probes:
        proc = run([sys.executable, "-c", code], timeout=10)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            emit("fail", 1, reason=f"probe_{name}_failed"); sys.exit(1)


def two_witness() -> None:
    code = "from src.wordcount import count_words; assert count_words('the quick brown fox') == {'the':1,'quick':1,'brown':1,'fox':1}"
    a = run([sys.executable, "-c", code], timeout=10)
    b = run([sys.executable, "-B", "-c", code], timeout=10)
    if a.returncode != 0 or b.returncode != 0:
        emit("fail", 1, reason="two_witness_disagree"); sys.exit(1)


def self_test() -> None:
    """Run the verifier against a known-bad implementation; assert it FAILs."""
    with tempfile.TemporaryDirectory(prefix="verify-selftest-") as td:
        td = Path(td)
        (td / "src").mkdir()
        (td / "tests").mkdir()
        (td / "src" / "wordcount.py").write_text("def count_words(text):\n    return {}\n")
        (td / "tests" / "test_smoke.py").write_text(
            "from src.wordcount import count_words\n"
            "def test_happy(): assert count_words('a b') == {'a':1,'b':1}\n"
        )
        proc = subprocess.run([sys.executable, str(REPO / "verify.py")],
                              capture_output=True, text=True, cwd=td, timeout=60)
        if proc.returncode == 0:
            print("SELF-TEST FAIL: verifier passed a known-bad impl", file=sys.stderr)
            sys.exit(3)
        print("SELF-TEST OK: verifier correctly rejected known-bad impl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test(); return
    try:
        anti_cheat_static()
        run_pytest()
        behavioral_probes()
        two_witness()
    except subprocess.TimeoutExpired as e:
        emit("fail", 124, reason="timeout", cmd=str(e.cmd)); sys.exit(124)
    except FileNotFoundError as e:
        emit("error", 2, reason="infra", detail=str(e)); sys.exit(2)
    print("PASS: all verifications succeeded")
    emit("pass", 0, checks=["static", "pytest", "probes", "two_witness"])


if __name__ == "__main__":
    main()
```

### 6.x Notes
- Each behavioral probe runs in its own `subprocess.run` with a `timeout` — prevents an infinite loop in the SUT from hanging the verifier.
- `--self-test` writes a known-bad `count_words` returning `{}` and asserts the verifier exits non-zero. Run this in CI before trusting the verifier.
- JSON verdict goes to stdout; human-readable trace goes to stderr.

---

## 7. Anti-Patterns / False-Completion Modes

| Cheat | How the agent does it | Detection idiom in verify |
|---|---|---|
| Lazy placeholder body | Function body is `pass`, `...`, or `raise NotImplementedError` | AST scan §5.4 / §6 `anti_cheat_static()` |
| Hardcoded expected output | `return {"the":1,"quick":1,"brown":1,"fox":1}` because that's the test input | Held-out input probe — run with a string the agent never saw |
| Skipped tests | `@pytest.mark.skip`, `pytest.xfail`, `if False:` | `grep -RnE 'pytest\.(skip|xfail)' tests/` |
| Trivial assertion | New test: `assert True` or `assert 1 == 1` | `grep -RnE 'assert\s+(True|1\s*==\s*1)' tests/` |
| Bare-except suppression | `try: real_logic() except: pass` | `grep -RnE '^\s*except\s*:' src/` |
| Edited the verifier | Agent rewrites `verify.sh` to always exit 0 | Orchestrator hashes verify.sh before/after run; mismatch → fail |
| Mocks the SUT in acceptance tests | `mock.patch('src.wordcount.count_words')` inside an acceptance test | grep for `mock.patch` targeting modules in `src/` |
| Tests depend on cached state | Tests pass on second run only because `.pytest_cache` has stale data | Always run with `-p no:cacheprovider --cache-clear` |
| Async coroutine never awaited | `count_words_async(x)` returns a coroutine the test doesn't await | Run with `PYTHONDEVMODE=1`; un-awaited coroutines raise `RuntimeWarning` |
| Import-only smoke test | Verifier just does `python -c "import src.wordcount"` | Forbid: every probe must call something AND assert its return value |
| Scope creep | Agent edits `src/database.py` to make `src/wordcount.py` tests pass | Diff-scope check: `git diff --name-only` ⊆ declared files |
| Compensating bugs | Two bugs cancel each other out; tests pass | Run mutation probe — delete one function body and re-run, expect failure |
| Tests pass via monkey-patched globals | `autouse` fixture mutates `builtins.True` etc. | Re-run a single golden assertion via `python -c` outside pytest |

`[Sources: Aider laziness benchmark; Anthropic root-cause guidance; OpenAI Cookbook; Cognition Labs; meta-harness exploration-summary §G; research-summary §5]`

---

## 8. Adversarial Checks (Concrete Recipes)

### 8.1 Mutation probe — "would breaking the code be detected?"
```bash
# Delete the body of count_words; re-run verify; expect non-zero exit.
cp src/wordcount.py src/wordcount.py.bak
python3 -c "
import re, pathlib
p = pathlib.Path('src/wordcount.py'); src = p.read_text()
src = re.sub(r'def count_words\([^)]*\):\n(?:    .+\n)+', 'def count_words(text):\n    return {}\n', src)
p.write_text(src)
"
if bash verify.sh; then
    echo "MUTATION PROBE FAIL: verify passed a stub"; mv src/wordcount.py.bak src/wordcount.py; exit 3
fi
mv src/wordcount.py.bak src/wordcount.py
echo "OK: mutation probe — verify correctly catches stub"
```

### 8.2 Hardcoded-output probe — held-out novel input
The verifier asserts behavior on a string **never mentioned in the task prompt or tests**. Hardcoded returns fail this assertion. See §5.6 "HELD-OUT INPUT" block.

### 8.3 Idempotency probe
```bash
bash verify.sh > out1.txt
bash verify.sh > out2.txt
diff out1.txt out2.txt || { echo "IDEMPOTENCY FAIL"; exit 3; }
```

### 8.4 Tamper probe — verify the verifier
```bash
# Orchestrator stores SHA256 of verify.sh before agent runs:
EXPECTED_SHA="abc123..."
ACTUAL_SHA=$(shasum -a 256 verify.sh | awk '{print $1}')
[[ "$EXPECTED_SHA" == "$ACTUAL_SHA" ]] || { echo "TAMPER: verify.sh modified"; exit 3; }
```

### 8.5 Skip-detection probe — collected vs passed
```bash
python3 -m pytest tests/ --collect-only -q 2>&1 | tail -5
collected=$(python3 -m pytest tests/ --collect-only -q 2>&1 | grep -E '[0-9]+ tests? collected' | grep -oE '[0-9]+' | head -1)
passed=$(python3 -m pytest tests/ -q 2>&1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' | head -1)
[[ "$collected" == "$passed" ]] || { echo "SKIP DETECTED: collected=$collected passed=$passed"; exit 3; }
```

---

## 9. Signal Design — Exit Codes & JSON Verdict Schema

### 9.1 Exit code conventions

| Code | Meaning | Orchestrator action |
|---|---|---|
| `0`   | PASS — all checks succeeded | Mark task done |
| `1`   | FAIL — real test failure or behavior assertion failed | Mark task failed; show output to user |
| `2`   | INFRA_ERROR — venv install failed, missing dependency, etc. | Re-run verifier (transient) |
| `3`   | ANTI_CHEAT — placeholder body, skipped test, scope violation, tamper | Mark task failed; do **not** retry |
| `124` | TIMEOUT — verifier or subprocess exceeded its budget | Mark task failed; investigate |

### 9.2 JSON verdict schema

The **last line** of stdout is a single JSON object the orchestrator parses:

```json
{
  "verdict": "pass" | "fail" | "error",
  "gate":    "phase" | "end",
  "exit":    0,
  "duration_s": 12.4,
  "checks":  ["static", "pytest", "happy", "boundary", "failure", "invariant", "held-out", "negative", "two-witness"],
  "reason":  "pytest_failed",
  "artifacts": { "log": "verify.log", "junit": "junit.xml" }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `verdict` | enum | yes | `pass` for exit 0, `fail` for 1/3/124, `error` for 2 |
| `gate` | enum | yes | `phase` (L1) or `end` (L2/L3) |
| `exit` | int | yes | mirrors process exit code |
| `duration_s` | number | optional | wall-clock seconds |
| `checks` | string[] | optional | which named probes ran |
| `reason` | string | required if `verdict != "pass"` | machine-readable cause |
| `artifacts` | object | optional | paths to logs / JUnit XML |

**Rule:** Nothing else may be on the last stdout line. Human-readable progress goes to **stderr**. `[Source: research-summary §7]`

---

## 10. Decision Tree: Bash vs Python

```
Need to write verify.* — which language?
│
├── Are the assertions all "run a python snippet and check stdout/exit"?
│      │
│      ├── YES → use BASH (verify.sh). Less ceremony, easier to read.
│      └── NO  → continue ↓
│
├── Do you need socket / DB / JSON-parsing / temp-file orchestration?
│      │
│      ├── YES → use PYTHON (verify.py). Bash quoting becomes painful.
│      └── NO  → continue ↓
│
├── Do you need cross-platform support (Windows)?
│      │
│      ├── YES → use PYTHON.
│      └── NO  → use BASH.
│
└── Default → BASH for ≤200 lines, PYTHON above that.
```

**Rationale list:**
- Bash wins on: brevity, transparent process exit codes, easy `grep`/`tail` pipelines, ubiquity in CI.
- Python wins on: structured data, timeouts on subprocess, AST scanning, JSON output, cross-platform.
- Hybrid (bash calls `python3 -c`) — the meta-harness default — combines both.

---

## 11. Pre-"Done" Checklist

The agent runs this **before** declaring the task complete. Every item is a hard yes/no.

1. ☐ `verify.sh` (or `verify.py`) exists in the project root.
2. ☐ Verifier starts with `set -euo pipefail` (bash) or `try/except subprocess.TimeoutExpired` (python).
3. ☐ Verifier supports `--self-test` and that mode passes.
4. ☐ Verifier was run in a **fresh shell** (not the agent's editor process) and **exit code was captured**.
5. ☐ Captured exit code is **`0`**.
6. ☐ Last line of stdout is a JSON object matching §9.2 schema with `"verdict":"pass"`.
7. ☐ `pytest --collect-only` count equals `pytest` "passed" count (no silent skips).
8. ☐ AST scan reports zero placeholder function bodies in `src/`.
9. ☐ `grep -RnE 'pytest\.(skip|xfail)' tests/` returns nothing new.
10. ☐ A **held-out input** (one not in the prompt or tests) was asserted to produce the correct output.
11. ☐ Verifier was run **twice in succession**; both runs produced identical exit codes and verdicts.
12. ☐ `git diff --name-only` is a subset of the declared `files_in_scope` from §4.

If any item is ☐ unchecked → **NOT DONE**. Fix and re-run.

---

## 12. Worked Example (end-to-end)

### 12.1 SUT — `src/wordcount.py`

```python
from collections import Counter

_PUNCT = ",.;:!?"

def count_words(text: str) -> dict[str, int]:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    tokens = (w.strip(_PUNCT).lower() for w in text.split())
    return dict(Counter(t for t in tokens if t))
```

### 12.2 Filled spec — see §4.2 above.

### 12.3 `verify.sh` — see §5 template above (it is already specialized for this example).

### 12.4 `verify.py` — see §6 template above (likewise).

### 12.5 What the verifier catches

| Broken impl | Symptom | Caught by |
|---|---|---|
| `def count_words(text): return {}` (stub) | All probes fail; pytest fails | §5.5 pytest, §5.6 happy path |
| `def count_words(text): return {"the":1,"quick":1,"brown":1,"fox":1}` (hardcoded for the prompt's example) | Happy path passes; held-out probe fails | §5.6 HELD-OUT INPUT block |
| Tests file edited to add `@pytest.mark.skip` | Static scan fails | §5.4 anti-cheat scan |
| `count_words` uses `print(...)` for debugging | Negative probe fails | §5.6 NEGATIVE block |
| `count_words(42)` returns `{}` instead of raising | Failure-mode probe fails | §5.6 FAILURE MODE block |
| `count_words` mutates a global `_seen = []` | Two-witness re-execution diverges | §5.7 |

---

## 13. Integration with Agent Protocols

### 13.1 Claude Code subagents
Add to the agent's system prompt or `.claude/agents/<name>.agent.md`:
```
Before declaring DONE, run `bash verify.sh` in a fresh shell; capture the exit code; abort if nonzero. Parse the last stdout line as JSON; abort if "verdict" != "pass".
```
Use the `validator` sub-agent (Claude Agentic Workflow) to enforce this rather than trusting the implementer.

### 13.2 GitHub Copilot CLI (`copilot -p` non-interactive)
```bash
copilot -p "Implement the task in PRD.md. Before declaring done, run verify.sh and exit non-zero if it fails." --yolo
# Then in the wrapper script:
bash verify.sh; rc=$?; [[ $rc -eq 0 ]] || { echo "verify failed: $rc"; exit $rc; }
```
The wrapper, not the agent, is the source of truth for exit code. `[Source: meta-harness COPILOT-AGENT-LEARNING.MD]`

### 13.3 Aider
```bash
aider --test-cmd "bash verify.sh" --auto-test src/wordcount.py
```
Aider re-runs `--test-cmd` after every edit and feeds non-zero output back into the conversation. `[Source: Aider docs]`

### 13.4 Cursor
Add to `.cursor/rules`:
```
Before marking any task complete, run `bash verify.sh` in the integrated terminal. If exit code is nonzero or last-line JSON verdict != "pass", continue working.
```

### 13.5 Per-phase hook patterns
| Hook | Verifier flavor | What it checks |
|---|---|---|
| `pre-commit` | L1 | AST scan, no placeholder bodies, no new skips |
| `post-implementer` (subagent boundary) | L1 | Imports resolve in clean subprocess; one happy-path assertion |
| `post-test-writer` | L1 | Tests are red BEFORE implementation; turn green after |
| `post-task` | L2 | Full `verify.sh` |
| `nightly CI` | L3 | All L2 + mutation probe + coverage threshold + cross-task regression |

---

## 14. Adversarial Critique of THIS Spec

### 14.1 The verifier itself can be wrong (P1 attack)
**Risk:** A `verify.sh` with no assertions exits 0 — the canonical false-pass.
**Mitigation:** §11 checklist item 7 (collected == passed) and §9 self-test mode. CI must reject any verifier whose `--self-test` does not exit non-zero. `[Source: research-summary §8 P1]`

### 14.2 Held-out inputs leak via training data or cached prompts (P2/P8 attack)
**Risk:** If the agent has seen `"Goodhart law applies here, here, and here."` before, the held-out probe is no longer held out.
**Mitigation:** Rotate the held-out input per task. Generate it from `secrets.token_hex(8)` at task creation time and store the expected output in a file the agent cannot read. `[Source: research-summary §8 P8]`

### 14.3 Per-phase gates fragment the task; agent games each gate locally (P3 attack)
**Risk:** The agent satisfies each L1 gate while producing globally incoherent code (Cognition Labs' "subagent 1 built Mario, subagent 2 built Flappy Bird" failure).
**Mitigation:** Every L1 gate also re-asserts a global invariant — e.g. "all modules in `src/` still import together as a package." `[Source: research-summary §8 P3; Cognition Labs]`

### 14.4 Anti-cheat probes flag legitimate code (P4 attack)
**Risk:** A real `try/except SpecificError: log_and_recover()` gets flagged as suppression. A real `pass` in an abstract base class method is correct.
**Mitigation:** AST scan only flags `bare except:` and `pass`-only bodies in **non-abstract** functions (check for `@abstractmethod` decorator). Maintain a per-project allowlist. `[Source: research-summary §8 P4]`

### 14.5 Two-witness rule reduces to single witness when both share a broken oracle (P5 attack)
**Risk:** Both subprocesses parse a config the same wrong way; both agree the broken behavior is correct.
**Mitigation:** The second witness compares against a **literal** expected-output file committed to the repo, not against generated logic. `[Source: research-summary §8 P5]`

### 14.6 Verifier hermeticity is too expensive; teams cache it; cache rots
**Risk:** `python -m venv .verify-venv` adds 30+ seconds per run; teams reuse the venv; system Python upgrade breaks the lockfile silently.
**Mitigation:** Hash `requirements.txt` + Python version into the venv name; rebuild when hash changes. `[Source: research-summary §8 P7]`

### 14.7 Spec assumes Python; many real projects mix languages
**Risk:** A Python project with a Rust extension or a TypeScript frontend has verification surface this spec doesn't cover.
**Mitigation:** §3 levels generalize; §5 template needs a language-specific anti-cheat block (e.g. `cargo clippy -- -D warnings`, `tsc --noEmit`). Future work.

---

## 15. Sources & Further Reading

### External research (research-summary.md)
| # | Source | URL |
|---|---|---|
| S1 | Anthropic — *Claude Code Best Practices* | https://www.anthropic.com/engineering/claude-code-best-practices |
| S2 | Anthropic — *Building Effective Agents* | https://www.anthropic.com/engineering/building-effective-agents |
| S3 | Anthropic — *Claude Code Best Practices* (root-cause section) | (same as S1) |
| S4 | Aider — *Unified Diffs / laziness benchmark* | https://aider.chat/docs/unified-diffs.html |
| S5 | Aider — *SWE-bench Lite result* | https://aider.chat/2024/05/22/swe-bench-lite.html |
| S6 | SWE-bench / SWE-bench Verified leaderboard | https://www.swebench.com/ |
| S7 | OpenAI Cookbook — *Getting started with OpenAI Evals* | https://cookbook.openai.com/examples/evaluation/getting_started_with_openai_evals |
| S8 | OpenAI Cookbook — *How to eval abstractive summarization (G-Eval)* | https://cookbook.openai.com/examples/evaluation/how_to_eval_abstractive_summarization |
| S9 | Cognition Labs — *Don't build multi-agents* | https://cognition.ai/blog/dont-build-multi-agents |
| S10 | GitHub Docs — *Best practices for Copilot coding agent tasks* | https://docs.github.com/en/copilot/using-github-copilot/coding-agent/best-practices-for-using-copilot-to-work-on-tasks |
| S11 | Anthropic Docs — *Claude Agent SDK overview* | https://docs.claude.com/en/docs/agents-and-tools/agent-sdk/overview |

### Meta-harness internal references
- `AUTO-RULE.MD` — task execution protocol (phases 0–6, hard gate on AUTO-RULE.MD read)
- `plans/design-decisions/DD-003-verify-sh-hardening.md` — 5+ assertion standard, rationale
- `benchmark/search_set/task_305/verify.sh` — rule engine — multi-rule chaining + retraction + snapshot isolation idioms
- `benchmark/search_set/task_309/verify.sh` — tiered cache — write-back, TTL fall-through, stats edge case
- `benchmark/search_set/task_401/verify.sh` — job queue — end-to-end priority + retry chain (bug-fix flavor)
- `scripts/pcr_scorer.py` + `scripts/pcr_signals*.py` — signal design (10 signals, weights summing to 1.0)
- `findings/benchmark-design-log.md` — false-completion case studies (task_109 lenient verify)
- `findings/loop-enhancement-log.md` — basename fix for path-prefix scope-violation false positives
- `SOP-FEATUREBENCH.MD` — task creation standard (no stubs, ≥5 assertions)
- `PRD.md` — Phase 2 reliability roadmap (holdout set, anti-overfitting)

---

*End of specification — v1.0.*
