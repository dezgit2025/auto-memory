# How to Use Verification Scripts

> Companion to [`verification-script-spec.md`](./verification-script-spec.md).
> The spec defines **what** a verify script must contain. This doc answers **when** to create one and **how** to wire it into your agent workflow.

---

## Short answer: **BEFORE** the code, then iterate alongside it

Write the **spec template** (§4 of `verification-script-spec.md`) before any code, write the **verify script** before or in lockstep with code, and **re-run after every phase**.

---

## The rule of thumb

| Phase | What to create | Why |
|---|---|---|
| Plan finalized | **Verification spec** (YAML in §4) — acceptance criteria, happy/boundary/failure cases, invariants, anti-cheat checks | Forces you to define "done" in observable terms before the agent can game it |
| Before first commit | **Skeleton `verify.sh`** — pytest call + 1 happy-path assertion + `--self-test` stub | Establishes the contract; locks the gate |
| During implementation | Add one assertion per acceptance criterion as code lands | TDD-lite; catches drift in the same turn |
| End of each phase | Run `verify.sh` → require exit 0 | This is the L1 gate; if it fails, agent doesn't proceed |
| Task end | Run `verify.sh --self-test` then real run | L2 gate; catches a verifier the agent quietly weakened |

---

## Why "before" beats "after"

1. **Goodhart's Law.** Anything the agent reads, the agent optimizes for. If the verifier is written *after* the code, the verifier's author (often the same agent) tailors it to what the code already does — guaranteeing PASS without proving correctness. Aider and SWE-bench solve this by holding out tests until evaluation time. *(spec §1.2)*
2. **Lazy code prevention.** Aider measured "lazy comments on 12 of 89 tasks" at GPT-4 baseline. A pre-existing verify script with a behavioral assertion makes `pass` / `# TODO` instantly fail. *(spec §1.1)*
3. **Spec-as-contract.** The §4 YAML spec is what you point the implementer agent at. It's the source of truth for *both* the implementer ("build this") and the verifier ("prove this"), so they can't drift.

---

## How to do it — concrete workflow

```
1. plans/plan.md                 ← human or planner agent writes
2. doc/verify-spec/<task>.yaml   ← fill in §4 template (acceptance criteria, anti-cheat)
3. verify.sh                     ← write skeleton from §5 template, fill assertions from spec
4. Implementer agent prompt:     "Read plan.md AND verify-spec/<task>.yaml.
                                  Make verify.sh exit 0."
5. After each phase:             bash verify.sh   # exit != 0 → do not advance
6. End of task:                  bash verify.sh --self-test && bash verify.sh
```

### Standard implementer prompt (point the agent at plan + code + verifier)

```
Context files:
- plans/plan.md                    ← what to build
- doc/verify-spec/<task>.yaml      ← how "done" is defined
- doc/verification-script-spec.md  ← the meta-rules for verify scripts
- src/                             ← code root
- verify.sh                        ← the gate you must make pass

Constraint: do not modify verify.sh or tests/ directory.
Goal:       make verify.sh exit 0.
```

The **"do not modify the verifier"** line is the single most important guardrail — it converts the verifier from a suggestion into a contract.

---

## Quick checklist

Before declaring a task done:

- [ ] `doc/verify-spec/<task>.yaml` exists and was written **before** code
- [ ] `verify.sh` exists with `set -euo pipefail` and `--self-test` flag
- [ ] Implementer agent was given plan + spec + verifier as read-only context
- [ ] `bash verify.sh` was run at the end of each phase (exit code captured in transcript)
- [ ] `bash verify.sh --self-test` passes (verifier rejects known-bad reference)
- [ ] `bash verify.sh` passes against current code
- [ ] Diff shows verifier and `tests/` are unchanged from their pre-implementation state

---

## See also

- [`verification-script-spec.md`](./verification-script-spec.md) — the full spec (15 sections)
- [`verification-spec-research/`](./verification-spec-research/) — provenance for spec claims
