# Codex session-recall repair budget

The active, packaged configuration for new Codex recall repairs is
[`src/session_recall/codex_fix/data/model-policy-v3.json`](src/session_recall/codex_fix/data/model-policy-v3.json).
This file explains that configuration; it is not a second source of settings.

| Field | Active value | Meaning |
| --- | ---: | --- |
| `initial_allowance_tokens` | 100,000 | Starting allowance for one schema-repair incident |
| `daily_ceiling_tokens` | 100,000 | Starting daily allowance for new repairs |
| `requests_per_grant` | 3 | Model requests available in each approved block |
| `grant_increment_tokens` | 100,000 | Tokens added by one later owner-approved grant |

Each model request still reserves an estimated 32,000 tokens. These allowances
control whether another request may start; they are not hard limits on a single
model response or a dollar-cost guarantee. The model is GPT-6 Astra at medium
reasoning. Candidate activation and further grants remain explicit decisions.

Policy v3 writes to its own `budget-v3` ledger. Earlier ledgers are preserved.
If an earlier policy spent tokens on the current UTC day or has unresolved usage,
the new ledger refuses to start that day; this prevents a policy change from
silently resetting the daily allowance. The next UTC day can begin under v3
after earlier usage has settled. Never edit or delete a live ledger to bypass
that check.

When revising this configuration, update the policy contract and synthetic
tests with it, then reinstall the package and verify the installed CLI. Do not
change Codex-owned session databases.
