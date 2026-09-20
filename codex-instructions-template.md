# auto-memory — Codex Instructions Template

> **Note:** For installation, use [`deploy/install-codex.md`](deploy/install-codex.md) — it walks through install, verification, and appending these blocks with confirmation.

Two blocks, for two different files. Do not mix them up:

| Block | Put it in | Read by |
|-------|-----------|---------|
| Global block | `~/.codex/AGENTS.md` | Codex only — fires every Codex session, zero detection needed |
| Repo block | a repository's `AGENTS.md` | any agent honoring AGENTS.md — self-routes by identity |

---

## Global block — put this in `~/.codex/AGENTS.md`

```markdown
<!-- session-recall-codex:v1 START -->
## Session recall (Codex)

Before executing any other command in a new Codex session, validate the recall
adapter, then ground yourself in recent history:

    session-recall-codex schema-check

    session-recall-codex list --json --limit 5

Other commands:

    session-recall-codex repos                  # which repos have recent sessions
    session-recall-codex list --repo <label>    # sessions for one repo (exact label)
    session-recall-codex schema-check           # validate storage (run after a Codex upgrade)

Cost: ~50 tokens per query. Prefer it over blind filesystem searches.
If a command exits 2 with "schema changed" or exits 4 (storage missing /
version changed), report it and continue without recall — never try to
repair it automatically or bypass it, and never read ~/.codex/*.sqlite directly.
If the user explicitly requests repair, follow deploy/install-codex.md in the
auto-memory repository and use session-recall-codex-fix. Generated repairs
require review and explicit approval before application; storage problems
do not trigger AI repair.
(search / show / files / health arrive in a later auto-memory release.)
<!-- session-recall-codex:v1 END -->
```

---

## Repo block — put this in a repository's `AGENTS.md`

Shared file, so it self-routes by agent identity:

```markdown
<!-- session-recall-multi:v1 START -->
## Session recall (multi-agent)

Ground yourself in recent history before searching the filesystem. Pick the
command for the agent you are:

- If you are **Codex**:        session-recall-codex list --json --limit 5
- If you are **Copilot CLI**:  session-recall list --json --limit 5
- If you are **Claude Code**:  SESSION_RECALL_ENABLE_CLAUDE_BACKEND=1 session-recall-cc list --json --limit 5

All three are read-only. If your command errors, continue silently — it is
a convenience, not a blocker. Do not run another agent's variant unless
explicitly asked to check that agent's history.
<!-- session-recall-multi:v1 END -->
```
