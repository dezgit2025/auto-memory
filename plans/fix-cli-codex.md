# Repair plan: session-recall-codex schema drift

Status: **V5 IMPLEMENTED — offline acceptance passed; live smoke failed safely and further live verification awaits an explicit budget grant.**

**Repository publication:** version **0.6.0** was committed and pushed to `main`
on **2026-09-20** in commit `88710b9`. Direct GitHub installation and hosted
Linux/macOS CI passed. The final journal records the evidence. No PyPI upload,
global local-machine installation or new live model attempt was performed.

**GitHub release:** [v0.6.0](https://github.com/dezgit2025/auto-memory/releases/tag/v0.6.0)
was published as **Latest** on 2026-09-20 at tag target `3cbd61d`. This is a
GitHub-only release; the exact tag is excluded from automatic PyPI publication.

Current checklist: the V5 section below. Earlier detail is retained for recovery,
not as additional requirements to execute the simplified design.
Journal: [progress-fix-cli-codex.md](progress-fix-cli-codex.md).

Initial implementation outcome (2026-09-20 UTC, before repository publication):
steps 1–3 are implemented and independently
reviewed using GPT-5.6-sol agents. Regression, adversarial sandbox, mutation,
clean-install and cumulative offline gates pass. The single synthetic live
attempt returned `process_failed` without usage telemetry; its ledger records a
conservative estimated 32K charge, not measured consumption. No generated code
was executed or activated. Subsequent local diagnosis led to an explicitly typed
output-schema constant and sanitized failure categories; these do not establish
the original failure cause or live success. A further live attempt requires
one explicit +32K grant. The journal records the final corrected-source gates.
At that point, global installation, startup edits, real activation, commits and
publication had not been performed. Live validation still needs a separately
budget-approved synthetic retry.

## Repository release follow-up — authorized 2026-09-20

The user approved diagram version 2, prominent dated README placement, a CLI
version upgrade, public installation guidance, and committing/pushing the full
Codex repair implementation to this repository. This authorizes the repository
commit and push; earlier no-commit/no-push statements describe prior work.

Selected release: **0.6.0**, reflecting the new repair companion and workflow.

1. **R1 — Prepare:** put the dated Codex explanation and approved diagram near
   the top of README; retain the standalone versioned Markdown; reconcile
   install guidance, package/CLI versions, bundled adapters and trust catalogue.
2. **R2 — Verify:** independently review documentation and packaging; run
   appropriate source regressions, reproducible artifact checks, and cumulative
   clean-install verification against the released version. Review and refresh
   only affected protected hashes. Audit the staged file list for runtime data.
3. **R3 — Publish to Git:** commit the reviewed source, assets, tests, guides and
   planning records, then push normally to the existing main repository. Verify
   the remote commit matches and report the commit/version and known limits.

Acceptance: a clean installation from the pushed repository contains both Codex
commands, reports version 0.6.0, includes all runtime assets, and passes the
synthetic repair/approval/activation/rollback flow. README clearly distinguishes
GitHub installation from PyPI publication, explicit repair from background
automation, and offline verification from the still-unverified live model path.

Excluded: PyPI upload, global local-machine reinstall, another paid/live model
attempt, startup automation, real candidate activation and force-push. The
pending live retry remains a separate budget decision recorded in the journal.

### GitHub Releases entry — additionally authorized 2026-09-20

The user subsequently requested updating GitHub's Releases panel. Create tag
and published **v0.6.0** release marked Latest; do not increment again to0.6.1,
because the implementation and package already identify this feature release
as0.6.0. This supersedes the earlier no-tag scope for this release only.

Before creating the tag, exclude exactly `v0.6.0` from the existing automatic
PyPI tag workflow. Preserve the workflow for other version tags. Validate the
filter and release notes, commit/push that narrow guard, create the GitHub release
at the verified commit, then verify its tag target and Latest status. No PyPI
upload or new live AI request is authorized by this GitHub-release action.

## V5: the simple path to implement

**The fallback is Codex, not another provider.** Keep the existing deterministic
repair. If no reviewed recipe matches an unknown schema, invoke the installed
Codex CLI with the existing login to repair `session-recall-codex`.

1. Check the schema. Supported stores need no repair; known recipes use the
   existing deterministic path. Storage/access failures do not trigger AI.
2. Start one isolated `codex exec` job with `--model gpt-6-astra` and
   `model_reasoning_effort="medium"`. These are repair-worker defaults, not a
   request to change global Codex settings.
3. Provide the schema difference, relevant adapter source and fixed output
   schema. Request one candidate patch. No session contents, credentials,
   nested repair workers, Codex-binary edits or Codex-database repairs.
4. Validate patch format, paths and base digest. Test in a disposable isolated
   copy with synthetic stores, regressions, smoke tests and end-to-end checks.
   Candidates cannot modify protected tests, policy or the controller.
5. By default, show the passing patch and rollback information for approval,
   then use the existing managed activation/rollback path. Failure leaves the
   current adapter unchanged.

[GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) uses
`gpt-6-astra` and supports medium reasoning.
[Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
supports saved login and structured final output. Use a direct subprocess with
fixed arguments. Do not build a provider router, alternate API transport, model
ranking system, or app-server attestation layer. Record requested settings and
any reported mismatch; do not claim independent provider attestation. Missing
per-turn model metadata is not failure. An explicit model mismatch, unavailable
model or failed login stops that attempt; never silently select something else.

Retain approximately32K tokens initially, checkpoint around28K or a forecast
overrun, and ask for each additional32K. Use usage reports or labeled estimates;
no exact cap is required. Reuse the completed budget and rollback mechanisms.
Do not expand them just to finish the Codex integration.

Suggested defaults: explicit foreground repair command and review before real
activation. The user has been asked whether to prefer automatic triggering
and/or activation after passing tests. These questions are optional; until
answered, implement those safe defaults. Provider, model, budget and attestation
choices are resolved and must not be reopened as implementation blockers.

### V5 implementation checklist (execution evidence in journal)

1. Migrate the Sol-specific policy/tests to GPT-6 medium with a reviewed policy
   version/digest change. Preserve old receipts/history and invalidate stale
   grants. Remove any requirement to invent an `effective_model` value; record
   requested and reported settings separately.
2. Add one thin `codex exec` runner and connect `assist`. Use recording fakes
   first. Handle login failure, unavailable model, timeout and malformed output
   without provider/model switching or silent retries.
3. Connect fixed candidate validation, isolated tests, review, activation and
   rollback. Use a terminal confirmation, or persisted JSON action-needed
   response when no terminal exists; not a new approval service.
4. Run regressions, smoke, mutation checks and clean-install E2E: unknown schema
   → Codex candidate → tests → approved synthetic activation → rollback. Only
   after offline gates, run one small live check using synthetic input and the
   selected budget; no real adapter activation. Refresh hashes after review.

No additional design choice is needed to begin. Expired login, actual permission
denial or failed isolation tests can still be genuine runtime blockers; they
do not justify another provider. Budget extensions and real activation remain
intentional runtime approvals, not prerequisites to implementing/testing the
workflow. No global install, startup edit, commit or publication is included.

Older C architecture and Sol/attestation requirements below are historical where
they conflict with V5. The original540-test acceptance covers the old implementation. V5 implementation
and its newer verification evidence are recorded separately in the current journal.

## Historical work and earlier detailed design

Execution update (2026-09-20 UTC): the user requested autonomous execution with
multiple `gpt-5.6-sol` sub-agents and one-minute updates. The earlier planning-only
restriction below is historical. The named progress journal remains the recovery
record. Direct maintenance capture remains restricted under AGENTS.md;
commits, publication, paid model runs, and unresolved dependent B/C policy choices
are not implicitly approved by this status update.

Version: 5, revised 2026-09-20 UTC: one Codex CLI repair path, GPT-6 medium,
no alternate provider/model and no independent model-attestation prerequisite.
This supersedes the Sol-only and multi-transport design. Original v3 restrictions were
superseded for the completed A/B execution. The user subsequently authorized
Stage C execution. Live generation and candidate execution still require their
budget/model/sandbox gates. No global installation, commit, publication or direct
Codex database access is authorized by this revision.

Roadmap: [CX-001](../ROADMAP.md#codex-compatibility).
Journal: [progress-fix-cli-codex.md](progress-fix-cli-codex.md).

Stage A acceptance (2026-09-20 UTC): 404 tests pass without warnings; source lint
passes. Supported live schema-check/list/repos all exit0. Independent verifier
self-test and two A/L2 runs pass with identical stable verdicts, including trial
smoke, schema gates, no-query/read-only assertions, and isolated wheel0.5.1
installation. [Stage B architecture](fix-cli-codex-architecture.md) is reviewed;
automatic activation and live AI transport remain configurable, not enabled.

Stage B acceptance (2026-09-20 UTC): the companion checker/planner, digest-pinned
adapter launcher, reviewed local recipe, atomic activation and recovery are
implemented. Full source tests (437) and explicit integration tests (51) pass.
Independent self-test and two
cumulative A+B L2 runs pass (35.705s / 35.824s), with identical stable verdicts.
Coverage includes every durable activation/rollback boundary, a final precommit
schema witness, fresh-process no-op reapply, and clean-wheel end-to-end
plan/apply/launch/rollback/refusal. Defaults remain explicit
application, no startup mutation, no downloads and no model calls. The packaged
entry points have been changed, but the global installation has not been replaced.

Stage C capability update: nested `sandbox-exec` inside the restricted session
fails (positive `/usr/bin/true` probe exits 71), but the approved no-op probe
outside that restriction succeeds. This establishes basic OS capability, not
the required candidate network/file/credential denial guarantees. The user has
selected existing Codex login, now `gpt-6-astra` at medium reasoning and the
[32K approval-block policy](#human-approved-32k-budget-blocks), subsequently
clarifying that rough token estimates are acceptable. Independent per-turn model
identity is no longer a prerequisite. Runtime integration and isolation still need testing.
No AI repair is enabled; the remaining candidate/transport contracts in the
architecture document are specifications, not an operational fallback.

Budget-unit acceptance (2026-09-20 UTC): the estimate-aware C1 contracts and C2
durable ledger are implemented and independently reviewed. Consolidated tests:
540 passed with warnings as errors. The budget verifier's deliberate-bug
self-test and two store runs pass with identical stable verdicts (1.051s/1.034s);
the cumulative A/B gate also passes, including CLI smoke and clean-wheel E2E.
The ledger preserves rough estimates/actual overshoot, single-use +32K grants,
crash recovery, stale-question retirement and the 35K → 64K → 96K headroom flow.
This is an internal budget API, not a working `assist` command. Production
approval UI, the simple Codex invocation, Candidate I/O validation and
OS-isolated candidate execution still need implementation/verification.

The original proposal below is retained as design history. Statements such as
“proposed”, “not started” or “runner not implemented” in that original narrative
are superseded for A/B and the budget-only C units by this acceptance block and
the current journal. The complete AI workflow remains unfinished.
`--through C` explicitly returns an infrastructure error
(exit 2), never a pass inferred from A/B.

Version 2 adds the requested design for a deterministic fixer first, followed by
an LLM-assisted repair when no reviewed recipe matches. Startup options, a strict
model/effort gate, and suggested safeguards are recorded below. These are plan
changes only; no fixer, startup integration, or model call has been executed.

Version 3 reviews coherence and readability, makes candidate approval and
recovery explicit, and appends the requested Munger inversion review.

## Start here: what we are building

Codex owns the databases. Our `session-recall-codex` program reads them. When
Codex changes their structure, our reader refuses to run until we have checked
that it still understands the data. The fixer updates **our reader** and its
compatibility rules; it never changes Codex's database to make an error disappear.

There are three deliverables, built in this order:

| Stage | Deliverable | Done when |
| --- | --- | --- |
| A — restore today's CLI (CX-001) | A reviewed fix for the observed migration-55 store | The five immediate repair steps pass, including installed CLI checks. |
| B — deterministic fixer (CX-003) | Recognize exact known problems and apply reviewed repairs | The same inputs select the same repair; application, interruption, and rollback tests pass. |
| C — LLM fallback (CX-004) | Ask an approved model for a candidate when B has no known repair | The model gate, isolated testing, and candidate review work; no lower-model request is possible through the controller. |

Within one repair attempt, the routing is:

```text
Check current schema
  -> supported: use recall
  -> known repair: stage -> test -> activate under selected policy -> recheck
  -> unknown schema: check LLM policy/model -> generate candidate -> test
                     -> maintainer review -> approved repair -> activate -> recheck
  -> storage/access problem: report it; continue Codex without recall
```

The unknown-schema route is not a fallback for every error. An unreadable
database or failed installation needs diagnosis, not generated code. The LLM
step may vary between runs. The rule-based selection is deterministic;
verification uses fixed rules but can still encounter environmental failures.

### Vocabulary

| Term | Meaning in this plan |
| --- | --- |
| Schema / metadata | Table and column definitions and migration status; not conversation text. |
| Migration | A numbered database change made by Codex. A higher number alone does not establish compatibility. |
| Profile | The exact schema our adapter has been reviewed and tested against. |
| Preflight | The check performed before attempting a session query. |
| Recipe | A reviewed record for one known repair, with exact starting conditions and expected result. |
| Manifest | The machine-readable plan for one repair: inputs, affected files, checks, and rollback. |
| Artifact / digest | A built adapter or patch, and its cryptographic checksum identifying exact bytes. A checksum alone does not establish trust. |
| Staging | A separate installation or checkout for testing before a change becomes active. |
| Activation / rollback | Select the tested adapter / restore the previous adapter. Neither modifies Codex data. |
| Gate | A condition that must pass before proceeding. Failure stops that path with an explanation. |
| Transport | Code that invokes the model through an API or a controlled Codex subprocess. |

### How to use this document

Read the findings, then implement Stage A only when execution is requested. Its
steps are numbered 1–5 under “Ordered implementation steps.” Stages B/C have
their own sequence under “Implementation sequence and observable extension
gates.” Do not mix the sequences. Commands for `session-recall-codex-fix` are
proposed interfaces, not commands to run today.

The user selected deterministic-first routing, LLM fallback, and a minimum
model/effort requirement. Model spelling, activation policy, startup coverage,
update source, transport, and budget remain open. Independent design or synthetic
test work need not wait for every choice; stop where an unresolved choice
determines implementation. This draft is ready for discussion, not unattended
implementation of Stages B/C.

## Confirmed root cause

Codex's state schema advanced to migration **55**, while the running recall
adapter requires **52**. Its exact table-definition comparison also rejects two
new `threads` columns: **`originator`** and **`daybreak_enabled`**. Thread history
still matches migration **6** under the adapter's checks.

The adapter is intentionally refusing an unreviewed schema. This is the direct
cause of the observed CLI failure; the output does not indicate missing storage,
locking, failed migrations, or unavailable JSON1 support.

Diagnostic evidence, obtained through the supported adapter:

| Command | Result |
| --- | --- |
| `session-recall-codex schema-check` | Exit 2; expected state 52/history 6, found state 55/history 6; the three differences above. |
| `session-recall-codex list --json --limit 5` | Exit 2, `error: schema_drift`, `query_executed: false`; same differences. |
| `session-recall-codex schema-check --json` | Same structured failure and expected profile names. |

No session rows were obtained. No direct Codex database inspection, schema
capture, profile update, or live data-query bypass was performed.

### Failure path and affected code

1. [schema.py](../src/session_recall/providers/codex/schema.py) loads
   [captured-profiles.json](../src/session_recall/providers/codex/verifications/captured-profiles.json)
   at import time. `_diff_columns()` compares the complete ordered definitions;
   `_check_migrations()` requires an exact successful migration ceiling.
2. [provider.py](../src/session_recall/providers/codex/provider.py) calls
   `preflight()` before querying either `list_sessions()` or `list_repos()`.
3. A mismatch raises `CodexSchemaDrift`; [cli.py](../src/session_recall/providers/codex/cli.py)
   returns exit 2 with the diagnostic object.

Changing the ceiling alone cannot fix the unexpected-column failures. Allowing
arbitrary extra columns or newer migrations would remove the intended guard.
The repair should update the reviewed profile and associated fixtures while
preserving exact validation.

The executable imports this checkout's `cli.py` and profile, so this failure is
not explained by a disconnected installed copy. Installed distribution metadata
reports 0.4.0 while package source and `pyproject.toml` report 0.5.1. That is a
secondary installation-consistency issue, not the schema-drift cause; check it
during the eventual installation validation.

### Existing work that must be preserved

The initial worktree already contained an uncommitted migration-51-to-52 update:
`CHANGELOG.md`, `codex-instructions-template.md`, Codex tests
`_fixture_drift.py`, `test_cli.py`, `test_fixtures.py`, `test_schema.py`, and
verification files `BASELINE-HASHES.txt`, `_verify_lib.sh`,
`captured-profiles.json`, `smoke.sh`, `spec.yaml`, `verify_schema.sh`.
Review and build on those edits; do not reset or overwrite them.

### Additional validation defect found

The existing schema and CLI diagnostic tests returned **44 passed, 3 failed**.
Failures were `test_list_json_default_rows`, `test_list_include_archived`, and
`test_repos_include_local`. Fixtures use fixed `REF_NOW_MS = 1787486400000`, which
is **2026-08-23 12:00 UTC** despite a comment saying August 30. Production queries
use wall-clock time, so intended fixture rows now fall outside the 30-day window.

A diagnostic rerun replaced only `state_queries.time` in memory with a clock at
`REF_NOW_MS`; all **47 tests passed**. No file was edited for this experiment.
Unrelated pytest plugin autoload was disabled in that rerun; the original run
also emitted 1,663 third-party asyncio deprecation warnings. These warnings are
environment noise, distinct from the three failed row-count/filter assertions.

Baseline command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest \
  src/session_recall/providers/codex/tests/test_schema.py \
  src/session_recall/providers/codex/tests/test_cli.py \
  -q -p no:cacheprovider --import-mode=importlib
```

The real diagnostic used the console script's Python 3.14 interpreter. The
clock-aligned result establishes a test-time defect, not live migration-55
compatibility. The full suite and shell verifiers have not been run in this task.
Before using the clock experiment as acceptance evidence, repeat it with plugin
loading held constant: the earlier rerun changed both clock and plugin autoload
settings. Do not describe it as a single-variable experiment.

## Scope and boundaries

Restore the existing `schema-check`, `list`, and `repos` commands for one reviewed
current schema; repair the test clock so its acceptance evidence is repeatable.
Keep read-only connections, validation before data queries, exact column
definitions and migration ceilings, current output contracts, and provider
isolation. No new runtime dependencies.

For the immediate repair, exclude `search`, `show`, `files`, `health`, schema
auto-learning, arbitrary future migration acceptance, database migrations/downgrades, and unrelated provider
fixes. Multiple-profile support is deferred to roadmap CX-002. Do not alter the
historical port plan or resume its unimplemented phases.

The proposed fixer extension below is a subsequent increment (CX-003/CX-004),
explicitly added at the user's request. It does not make unfamiliar schemas
automatically trusted or expand the immediate repair steps 1–5.

The existing session-recall instructions prohibit direct database reads after
drift. Exact types, defaults, nullability, column positions, and migration
descriptions for the new columns are therefore **not established here**. Step 1
requires explicitly authorized maintenance metadata capture; a generic request
to resume should not silently waive that restriction. If it remains unavailable,
use a user-supplied trusted metadata capture and stop before adopting a profile
that cannot be reviewed. No request for that authorization is needed to finish
this planning-only task.

When authorizing Stage B, settle metadata-inspection permission and the narrow
exception allowing the fixer workflow in recall instructions. This can establish
a persistent policy rather than a new permission question for every approved
recipe. Saving the design does not change installed instructions or runtime
permissions.

## Ordered implementation steps — proposed, not executed

### 1. Establish the reviewed schema contract

Integration owner: reread this plan/journal, inspect current edits and interpreter
resolution, and repeat the supported schema check. If Codex has advanced beyond
55, revise the target with evidence before changing expectations.

With the maintenance exception explicitly authorized, reuse
[capture_schema.py](../src/session_recall/providers/codex/verifications/capture_schema.py)
to capture metadata only, initially without `--write`. Review full ordered
`PRAGMA table_info` rows and migration metadata for all used tables in both
databases. Do not export session content or invent new-column definitions.
Review relevant upstream migration definitions where available to check whether
the additions affect top-level thread filtering, archive handling, or recency.

Gate: reviewed metadata establishes the target state profile, unchanged or
separately reviewed history profile, zero failed migrations, and JSON1 support.
New-column semantics affecting the existing commands must be resolved. Until
then, a profile-only repair is a proposal, not a proven complete fix.

A1 execution evidence (2026-09-20): direct live capture was avoided. The installed
Codex 0.155.1 binary embeds `ALTER TABLE threads ADD COLUMN originator TEXT;`
and `ALTER TABLE threads ADD COLUMN daybreak_enabled BOOLEAN;`, followed by an
unused artifacts-to-attachments table/index rename. The supported schema-check
reports all original ordered definitions/history6 unchanged, with only those
two extra columns and state ceiling55. Applying the exact two statements to a
synthetic profile52 store produced the independently reviewed
[used-table projection](../verify/fixtures/codex-reviewed-55.json). This is not
a full-store capture. The final supported live schema-check must close the
structural gate with zero differences before live list/repos validation.

The new columns are nullable with no default/non-PK at positions38/39. Preserve
current source/agent_path filtering and test NULL/non-NULL values; no new originator
semantics are asserted. The ancillary label `thread attachments` is normalized
from embedded text and is not an acceptance oracle; runtime checks do not compare
migration descriptions. No Codex database was opened outside the adapter.

### 2. Specify regression coverage and stabilize test time

After step 1, delegate a bounded test plan to `test-planner`, then individual
test changes to `test-writer`. Owned paths: Codex `tests/` only; one writer at a
time. The integration owner maintains the journal.

Align the CLI tests' query clock with the fixed fixture reference using an
isolated test fixture; correct the misleading timestamp comment. Preserve the
30-day production default and the five/six-row, local-repository, archive, and
subagent assertions. Do not merely advance the fixture date or weaken counts.

Specify acceptance for the reviewed profile and rejection of an unknown added
column, removed/changed required column, wrong column definition, failed
migration, future state migration (56 if the target remains 55), history
migration 7, and lower/older profiles. Include an assertion that list/repos never
reach their data query when preflight fails, beyond checking the JSON flag.

Gate: test-clock coverage is stable; schema regression tests demonstrate the
missing compatibility before the profile repair.

### 3. Update the profile and synthetic data together

Delegate a bounded implementation to `generic-subagent`. Owned paths:
`verifications/captured-profiles.json` and Codex synthetic fixture helpers,
coordinated sequentially with step 2. Review the existing 52 edits first.

Adopt the reviewed full state profile, keeping the history profile unchanged if
step 1 confirms it. Extend `_fixture_state.py` values for the new columns:
`insert_threads()` iterates every profile column and accesses `row[c]`, so a
JSON-only update would otherwise raise `KeyError`. Choose valid synthetic values
from the reviewed definitions; verify shell fixture generation as well.

Update profile names, explicit migration assertions, future/lower drift cases,
and failure mutations in `test_cli.py`, `test_schema.py`, `test_fixtures.py`, and
`_fixture_drift.py`. Prefer existing shared profile access where appropriate,
while retaining independently specified acceptance evidence.

Gate: all Codex pytest tests pass for the reviewed schema, and negative cases
still refuse session queries. Change query/normalization code only if step 1
finds a concrete semantic incompatibility; record any scope revision first.

### 4. Review and run verification gates

Delegate verifier updates to `verification-writer`, then each script run to
`verification-runner`. Owned paths: Codex `verifications/` excluding the profile
already owned by step 3. Review `spec.yaml`, `_verify_lib.sh`, `verify_schema.sh`,
and `smoke.sh` together. Retain all rejection, read-only, isolation, and self-test
assertions. Audit any temporary-directory cleanup against the session's path
validation rules before executing shell verifiers.

Record why verifier expectations changed before refreshing affected entries in
`BASELINE-HASHES.txt`; never regenerate hashes merely to hide a failing check.
A `reviewer` checks the complete change, preservation of user edits, and the
metadata evidence. A `validator` runs the regression suite and relevant lint.

Required commands after the changes, using the intended Python environment:

```sh
python3 -m pytest src/session_recall/providers/codex/tests -q -p no:cacheprovider
bash src/session_recall/providers/codex/verifications/verify_schema.sh --self-test
bash src/session_recall/providers/codex/verifications/verify_schema.sh
bash src/session_recall/providers/codex/verifications/smoke.sh --self-test
bash src/session_recall/providers/codex/verifications/smoke.sh --trial
python3 -m pytest src/ -q -p no:cacheprovider
ruff check src/session_recall/providers/codex
```

Gate: required checks pass with no weakened assertions or new skips. Report
pre-existing suite/environment failures separately; do not claim a clean gate
while any required failure remains unresolved.

Execution review (2026-09-20): the existing default smoke suite covers the
unshipped full-port commands. Add an explicit `--trial` mode for schema-check,
list, repos, and rejection of unsupported trial commands; preserve default full
coverage. Stage A uses the trial gate. This is a scope correction, not permission
to implement deferred commands or silently drop their future acceptance tests.

### 5. Validate the installed command and close the repair

Integration owner: verify the built wheel contains the profile, then validate an
isolated installation against synthetic fixtures. Reconcile the observed package
metadata mismatch when performing an authorized reinstall; determine the current
installation method before choosing a command. Do not automatically upgrade
unrelated packages or perform a global install during planning.

Run live `schema-check` through the repaired adapter first. Only after it passes,
run `list --json --limit 5` and `repos --json --limit 5`. Verify valid results and
unchanged filters/output shapes; an empty result is valid if the selected window
contains no sessions. Retain sanitized outcomes only, not private session rows.
Use synthetic-store hashes and read-only connection tests for no-write proof;
live Codex may independently change its WAL during validation.

Update relevant changelog/install guidance, journal acceptance evidence, and
roadmap CX-001 status. Preserve historical release facts. Commit/push/release
only when separately authorized. The smallest next increment is this verified
compatibility repair; broader profile support remains deferred.

## Observable acceptance criteria

- Installed `schema-check` exits 0 for the reviewed current state/history pair.
- Installed `list` and `repos` exit 0 with valid existing output contracts.
- Unsupported schemas still exit 2 before session queries; missing/versioned
  storage retains exit 4.
- Reviewed synthetic fixtures include the new columns with valid values; tests
  remain correct independently of the calendar date.
- Required pytest, verifier self-tests, behavioral gates, and lint pass; baseline
  changes have review evidence. Package profile inclusion and import provenance
  are verified.
- Codex-owned storage is never modified, existing user changes are preserved,
  and implementation remains limited to the approved repair scope.

## Proposed extension: deterministic repair, then LLM assistance

### Decisions and suggested defaults

User-selected requirements: deterministic diagnosis/repair selection first; an
LLM as the second attempt for unsupported schema changes; at least the requested
GPT-5.6 “Soul” model at medium reasoning; never silently run a lower model.

The likely intended identifier is `gpt-5.6-sol`, pending the user's spelling
confirmation. Official documentation confirms that GPT-5.6 Sol supports medium
reasoning and identifies `gpt-5.6` as an alias. Use the explicit identifier in the
proposed policy rather than the alias. This lookup establishes the documented
model, not its availability in a particular account or runner.
[OpenAI model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

Suggested defaults below are **recommendations, not recorded user selections**:
apply only reviewed recipes automatically after one-time opt-in; keep unknown
LLM repairs staged for approval; use local repair artifacts initially; and use
the existing session instructions plus CLI preflight for the first version.
The three workflow questions already asked remain open unless answered later.

### Entry points and startup behavior

The current provider already preflights every data command on the same database
connections used for the query. Keep that behavior: a first-use check alone
cannot detect an upgrade that occurs later in the session.

Add a companion command, provisionally `session-recall-codex-fix`, sharing the
provider's schema inspection and error-reporting code. Proposed interface:

| Command | Proposed behavior |
| --- | --- |
| `session-recall-codex-fix check --json` | Metadata-only diagnosis and deterministic classification; no installation, LLM call, or application changes. |
| `session-recall-codex-fix plan --json` | Produce a stable repair manifest or identify why no recipe matches. |
| `session-recall-codex-fix apply --plan <file>` | Verify exact preconditions, stage a reviewed repair, test, activate, and verify again. |
| `session-recall-codex-fix assist --plan <file>` | After deterministic classification finds no supported recipe, use the gated model to produce a candidate in isolation. |
| `session-recall-codex-fix approve --candidate <id>` | A maintainer records review of the exact candidate digest, independent test results, and schema, producing an approved repair manifest. Does not activate the adapter. |
| `session-recall-codex-fix rollback --repair <id>` | Restore the previous adapter artifact/selection; recheck compatibility and report whether recall is available. |

These commands do not exist yet. Prefer a thin companion entry point over a
second implementation of schema validation. The fixer must remain usable when
the ordinary data-command gate rejects the schema; that does not allow it to
query session rows before validation.

The companion's bootstrap and rollback logic must not import the active
replaceable adapter at startup. Keep a small stable controller outside the
adapter's versioned installation directories, with a shared metadata-inspection
module available to it. Updating the controller itself is a separate release
operation. Test that a missing profile or broken adapter import still permits
`check` to report the problem and `rollback` to run. Controller corruption may
still require reinstalling it; do not promise self-repair of every file.

Startup options:

- **Recommended first increment:** retain CLI preflight and update the installed
  session instructions to run the fixer check before recall. Once the owner has
  selected an automation policy, instructions may invoke its explicit repair
  workflow on a recognized result. JSON data commands keep their current output
  shape; diagnostics go to stderr or the dedicated check command.
- **Optional guaranteed terminal launch check:** an explicitly installed wrapper
  runs a bounded check and then launches the real Codex executable, forwarding
  arguments, signals, and exit status. This covers only launches through that
  wrapper, not desktop sessions or other launchers. Do not overwrite the real
  Codex binary or claim universal coverage.

Codex loads AGENTS.md instructions at startup. The design inference is that an
instruction to run a command is distinct from a process-launch hook; keep the
CLI guard regardless. Native hook support has not been established in this
investigation and is not a dependency of the proposed first increment.
[Official AGENTS.md guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

A startup check should let Codex continue without recall when repair is pending.
Do not synchronously wait for an LLM at every launch. An elected automation
policy may start one bounded repair job, with a durable status that subsequent
CLI calls can inspect. Repeated calls must not spawn duplicate jobs.

For the first version, prefer an explicit foreground `assist` invocation after
the warning. Automatic background LLM work is a later option requiring a chosen
budget and job lifecycle. The default startup check and ordinary CLI queries
must not incur model charges merely because the schema changed.

### Deterministic first attempt

Define the input as canonical metadata for both databases, exact adapter build,
runtime compatibility facts, repair catalogue version/digest, and explicit
policy. Preserve ordered column definitions and migration success state in the
schema fingerprint. Exclude session contents and volatile log timestamps.
Canonical serialization and deterministic rule ordering produce the same
classification and repair manifest for identical inputs.

| Diagnosis | Deterministic action | LLM eligibility |
| --- | --- | --- |
| Exact supported schema | Continue recall; no repair required | No |
| Exact reviewed repair recipe matches | Stage its pinned adapter artifact or compatibility patch and verify | No |
| Unknown schema, metadata readable | Prepare sanitized metadata diff and candidate-repair workspace | Yes, after model/policy gates |
| Missing storage, lock/busy, permissions, failed migration, corrupted metadata | Report the specific operational problem; bounded retry only where appropriate | No automatic schema-repair escalation |
| Known recipe fails verification | Preserve/restore the last adapter; report a failed recipe | No blind LLM retry against an unexplained failure |

A recipe must identify its exact supported source adapter, target schema
fingerprint, artifact digest, affected adapter paths, checks, and rollback.
More than one equally eligible recipe is an error, not an arbitrary selection.
Unknown additive columns are still unknown: structural compatibility does not
prove unchanged filtering or session semantics.

Define a versioned manifest before coding the executor. Required fields: format
version, input fingerprint, adapter/catalogue/policy digests, exact recipe or
candidate ID, target artifact digest, allowed output paths, named verification
checks, activation target, and prior artifact reference. Observation times and
job IDs belong in an execution record, not the deterministic manifest. Recipes
select built-in operations and checks; they do not supply arbitrary shell
commands. Reject unknown format versions, fields, and unsupported actions.

The fingerprint includes the storage format family and both schema profiles,
not just migration 55. Capture each database through read-only transactions and
verify the pair's metadata is stable across capture. Retry a bounded number of
times if Codex is upgrading. Separate database files do not share an atomic
snapshot; if a supported stable pair cannot be established, report
`storage_changing` and defer repair. Repeat capture before activation, then keep
the existing per-query guard after activation.

If the installed adapter already supports several reviewed profiles, select the
exact matching profile directly; that is compatibility selection, not a repair.
A locally cached reviewed update can restore support without network access.
No matching local artifact means report that fact; do not invent or silently
download a replacement. Network update policy is an open choice.

Use one writer lock per managed adapter installation. Recheck metadata and
artifact preconditions immediately before activation; if they changed, discard
the stale plan and rediagnose. Keep staged and previous artifacts, use atomic
activation with a durable journal, and recover by verifying actual state before
replaying a step. A second application of the same recipe should be a no-op.
Rollback restores the adapter, never downgrades Codex's databases; the older
adapter may still refuse the current schema, which must be reported honestly.

Do not self-edit an editable checkout or overwrite current user changes. Detect
installation provenance and either use an isolated managed installation or
produce a patch for review. Never mutate Codex-owned storage. Checks may be
repeated; only notification/repair-attempt deduplication may be cached. Cached
success must never replace the per-query schema gate.

Before activation, verify the selected installation is writable and resolvable
by the CLI launcher. Do not elevate privileges or replace a system package as
a fallback. Report concrete installation instructions if the managed target
cannot be used. Versioned directories plus one atomic launcher selection are
the proposed mechanism; the architecture step must specify platform-specific
locking, durable writes, and crash-recovery rules.

### Second attempt: LLM-generated candidate, deterministic verification

Run this path only for an unsupported schema after the first attempt establishes
that no reviewed recipe applies. LLM generation is **not deterministic**; a fixed
model and low temperature cannot make it so. The routing, policy enforcement,
patch validation, tests, and activation rules remain deterministic. Preserve the
candidate and its digest so a validated repair can later become a reviewed
recipe; do not regenerate it on each startup.

Give the model the sanitized schema diff, relevant adapter source, existing
contracts, and synthetic fixtures. Session content, credentials, personal paths,
and live database files are excluded. Treat schema text and generated code as
untrusted inputs. Work in an isolated staging directory with a bounded patch
scope. The model may propose adapter/profile/fixture changes, but cannot change
its own model gate, trusted recipe catalogue, acceptance tests, or verification
baselines to declare itself successful. Maintainer review handles necessary
changes to independent acceptance expectations.

Validate patch paths and symlinks, run frozen independent tests in isolation,
and check that unknown future schemas still fail. A candidate that merely
disables schema validation must fail. Recommend showing a concrete patch, test
report, and rollback plan before the first activation of a novel LLM repair.
The user has selected LLM fallback, but has not yet selected automatic activation
of newly generated code. Staging and activation must remain separate decisions.

Candidate lifecycle: `generated -> testing -> awaiting_review -> approved ->
staged -> active`, with `rejected`, `failed`, or `rolled_back` outcomes recorded
at the relevant step. The `approve` command records a maintainer's decision; it
does not infer approval from passing tests. Bind that decision to candidate,
schema, independent-check, and policy digests. Any subsequent change invalidates
it. The deterministic `apply` path accepts only a trusted reviewed recipe or
this approved manifest. It must reject a candidate that sets its own JSON
`approved` flag. Restrict trust records and verifier expectations outside the
model-writable workspace.

Tests execute proposed Python code, so a temporary folder alone is insufficient
isolation. Before running a candidate, establish an OS-enforced sandbox with no
live Codex storage, inherited credentials, home-directory mounts, network, or
write access to the controller/trust records. Supply only synthetic databases
and the required test dependencies. If this isolation is unavailable, leave the
candidate unexecuted and report the missing capability.

When Codex is the generation transport, use an isolated repair-worker context
that disables recall startup and cannot launch nested repair/model processes.
The parent controller owns the incident lock and attempt budget. Test that a
repair-worker launch cannot recursively start another fixer. A worker may
produce a patch; it may not invoke `approve`, `apply`, or catalogue updates.

### Human-approved 32K budget blocks

Selected by the user on 2026-09-20, then authorized for implementation. The user
subsequently accepted **rough token estimates**, not an exact hard cutoff. Use the
existing Codex login only, now `gpt-6-astra`, medium reasoning. No API-key
fallback, model substitution, background generation or automatic credit purchase.
Known deterministic recipes use zero AI tokens.

| Control | Initial policy |
| --- | --- |
| Initial incident allowance | Approximately 32,000 total tokens; a soft planning budget, not a hard billing limit |
| Input / generated-token reservation | Initially estimate 16,000 each per request; generated total includes reasoning |
| Early checkpoint threshold | Around 28,000 estimated total, or sooner if the next step is forecast to exceed the remaining allowance |
| Additional allowance | Exactly +32,000 per explicit human approval: cumulative 32K → 64K → 96K |
| Generation requests | One initial request; each approved block permits at most one continuation, never an automatic retry |
| Active generation timeout | Five minutes per request; approval-wait time is not generation time |
| Controller-wide daily allowance | 64,000 estimated tokens; a planned extension crossing it must explicitly name and approve the raised daily allowance |

The input/generated split is an initial estimate, not a claim that the Codex
runner exposes enforceable token controls. Prefer trusted runtime usage when
available; otherwise use a documented rough estimate of supplied text and
generated work, with uncertainty clearly labeled. Reasoning usage may be
unobservable; include a planning allowance rather than pretending visible output
measures it exactly. Count total input, including
cached input, once; count all generated tokens, including reasoning, once. Replayed
context on continuation is new input usage. Do not add cached/reasoning subsets
again when the transport already includes them in totals. Verify the meaning of
reported usage fields before treating them as actual counts; unknown meanings
remain estimates. Exact in-flight caps are no longer a prerequisite selected by
the user. Explicit model/effort, approval and candidate isolation remain; V5
does not require independent per-turn model attestation.

Before each request, atomically reserve its estimated token usage from both the
incident and daily allowances under the controller lock. Reconcile with trusted
actual usage afterward, including any overshoot: never discard an over-limit
usage report or make the ledger appear within budget by truncating it. An
in-flight request may exceed the estimate before it can be stopped; report that
honestly and pause before further generation. A crashed/cancelled request with unknown
usage and no usable final estimate keeps its reservation. A controller-produced
final rough estimate may settle it, labeled estimated rather than actual;
later trusted actual usage must reconcile the difference without double charging.
Process restart, midnight, a new repo or a repeated
CLI invocation must not reset the incident allowance or silently release usage.
No parallel workers or nested model calls may spend around this ledger.

When estimated usage approaches the allowance, checkpoint and pause at the next
safe observable boundary, before knowingly starting over-budget work, then ask:

> Used approximately 28K of the approved 32K. Completed: [short result].
> Remaining: [specific work and why it is needed]. Approve another 32K tokens,
> raising this incident's allowance to 64K? Continue / Stop.

For later blocks, report the real cumulative usage and new ceiling. The user
must affirmatively approve each increment; a preselected choice, silence, one
minute passing, disconnect or a restarted process is not approval. “A minute in
the loop” means a human decision point, not an automatic one-minute renewal.
Remain `awaiting_budget_approval` with no new model requests until a valid response.
Any late usage from an already-dispatched request must still be reconciled;
stopping a local worker cannot promise instantaneous provider-side cancellation.
A denial stops the incident and preserves its checkpoint. Keep at most one
pending request per incident. A grant authorizes spending only, never patch
approval, verification bypass or adapter activation.

Bind every grant to the incident/input fingerprint, model-policy digest, ledger
revision and checkpoint digest; include +32,000, the exact new incident ceiling,
and any explicit daily-ceiling override. Consume a grant once. Stale, replayed,
duplicate or candidate-authored approvals must fail without a model call. Resume
only the same incident after rechecking schema/source/policy and sandbox gates;
a changed incident requires a new review, not reuse of an old grant.

**Estimation caveat:** a prompt saying “stop at 28K” is not a hard budget control.
The [official JSONL example](https://learn.chatgpt.com/docs/non-interactive-mode)
reports usage on `turn.completed`; it does not establish live usage updates or
a hard request cap. Use available telemetry, conservative estimates and checkpoint
boundaries; do not block solely because an exact request cap is unavailable.
If no usable estimate or usage signal can be obtained, pause for human review
instead of silently running without accounting. Cancellation does not undo
already-consumed tokens. The 32K policy is not a guaranteed token or dollar cap.

Required new Stage C checks (add before product implementation): estimated
28K/32K boundaries; predicted overrun before dispatch; zero calls while awaiting/denied;
one valid grant adds exactly32K and enables at most one continuation; daily
override consent; replay/stale/tampered grant rejection; concurrent reservation;
crash recovery without double spend; missing/delayed usage; over-estimate and
under-estimate reconciliation including actual overshoot; cached/reasoning
accounting; timeout; preserved model identity; no generated approval or activation.
Use recording fakes first, then independently authored end-to-end gates. Existing
A/B protected verification inputs must not be silently changed or rebaselined.

### Historical v3 model-attestation design — superseded by V5

Do not implement the obsolete attestation/provider-selection requirements below.
V5 selects a single GPT-6-medium Codex invocation and ordinary configuration
checks; these earlier requirements remain only as design history.

Implement this in the runner/controller, not as a prompt instruction:

1. Resolve the requested model name explicitly. Pending spelling confirmation,
   draft the initial allowlist as `gpt-5.6-sol` only, with default `medium`.
   Permit `high`, `xhigh`, or `max` only when explicitly configured and supported.
   Reject `none`, `minimal`, `low`, unset effort, and unrecognized values.
2. Treat “at least” as a curated allowlist of approved models, not a numeric or
   lexical comparison of names. A newer version or a similarly named tier is
   not automatically eligible. Add a stronger model only through an explicit
   reviewed policy change; do not substitute one here.
3. Pin an official snapshot when available and approved; otherwise record the
   concrete documented ID and its alias/mutability limits. Set model and effort
   explicitly on every request, continuation, retry, and any delegated model
   invocation. Do not inherit the caller's default model or reasoning setting.
4. Inspect the final outgoing request/configuration before starting generation.
   Reject conflicting environment/profile/provider overrides. Disable all
   automatic model fallbacks. Unavailable model, unsupported effort, exhausted
   budget, authentication error, or rate limit must never trigger a lower model.
5. Validate returned model identity against the approved ID/snapshot mapping
   using trusted transport metadata; never trust the model saying what it is.
   Record requested/effective model, effort configuration, policy digest, and
   request ID without secrets. Reject missing or inconsistent evidence before
   accepting a patch. Reasoning effort enforcement relies on the trusted API or
   runner honoring its validated configuration; it is not provable from prose
   or a reasoning-token count.
6. Choose a transport that exposes and enforces these controls. Responses API
   requests can explicitly use `model` and `reasoning.effort`; a Codex runner
   must explicitly set `model` and `model_reasoning_effort` and prove that its
   effective settings satisfy the same contract. If the installed runner cannot
   supply sufficient evidence, keep assistance unavailable rather than silently
   relaxing the gate. Transport/account availability remains to be verified.
7. The minimum also applies to any LLM reviewer or nested agent in the fallback
   workflow. Existing installed custom agents may have fixed lower-tier models;
   they must not be used for this runtime fallback if they violate the policy.
   Prefer no nested LLM calls for the initial implementation.

The controller can prevent this tool from requesting or falling back to a lower
model. It cannot independently attest to undisclosed server internals; its
guarantee rests on the configured trusted provider and reported identity.
Official references: [model capabilities](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
and [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference).

### Implementation sequence and observable extension gates

These steps follow immediate repair steps 1–5; they are not started.

1. **Design and test contract:** an `architect` defines the metadata boundary,
   recipe/manifest format, managed installation strategy, and transport gate;
   `test-planner` specifies independent acceptance cases. Owned paths: planning
   artifacts only. Confirm open policy choices before implementation depends on
   them. Explicitly revise recall instructions to permit only the selected fixer
   workflow; the current blanket no-repair instruction otherwise still applies.
   Required output: architecture and test contracts specifying manifest version,
   JSON statuses/exit codes, filesystem ownership, trusted catalogue source,
   approval storage, sandbox support, and the exact generation transport. Stop
   before implementation if these dependencies are still unspecified.
2. **Deterministic checker and recipe engine:** bounded sequential work in Codex
   provider code/tests and the companion entry point. Demonstrate identical
   manifests for identical inputs, idempotence, exact-match routing, read-only
   storage, and rejection of changed or ambiguous preconditions.
3. **Activation and startup integration:** implement staging, rollback, locking,
   crash recovery, and the chosen startup method. Test concurrent invocations,
   interruption before/after activation, stale plans, permission failures, and
   editable installs. Codex must still launch when recall cannot be repaired.
   Also corrupt the active adapter deliberately in a synthetic install: the
   independent controller must still diagnose it and restore the prior artifact.
4. **Model-gated assistant:** add the isolated candidate workflow only after the
   deterministic path passes. Before any paid live test, use a fake transport to
   prove lower models/efforts cause zero generation requests, all continuations
   preserve policy, unavailable models never downgrade, and mismatched response
   identities cannot yield an accepted patch. Test an unknown schema, rejected
   patch, malicious schema string, timeout, and budget exhaustion.
   Test candidate approval invalidation, forbidden path/network/database access,
   unchanged acceptance tests, and prevention of recursive repair-worker launches.
5. **Independent verification and rollout:** `verification-writer` authors
   adversarial checks; `verification-runner` runs them; `reviewer` inspects the
   implementation; `validator` runs regressions. Apply the minimum model policy
   to any agents used for LLM-fallback evaluation. Integration owner records all
   evidence and does externally mutating work. No overlapping write ownership.

Success means known repairs require no generation, unknown repairs can produce
a tested candidate only through the approved model gate, and every activation
has reproducible evidence and recovery. No test or LLM can authorize an unknown
schema merely by recapturing it as the new expected profile.

### Worked examples for implementation and tests

1. **Known update:** the current store is state 55/history 6. A reviewed recipe
   exactly matches the installed adapter and metadata. `plan` selects that recipe
   without calling a model. If the chosen activation policy permits application,
   the controller stages its artifact, runs the named checks, activates it, and
   reruns schema-check. Applying it again produces no changes. This is the
   intended behavior once Stage A has supplied a reviewed recipe; no such recipe
   is asserted to exist today.
2. **Unfamiliar update:** synthetic state 56 adds a column and no recipe matches.
   The CLI refuses session queries. With explicit `assist` or an elected policy,
   the controller checks model/effort, generates a candidate, and runs isolated
   tests. Passing tests produce `awaiting_review`, not `active`. Maintainer
   approval of that exact candidate makes it eligible for `apply`.
3. **Wrong model:** a configuration requests `gpt-5.6-luna` or effort `low`.
   The controller reports `model_policy_rejected` before any generation request.
   If a trusted response instead reports an unexpected model, the controller
   rejects the result and cannot promote its patch. It does not retry with a
   cheaper model.
4. **Storage problem:** a database is locked or missing. The fixer reports the
   specific problem, uses only the applicable bounded retry, and makes no model
   call. Codex continues without recall.

### Coherence and readability review — 2026-09-19

Review result: coherent as a staged design; Stage B/C implementation readiness
still depends on the explicit architecture/policy decisions above. No product
behavior was validated by this document review.

| Issue found | Revision made | Remaining proof |
| --- | --- | --- |
| A small compatibility fix grew into an autonomous repair system | Added stages A/B/C, separate acceptance gates, and a reading guide | Stage A must pass before later rollout. |
| “Deterministic” appeared to include model output and environmental outcomes | Defined deterministic inputs/selection and kept generation explicitly variable | Replay manifests in hermetic tests. |
| LLM output had no route into reviewed deterministic application | Defined maintainer approval, digest binding, and candidate states | Tampered/self-approved/stale candidates must fail. |
| Updating the adapter could break its own repair tool | Specified an independent stable controller and managed adapter versions | Broken-import and interrupted-activation recovery tests. |
| “Sandbox” could mean only a directory | Required OS-enforced restrictions before candidate execution | Prove denied storage/network/credential access. |
| Startup versus instruction-driven checks was ambiguous | Defined coverage and made foreground assistance the initial recommendation | Verify selected launcher/transport integration. |
| Open recommendations could be mistaken for user decisions | Kept questions open and separated user-selected requirements | Resolve choices only before dependent work. |
| Terminology and two step sequences burdened a junior reader | Added glossary, worked examples, concrete deliverables, and gate descriptions | A developer should be able to explain each transition without assuming missing policy. |

## Suggestions and questions for the next revision

- **Promote successful fixes into recipes.** After independent review, save the
  exact patch/artifact, schema fingerprint, and tests so that the next occurrence
  uses the deterministic path with no model call.
- **Start with local artifacts and visible activation.** Add trusted download
  sources later if distribution delay is the main obstacle. Artifact integrity
  must be anchored in an authenticated release or pinned trusted catalogue;
  an untrusted download plus its own checksum is insufficient.
- **Bound the LLM attempt.** Recommend one candidate attempt per incident, a
  configurable timeout/token ceiling, and no repeated startup retries. Reset
  the attempt only after a relevant schema/catalogue/policy change or explicit
   retry. Version4 selects the [32K approval-block policy](#human-approved-32k-budget-blocks),
   replacing the earlier zero-continuation proposal with human-approved extensions.
- **Use metadata-only incident reports.** Keep reports outside the tracked repo
  and Codex storage, with schema/adapter/recipe digests and concise outcomes.
  Preserve no prompts, session rows, credentials, or sensitive raw logs by default.
- **Test the downgrade prohibition first.** The highest-value early gate is a
  fake provider that tries to substitute a lower model; no generated patch may
  be applied or accepted, and no controller-originated lower-model call may occur.

Policy decisions and remaining questions:

1. Resolved by V5: `gpt-6-astra`, medium reasoning; Codex CLI only.
2. Should reviewed recipes activate automatically after one-time opt-in, while
   a novel LLM patch requires review? Suggested: yes.
3. Should the initial trigger be CLI use plus session instructions, or a terminal
   launch wrapper as well? Suggested: CLI plus instructions first.
4. Should updates remain local, download only for review, or activate trusted
   downloaded recipes automatically? Suggested: local first.
5. Resolved: one isolated `codex exec` invocation using the existing login;
   no alternate provider/API and no independent identity-attestation requirement.
6. Resolved: initial32K and explicit +32K grants; operational defaults and
   enforcement caveats are in the budget-block section above.

## 🔴 Red Team — Munger Inversion Check

Reviewed 2026-09-19 against version 3 after the coherence/readability pass.
Findings below are design risks, not claims that an implemented fixer failed.
Their controls are requirements to verify during implementation.

### Inversion #1 — "What if the fixer makes the test agree with the mistake?"

**Failure mode:** The tool copies an unfamiliar database definition into both
the production profile and its fixtures. Every test passes because the expected
answer was replaced, even though session filtering now has different semantics.

**Evidence I may be wrong:** Runtime checks and synthetic fixtures both use
`captured-profiles.json`; the proposed model can edit profiles and fixture data.

**Fix:** Keep independent output/filter contracts outside model write scope.
Require reviewed migration semantics and a negative test against a still-unknown
schema. Capture alone never promotes compatibility. Implement in A1/A2 and
extension steps 1/4; frozen-test tampering must fail verification.

### Inversion #2 — "What if the two databases describe different upgrade moments?"

**Failure mode:** A repair is selected from state metadata captured before an
upgrade and history metadata captured afterward. It matches neither usable pair.

**Evidence I may be wrong:** Codex uses two separate SQLite files; a connection
transaction in one does not give an atomic snapshot of the other.

**Fix:** Include both schemas in the fingerprint, require a stable supported
pair across capture, and revalidate before activation and data access. Simulate
changes between reads; after bounded retries, report `storage_changing` rather
than fabricate a profile. Implement in extension steps 1/2/3.

### Inversion #3 — "What if the requested model is only a label?"

**Failure mode:** A runner inherits a cheaper default, downgrades on failure, or
uses a lower-tier nested agent while claiming compliance in its final text.

**Evidence I may be wrong:** “Soul” is not yet confirmed as `gpt-5.6-sol`, and
installed custom agents can have fixed model settings different from the request.

**Fix:** Resolve the identifier, validate every outgoing request, disallow
fallbacks, and inspect trusted response identity. Exercise retries, continuations,
and attempted nested calls with a fake transport. Reject before generation when
configuration is lower; reject artifacts when response identity conflicts.
Implement the gate before any live LLM repair in extension step 4.

### Inversion #4 — "What if an attacker supplies a repair and its matching hash?"

**Failure mode:** A malicious patch looks valid because it has a checksum and
an `approved` field, but neither came from a trusted maintainer or release.

**Evidence I may be wrong:** The design uses local artifacts, manifests, hashes,
and a future download option; checksums verify bytes, not who authorized them.

**Fix:** Specify a trusted catalogue/approval store outside model write scope.
Bind approval to exact input, policy, tests, and candidate digests. Reject a
self-approved candidate or catalogue supplied alongside an untrusted download.
Implement provenance in extension step 1 and enforce it in steps 2/3/4.

### Inversion #5 — "What if passing tests silently becomes permission to install?"

**Failure mode:** An LLM candidate automatically moves into production even
though the owner only authorized generation and testing, or approval covers a
different patch than the one applied.

**Evidence I may be wrong:** Version 2 exposed `assist` and `apply` without a
complete promotion contract; novel-code activation policy remains unanswered.

**Fix:** Version 3 defines `approve`, digest-bound review, and explicit candidate
states. Only reviewed manifests enter `apply`; changed candidates return to
review. Test that successful tests alone cannot activate a candidate and that
approval is invalidated by any patch change. Implement in extension steps 3/4.

### Inversion #6 — "What if the candidate steals data during its test run?"

**Failure mode:** Proposed code imports a module or executes a test that reads
the user's home directory, leaks credentials, or changes the live database.

**Evidence I may be wrong:** Tests run arbitrary Python; a staging directory
changes file location but does not restrict process access.

**Fix:** Use an OS-enforced candidate sandbox with synthetic stores, no inherited
secrets, no network, and no access to live databases or controller files. Prove
denial with an intentionally hostile fixture. If sandboxing cannot be enforced,
leave the patch unexecuted. Implement as a prerequisite to extension step 4.

### Inversion #7 — "What if the update breaks the tool needed to undo it?"

**Failure mode:** A bad profile or import prevents both normal recall and the
fixer from starting, or an interruption leaves a half-installed adapter selected.

**Evidence I may be wrong:** The existing adapter loads its profile at import
time, and the companion initially proposed sharing that same implementation.

**Fix:** Keep a stable controller independent of the replaceable adapter,
versioned artifacts, a durable journal, and atomic selection. Inject crashes
around each activation boundary and corrupt the active profile/import. The
controller must diagnose and roll back without importing the broken adapter.
Implement in extension steps 1/3; rollback may correctly leave recall unavailable.

### Inversion #8 — "What if one schema error launches an endless repair loop?"

**Failure mode:** Startup launches Codex for a repair, which follows startup
instructions and launches another repair. Repeated sessions also exhaust the
model budget while trying the same unsupported change.

**Evidence I may be wrong:** The proposal combines Codex-start instructions,
Codex as a possible generation transport, and automatic assistance as an option.

**Fix:** Start with foreground assistance. Isolate repair-worker instructions,
disable nested repair/model launches, and let one parent controller own the
incident lock, budget, and durable attempt state. Test simultaneous CLI calls
and worker startup recursion. Implement in extension steps 3/4.

### Inversion #9 — "What if a junior developer implements the recommendations as facts?"

**Failure mode:** They execute proposed commands that do not exist, allow an
unconfirmed model, or implement all optional automation before restoring recall.

**Evidence I may be wrong:** The document has two numbered step sequences and
several policy choices; the scope expanded during planning.

**Fix:** Use the A/B/C reading guide, glossary, examples, and separate gates.
Keep unresolved choices visible and command names explicitly proposed. Before
coding, require a short walkthrough of known-schema, unknown-schema, and wrong-
model examples with expected state transitions. This is a readiness check, not
a request to reapprove settled decisions.

### Inversion #10 — "What if the deterministic fixer never has a useful recipe?"

**Failure mode:** The system looks automatic but every new Codex update takes
the LLM/manual path because no one owns reviewing and publishing recipes.

**Evidence I may be wrong:** Local-only recipes are the suggested first release,
and migrations have already advanced from 51 to 52 to 55. Runtime machinery
alone cannot create reviewed compatibility knowledge.

**Fix:** Use the Stage A repair as the first concrete recipe and name a maintainer
for recipe promotion/distribution before Stage B rollout. Measure repair reuse,
unknown-schema incidence, and time to reviewed support without collecting
session data. Add a trusted update source only if those results justify it;
do not compensate by auto-approving novel model patches.

### 🎯 Munger-Style Questions to Ask Myself BEFORE implementation

1. Am I restoring useful recall, or building an updater before I have one good repair?
2. Which piece of evidence would persuade me that the new columns change query semantics?
3. Would I trust these tests if the model wrote the patch and wanted them to pass?
4. What happens when I kill the process at the worst possible activation moment?
5. Can I demonstrate the minimum-model rule without trusting a prompt or generated prose?
6. Which decisions are actually the user's, and which are still my recommendations?
7. What is the smallest reversible release that proves a real repair can be reused?

### ✅ Net Verdict

| Section / Component | Verdict |
| --- | --- |
| Immediate migration-55 repair | **KEEP** — confirmed failure; full compatibility still needs review and tests. |
| Deterministic selection | **KEEP** — exact recipes and canonical inputs make routing reproducible. |
| Automatic acceptance of unknown additive schemas | **CUT** — structural additions do not prove semantic compatibility. |
| Candidate-to-repair promotion | **REWRITE** — v3 adds explicit maintainer approval and digest binding; tests remain pending. |
| Fixer bootstrap and rollback | **REBUILD** — isolate the controller from the adapter it replaces; verify failure recovery. |
| Minimum model gate | **VERIFY** — documented model capabilities exist; identifier, runner enforcement, and account access still need confirmation. |
| Candidate execution | **VERIFY** — OS isolation and protected independent checks must be demonstrated. |
| Startup automation | **REWRITE** — begin with bounded checks and foreground assistance; wrappers/background jobs stay optional. |
| Junior-developer handoff | **KEEP** — guide and examples clarify order; resolve architecture choices before dependent coding. |

Make the first repair small and reversible, and require stronger evidence to trust a new repair than to generate one.

## Verification

> Added with `verify-add` on 2026-09-20 UTC using repository-local
> [how-to guidance](../verify/how-to-use-verify.md) and
> [verification specification](../verify/verification-script-spec.md).
> Append-only addendum to plan v3. All implementation gates are **PENDING**.

This section covers the three stages already named in the plan: A (immediate
repair, steps 1–5), B (deterministic fixer, extension steps 1–3), and C (AI
fallback, extension step 4). Extension step 5 closes each implemented stage.
It uses Python/pytest, not the skill template's TypeScript/Vitest commands.
The [declarative specifications](../verify/fix-cli-codex.yaml) contain one YAML
document per stage. No executable verifier is created or run by this revision.
The proposed runner below must be authored before implementation depends on it.
[spec §§3–4; how-to: “How to do it”]

### 0. Baselines — capture before implementation

Record fresh evidence with the selected interpreter and fixed plugin settings.
Earlier diagnostic counts are historical context, not a new passing baseline.
Do not snapshot, hash, or copy live Codex databases as part of these checks.
[spec §§2, 7, 11]

| Evidence | Proposed capture | Current status |
| --- | --- | --- |
| Existing work and protected checks | `git status --short`; digests of scoped source, tests, profile, verifier/spec files, and independent expected results | Pending; preserve pre-existing user changes when comparing later diffs. |
| Python/package provenance | Interpreter version, imported package path, installed distribution metadata, dependency and plugin versions | Pending; previous 0.4.0 metadata versus 0.5.1 source discrepancy remains recorded above. |
| Collected/passed/failed/skipped tests | `python3 -m pytest src/ --collect-only -q -p no:cacheprovider`, then the same suite without `--collect-only` | Pending; previous targeted run was 44 passed / 3 failed. |
| Clock defect control | Same targeted tests and plugin loading with wall clock versus isolated fixture clock | Pending; change only the query clock between controls. |
| Lint findings | `ruff check src/` with exit code and rule/path counts | Pending; distinguish old findings from newly introduced findings. |
| TypeScript compilation | Not applicable to this Python repair | No `tsc` or Vitest gate. |
| Timing | Per-stage elapsed time under a recorded interpreter/environment | Pending; use the bounded budgets in the YAML, separate from model spending policy. |

### Contract and execution rules

`verification-writer` owns the frozen spec, independent expected results, and
later verifier scripts; `verification-runner` executes one script in a fresh
shell after execution is requested. The integration owner owns this journal.
Freeze tests and review necessary fixture/schema expectation updates **before**
the product implementation handoff. This refines step 4's execution timing:
author the gates at A2/B1, run them at each applicable step and at A4/B3/C4.
Do not wait until the repair is implemented to decide its expected behavior.
[spec §§1–4, 13; how-to: “Before first commit”]

Use fresh temporary synthetic stores, a controlled test clock, pinned test
dependencies, `PYTHONHASHSEED=0`, `PYTHONDEVMODE=1`,
`PYTHONDONTWRITEBYTECODE=1`, `TZ=UTC`, and explicit plugin loading. Clear
`PYTHONPATH` and `PYTEST_ADDOPTS`. Set all Codex storage overrides to synthetic
paths and deny fallback to real storage. Candidate execution additionally needs
the OS sandbox specified in Stage C; environment variables alone are not a
sandbox. No network, paid calls, global installation, or startup changes in
synthetic gates. [spec §2 P2/P8, §§5–6]

Each L1 gate checks the completed step's behavior, an applicable global invariant,
and scope/tamper rules. L2 runs pytest first, then at least five independent
behavioral probes spanning happy, boundary, failure, invariant, and negative
cases. Two fresh subprocesses compare the canonical behavior with independently
reviewed expected output, not with an oracle generated from the mutable profile.
Run twice; compare stable result fields, excluding duration and run identifiers.
[spec §§2–3, 8, 14.5]

Known public examples, including “Goodhart law applies here, here, and here.”,
are useful test inputs but **not held out**. Add privately seeded strings and
schema mutations at verification time; preserve the seed outside candidate
write access for reproducibility. AST checks cover new/changed concrete
functions and new skips, bare-except suppression, literal-output shortcuts, and
empty assertions. Baseline-allowlist existing abstract methods and deliberately
deferred `NotImplementedError` stubs; do not implement deferred commands to
satisfy a blanket scan. [spec §§7–8, 14.2–14.5]

Every verifier exit path emits a final JSON verdict with `verdict`, `gate`,
`exit`, executed case IDs, and a failure reason where applicable. Use verifier
exits 0 (pass), 1 (behavior failure), 2 (infrastructure), 3 (tampering), and 124
(timeout); assert the CLI's different exit meanings inside the probes. A missing
test/script, unsupported sandbox, skipped required case, or zero collected tests
cannot count as pass. [spec §9]

Self-tests must launch a deliberately broken implementation from an isolated
target and prove it was imported/executed. Require the expected behavior failure,
not just any nonzero result: missing dependencies or a timeout do not prove the
verifier detects a bug. The outer `--self-test` exits 0 only when the expected
rejections are observed, and 3 if it accepts a known-bad target. This resolves
the contradictory self-test wording in spec §14.1 using §§2 P9, 9, and 11.
Never mutate the user's checkout for a mutation probe. [spec §§8–9, 11, 14.1]

### Phase A — restore the CLI · L1 gates

The YAML document `fix-cli-codex-A` specifies the full cases. A1 requires reviewed
metadata evidence; tests must not invent the new columns' SQL definitions.
At A2, the known-bad migration-52 adapter must reproduce the expected refusal;
that is expected-red evidence, not a working migration-55 repair. At A3, require
the reviewed profile to pass with independent output/filter expectations. A4
requires negative schema probes and verifier self-tests. A5 requires an isolated
built-wheel install to produce correct CLI results without importing the source
checkout. [spec §§3–4, 7; how-to: “During implementation”]

```yaml
task_id: fix-cli-codex-A
acceptance_criteria:
  - Reviewed current schema returns correct list/repos output; unknown schemas fail before session queries.
boundary_cases:
  - Empty store and exact 30-day cutoff preserve the documented output/filter contract.
invariants:
  - Both synthetic stores remain unchanged and invalid schemas execute zero session-data queries.
anti_cheat_checks:
  - Reject bypassed preflight, profile-derived output oracles, and changed frozen expectations.
```

Proposed runner command after each A step: `python3 verify/fix-cli-codex.py
--phase A --level L1 --step A1` (then A2 through A5). The runner is **not yet
implemented**; its step selector must distinguish expected-red evidence from
final acceptance. Regression: existing Codex tests, schema/smoke verifiers,
provider isolation, and the full `src/` suite at A completion. [spec §§3, 13]

### Phase B — deterministic fixer · L1 gates

The YAML document `fix-cli-codex-B` covers extension B1 contract readiness, B2
exact recipe routing, and B3 activation/recovery. The same canonical schema,
adapter, catalogue, and policy must produce byte-identical manifests. Known
repairs require **zero generation calls**. Unknown metadata permits eligibility
for assistance; missing/locked/corrupt storage and failed known recipes do not.
No selected activation policy means no activation. [spec §§2–4, 8]

```yaml
task_id: fix-cli-codex-B
acceptance_criteria:
  - An exact trusted recipe stages, verifies, and activates only under the selected policy.
failure_mode_cases:
  - Stale or ambiguous manifests, changing metadata pairs, and interrupted activation fail or recover predictably.
invariants:
  - Reapplying an active repair is a no-op; one installation has one activation writer; model calls equal zero.
anti_cheat_checks:
  - Reject self-approved recipes, untrusted matching hashes, and manifests containing executable commands.
```

Proposed L1 command: `python3 verify/fix-cli-codex.py --phase B --level L1
--step B1` (then B2/B3). Validate reordering of irrelevant JSON object keys while
preserving meaningful column order. Kill test processes at each durable journal
and activation boundary, then resume from actual state. Check the controller
still diagnoses a corrupt active adapter, and rollback reports incompatibility
honestly. Regression: all Stage A acceptance plus previously completed B cases.
[spec §§2–4, 8, 13]

### Implemented C budget-only verification

The independently authored [budget verifier](../verify/codex_budget_verify.py)
covers C1/C2 only. Its JSON always includes `scope: "budget-only"` and
`full_stage_c_verified: false`:

```bash
python3 verify/codex_budget_verify.py --self-test
python3 verify/codex_budget_verify.py --level unit
python3 verify/codex_budget_verify.py --level store
```

The store level includes pure-unit probes and all four durable-store suites
(basic, adversarial records, approval proofs and overshoot headroom). Synthetic
process crashes, concurrency, duplicate/stale approvals, silence, midnight,
estimate-to-actual reconciliation and unsafe files are tested. The separate
[C hash manifest](../verify/codex-budget-hashes.txt) protects 31 reviewed inputs.
The A/B manifest retains all original74 hashes and adds16 required C source/test
entries; its cumulative gate still passes. These results do not satisfy the
remaining full-C transport, real approval-channel or candidate-sandbox gates.

### Phase C — AI repair with fixed input/output contracts · L1 gate

The YAML document `fix-cli-codex-C` covers extension C4. “Fixed” means versioned,
strictly validated **formats** for input and output, not identical code from
every generation. The schema metadata values vary with Codex's storage version.
Before implementation, freeze these envelope contracts and exact size/depth
limits; values below describe required contents, not a shipped API. [spec §§4, 7]

| Boundary | Required content and deterministic checks |
| --- | --- |
| Input envelope | Format version; canonical metadata for both stores; current/target schema fingerprints; adapter, catalogue, and policy digests; allowed patch paths; immutable acceptance-contract reference. Only allowlisted schema/source context, never session rows, secrets, or machine-specific paths. |
| Candidate envelope | Format version; matching input fingerprint; base artifact digest; proposed patch/artifact with constrained file list. Controller recomputes digests; generated claims about tests, approval, or model identity have no authority. |
| Independent result | Controller-generated verdict, executed case IDs, trusted request/model metadata, and candidate/schema/policy/test digests. Passing checks yields `awaiting_review`; only digest-bound maintainer approval enables application. |

Reject malformed JSON, duplicate/unknown keys, unsupported versions, missing or
wrongly typed fields, stale input/base digests, over-limit content, path traversal,
symlink escapes, attempts to change protected tests/policy/catalogues, and
self-approval fields before executing any candidate. Schema strings containing
instructions are inert data. An output-validation error must not trigger an
unbounded regeneration loop. [spec §§4, 7–8]

```yaml
task_id: fix-cli-codex-C
acceptance_criteria:
  - Eligible unknown schema yields only a validated candidate through the explicitly approved model/effort policy.
failure_mode_cases:
  - Invalid envelopes or missing/conflicting model evidence cannot produce an accepted patch.
invariants:
  - Lower-model/effort requests are never sent; passing tests alone never activates code.
anti_cheat_checks:
  - Independent transport counts, sandbox-denial probes, and protected digest checks override model-authored claims.
```

Proposed L1 command: `python3 verify/fix-cli-codex.py --phase C --level L1
--step C4`. Use a fake transport with independently captured outgoing calls.
Cover initial calls, retries, continuations, exhaustion, identity mismatch, and
attempted nested repair/model launches. Invalid local configuration makes zero
generation calls; response mismatch may follow a call but cannot approve its
candidate. Pin an explicit **synthetic** model policy in tests. Version4 resolves
model, login transport and incremental budget choices, but fake tests do not
prove live enforcement or authorize candidate activation.
Regression: Stage A+B acceptance, including zero-model routing for known recipes.
[spec §§2–4, 8]

### Inversion findings mapped to observable probes

The skill's inversion pass rechecked the existing ten Munger findings. Retain
that historical review; the following probes operationalize its fixes without
adding a second Red Team section. All are pending. [spec §§2 P6, 7–8, 14]

| Existing inversion | Required rejection or observable proof |
| --- | --- |
| 1 — Tests agree with the mistake | Bypassed preflight and rewritten output oracles fail independent A/C probes. |
| 2 — Mixed database upgrade moments | Change one synthetic schema between captures; bounded retries end in `storage_changing`, with no activation. |
| 3 — Model identity is only a label | Wrong outgoing policy yields zero requests; conflicting response identity yields zero accepted candidates. |
| 4 — Attacker provides hash and approval | Matching attacker-controlled hash/catalogue plus `approved` flag remains untrusted. |
| 5 — Tests become installation permission | A passing unapproved candidate cannot activate; any digest change invalidates approval. |
| 6 — Candidate steals data | Hostile synthetic candidate cannot read outside its allowed sandbox, access secret sentinels, reach network, or modify protected stores. |
| 7 — Fixer cannot undo its own update | Corrupt active imports and interrupt each activation boundary; independent controller recovers a complete prior/target selection. |
| 8 — Recursive repair and runaway spending | Concurrent invocations create one attempt; worker recursion and exhausted retries send no extra generation requests. |
| 9 — Draft defaults treated as decisions | Unset policy/contracts block their dependent actions; Stage A can complete without B/C being marked passed. |
| 10 — No useful recipe | Reuse the independently reviewed A repair in B with zero model calls; maintainer/approval provenance remains auditable. |

### End-to-end verification — after each implemented stage

Choose a Python runner for subprocess, JSON, database-fixture, and crash-state
orchestration. Its proposed path is `verify/fix-cli-codex.py`; it does not exist
yet. Every invocation below inherits the hermetic settings above. The runner
must enforce those settings itself and bind results to the tested artifact,
spec, and oracle digests. [spec §§5–6, 9–10]

```sh
# After Stage A implementation; proposed commands, not executed during planning.
python3 verify/fix-cli-codex.py --phase A --self-test
python3 verify/fix-cli-codex.py --phase A --level L2
python3 verify/fix-cli-codex.py --phase A --level L2

# After B implementation, include A; after C implementation, include A+B.
python3 verify/fix-cli-codex.py --through B --self-test
python3 verify/fix-cli-codex.py --through B --level L2
python3 verify/fix-cli-codex.py --through B --level L2
python3 verify/fix-cli-codex.py --through C --self-test
python3 verify/fix-cli-codex.py --through C --level L2
python3 verify/fix-cli-codex.py --through C --level L2
```

L2 includes each selected stage's pytest and independent probes, the applicable
existing Codex schema/smoke self-tests and gates, full regression, and scoped
lint. Stage-specific self-test mutants include always-pass preflight (A),
always-select-first recipe/stale activation (B), and accept-wrong-model or
self-approved candidate (C). An aggregate cannot report pass if a selected
stage is unavailable. No live model call is necessary for deterministic
controller verification; a later authorized transport check establishes real
integration only. [spec §§2–3, 8–11]

L3, when CI work is authorized, repeats cumulative L2, mutation/self-tests and
supported Python/platform regression, with synthetic fixtures and private seeds.
Record an agreed coverage baseline for changed paths before imposing a threshold.
Do not add CI configuration or broaden the supported-platform contract in this
planning revision. [spec §3]

### Pre-"Done" checklist

These boxes concern **implemented stage acceptance**, not completion of this
planning request. [spec §11; how-to: “Quick checklist”]

- [ ] Reviewed metadata, stage contracts, and policy choices needed by this stage are resolved.
- [ ] YAML, independent expected results, and verifier were frozen before implementation handoff.
- [ ] L1 step gates captured expected-red versus final-green evidence correctly.
- [ ] L2 self-test detects known-bad implementations for the intended reasons.
- [ ] Fresh-shell L2 runs twice with matching stable verdicts and captured exit 0.
- [ ] All required cases execute; collection equals passed count, without new skips/deselection.
- [ ] Independent probes cover every acceptance criterion and applicable inversion above.
- [ ] Protected checks remain unchanged or have explicit independent review and new digests.
- [ ] Synthetic no-write, sandbox, crash/rollback, and model-call-count evidence passes where applicable.
- [ ] Test artifact/import provenance matches what will run; source checkout cannot mask a broken wheel.
- [ ] Pre-existing changes are preserved; remaining limitations and stage status are recorded in the journal.
- [ ] Later stages remain not started until separately executed; no unsupported-schema bypass or automatic model downgrade was introduced.

## 2026-09-25 owner follow-up: schema 57/7 and 100,000-token grants

The owner requested an exact repair of the installed Codex recall CLI and a
versioned 100,000-token repair grant in this project. The fixer classified state
migration 57 and history migration 7 as unknown. One authorized Astra/medium
candidate request failed because the fixer's usage-event parser omitted fields
now emitted by Codex 0.157. A narrow parser correction preceded the separately
approved retry. The candidate changed only the captured schema profile, passed
the fixer's isolated checks, and was explicitly approved and activated. The
installed `session-recall-codex` launcher must be verified after installation;
activating the adapter alone does not replace a legacy console script.

The active future budget is the packaged
[`model-policy-v3.json`](../src/session_recall/codex_fix/data/model-policy-v3.json),
explained at the project root in [`CODEX_REPAIR_POLICY.md`](../CODEX_REPAIR_POLICY.md).
It starts with 100,000 tokens and three requests. An owner-approved extension
adds 100,000 tokens and three requests, with a matching daily-ceiling increase.
Each request still has a 32,000-token estimate and no hard response-token cap.
The old v2 ledger remains immutable; same-day spend or unresolved usage blocks
a v3 ledger reset. Keep old grants and receipts bound to their policy version.
No Codex-owned database or session row is modified by the repair.
