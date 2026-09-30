# Codex schema repair: versioned README diagrams

Version 2 approved for publication on **2026-09-20**, with **auto-memory 0.6.0**.
It appears under **How it works** near the top of
[README.md](README.md#codex-schema-repair--v060-2026-09-20).

Version 1 preserves the initial draft. Version 2 leads with the problem and is
the approved README version. Implementation and live-verification status remain
in the [progress journal](plans/progress-fix-cli-codex.md).

## Version 1 — initial draft

### How it works: keeping up with Codex schema changes

Codex stores session history in a local database. When OpenAI changes its structure, the recall tool checks compatibility before reading sessions. If a repair is needed, it updates **our reader—not Codex’s database**.

```text
              Check the Codex database structure
                              |
                     Is it supported?
                      /             \
                    Yes              No
                     |                |
              Recall sessions   Stop safely and
                                report the change
                                      |
                              You start a repair
                                      |
                         Is there a reviewed fix?
                            /               \
                          Yes                No
                           |                  |
                    Use the known fix   Ask Codex to propose
                                        a reader update
                           |                  |
                           +--------+---------+
                                    |
                         Test with synthetic data
                                    |
                              Tests pass?
                             /           \
                           No             Yes
                            |              |
                     Keep the current   Review and
                     reader unchanged   explicitly apply
                                           |
                                  Select the repaired reader
                                           |
                                    Recheck compatibility
                                      /           \
                                    Pass          Fail
                                     |             |
                              Recall sessions   Roll back
```

**What stays protected:**

- Codex’s databases are never modified.
- Generated repairs are tested in an isolated sandbox before approval.
- Failed repairs leave the current reader unchanged or restore it through rollback.
- Additional AI repair attempts require explicit budget approval.

Missing or inaccessible databases are reported as storage problems; they do not trigger AI repairs.

## Version 2 — problem first

### How it works: repairing Codex schema changes

**The problem:** As Codex evolves, OpenAI may change the schema—the structure
of the local databases that store its session state and history. A tool built
for an earlier schema can stop working until its reader is updated.

**The solution:** `auto-memory` checks compatibility before reading sessions.
When it detects an unsupported change, it stops safely. You can then start a
repair: the tool uses a reviewed fix when available, or asks Codex to propose
an update to the recall reader. It tests the repair before you approve and
apply it, keeping Codex’s databases untouched.

```text
          Codex changes its session-state schema
                             |
                   Check compatibility
                             |
                  Can our reader handle it?
                     /               \
                   Yes                No
                    |                  |
             Recall sessions    Stop safely and
                                report the change
                                      |
                             You start a repair
                                      |
                           Reviewed fix available?
                             /                \
                           Yes                 No
                            |                   |
                     Use that fix      Codex proposes a
                                       reader update
                            |                   |
                            +---------+---------+
                                      |
                           Test with synthetic data
                                      |
                                 Tests pass?
                                /           \
                              No             Yes
                               |              |
                       Keep current      Human approval
                       reader unchanged  and explicit apply
                                              |
                                    Recheck repaired reader
                                       /             \
                                     Pass            Fail
                                      |               |
                               Recall sessions     Roll back
```

### Optional notes below version 2

- **Human in the loop:** repairs start explicitly. Generated fixes are tested
  in an isolated sandbox; you review and approve them before activation. Known
  fixes are already reviewed and still require explicit application by default.
- **Approximate budget:** AI repair starts with roughly 32K tokens. Each
  additional 32K block requires approval. Estimates are not hard token or cost caps.
- **Storage problems:** missing or inaccessible databases are reported without
  starting AI repair.

### Editorial decisions

- Use “may change” rather than an unsupported claim about how frequently OpenAI
  changes the schema.
- Describe both session state and history, since the adapter checks both stores.
- Describe automated repair preparation and testing with explicit human control;
  the current implementation does not start repairs or activate candidates in
  the background.
- Keep implementation acceptance and the pending live-verification follow-up in
  the journal; this diagram describes the implemented workflow.
