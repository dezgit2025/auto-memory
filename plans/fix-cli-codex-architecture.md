# Codex fixer architecture contract

Status: **V5 workflow implemented and offline-verified; live generation remains unverified after one safe failed smoke attempt. See the journal.**

## V5 implementation direction — authoritative

Use the [simple V5 plan](fix-cli-codex.md#v5-the-simple-path-to-implement).
Known recipe first; otherwise one `codex exec` job using the existing login,
`gpt-6-astra`, medium reasoning, fixed candidate output, isolated tests and the
existing activation/rollback path. No alternate provider/API, model router,
app-server dependency or independent model-attestation layer. Missing per-turn
model metadata is not a blocker; explicit mismatches and invocation errors fail
the attempt without substitution.

Keep approximate32K/+32K human approvals and reuse the completed ledger. Default
to foreground invocation and review before real activation while two optional
preference questions await answers. They do not block implementation. Migrate
the active Sol-specific policy/usage validators and tests during execution;
do not fabricate an effective-model claim, rewrite old receipts or reset usage.
Keep candidate path validation, synthetic tests and OS isolation; these are
engineering tasks, not reasons to request another provider or model choice.
The older C protocol/attestation notes below are historical when inconsistent
with V5; completed B/C-budget code is preserved, not deleted or redesigned.

### V5 execution contracts (2026-09-20)

- Policy v2 uses `astra-medium-budget-v2`; requested model/effort and optional
  reported model/effort are separate. Exact legacy v1 receipts stay readable.
- Migration must not reset usage. Keep the legacy ledger and permit settlement
  of old reservations, but never new v1 requests or grants. Conservatively block
  v2 dispatch while any legacy hold or current-UTC-day charge remains; a fresh
  day after settlement can use v2. Invalid legacy records fail closed. This
  avoids introducing another budget accounting system during the runner work.
- Candidate file paths are archive-relative (`session_recall/providers/codex/…`),
  selected from a controller-owned allowlist. Each source digest hashes raw UTF-8
  bytes. Full-file replacements use the existing Candidate wire contract below.
- The transport-only CandidateDraft permits `Source.sha256: null`. The controller
  computes raw UTF-8 hashes before the unchanged strict Candidate validator;
  supplied non-null hashes must match. No null hash reaches stored reviews or
  approvals. The exact input digest is supplied in fixed developer instructions.
  This lets the worker propose arbitrary allowed code edits with tools disabled.
- Generation uses an isolated Codex home with only the existing authentication
  material, ignores user configuration/rules, disables shell tools, and sends
  canonical CandidateInput on stdin. No conversation storage is copied.
- Candidate execution uses a separate macOS SBPL sandbox with a narrow Python
  runtime/read allowlist, disposable scratch writes, and no network. Both positive
  controls and hostile denial probes must pass before candidate execution.
- Approval promotes a reviewed local candidate into an effective catalogue built
  from the unchanged compiled base catalogue plus validated durable approvals.
  The existing store transaction and rollback remain the activation mechanism.
  A fresh launcher must validate the same approval and artifact bindings.

This freezes the smallest stdlib-only Stages B/C design in the [repair plan](fix-cli-codex.md); Stage A and its [verification gates](../verify/fix-cli-codex.yaml) remain prerequisites.

## Selected policy

- Recipes and adapter artifacts are bundled/local only; no downloader or custom catalogue in v1.
- Reviewed recipes default to explicit `apply`; persisted opt-in may auto-apply a known recipe when invoked, never via startup/background, privilege, or checkout mutation.
- `assist` is foreground and produces at most a candidate; approval and apply are separate.
- The repair-worker default is `gpt-6-astra`, medium reasoning, passed explicitly to Codex. No alternate model or global-settings rewrite.
- One initial generation request; each explicit +32K human grant permits at most one continuation. No automatic retries or nested model calls.
- Selected transport: a thin `codex exec` subprocess with existing login. No provider fallback. Use ordinary requested-setting/error checks, approximate accounting and isolated candidate validation.
- Retained budget policy: [human-approved 32K blocks](fix-cli-codex.md#human-approved-32k-budget-blocks). Initial32000, pause threshold28000, +32000 per consumed-once grant, daily64000 with explicitly named overrides, five-minute active-request timeout. Waiting dispatches no new model work; late usage from an in-flight request remains accountable.

## Boundary and packaging

`session_recall.codex_fix` is the stdlib-only stable controller and never imports
`session_recall.providers.codex`. `session_recall.codex_metadata` is a stable leaf
module exposing `inspect(state_conn,history_conn)->SchemaSnapshot`; it imports no
provider/adapter and may later be reused by the provider. The first B increment adds:

- `session-recall-codex-fix = session_recall.codex_fix.cli:main`

The replaceable adapter is a reproducible `adapter.pyz`. Replace `schema.py`
`Path(__file__)` profile loading with `importlib.resources.files(...).joinpath(...).read_text(encoding="utf-8")`, tested from source, wheel, and zipapp. Builds sort
entries, fix timestamps/modes, exclude bytecode, embed a manifest, and hash bytes.

Keep the existing `session-recall-codex` entry point until a release bundles and
validates the state-55 seed. That release may switch it to
`session_recall.codex_fix.launcher:main`; absent a selection it verifies/runs the
seed without mutation. Legacy/editable installs are diagnosis-only `unmanaged_legacy`.

The launcher resolves only digests, rejects symlinks/non-files, rehashes, and runs
`[sys.executable, artifact, *argv]` without a shell. POSIX uses `execv`; verified
alternatives propagate exit status. Broken adapters cannot block `check`/`rollback`.

Compiled `TRUSTED_CATALOGUE_SHA256` authenticates bundled `catalogue-v1.json`;
recipes authenticate artifacts. Controller replacement is out of scope. Catalogue,
policy, approvals, and independent checks are never candidate/adapter-writable.

Builder contract: `scripts/build-codex-adapter.py --profile 52|55 --output PATH.pyz`
emits `{artifact_digest,schema_fingerprint,output,profile_ids}`. The zip root
`ADAPTER-MANIFEST.json` contains exactly `{format_version:1,entry_point:
"session_recall.providers.codex.cli:main",profile_ids:{state,history},
schema_fingerprint,profiles:{state,history}}`. The profiles are the same captured
profile data supplied to the adapter resource; the schema digest converts them
to UsedProfile and excludes ancillary descriptions. No digest contains itself.
Entries are sorted with fixed timestamps/modes; tests require byte-identical
rebuilds and source52 refusal versus target55 success on a synthetic55 store.

## Managed state and durability

Default root: `$XDG_STATE_HOME/session-recall-codex-fix`, else
`~/.local/state/session-recall-codex-fix`. Resolve once; require user-owned `0700`
and no symlink components. Reject writable non-sticky ancestors; allow OS-owned
sticky `/tmp` only above a process-owned `0700` `mkdtemp`. Never clean unresolved paths.

```text
artifacts/sha256/<64hex>/adapter.pyz
staging/<operation-id>/
selection/current.json        selection/previous.json
journal/<operation-id>.json   locks/activation.lock
candidates/<candidate-id>/    approvals/<candidate-digest>.json
```

One advisory lock protects each root (`fcntl` or a tested stdlib alternative);
unsupported locking disables activation. Records use same-directory exclusive temp,
file fsync, `os.replace`, and directory fsync; unsupported durability disables apply.

Journal phases: `prepared`, `artifact_verified`, `staged`, `checks_passed`,
`selection_committed`, `postcheck_passed`, `complete`, `rollback_required`,
`rolled_back`, `failed`; each records digests. Recovery locks and reconciles actual
state, never replays blindly. Reapply is a no-op; rollback may remain incompatible.

## Canonical JSON and limits

Envelopes are UTF-8 JSON with `format_version:1`, no duplicate/unknown keys or
floats, and sorted compact canonical bytes. Arrays preserve order. Digests are
`sha256:` + 64 lowercase hex; IDs match `[a-z0-9][a-z0-9._-]{0,63}`. Integers are
`0..2^63-1`, strings <=512 UTF-8 bytes, depth <=16, decoded size <=2 MiB.

`UsedProfile` is `{filename:string<=128, migration_ceiling:int<=1000000,
failed_migrations:int<=1000000,json1:bool,tables:Table[<=4]}`; `Table` is
`{name:string<=128,columns:Column[<=256]}`; `Column` is `{cid:int<=255,name:string<=128,
declared_type:string<=128,not_null:bool,default_sql:string<=512|null,pk_position:int<=32}`.
State uses `threads,_sqlx_migrations`; history uses `thread_items,thread_turns,_sqlx_migrations`.
Capture twice; instability after two retries is `storage_changing`. Descriptions,
checksums, and unrelated objects are diagnostics excluded from every semantic digest.

The v1 envelopes are:

- `SchemaSnapshot`: `{format_version,storage_family,state:UsedProfile,
  history:UsedProfile,schema_fingerprint,diagnostics:string[<=128]}`. Inspection
  returns only this; schema fingerprint hashes family/state/history.
- `Observation`: `{format_version,snapshot:SchemaSnapshot,adapter:AdapterIdentity,
  catalogue_digest,policy_digest,input_fingerprint}`. Input fingerprint adds
  adapter/catalogue/policy and never diagnostics.
- `AdapterIdentity`: `{kind:"managed"|"bundled"|"legacy", artifact_digest:
  null|digest, profile_id:null|id}`. It comes from selection/package metadata and
  byte hashes without importing active adapter code.
- `Classification`: `{format_version,status:"supported"|"known_repair"|
  "assistance_eligible"|"unmanaged_legacy"|"ambiguous_recipe"|"invalid",
  observation_digest,recipe_id:null|id,reason_code:null|id}`.
- `Catalogue`: `{format_version, catalogue_id, seed_artifact_digest,
  recipes:Recipe[<=128]}`. `Recipe` is `{recipe_id, source_adapter_digest,
  schema_fingerprint, target_artifact_digest, check_ids:id[1..16]}`. Matching is
  exact; zero is `no_recipe`, more than one is `ambiguous_recipe`.
- `Plan`: `{format_version, kind:"reviewed_recipe", input_fingerprint,
  source_adapter_digest, catalogue_digest, policy_digest, recipe_id,
  target_artifact_digest, check_ids, prior_selection_digest:null|digest,
  activation:"explicit_apply"|"opted_in_known_auto"}`. It contains no time, run
  ID, path, or command.
- `Selection`: `{format_version, generation:int, artifact_digest,
  source:"bundled"|"managed", recipe_id, activated_plan_digest}`.
- `Journal`: `{format_version, operation_id, plan_digest, phase,
  prior_selection:null|Selection, target_selection:Selection,
  started_at:string<=64, updated_at:string<=64, failure:null|string<=512}`.
- `ExecutionResult`: `{format_version,status:"staged"|"active"|"no_op"|
  "rolled_back"|"rolled_back_incompatible"|"recovered"|"stale_plan"|"storage_changing"|"busy"|
  "invalid"|"failed",operation_id:null|id,plan_digest:null|digest,prior_selection:null|Selection,
  current_selection:null|Selection,executed_check_ids:id[<=16],reason_code:null|id}`.
- `ModelPolicy` (implemented C-only v1 contract; exact fields/values in
  [budget fixtures](../src/session_recall/codex_fix/tests/_c_budget_fixtures.py)):
  selected transport/model/effort above, initial token allowance32000,
  input/generated estimates16000 each (reasoning allowance included), reserve margin4000,
  grant increment32000, daily ceiling64000, one request per allowance grant,
  zero automatic retries, timeout300 seconds, background:false, auto_activate:false.
  This supersedes the unimplemented one-request/zero-continuation C proposal;
  existing B v1 contracts and fixed Candidate I/O must not change silently.
- `IncidentLedger` / `DailyLedger` / `BudgetGrant` (implemented C-only contracts): controller-owned
  monotonic incident usage/reservations/revision, daily usage, checkpoint and
  input/policy bindings; a grant names its single-use ID, +32000, cumulative
  ceiling and any explicit daily override. Model output cannot create a grant.
  Estimated request reservation, truthful usage normalization and atomic crash recovery are
  required; pending or unknown usage cannot be silently released. Details follow
  the plan's budget-block section. Production human/transport provenance remains
  a separate gate; JSON validity alone supplies no such authority.
- `RuntimeConfig`: `{format_version, transport_id:"disabled"|"codex-runner-v1",
  executable:null|absolute-path<=4096, billing_context_label:null|string<=128}`;
  missing or disabled config is unavailable.
- `ActivationPolicy`: `{format_version, known_recipe_mode:"explicit"|"auto_opt_in", startup_trigger:"none", allow_downloads:false}`; default explicit.
- `CandidateInput`: `{format_version,incident_id,input_fingerprint,base_artifact_digest,
  catalogue_digest,policy_digest,acceptance_contract_digest,allowed_paths:path[1..32],
  schema_diff:{differences:string[1..256]},
  source_files:Source[1..32]}`; each source is `{path, sha256, content}` with relative normalized paths, no `..`, content <=256 KiB, and total <=1 MiB.
- `Candidate`: `{format_version, input_digest, base_artifact_digest,
  files:Source[1..32]}`. It cannot contain approval, test, model, or activation
  claims; paths and all digests are recomputed before any execution.
- `IndependentResult`: `{format_version, candidate_digest, input_fingerprint,
  policy_digest, acceptance_contract_digest, check_ids, verdict:
  "pass"|"fail"|"infrastructure", transport_evidence_digest}`.
- `Approval`: `{format_version, candidate_digest, input_fingerprint,
  policy_digest, independent_result_digest, decision:"approved",
  actor_label:string<=128, approved_at:string<=64}`. Any bound digest change
  invalidates it.

Controller checks are fixed API IDs, not recipe shell: `artifact_manifest_v1`,
`synthetic_schema_v1`, `trial_cli_contract_v1`, `unknown_drift_rejected_v1`, and
`synthetic_no_write_v1`. Apply re-captures metadata immediately before selection,
runs every named check, commits selection, then runs schema check through the new
artifact. A failed postcheck restores the prior selector under the same lock.

Required recipe `codex-state52-artifact-to-state55-v1` binds the reproducible
profile-52 artifact, reviewed state55/history6 fingerprint, profile-55 seed, and
all checks. Synthetic managed source52 must select target55 with zero model calls;
legacy installs never impersonate that digest.

Internal `Context` is `{paths,managed_root,catalogue,catalogue_digest,policy,
policy_digest,check_registry,recapture,test_hooks,adapter_identity,current_observation}`.
It is a dataclass; `paths` maps `state_db`, `history_db`, `sessions_root`, and
`current_selection` to `pathlib.Path` values. Production derives current_selection
under managed_root; it is not a freely supplied CLI path. `current_observation`
defaults to null and is set explicitly with the validated Observation before plan.
`recapture()->SchemaSnapshot`
opens fresh read-only connections. Production checks are a sealed mapping from the
five IDs to callbacks; tests inject callbacks over synthetic roots. Production has
no `test_hooks`.

APIs: `inspect((state_conn,history_conn))->SchemaSnapshot`, `observe(snapshot,context)->Observation`,
`classify(observation,context)->Classification`, `plan(classification,context)->Plan`,
`apply(plan,context)->ExecutionResult`, `rollback(operation_id,context)->ExecutionResult`,
`launch(argv,context)->NoReturn|int`. First four are read-only. Apply/rollback lock,
call `recover_pending(context)` first, recapture before selection, and may return
`recovered` after reconciling the requested operation from durable state.

Core contracts API: `parse(text, kind)` validates decoded JSON, `validate(value,
kind)` returns the validated value, `canonical_bytes(value)` returns sorted compact
UTF-8 JSON with `ensure_ascii=False` and no Unicode normalization, and `digest(value)`
returns the prefixed SHA256. Kinds use exact envelope names. Violations raise
`ContractError(code=...)`; changing metadata raises `StorageChangingError` with
code `storage_changing`. `classify` returns refusal statuses without side effects;
`plan` raises ContractError codes `no_recipe`, `ambiguous_recipe`, or
`unmanaged_legacy` for those classifications. `reason_code` equals the corresponding
refusal code; successful classifications use null. Missing/invalid identity is
`invalid`, never assistance-eligible.

Digest projections are exact: schema_fingerprint hashes
`{storage_family,state,history}`; input_fingerprint hashes
`{schema_fingerprint,adapter,catalogue_digest,policy_digest}`. For the standard
files, storage_family is `codex-state-v5-history-v1`. Classification's
observation_digest equals input_fingerprint, the semantic observation identity;
diagnostics never enter it. Plan verifies context.current_observation has that
identity before constructing the manifest. No digest contains itself.

## Commands, statuses, and exits

Every JSON response has exactly `{format_version, command, ok, status, detail}`;
`detail` is null or one validated envelope above, <=256 KiB. Statuses are `supported`,
`known_repair`, `assistance_eligible`, `unmanaged_legacy`, `ambiguous_recipe`,
`invalid`, `planned`, `staged`, `active`, `no_op`, `awaiting_review`, `approved`,
`rejected`, `failed`, `rolled_back`, `rolled_back_incompatible`, `recovered`,
`stale_plan`, `busy`, `storage_changing`, `transport_unavailable`, `sandbox_unavailable`.

Exit 0 means the requested operation completed, including diagnostic `check` and
an honest incompatible rollback. Exit 2 means invalid/refused/stale/ambiguous
contract or policy; 3 means busy/changing transient state; 4 means missing or
unreadable required storage; 5 means verification/candidate failure; 6 means
transport or sandbox capability unavailable; 130 means interrupted. `plan` with
no recipe exits 2 and status `assistance_eligible`; no code path silently calls a
model. CLI argument errors also exit 2 before storage access.

`cli.main(argv,*,context_factory=production_context)` provides `check`, `plan`,
`apply --plan FILE`, and `rollback --repair OPERATION_ID`; commands accept `--json`,
`--root`, `--state-db`, `--history-db`, `--sessions-root`, and `--config`. Arguments
override config. Config selects local paths/policy but never transport/billing
implicitly. Plain `check` and every `plan` are read-only. `check --auto` may apply
only when persisted policy is already `auto_opt_in`; otherwise it returns `invalid`
without writing policy or managed state.

B factory configuration is a separate `ControllerConfig` JSON object with exactly
`{format_version:1,root:null|string,state_db:null|string,history_db:null|string,
sessions_root:null|string,activation_policy:ActivationPolicy}`. Paths are bounded
to 4096 UTF-8 bytes and explicit CLI paths override non-null config paths. There
is no catalogue, check-callback, test-hook, approval, or transport field in it.
Absent config uses explicit/local ActivationPolicy. `production_context(args)`
loads only the bundled catalogue via `trust.load_catalogue()`, which recomputes
its canonical digest against compiled `TRUSTED_CATALOGUE_SHA256`; a supplied
catalogue and its matching self-digest are never a trust source. Production
contexts are lazy about live metadata: `recapture` opens the configured read-only
pair when the requested operation needs it, so a corrupt active adapter cannot
prevent constructing a rollback context. No active adapter module is imported.

Crash tests inject `TestHooks.on_phase(phase)` plus a barrier through `Context`;
apply invokes it only after a durable phase write and before the next effect. No
CLI flag, environment variable, config key, catalogue field, or production factory
can enable test hooks.

Store test/implementation contract: `operation_id` is the 64-hex portion of
`digest(plan)`; its record is `journal/<operation_id>.json`. Cached artifacts live
at `artifacts/sha256/<64hex>/adapter.pyz`; a production resolver may also use the
digest-pinned bundled seed. Fixed checks have signature `(artifact_path, context)
and must return true; false/exception fails without activating. Actual postcheck
invokes the selected artifact's `schema-check --json` with the configured storage
paths and an isolated Python environment; test callbacks cannot replace it.

`recover_pending(context)` returns null if no pending record exists. For a crash
before selection commit with the prior selection still active, it records a
rollback and returns `recovered` / `rolled_back_before_commit`. After commit,
it verifies the target and postcheck, then returns `recovered` /
`completed_after_commit`; a failing target restores the prior selection instead.
Recovery never trusts the recorded phase over actual selection/artifact bytes.
Reapply of the same plan returns `no_op` only after metadata, catalogue/policy,
target digest, and activated-plan identity still match. Explicit rollback of a
completed operation verifies/restores the prior artifact, then reports
`rolled_back_incompatible` when that adapter rejects the current schema.

Reapply must also work through a fresh companion process: the active adapter
identity then names the target, not the original source. Authenticate the saved
plan against the selected activated-plan digest, exact trusted recipe and fresh
metadata before reporting `no_op`; do not require the old in-memory observation.
Recapture again after all fixed checks and immediately before selection commit.
A changed/unavailable witness at that point is `storage_changing` (exit 3), with
no selection commit. A null-prior recovery record cannot claim restoration when
the failing target is still selected; report `failed` / `recovery_unavailable`.

Candidate states are `generated`, `testing`, `awaiting_review`, `approved`,
`staged`, `active`, `rejected`, `failed`, and `rolled_back`. Passing checks only
reaches `awaiting_review`; only the digest-bound approval plus explicit `apply`
can reach `active`.

## C transport and sandbox gates

Installed-runtime review (2026-09-20): Codex0.155.1 exec help and generated
app-server schemas provide model/effort configuration, fallback control and
usage/goal telemetry, but no verified per-request generated-token ceiling.
Goal tokenBudget is not evidence of an in-flight hard cap. The user's subsequent
rough-estimate decision removes an exact-cap prerequisite: use approximate
reservations, available telemetry and human checkpoints, report any in-flight
overshoot and stop before further spending. V5 also removes positive per-turn
attestation and hidden-provider-retry-proof requirements. Use Codex's explicit
GPT-6/medium configuration, no controller retries or alternate provider, and
account for reported/estimated usage. Do not infer that service internals are
independently attested. Remaining work is runner integration and safe candidate
validation, not another model-policy decision.

### First C implementation unit: pure budget transitions

Use separate `c_contracts.py` and `budget.py`; do not modify the accepted B
contract registry. Exact six-envelope examples will be frozen in C test fixtures
before implementation: ModelPolicy, IncidentLedger, DailyLedger, BudgetGrant,
RequestReservation and UsageEvidence. Every transition returns new values,
preserving its inputs and validating all ledger arithmetic/bindings.

APIs: `validate_c(value, kind)`, `new_incident(controller_id, incident_id,
input_digest, policy, *, utc_day)`, `consume_grant(incident,daily,grant)` returning
the updated incident/daily pair; `reserve_request(incident,daily)` returning that
pair plus a reservation; `normalize_usage(evidence)`; and
`settle_request(incident,daily,reservation,evidence)` returning the updated pair.
`should_pause(incident, *, observed_total_tokens, next_request_tokens=0)` is a
pure boundary decision, not a claim of live telemetry. Record created_utc_day
on incidents and utc_day on reservations; accounting for a request remains on
its reservation day even when completion happens after midnight.

Initial requests reserve an estimated32000 before dispatch; usage includes input/generated
totals once, with cached/reasoning values checked only as subsets. Grants bind
controller/incident/input/policy/current revision/checkpoint/daily digest and
raise allowance by32000 plus one request. Explicit daily overrides return an
updated DailyLedger. A grant for stale state is unusable. Unknown final usage
retains the reservation, rather than granting a free retry. Actual usage may
exceed the reservation: charge the full amount and pause instead of rejecting
the evidence or hiding the excess. ModelPolicy uses input_estimate_tokens and
generation_estimate_tokens, with estimated_with_actual_reconciliation_v1
accounting; these must not be described as enforced output caps.
RequestReservation names its estimate estimated_reserved_tokens; IncidentLedger
tracks usage_status (none/estimated/actual). UsageEvidence records usage_basis
(actual/estimated), never a model-authored trust flag. A usable final controller
estimate can settle as estimated; missing/nonfinal evidence retains the hold in
awaiting_usage, preventing automatic retries. Later actual reconciliation must
be bound to the same request and charge only the difference.

This first unit does not persist state, authenticate human/transport provenance,
or dispatch a model. Its caller is the trusted controller. Serialized JSON cannot
prove human approval or trusted usage by itself. Durable locking/atomic recovery,
the trusted approval channel and recording transport are subsequent units with
their own frozen tests. Passing pure tests is not Stage C acceptance.

OS capability review: nested `sandbox-exec` is refused by the restricted session
(exit 71); the approved no-op `/usr/bin/true` probe outside that restriction exits
0. This proves the binary can install a basic policy, not that a candidate
sandbox denies every required file, credential, network and recursion access.
No candidate execution backend or denial-test suite has been implemented.

Capability review (2026-09-20): installed Codex0.155.1 help and
[official non-interactive guidance](https://learn.chatgpt.com/docs/non-interactive-mode)
confirm model/config flags, `--output-schema`, JSONL output, and controls for
ignoring user configuration. V5 uses this simple invocation/output path and
does not require an independent per-turn identity guarantee. No live generation
has been run by this implementation work.

`Transport.generate(input, policy) -> (Candidate, trusted evidence)` receives a
fully validated policy. V5 implements this as one thin Codex CLI wrapper, not a
pluggable transport framework. Tests capture exact model/effort arguments and
request count. Use a fixed executable, controlled environment, isolated cwd and
no shell interpolation. Invocation/configuration errors return an unavailable
or failed result; missing per-turn model metadata alone does not. Never switch
to an API, another account or model.

Candidate execution additionally requires a verified OS sandbox denying network,
live Codex paths, home/credentials, controller state, recursion, and writes beyond
the workspace. A directory and environment variables are not a sandbox. With no
backend, generation may end at `generated`, but testing/approval/activation return
`sandbox_unavailable`; Stage C must remain incomplete.

### Second C unit: durable budget store

After C1 passes, implement `BudgetStore(managed_root,controller_id,policy,
*,clock,approval_source=None,test_hooks=None)` in new C-only modules. Clock exposes
`now_utc()`; approval source exposes `source_id` and `resolve(challenge)`. A verified
human event includes event_id, actor_label, approved_at, decision and the exact
challenge_digest. No method accepts a model-authored approval/grant JSON file.
The trusted source boundary must be independently reviewed before production use.

Methods: `initialize()`, `read()`, `create_incident(incident_id,input_digest,
*,expected_revision)`, `checkpoint_for_approval(incident_id,*,expected_revision,
daily_ceiling_override_tokens=None)`, `apply_verified_approval(challenge_id,
*,expected_revision)`, `reserve_request(incident_id,*,expected_revision)`, and
`settle_request(reservation_id,evidence,*,expected_revision)`. Checkpoint returns
the durable challenge; reserve returns its reservation only after commit; other
methods return the controller record. No generic transaction callback.

One private file `budget-v1/controller-ledger.json` holds controller_id,
policy_digest, revision, initialized_at, updated_at and sorted unique arrays of
incidents, days, grants and reservations, plus format_version1. Limits are32
incidents/8UTCdays/256grantrecords/256reservationrecords and1MiB decoded bytes.
Keep C1 nested envelopes unchanged. Grant records retain pending/consumed
challenge bindings and the source/event/actor evidence after consumption;
reservation records retain held/settled_estimated/settled_actual status and
evidence digests/token charges needed for idempotent later reconciliation.
Exact C2 record keys are frozen in its independent fixtures before implementation.

Review refinement: grant records also permit `invalidated`, retaining their
challenge and no consumed approval proof. Live pending questions must match the
current incident and bound daily ledger, at most one per incident. A mutation
that changes either binding must atomically retire affected pending questions,
including questions for other incidents sharing that day. Later actual usage
may invalidate a question; this must not block valid reconciliation or a fresh
question. An old-day approval cannot be consumed on a new UTC day; checkpointing
must retire the expired question and create a new one without a deadlock.
Validate each day's ceiling against consumed explicit overrides only, consumed
incident grants in exact32K steps, deterministic reservation IDs, and aggregate
usage uncertainty against all settlement records on every reopen.

Headroom refinement for rough-estimate overshoot: a ready incident may have an
unused request credit but insufficient tokens for the next estimated32K. In that
case checkpointing may atomically move it to awaiting_budget_approval without
creating a request/reservation or consuming the credit. The C1 awaiting-state
validator therefore permits requests_started <= requests_allowed, still with no
hold. Adequately funded ready incidents cannot pre-stack approvals. Example:
actual35K, approval raises ceiling to64K (only29K remains), another explicit32K
approval raises it to96K, then an explicit reservation may proceed. No automatic
retry or fabricated request count is allowed.

One nonblocking `locks/budget.lock` serializes mutations. Each mutation rereads
and validates the full record, checks expected revision, changes it once, and
atomically fsyncs/replaces the entire file; no partially updated incident/day
pair. Initialize explicitly with a private staged directory and atomic publish.
Existing missing/corrupt/unsafe/over-capacity state never triggers reinitialization
or automatic history pruning. Reject symlink ancestry and unsafe permissions.
Internal-only TestHooks.on_phase(before_replace/after_replace) enable real
process-crash tests, not CLI/config/environment overrides.

Permit at most one unresolved reservation controller-wide. Silence/denial leaves
the already-persisted challenge and ledger unchanged. Resolve a human event
outside the lock, then recheck revision/challenge under lock before consuming it
once. Unknown usage stays held. Final estimate can settle; later actual replaces
only that request's estimated charge by delta (positive or negative) on its
reservation UTC day. Exact evidence replay is a byte/revision no-op; conflicting
actual evidence fails. Track full actual overshoot and uncertainty without
truncation; only reconciliation of all estimated charges may label the aggregate
actual. Spending approval never authorizes candidate approval/activation.

## Build units and gates

1. **Contracts/diagnosis worker:** `session_recall/codex_metadata.py`,
   `codex_fix/{contracts,storage,engine,cli}.py`, catalogue, and tests. Gate: exact
   routing, stable dual capture, zero transport calls.
2. **Artifact/activation worker:** `codex_fix/{store,launcher}.py`, zipapp builder,
   packaging entries/data, and matching tests. It starts after contract APIs freeze.
   Gate: digest/path rejection, concurrent lock, every crash boundary, broken
   adapter rollback, editable-install refusal, and cumulative Stage A+B verifier.
3. **Candidate worker:** `codex_fix/{policy,transport,candidate,sandbox,approval}.py`
   and fake-only tests. It starts only after B passes. Gate: strict envelopes,
   exact model/effort/request evidence, sandbox denial, approval invalidation, and
   zero activation without approval.

The integration owner owns the journal, shared verifier, catalogue review, and
packaging integration; workers do not overlap files. Ready now: B contracts,
synthetic planner/store/launcher tests, and fake-only C contracts. Blocked:
live assistance until the single Codex runner and approximate accounting are
integrated and tested; candidate
execution and Stage C completion until an OS sandbox passes denial probes.
