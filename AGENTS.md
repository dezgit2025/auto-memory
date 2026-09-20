# Project planning and recovery

## Default Python CLI installation guidance

For future work in this repository, present installation methods in this order:

```bash
pipx install my-tool      # recommended: isolated CLI environment
uv tool install my-tool   # alternative: isolated tool environment
python -m pip install my-tool  # only inside an explicitly activated venv
```

Use the actual package name and a released version/source in user-facing docs.
Choose the interpreter explicitly when compatibility requires it. For the
current Codex AI sandbox, use the tested Apple silicon Homebrew Python 3.14
path; generic version selection is not proof of a supported Python build.
Install auto-memory once for all backends, retaining backend-specific setup.
Do not suggest system/global pip installs or silently switch an existing
installation between managers. Keep README and backend guides consistent.

## Planning records

- Future direction: [ROADMAP.md](ROADMAP.md).
- Codex CLI repair plan: [plans/fix-cli-codex.md](plans/fix-cli-codex.md).
- Its execution journal: [plans/progress-fix-cli-codex.md](plans/progress-fix-cli-codex.md).
- Fixer architecture: [plans/fix-cli-codex-architecture.md](plans/fix-cli-codex-architecture.md).
- Approved README diagram and version history: [codex-schema-repair-flow.md](codex-schema-repair-flow.md).

The 2026-09-20 repository release follow-up authorizes preparing version 0.6.0,
committing the reviewed Codex repairs and documentation, and pushing normally to
the existing main repository. It does not authorize PyPI upload, a new live AI
request, global installation or real candidate activation. The active plan and
journal record release gates and the separate live-validation limitation.

Execution of the repair plan was requested on 2026-09-20 UTC, using multiple
`gpt-5.6-sol` sub-agents. Read the plan and its journal before resuming; gate
completion and unresolved access/policy decisions are recorded there. The integration owner maintains timestamped
before/after checkpoints and append-only activity history. Delegate bounded
implementation, review, and verification work according to the session's agent
routing instructions, honoring the user's explicit model selection.

Preserve existing user edits. Keep secrets, session content, raw logs, and local
runtime state out of planning records. The named plan, journal, and architecture
document are allowlisted for Git; historical local planning documents remain ignored.

For session recall, run `session-recall-codex schema-check`, then
`session-recall-codex list --json --limit 5`. On schema drift or missing/versioned
storage, report the failure and continue without recall. Do not bypass the
adapter or directly read Codex-owned SQLite databases. Maintenance schema capture
requires explicit authorization for that exception. Never modify Codex-owned
storage.

## Launch records

Entry: [launch/README.md](launch/README.md). Plan: [launch/launch-plan.md](launch/launch-plan.md). Journal: [launch/progress-launch-plan.md](launch/progress-launch-plan.md). Git-trackable checklist: [launch/tasks.md](launch/tasks.md); root TASKS.md remains local-only. Read before resuming launch/application work.
