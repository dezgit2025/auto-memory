> Process: Follow plans/AGENT-PLAN.md for all task execution.

# Project: Progress Tracker

**Plan:** `plans/pr5-plan.md`
**Dev folder:** `/Users/dez/Projects/auto-memory`

---

## Gates

### Plan Gate

> **Auto-populated:** `pr5-plan` is replaced with the plan filename when this progress.md is created or updated.

- **Read `plans/pr5-plan.md` before AND after every step.**
- Before: confirm your approach aligns with the plan's specification.
- After: diff your changes against the plan — if anything deviates, fix the code before moving on.
- The plan file is **read-only** — never modify it from progress.md context.

### Architecture Gate

> **Conditional:** Only applies if `plans/architectural-design.md` exists. If no architecture doc exists, skip this gate entirely.

**Gate control** is set in the frontmatter of `plans/architectural-design.md`:

| `gate` value | Behavior |
|-------------|----------|
| `enforced` | **Default.** Read before/after every step. Contradictions block progress. |
| `advisory` | Reference during steps. Contradictions are noted but don't block. |
| `skip` | Gate inactive. Document is reference-only. |

- **If `gate: enforced`:** Read architecture doc before AND after every step, same as plan gate. Fix contradictions immediately.
- **If `gate: advisory`:** Read at phase start. Note deviations in Key Learnings but continue.
- **If `gate: skip`:** Ignore this gate. Proceed as if no architecture doc exists.
- Architecture doc is **read-only** — never modify it from progress.md context.
- Add the architecture reference to the header:

```markdown
**Architecture:** `plans/architectural-design.md` (gate: enforced)
```

---

## Rules to Follow

> See `plans/AGENT-PLAN.md` for the 5-phase task execution protocol.
> See `plans/workflow/` for detailed workflow rules:
> - `agent-orchestration.md` — sub-agent dispatch, parallelism, domain routing
> - `testing-protocol.md` — TDD, test placement, quality gates
> - `progress-discipline.md` — how to manage this file, recovery
> - `commit-protocol.md` — git workflow, branching, atomic commits
> - `code-gap-handling.md` — adaptive gap resolution: ImportError, API changes, auth failures, unknown blockers
>
> **Stack-specific rules** (only if present in the project):
> - `stacks/MAF.MD` — MAF & Azure AI Foundry: package resolution, version pinning, key packages, auth rules

### Core Rules
1. **Read this file FIRST** at the start of every session
2. **Update this file AFTER** completing each step — immediately, not in batch
3. **Never contradict this file** — if it says something is done, don't redo it
4. **Follow AGENT-PLAN.md** for task execution, testing, and commits
5. **Research before guessing** — log findings to `plans/research-log.md`

### Execution Model
- **Strict delegation.** Orchestrator coordinates — subagents do code work.
- **Only the orchestrator updates this file.** Subagents report back; orchestrator records.
- **Use subagents in parallel** when steps have no shared dependencies.

### Testing (After Every Step)
- Follow `plans/AGENT-PLAN.md` Phases 3-4 for all testing after implementation.
- 3 agents, sequential loop: `test-planner` → `test-writer` → `test-runner` (one test at a time).
- A step is not `[x]` until all planned tests pass AND verification passes.

### Step Verification
- **Commit after each phase is completed.** This is your checkpoint.
- **Each step should have a verification command.** A step is not complete until its verify command passes.
- **Mark a step `[x]` only when:** action is done, verification passes, AND tests exist.
- **On ANY error/exception:** Log it in the Exceptions & Learnings section.

### Recovery After Crash
```
1. Read this file → find last completed step
2. Check git log → verify last commit matches
3. Resume from the NEXT uncompleted step
4. If a step was in-progress, re-run it from scratch
```

---

## Import Rules

> **Optional section.** Include when the project has strict module boundaries that agents must respect.
> Delete this section if not applicable.

Define which modules can import from which. This prevents agents from creating circular dependencies or coupling unrelated modules.

**How to populate:**
```
[module A] -> [module B] + [module C]    (A can import from B and C)
[module B] -> [module D] only            (B can only import from D)
[module A] DO NOT import [module E]      (explicit prohibition)
```

**Example:**
```
tools -> core/* + clients/* + references/  (tools use core, clients, and references)
clients -> core/auth + config              (clients use only auth/config)
tools DO NOT import each other             (enables parallel development)
functions/ imports NOTHING from src/       (standalone deployment unit)
```

**Rules:**
- Each agent must check import rules before adding any `import` statement.
- If a step requires a cross-boundary import, STOP and flag it — the plan may need updating.

---

## Formatting Rules — How to Structure Phases, Steps, and Substeps

> These rules define how sprint progress sections must be written.
> Follow this structure exactly when filling in the Sprint Progress section.

### Current Status Table

The status table is the **first thing to check** at session start. It shows all phases and their state at a glance.

**How to populate:**
- Add one row per phase when you define it.
- Update the Status column immediately when a phase changes state.
- Include completion dates for finished phases.

```markdown
| Phase | Status |
|-------|--------|
| Phase I — Setup | Complete (2026-03-01) |
| Phase II — Core Logic | IN PROGRESS — Step 3 of 5 |
| Phase III — Integration | NOT STARTED |
```

**Valid statuses:** `NOT STARTED`, `IN PROGRESS — Step N of M`, `Complete (YYYY-MM-DD)`, `BLOCKED (reason)`

### Phase Format

Each phase is an `###` heading under Sprint Progress with a number, name, goal, and plan reference.

**How to populate:**
- Number phases sequentially (Phase I, Phase II, or Phase 0, Phase 1).
- Name describes the theme (not individual tasks).
- Goal is one sentence — what's true when this phase is done.
- Reference the plan file. `pr5-plan` auto-fills from the header.

```markdown
### Phase N — Descriptive Name

**Plan:** `plans/pr5-plan.md`
**Goal:** [One sentence — what this phase achieves]
```

- Every phase MUST have a **Goal** line.
- Add an **Architecture** line if an architecture doc exists:
  `**Architecture:** plans/architectural-design.md (source of truth)`

### Max Parallel Agents Table

Before each phase's steps, include a table showing how many agents run and when. This is the dispatch plan — it tells the orchestrator what to launch and in what order.

**How to populate:**
- One row per step (not per substep).
- Agent count = how many subagents run simultaneously for that step.
- Description = parallelism tag + brief summary.
- Total line summarizes the full phase.

```markdown
#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 2 | P1-A, P1-B (independent files) |
| Step 2 | 1 | GATE — integration verify |
| Step 3 | 3 | P2-A, P2-B, P2-C (independent modules) |

**Total: 6 agent dispatches across 3 steps.**
```

**Rules:**
- Sequential steps (`[SEQ]`) always have `1` agent.
- Gate steps (`[GATE]`) always have `1` agent.
- Parallel steps list all sub-labels (P1-A, P1-B, etc.).

### Step Format

Each step is an `####` heading under its phase. Include the parallelism tag and agent count.

**How to populate:**
- Number steps sequentially within each phase.
- Tag with `[SEQ]`, `[P1-A, P1-B]`, or `[GATE]`.
- State agent count after the tag.
- Launch condition: what must be true (prior step, gate, or "None").
- File ownership: which agent writes to which files (prevents merge conflicts).

```markdown
#### Step N — Description `[TAG]` — N agent(s)

> **Launch condition:** [What must be true before this step starts]
> **File ownership:** [Which agent writes to which file]

- [ ] Substep description
- [ ] Substep description
- [ ] **Verify:** `[shell command that proves the step worked]`
```

**Rules:**
- Every step MUST have a **launch condition** (or "None" if first step).
- Every step MUST end with a **Verify** substep — a runnable command.
- Steps that produce code MUST specify **file ownership** (which agent writes where).

### Substep Format

Substeps are checkboxes (`- [ ]`) under a step. They are atomic actions.

**How to populate:**
- Start with an action verb: Add, Fix, Replace, Create, Remove, Update, Configure.
- One action per substep — if it has "and", split it into two substeps.
- Include the target file or function when applicable.
- Last substep is always a **Verify** with a runnable shell command.
- When marking complete, add timestamp: `[x] (2026-03-07)`

```markdown
- [ ] Replace `load_dotenv()` with project-root-relative path in `src/main.py`
- [ ] Add `cli_entry()` sync wrapper around `main()` in `src/main.py`
- [ ] File stays under 80 lines
- [ ] **Verify:** `pytest tests/test_main.py -v`
```

**Status tracking on parallel substeps:**
```markdown
**`[P1-A]` Fix `src/main.py`** — NOT STARTED
**`[P1-A]` Fix `src/main.py`** — IN PROGRESS
**`[P1-A]` Fix `src/main.py`** — COMPLETE (2026-03-07)
**`[P1-A]` Fix `src/main.py`** — BLOCKED (waiting on API key)
```

### Parallel Step Naming

When steps run in parallel, name them with group prefixes.

**How to populate:**
- Bold the parallel tag: **`[P1-A]`**
- Include the target file in the label.
- Add status suffix after the label.
- Each parallel sub-step gets its own substep list.

```markdown
#### Step 1 — Code Changes `[P1-A, P1-B]` — 2 agents in parallel

> **Launch condition:** None (first step).
> **File ownership:** P1-A owns src/main.py, P1-B owns pyproject.toml.

**`[P1-A]` Fix `src/main.py`** — NOT STARTED
- [ ] Substep...
- [ ] **Verify:** `python -c "from src.main import cli_entry"`

**`[P1-B]` Update `pyproject.toml`** — NOT STARTED
- [ ] Substep...
- [ ] **Verify:** `grep -A1 'project.scripts' pyproject.toml`
```

### Success Criteria

Every phase MUST end with a success criteria section. These are the acceptance tests for the phase — if all are true, the phase is done.

**How to populate:**
- Number each criterion.
- Each must be **measurable** — a command you can run, a behavior you can observe.
- Always include a regression check ("All existing tests pass").
- Reference specific commands or observable outcomes, not vague goals.

```markdown
#### Success Criteria (Phase N)

1. `logicflow` command works from any directory
2. `python -m src.main` still works from project root
3. MCP server unaffected — no changes to `src/mcp_server.py`
4. All existing tests pass (zero regressions)
5. `src/main.py` stays under 80 lines
```

---

## Current Status

| Phase | Status |
|-------|--------|
| Phase 0 — Architecture | SKIP — PR review remediation, not new feature |
| Phase 1 — Wave 1: Foundation Fixes | Complete (2026-04-28) |
| Phase 1.5 — WSL/Linux Compat | Complete (2026-04-28) |
| Phase 2 — Wave 2: Structure + Hardening | Complete (2026-04-28) |
| Phase 3 — Wave 3: Security | Complete (2026-04-28) |
| Phase 4 — Wave 4: Regression Tests | Complete (2026-04-28) |
| Phase 5 — Wave 5: Convention Update | Complete (2026-04-28) |
| Phase 6 — Wave 6: Documentation | Complete (2026-04-28) |
| Phase 7 — E2E Testing | Complete (2026-04-28) |

---

## Parallelism Legend

| Tag | Meaning |
|-----|---------|
| `[SEQ]` | Sequential — must complete before next step |
| `[P1-x]` | Parallel group 1 — all P1 steps launch simultaneously |
| `[P2-x]` | Parallel group 2 — all P2 steps launch simultaneously |
| `[GATE]` | Sync point — waits for all prior parallel steps to finish |

---

## Key Learnings

> Carry forward across phases. When you hit a bug, conflict, or blocker that has a resolution, log it here so future phases don't repeat the mistake.

**How to populate:**
- **Type:** `Bug`, `Conflict`, `Blocker`, `Gotcha`, `Performance`
- **Description:** What happened — specific enough to recognize if it recurs.
- **Resolution:** What fixed it — specific enough to apply again.

| Type | Description | Resolution |
|------|-------------|------------|
| _(none yet)_ | | |

---

## Exceptions & Learnings

> Runtime errors, unexpected behaviors, and one-off issues encountered during execution. Unlike Key Learnings (which are reusable patterns), this section captures session-specific incidents.

_(Log new issues here as they arise.)_

---

## Sprint Progress

### Phase 0 — Architecture (SKIPPED)

> **Skipped:** This is a PR review remediation, not a new feature. The architecture is defined in `plans/pr5-plan.md` (CC-1 through CC-4 cross-cutting design changes + per-finding remediation).

---

### Phase 1 — Wave 1: Foundation Fixes

**Plan:** `plans/pr5-plan.md`
**Goal:** Fix all no-dependency HIGH findings and add env-var feature flag so file backends are opt-in.

#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 7 | P1-A through P1-G (all independent, no shared files except config.py) |
| Step 2 | 1 | [GATE] — verify all Wave 1 fixes pass tests |

**Total: 8 agent dispatches across 2 steps.**

---

#### Step 1 — Wave 1 Parallel Fixes `[P1-A, P1-B, P1-C, P1-D, P1-E, P1-F, P1-G]` — 7 agents in parallel

> **Launch condition:** None (first step).

**`[P1-A]` `cc1-env-flag` — add `ENABLE_FILE_BACKENDS` to config.py** — COMPLETE (2026-04-28)
> **File ownership:** P1-A owns `config.py`
- [x] (2026-04-28) Add `_truthy()` helper and `ENABLE_FILE_BACKENDS` flag to `config.py`
- [x] (2026-04-28) Update `discovery.py` to gate file-backend imports behind the flag
- [x] (2026-04-28) **Verify:** `python3 -c "from session_recall.config import ENABLE_FILE_BACKENDS; assert not ENABLE_FILE_BACKENDS"`

**`[P1-B]` `f7-list-default` — revert `--limit` default to 10** — COMPLETE (2026-04-28)
> **File ownership:** P1-B owns `commands/list_sessions.py`
- [x] (2026-04-28) Change `limit = args.limit or 50` to `limit = args.limit or 10` in `list_sessions.py`
- [x] (2026-04-28) **Verify:** `python3 -m pytest src/session_recall/tests/e2e/test_e2e_list.py -v`

**`[P1-C]` `f5-search-excerpt` — restore `excerpt` + 250-char truncation** — COMPLETE (2026-04-28)
> **File ownership:** P1-C owns search path in `providers/copilot_cli.py` and `providers/file_backends.py`
- [x] (2026-04-28) Revert `content` field to `excerpt` in search results
- [x] (2026-04-28) Restore 250-char truncation on excerpt field
- [x] (2026-04-28) **Verify:** `python3 -m pytest src/session_recall/tests/e2e/test_e2e_search.py -v`

**`[P1-D]` `f1-label-determinism` + F21 macOS paths (bundled)** — COMPLETE (2026-04-28)
> **File ownership:** P1-D owns `providers/copilot_cli.py:_local_workspace_label` + `providers/file_backends.py` (VS Code roots)
- [x] (2026-04-28) Drop `is_dir()` branch in `_local_workspace_label`; use deterministic `Path.expanduser()` only
- [x] (2026-04-28) Add macOS VS Code workspace path `~/Library/Application Support/Code/User/workspaceStorage` to root candidates
- [x] (2026-04-28) Fix failing test `test_cli_fallback_labels_non_repo_session_as_local_workspace`
- [x] (2026-04-28) **Verify:** `python3 -m pytest src/session_recall/tests/test_provider_backends.py -v`

**`[P1-E]` `cc4-jsonl-5day-default` — asymmetric lookback** — COMPLETE (2026-04-28)
> **File ownership:** P1-E owns `config.py` (additive only), `providers/base.py`, `commands/_lookback.py` (new)
- [x] (2026-04-28) Add `JSONL_DEFAULT_LOOKBACK_DAYS = 5` and `SQLITE_DEFAULT_LOOKBACK_DAYS = 30` to `config.py`
- [x] (2026-04-28) Add `uses_jsonl_scan()` method to `StorageProvider` ABC in `base.py`
- [x] (2026-04-28) Create `commands/_lookback.py` with `resolve_days()` helper
- [x] (2026-04-28) Apply `resolve_days()` in all command argparse layers
- [x] (2026-04-28) **Verify:** `python3 -m pytest src/ -q`

**`[P1-F]` `f10-repos-schema-check` — add schema_problems() to repos.py** — COMPLETE (2026-04-28)
> **File ownership:** P1-F owns `commands/repos.py`
- [x] (2026-04-28) Add `schema_problems()` call before querying in `repos.py`
- [x] (2026-04-28) **Verify:** `grep -n 'schema_problems' src/session_recall/commands/repos.py`

**`[P1-G]` `f13-provider-field-bloat` — omit/shorten provider field** — COMPLETE (2026-04-28)
> **File ownership:** P1-G owns provider output dicts in `providers/copilot_cli.py` and `providers/file_backends.py`
- [x] (2026-04-28) Omit `provider` field when only 1 provider active
- [x] (2026-04-28) Shorten to `cli`/`vsc`/`jb`/`nv` when multiple providers active
- [x] (2026-04-28) **Verify:** `python3 -m pytest src/session_recall/tests/e2e/test_e2e_list.py -v`

---

#### Step 2 — Wave 1 Gate `[GATE]` — 1 agent

> **Launch condition:** All P1-A through P1-G complete.

- [x] (2026-04-28) Run full test suite: `python3 -m pytest src/ -q` — 150 passed, 0 failed
- [x] (2026-04-28) Run lint: `ruff check src/` — 3 pre-existing warnings only
- [x] (2026-04-28) Fixed test assertions: `vscode→vsc` in test_provider_backends, `count==4→3` in test_days_filter
- [x] (2026-04-28) **Verify:** `python3 -m pytest src/ -q && ruff check src/`

---

#### Success Criteria (Phase 1)

1. `ENABLE_FILE_BACKENDS` defaults to `False` — file backends never load unless opted in
2. `list --limit` defaults to 10 (not 50)
3. `search` output uses `excerpt` field, ≤250 chars
4. `_local_workspace_label` is deterministic (no `is_dir()` call)
5. macOS VS Code path in root candidates
6. JSONL lookback defaults to 5 days; SQLite stays at 30
7. `repos` calls `schema_problems()` before querying
8. `provider` field omitted when single provider active
9. All existing tests pass (zero regressions)
10. Failing test `test_cli_fallback_labels_non_repo_session_as_local_workspace` now passes

---

### Phase 1.5 — WSL/Linux Compatibility

**Plan:** `plans/pr5-plan.md` (addendum — user request 2026-04-28)
**Goal:** Ensure all provider path discovery works on Windows 11 WSL and native Linux. Cover VS Code Server paths, XDG directories, and WSL-specific edge cases.

#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 1 | [SEQ] — WSL/Linux path compatibility across all providers |

**Total: 1 agent dispatch across 1 step.**

---

#### Step 1 — `wsl-linux-compat` — WSL/Linux path compatibility `[SEQ]` — 1 agent

> **Launch condition:** Phase 1 Gate complete.

- [ ] Add WSL VS Code Server path `~/.vscode-server/data/User/workspaceStorage` to VSCodeProvider root candidates
- [ ] Verify XDG-compliant paths for JetBrains (`~/.config/JetBrains/`) and Neovim (`~/.local/share/nvim/`)
- [ ] Add WSL detection helper (`/proc/version` contains "microsoft" or "WSL") for any WSL-specific path logic
- [ ] Verify Copilot CLI paths work unchanged on WSL (`~/.copilot/` is the same)
- [ ] Add tests for WSL path candidates in file_backends test suite
- [ ] Ensure `Path.home()` resolves correctly in WSL (it does — `/home/<user>`)
- [ ] **Verify:** `python3 -m pytest src/ -q`

---

#### Success Criteria (Phase 1.5)

1. VS Code Server WSL path in root candidates
2. JetBrains/Neovim XDG paths verified correct for Linux/WSL
3. Tests cover WSL path scenarios
4. All tests pass (zero regressions)

---

### Phase 2 — Wave 2: Structure + Hardening

**Plan:** `plans/pr5-plan.md`
**Goal:** Split file backends into isolated subpackage and add bounded JSONL reads.

#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 2 | P2-A (cc2-folder-split), P2-B (f3-bounded-jsonl) |
| Step 2 | 1 | [GATE] — verify structure + tests |

**Total: 3 agent dispatches across 2 steps.**

---

#### Step 1 — Wave 2 Parallel Fixes `[P2-A, P2-B]` — 2 agents in parallel

> **Launch condition:** Phase 1 complete (cc2 depends on cc1).

**`[P2-A]` `cc2-folder-split` — move file backends to `providers/file/`** — NOT STARTED
> **File ownership:** P2-A owns all files under `providers/file/` (new) and `providers/file_backends.py` (deleted)
- [ ] Create `providers/file/` subpackage with `__init__.py` (PEP 562 lazy `__getattr__`)
- [ ] Split `file_backends.py` → `vscode.py`, `jetbrains.py`, `neovim.py`
- [ ] Create `_base_file_provider.py` with shared mixin
- [ ] Split `copilot_cli.py` → `copilot_cli/provider.py`, `_labels.py`, `_state_parse.py`, `_sql.py`
- [ ] Update all imports in commands/* and discovery.py
- [ ] All files ≤200 LOC
- [ ] **Verify:** `python3 -m pytest src/ -q && ruff check src/`

**`[P2-B]` `f3-bounded-jsonl` — bounded JSONL reads in `providers/common.py`** — NOT STARTED
> **File ownership:** P2-B owns `providers/common.py`
- [ ] Create `iter_jsonl_bounded()` with `_MAX_LINE_CHARS` / `_MAX_PARSE_LINES`
- [ ] Use `f.readline(max+1)` pattern (fixes F9 too — no 2 GB allocation)
- [ ] Apply to both CLI provider and file providers
- [ ] **Verify:** `python3 -m pytest src/ -q`

---

#### Step 2 — Wave 2 Gate `[GATE]` — 1 agent

> **Launch condition:** P2-A and P2-B complete.

- [ ] Run full test suite + lint
- [ ] Verify `providers/file/` folder exists with expected structure
- [ ] **Verify:** `python3 -m pytest src/ -q && ruff check src/ && ls src/session_recall/providers/file/`

---

#### Success Criteria (Phase 2)

1. `providers/file_backends.py` deleted — replaced by `providers/file/*.py`
2. `copilot_cli.py` split into `copilot_cli/` subpackage, all files ≤200 LOC
3. `iter_jsonl_bounded()` used by all JSONL readers
4. No `for line in f:` unbounded reads remain
5. All tests pass (zero regressions)

---

### Phase 3 — Wave 3: Security

**Plan:** `plans/pr5-plan.md`
**Goal:** Add symlink guards, trust fencing, and mtime prefilter to file backends.

#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 3 | P3-A (f2-path-safety), P3-B (f4-trust-fence), P3-C (f6-mtime-prefilter) |
| Step 2 | 1 | [GATE] — verify security + tests |

**Total: 4 agent dispatches across 2 steps.**

---

#### Step 1 — Wave 3 Parallel Fixes `[P3-A, P3-B, P3-C]` — 3 agents in parallel

> **Launch condition:** Phase 2 complete (all depend on cc2 folder structure).

**`[P3-A]` `f2-path-safety` — `is_under_root` symlink guard** — NOT STARTED
> **File ownership:** P3-A owns `providers/file/_path_safety.py` (new)
- [ ] Create `is_under_root(path, root)` using `resolved.is_relative_to(root.resolve())`
- [ ] Apply at all glob sites in file providers + CLI provider's `_state_files`
- [ ] Skip + warn on symlink escape attempts
- [ ] **Verify:** `python3 -m pytest src/ -q`

**`[P3-B]` `f4-trust-fence` — trust level field + sentinel fence** — NOT STARTED
> **File ownership:** P3-B owns `providers/file/_trust.py` (new)
- [ ] Add `_trust_level: "untrusted_third_party"` to all file-backend records
- [ ] Add `_trust_level: "trusted_first_party"` to CLI provider records
- [ ] Create `wrap_untrusted()` with sentinel fence markers
- [ ] Apply at content boundary in all file providers (~5 call sites)
- [ ] No regex strip (fence-only per maintainer decision)
- [ ] **Verify:** `python3 -m pytest src/ -q`

**`[P3-C]` `f6-mtime-prefilter` — mtime cutoff + early termination** — NOT STARTED
> **File ownership:** P3-C owns `providers/file/_base_file_provider.py`
- [ ] Add `stat().st_mtime > now - days*86400` prefilter in `_iter_files`
- [ ] Add early termination once `limit` matches produced
- [ ] Add `lru_cache` on workspace glob results within a CLI invocation
- [ ] Bound `repos` fan-out (max 200 sessions per provider)
- [ ] **Verify:** `python3 -m pytest src/ -q`

---

#### Step 2 — Wave 3 Gate `[GATE]` — 1 agent

> **Launch condition:** P3-A, P3-B, P3-C complete.

- [ ] Run full test suite + lint
- [ ] Verify `_trust_level` field appears in file-backend output
- [ ] **Verify:** `python3 -m pytest src/ -q && ruff check src/`

---

#### Success Criteria (Phase 3)

1. Symlink escape blocked — `is_under_root` applied at all glob sites
2. `_trust_level` field on every record (trusted vs untrusted)
3. Sentinel fence wraps untrusted content
4. mtime prefilter skips stale files before opening
5. Early termination stops after `limit` matches
6. All tests pass (zero regressions)

---

### Phase 4 — Wave 4: Regression Tests

**Plan:** `plans/pr5-plan.md`
**Goal:** Add automated token budget and adversarial tests as CI guardrails.

#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 2 | P4-A (regression-budgets), P4-B (adversarial-tests) |
| Step 2 | 1 | [GATE] — verify all new tests pass |

**Total: 3 agent dispatches across 2 steps.**

---

#### Step 1 — Wave 4 Parallel Tests `[P4-A, P4-B]` — 2 agents in parallel

> **Launch condition:** Phase 3 complete (depends on f5/f6/f7 for budgets, f2/f3/f4 for adversarial).

**`[P4-A]` `regression-budgets` — token + latency budget tests** — NOT STARTED
> **File ownership:** P4-A owns `tests/test_budgets.py` (new)
- [ ] Create fixture DB for budget testing
- [ ] Add token budget assertions: `list --limit 10` < threshold, `search` < threshold, `files` < threshold
- [ ] Token tests: hard fail (deterministic)
- [ ] Latency tests: soft warning (3-run median), warn-only
- [ ] **Verify:** `python3 -m pytest src/session_recall/tests/test_budgets.py -v`

**`[P4-B]` `adversarial-tests` — security regression tests** — NOT STARTED
> **File ownership:** P4-B owns `tests/test_adversarial.py` (new)
- [ ] Test symlink escape: create symlink, verify `is_under_root` blocks it
- [ ] Test JSONL bomb: 10 MB single-line, verify bounded reader caps it
- [ ] Test prompt injection: plant injection content, verify `_trust_level == "untrusted_third_party"` + fence wraps it
- [ ] Test deeply-nested JSON: 100-deep dict under byte limit, verify no stack overflow
- [ ] **Verify:** `python3 -m pytest src/session_recall/tests/test_adversarial.py -v`

---

#### Step 2 — Wave 4 Gate `[GATE]` — 1 agent

> **Launch condition:** P4-A and P4-B complete.

- [ ] Run full test suite
- [ ] **Verify:** `python3 -m pytest src/ -q`

---

#### Success Criteria (Phase 4)

1. Token budget tests exist and pass for list, search, files
2. Adversarial tests exist and pass for symlink, JSONL bomb, injection, nested JSON
3. All tests pass (zero regressions)

---

### Phase 5 — Wave 5: Convention Update

**Plan:** `plans/pr5-plan.md`
**Goal:** Relax CLAUDE.md LOC cap to 200/300 to match post-remediation file sizes.

#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 1 | [SEQ] — update CLAUDE.md |

**Total: 1 agent dispatch across 1 step.**

---

#### Step 1 — `claude-md-update` — Update CLAUDE.md `[SEQ]` — 1 agent

> **Launch condition:** Phase 4 complete.

- [ ] Change "every `.py` file should be under 80 lines" to 200-line soft cap, 300-line hard cap
- [ ] Update related one-function-per-file guidance
- [ ] **Verify:** `grep -n '200\|300' CLAUDE.md`

---

#### Success Criteria (Phase 5)

1. CLAUDE.md reflects 200/300 LOC cap
2. No files in repo exceed 300 LOC after all remediation

---

### Phase 6 — Wave 6: Comprehensive Documentation

**Plan:** `plans/pr5-plan.md`
**Goal:** Generate `docs/pr5-docs.md` with full change reference, ASCII diagrams, env var table, migration guide.

#### Max Parallel Agents

| Step | Agents | Description |
|------|--------|-------------|
| Step 1 | 1 | [SEQ] — generate comprehensive docs |
| Step 2 | 1 | [SEQ] — update README with opt-in section |

**Total: 2 agent dispatches across 2 steps.**

---

#### Step 1 — `pr5-comprehensive-docs` — Generate `docs/pr5-docs.md` `[SEQ]` — 1 agent

> **Launch condition:** Phase 5 complete (all implementation done).

- [ ] Write executive summary
- [ ] Create architecture ASCII diagram (CLI → provider discovery → SQLite/JSONL/file backends → output)
- [ ] Create provider discovery flow ASCII diagram
- [ ] Create trust model ASCII diagram (trusted vs untrusted boundaries)
- [ ] Write env var & flags reference table (9 variables)
- [ ] Write command changes matrix (before/after with token impact)
- [ ] Write security hardening summary (F2/F3/F4/F18)
- [ ] Write token budget table (tier 1/2/3)
- [ ] Write file structure after remediation (ASCII tree)
- [ ] Write migration guide (pre-PR5 → post-PR5)
- [ ] Write findings resolution table (F1-F21 with status)
- [ ] **Verify:** `test -f docs/pr5-docs.md && wc -l docs/pr5-docs.md`

#### Step 2 — Update README `[SEQ]` — 1 agent

> **Launch condition:** Step 1 complete.

- [ ] Add "Multi-storage recall" section to README explaining opt-in flag
- [ ] Document `SESSION_RECALL_ENABLE_FILE_BACKENDS=1` and trust trade-off clearly
- [ ] Fix F20 docs typo (double space)
- [ ] **Verify:** `grep 'ENABLE_FILE_BACKENDS' README.md`

---

#### Success Criteria (Phase 6)

1. `docs/pr5-docs.md` exists with all 11 sections
2. README includes multi-storage opt-in documentation
3. F20 typo fixed
4. All tests still pass

---

### Phase 7 — E2E Testing (COMPLETE)

**Plan:** `plans/pr5-plan.md`
**Goal:** Add end-to-end test suite exercising all CLI commands against a fixture DB.

#### Status: Complete (2026-04-28)

- [x] (2026-04-28) Created `conftest.py` with fixture DB builder + `run_cli` helper
- [x] (2026-04-28) Created `test_e2e_list.py` — 8 tests
- [x] (2026-04-28) Created `test_e2e_search.py` — 8 tests
- [x] (2026-04-28) Created `test_e2e_show.py` — 7 tests
- [x] (2026-04-28) Created `test_e2e_files_checkpoints.py` — 9 tests
- [x] (2026-04-28) Created `test_e2e_health_schema.py` — 6 tests
- [x] (2026-04-28) Created `test_e2e_edge_cases.py` — 7 tests
- [x] (2026-04-28) **Verify:** `python3 -m pytest src/session_recall/tests/e2e/ -v` — 45 passed in 3.56s

#### Success Criteria (Phase 7)

1. ✅ 45 E2E tests covering all 7 commands + edge cases
2. ✅ All tests pass
3. ✅ Existing 105 tests unaffected (149/150 pass — 1 pre-existing F1 failure)
