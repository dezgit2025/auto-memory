# Roadmap

Planned work for auto-memory. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

- [ ] PyPI package publishing
- [x] CI with GitHub Actions (portable pytest/ruff matrix and macOS Codex repair verification)
- [ ] Session diffing (what changed between sessions)
- [ ] Export sessions to markdown
- [ ] Optional MCP server wrapper for IDE integration
- [ ] Richer health dimensions (token usage, context efficiency)

## Codex compatibility

| ID | Direction | Status and rationale | Dependencies / reconsideration trigger |
| --- | --- | --- | --- |
| CX-001 | Restore the trial CLI against the reviewed current Codex schema | Complete 2026-09-20 UTC: 404 tests pass, two independent A/L2 runs and live schema/list/repos pass. See [plan](plans/fix-cli-codex.md) and [journal](plans/progress-fix-cli-codex.md). | Review again on actual schema drift; preserve exact validation. |
| CX-002 | Support multiple reviewed Codex schema profiles | Deferred, uncommitted; a single exact profile deliberately refuses unknown schema changes. | Reconsider if CX-001 rollout demonstrates a need to support both older and newer stores. Preserve strict validation; do not execute as part of CX-001. |
| CX-003 | Deterministic schema fixer and startup/first-use diagnosis | Selected explicit/local implementation accepted 2026-09-20 UTC: 488 tests, self-test and two identical cumulative A+B verdicts; clean-wheel lifecycle passes. [Plan](plans/fix-cli-codex.md), [architecture](plans/fix-cli-codex-architecture.md). No startup or global installation changes. | Global rollout and startup automation remain separate authorized choices; automatic known-recipe application requires persisted opt-in. |
| CX-004 | Codex repairs unknown session-recall schema changes | Released to GitHub in 0.6.0 on 2026-09-20: one Codex CLI request, existing login, GPT-6 medium, approximate 32K grants, strict candidate validation, macOS isolation, explicit review and activation/rollback. Offline gates, public GitHub installation and hosted CI pass; live generation remains unverified. Evidence and runtime follow-up are in the [journal](plans/progress-fix-cli-codex.md). | PyPI publication, global rollout and startup automation remain separate increments after runtime acceptance. Revisit other OS backends only on concrete demand. |
