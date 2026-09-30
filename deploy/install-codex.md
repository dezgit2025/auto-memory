---
requires-user-confirmation: true
mutates-agent-instructions: true
tool: session-recall-codex
version: v0.6.0
---

# Deploy session-recall-codex (OpenAI Codex CLI)

> [!IMPORTANT]
> **Codex 0.157 / state 57 + history 7:** a fresh install from the current
> `main` branch bundles the verified adapter. The immutable `v0.6.0` tag
> used in the older release commands below bundles 55/6 and fails its
> schema check on Codex 0.157. Until a new release is tagged, install
> `auto-memory @ git+https://github.com/dezgit2025/auto-memory.git@main`
> with the same pipx/Python setup shown below, then run
> `session-recall-codex schema-check`. Existing managed selections remain
> pinned and need a separate reviewed upgrade.

**Humans:** skim the overview, then run the snippets — or ask your AI agent to do it.
**Updated: 2026-09-20 — auto-memory 0.6.0.**

**Agents:** read sections 1–8 in order. Obtain authorization before installing
packages or changing user configuration; existing explicit authorization applies.

```bash
brew install pipx python@3.14
pipx install --python "$(brew --prefix python@3.14)/bin/python3.14" \
  "auto-memory @ git+https://github.com/dezgit2025/auto-memory.git@v0.6.0"
session-recall-codex --version
session-recall-codex-fix --version
session-recall-codex schema-check
```

This is the recommended macOS installation, selecting the Homebrew Python 3.14
build verified by the sandbox tests on Apple silicon. A generic `--python 3.14`
can select a different build; Intel Homebrew dependency paths are not supported
by the current AI sandbox allowlist. For Linux/WSL recall or a manual-venv
alternative, see [the shared install guide](install.md). One pipx environment
also supplies the Copilot and Claude commands. Do not reinstall for each backend.
If PATH setup is needed, run `pipx ensurepath` and restart your terminal.
Our default is pipx recommended, uv alternative, and pip only inside a venv.
The shared guide provides the equivalent uv command with the same interpreter.

> [!NOTE]
> **Release availability:** install 0.6.0 from this GitHub repository. A repository
> push does not upload the package to PyPI, so `pip install auto-memory` may
> install an older release. A fresh installation reports `0.6.0`.
>
> **Recall scope:** `schema-check`, `list`, and `repos` are available. Codex
> `search`, `show`, `files`, and `health` are not yet implemented. The separate
> `session-recall-codex-fix` companion provides reviewed repairs and experimental
> AI assistance; the live AI path has not yet passed a successful live smoke.

---

## Section 1 — Overview

`session-recall-codex` reads Codex CLI's local SQLite storage (`~/.codex/state_5.sqlite` + `~/.codex/thread_history_1.sqlite`) and provides structured session recall for AI coding agents.

- **Read-only storage** — opens both databases with `mode=ro` + `PRAGMA query_only`; repairs update the recall reader and never modify Codex databases. Optional instruction-file setup is a separate configuration change.
- **No env gate** — invoking the dedicated binary is the opt-in. Installing auto-memory never changes Copilot CLI or Claude Code behavior
- **Fixed-schema pre-flight** — every data command validates both databases against captured schema profiles *before* querying. If Codex ships a new storage version, the CLI refuses cleanly (exit 2/4) instead of guessing
- **Structured output** — `--json` on every command, ~50 tokens per query

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | success (a valid empty result is still 0) |
| 1 | session not found |
| 2 | usage error / schema drift / ambiguous id |
| 3 | SQLite busy or read failure after bounded retries |
| 4 | Codex database not found (not installed, or storage version changed) |

---

## Section 2 — Prerequisites

- Python 3.10+, Git, and an existing Codex session store.
- A POSIX environment for the Codex launcher/controller (macOS or Linux/WSL).
- For AI-assisted repair: macOS with working `sandbox-exec` and runtime library
  inspection via `otool`, an installed Codex CLI, and an existing login with
  access to `gpt-6-astra`. Linux/WSL cannot run the current AI sandbox backend.
- A terminal that can create the OS sandbox. Restricted parent sandboxes can
  prevent this and return `sandbox_unavailable`; the tool does not bypass it.

```bash
python3 --version                # must be 3.10+
test -f "$HOME/.codex/state_5.sqlite" && echo "codex store: detected" || echo "codex store: not found"
```

> [!IMPORTANT]
> Codex CLI must have been used at least once so `~/.codex/state_5.sqlite` exists. If the file is missing but other `state_*.sqlite` files exist, Codex changed its storage version — `session-recall-codex` will report `storage_version_changed` (exit 4) and must be updated before use.

---

## Section 3 — Install

Use the pipx installation above. To replace an existing pipx-managed version or
switch its interpreter, repeat the command with `--force`:

```bash
pipx install --force --python "$(brew --prefix python@3.14)/bin/python3.14" \
  "auto-memory @ git+https://github.com/dezgit2025/auto-memory.git@v0.6.0"
# From an existing clone, inside your virtual environment:
# python3 -m pip install --upgrade .
```

Choose one installation method. Both Codex commands ship with the base package;
no optional extra or backend environment gate is required. Adding the chosen
environment's bin directory to PATH is separate from enabling a backend.
`install.sh` remains available for editable contributor installs; the commands
above install a normal package.

---

## Section 4 — Verify

```bash
command -v session-recall-codex
session-recall-codex --version
session-recall-codex-fix --version
session-recall-codex-fix --help
session-recall-codex schema-check
```

| Result | Meaning |
|--------|---------|
| `ok: schema matches fixed profiles (...)` exit 0 | Done — safe to query |
| exit 4, `storage_missing` | Codex not installed / never run |
| exit 4, `storage_version_changed` | Codex upgraded its storage — update auto-memory before use |
| exit 2, schema drift report | Stop recall; use an explicitly authorized repair or install a reviewed update |

The current source revision supports state migration 55 and thread-history
migration 6. A previously installed distribution may have an older profile;
check the actual command above after installation. Do not merely increase a
migration number or disable validation: new column definitions must be reviewed
and the updated adapter must pass its synthetic tests and installed-CLI checks.

Existing managed selections stay pinned after a package upgrade. An adapter
that still reports `0.5.1` can be upgraded through the reviewed `check` → `plan`
→ `apply` path below. Old artifacts remain available for rollback; do not remove
the managed state directory to force an upgrade.

For maintainers, the trial smoke gate is
`bash src/session_recall/providers/codex/verifications/smoke.sh --trial`.
The default full-port smoke suite retains checks for commands that have not yet
shipped in the trial CLI.

Then confirm real data comes back:

```bash
session-recall-codex list --json --limit 3
session-recall-codex repos
```

---

## Section 5 — Wire into Codex (Global, recommended)

Codex reads `~/.codex/AGENTS.md` at the start of **every** session, and only Codex reads it — so a block there fires only when Codex is the invoker, with zero detection logic.

> **Agent:** show the block and ask *"Append the session-recall-codex block to ~/.codex/AGENTS.md? (Y/n)"* — `AGENTS.md` is user-owned configuration; never edit it silently.

### 5a — Detect state

```bash
AGENT_FILE="$HOME/.codex/AGENTS.md"
if grep -q '<!-- session-recall-codex:v1 START -->' "$AGENT_FILE" 2>/dev/null; then
  echo "current"   # idempotent — skip to Section 6
elif grep -q 'session-recall-codex' "$AGENT_FILE" 2>/dev/null; then
  echo "stale"     # remove the old block, then append fresh
else
  echo "missing"   # append → 5b
fi
```

### 5b — Append (state = missing)

Append the **global block** from [`codex-instructions-template.md`](../codex-instructions-template.md) (the section marked "put this in `~/.codex/AGENTS.md`") between its `<!-- session-recall-codex:v1 START -->` / `END -->` markers.

### 5c — Uninstall the block

Delete everything between (and including) the START/END markers.

---

## Section 6 — Per-Repo Wiring (Optional)

A repo-level `AGENTS.md` may be read by several agents (Codex, Copilot CLI, and others honor it). Use the **repo block** from the template — it self-routes by agent identity so Codex runs `session-recall-codex` while Copilot CLI runs `session-recall`. Never place a block in a shared file that names a single CLI unconditionally.

---

## Section 7 — Smoke Test (Optional, recommended)

From a clone of this repository, maintainers can run synthetic verification:

```bash
python3 -m pip install -e '.[dev]' 'setuptools>=68' wheel
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 verify/fix-cli-codex.py --through C --level L2
```

Run in a development virtual environment on macOS. This checks synthetic stores,
real sandbox denial rules, installed-wheel behavior and rollback without a live
model request. Sources and fixtures are under `verify/`; the untracked local
`codex-test/` workspace is not required by public users.

---

## Section 8 — Safety & Troubleshooting

- **Never modify Codex storage.** Do not edit, migrate or downgrade its databases. Optional AGENTS.md setup changes only user instructions with authorization.
- **Schema drift (exit 2):** report it and continue without recall. An explicitly authorized repair uses the companion below; never bypass pre-flight or query the database directly.
- **Missing/versioned storage (exit 4):** report the storage problem; AI repair is not used for it.
- **Locked database (exit 3):** Codex was writing at that moment; retry later.
- **Command not found:** ensure your pip/uv tool bin dir (e.g. `~/.local/bin`) is on `PATH`.

## Reviewed-recipe maintenance (separate, explicit workflow)

The 0.6.0 package includes `session-recall-codex-fix` and a stable adapter
launcher. Existing installations need the GitHub upgrade above to obtain the
new entry points; editing a checkout does not replace installed scripts.
This maintenance workflow is not permission for an agent to ignore the normal
session-start no-repair instruction.

After explicit maintenance authorization, the companion supports:

The exit-code table above describes the recall CLI. The companion can also
return exit 2 with `status: action_needed` when human review or a budget grant
is pending; inspect the JSON `status` and `detail` before treating it as a failure.

```bash
session-recall-codex-fix --json check
session-recall-codex-fix --json plan
session-recall-codex-fix --json apply --plan reviewed-plan.json
session-recall-codex-fix --json rollback --repair OPERATION_ID
```

`--json plan` emits an envelope; `reviewed-plan.json` must contain its `detail`
Plan object, not the whole response. A supported adapter needs no plan. Only an
exact reviewed recipe can be applied; legacy/unmanaged installations are not
silently adopted. The initial recipe upgrades a managed profile-52 artifact to
the reviewed profile-55 artifact. A fresh package already bundles profile 55.

The default policy requires explicit `apply`. `check --auto` is refused unless
an explicitly supplied controller configuration already selects `auto_opt_in`;
the command never writes that opt-in itself. There are no downloads, background
startup changes, model calls or Codex-store writes in this deterministic path. Managed state holds adapter
artifacts, selection and recovery journals, not session data.

Unknown readable schemas can use the explicit foreground AI maintenance command:

```bash
session-recall-codex-fix --json assist
session-recall-codex-fix --json approve --candidate CANDIDATE_ID --yes
session-recall-codex-fix --json apply-candidate --candidate CANDIDATE_ID
session-recall-codex-fix --json rollback --repair OPERATION_ID
```

`assist` uses one installed Codex CLI job, the existing login, and
`gpt-6-astra` with medium reasoning. It has no alternate provider/model or automatic
retry. Supported stores and known recipes do not start AI work. The job has tools
disabled and receives schema metadata plus allowlisted adapter source, never
session rows. Review the returned diff, test evidence, and prior artifact before
approving. Without `--yes`, terminal approval asks for confirmation; nonterminal
commands return `action_needed`. Approval and activation are separate actions.

Candidates run under a verified macOS SBPL sandbox with synthetic stores, denied
network/credential/controller access, bounded output and process timeouts. Other
platforms or a parent sandbox that prevents installing SBPL fail closed with
`sandbox_unavailable`. Tests passing only saves an immutable review record. A
human approval is required to add a local recipe to the effective catalogue;
activation and rollback use the existing transaction and fresh launcher checks.

The budget starts at approximately 32K tokens, with a 28K checkpoint marker in
the reservation. Another request requires the
explicit challenge emitted by a later `assist` invocation:

```bash
session-recall-codex-fix --json budget-approve --challenge CHALLENGE_ID --yes
```

The challenge names the additional32K allowance and any daily-ceiling increase.
Approving it never starts a request; invoke `assist` again deliberately. Usage
reports are recorded when available, otherwise labeled estimates are charged.
These estimates are not guaranteed token or billing caps. Legacy v1 receipts stay
readable and can settle outstanding requests; new v2 spending is conservatively
blocked while legacy holds or current-UTC-day charges remain. After settlement
and day rollover, v2 can proceed without discarding old history.

Offline acceptance uses the standalone `verify/codex_assist_verify.py --level L2`
and cumulative `verify/fix-cli-codex.py --through C --level L2` gates. See the
[execution journal](../plans/progress-fix-cli-codex.md) for the exact tested state,
live smoke outcome, and limitations. These commands do not authorize a global
reinstall, startup automation, or real candidate activation.

Current live verification: one synthetic attempt failed safely without usage
telemetry. Its conservative 32K estimate is retained. The strict output-schema
compatibility correction is offline-tested; successful live generation still
needs a separately approved retry. This work has not globally installed a release.
