# Reddit launch drafts

Draft, not posted. Target week September 21–27, 2026.
Candidate r/codex: verify current rules, flair, self-promotion policy and showcase threads before posting. Rules have not been checked. Tailor additional community posts.

## Main Reddit post

**Title: I built an open-source session-recall tool for Codex CLI — now with compatibility checks and reviewed repairs**

I'm the maintainer of **auto-memory**. Starting a new coding session often means reconstructing what I was doing last time. My current focus is making that handoff easier for Codex CLI users.

The Codex integration reads local session metadata and returns structured results the agent can use to find recent work. You can list sessions, filter by repository, and see which repositories have recent activity.

Available today:

- `session-recall-codex list --json --limit 5` — list recent sessions.
- `session-recall-codex repos` — discover repositories with session history.
- `session-recall-codex schema-check` — check compatibility before querying.
- Optional AGENTS.md instructions so Codex checks recent history at session start.
- A repair companion for the recall adapter when Codex changes storage schema, with reviewed fixes and rollback.

Codex databases stay read-only. Repairs update auto-memory's reader.

**Current limits:** Codex search/show/files/health are not implemented. An experimental path lets Codex propose adapter repairs. Synthetic verification passes, but successful live generated repair remains unverified. That path needs a supported macOS environment and human approval before activation. Normal recall makes no model requests; optional AI repair uses your own Codex access.

The project is MIT-licensed. v0.6.0 is available from GitHub; follow the installation guide because PyPI may have an older release.

Repo: https://github.com/dezgit2025/auto-memory
Setup: https://github.com/dezgit2025/auto-memory/blob/main/deploy/install-codex.md
Release: https://github.com/dezgit2025/auto-memory/releases/tag/v0.6.0

For people working across several Codex sessions: does listing recent sessions help you resume, or is searching previous decisions the feature you need first? If you try it, your OS, Codex version and compatibility errors would help. Please don't post private session contents or database files.

## Short showcase-thread post

I'm building **auto-memory**, an MIT-licensed session-recall tool focused now on Codex CLI. It lists recent sessions/repositories, integrates through optional AGENTS.md instructions, and checks compatibility before reading local storage. Codex databases stay read-only. v0.6.0 adds reviewed adapter repairs and rollback. AI-generated repair is experimental and not verified live; Codex full-text search is future work. Feedback welcome: https://github.com/dezgit2025/auto-memory

## GitHub Discussion / development update

**Title: auto-memory v0.6.0: Codex session recall and compatibility repair**

My current focus is Codex CLI continuity. auto-memory lists recent sessions and repositories and checks storage compatibility before querying. v0.6.0 adds reviewed adapter repairs and rollback without changing Codex databases.

AI-assisted repair remains experimental: offline verification passes, but successful live generation is unverified. Codex search/show/files/health remain unimplemented. I'd welcome feedback on resuming work and reproducible compatibility reports.

[Setup](https://github.com/dezgit2025/auto-memory/blob/main/deploy/install-codex.md) · [Release](https://github.com/dezgit2025/auto-memory/releases/tag/v0.6.0)

## Suggested replies

**Does it change Codex itself?** It is an independent companion; repairs change auto-memory's reader.

**Unlimited memory?** No. Codex currently exposes session metadata through list/repos, not full-text recall or an unlimited context window.

**Is it local?** Normal recall is local. Optional AI repair sends schema metadata and allowlisted adapter source to Codex, not session rows, according to the current design.

**Cost?** MIT-licensed software. Normal recall makes no model calls; optional AI repair uses your Codex access and can consume its allowance.

## Demo before publication

Capture schema-check, list --json --limit 3, and repos with synthetic/anonymized data. Measure actual output size and time to resume. Avoid universal 50-token, 200x, or hour-per-day claims. Do not present simulated repair as a verified live success.
