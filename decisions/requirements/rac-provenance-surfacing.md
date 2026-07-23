---
schema_version: 1
id: RAC-KV6KFN3HPGS1
type: requirement
tags: [user-facing, provenance, git, mcp]
---
# Requirement: Provenance Surfacing

## Status

Accepted

Classification: `[user-facing]` — the agent can cite who decided and when.
Scoped to the v0.23.0 hardening release (WS5). Implemented on the existing
`provenance` object: WS5 keeps the WS11 `status` field as the present-status
signal and adds the five git-derived fields beside it (`last_committed`,
`last_author`, `first_committed`, `first_author`, `status_history`), reconciled
additively from the original `current_status` wording to stay backward-compatible
(ADR-007).

## Problem

Lore claims every decision has an accountable human author, but `get_artifact`
does not surface that accountability. Today its payload is
`{schema_version, id, type, title, path, outgoing, incoming}` — no author, no
date, no status. An agent grounding on a decision cannot cite who made it, when,
or whether it has moved from proposed to accepted to superseded. The lifecycle
`status` already exists as parsed metadata (the `## Status` section, enum per
type); the rest exists in git history. None of it is on the tool surface.

## Requirements

- [REQ-001] `get_artifact` MUST expose, additively and backward-compatibly, at minimum: author(s) plus last-commit author, relevant dates, and status history (Proposed → Accepted → Superseded), sourced from front matter plus git. It does so through the additive `provenance` object on its JSON payload; the existing top-level keys are unchanged and the `provenance` object — introduced by WS11 — gains fields, never has its existing keys reshaped or removed (ADR-007). For the present lifecycle status it reuses the field WS11 already ships on this object — `status` (string — the reviewed `## Status`, sourced from parsed front-matter-section metadata (`metadata["status"]`), not git; present-but-empty (`""`), never omitted, when the section is absent) — rather than adding a renamed or duplicate `current_status`, so the object stays backward-compatible. It then adds these git-derived fields: `last_committed` (ISO-8601 timezone-aware string, or `null` — the most recent commit time for the file, from git (ADR-045), reusing `recency.py` `_last_committed`); `last_author` (string `Name <email>`, or `null` — the author of that most recent commit, same `git log -1` record); `first_committed` / `first_author` (ISO-8601 string and `Name <email>`, or `null` — the creation commit, reusing `recency.py` `_first_committed`, the accountable original author); and `status_history` (ordered list of `{status, committed, author}` entries, or an empty list, derived from git by reading the `## Status` value at each commit that changed it; see REQ-003).
- [REQ-002] Provenance MUST be derived from git rather than stored dates in front matter (ADR-045); a `reviewers` front-matter field MAY be used to power the WS11 review signal. Concretely, provenance dates and authorship MUST be derived from git, never from stored front-matter dates (ADR-045); no front-matter field is added and `schema_version` is not bumped. Status *value* is read from parsed metadata, not git; only its *history* is reconstructed from git. The `reviewers` front-matter field is the seam the future WS11 review signal MAY use, recorded here only to reserve the name; it is not introduced this release.
- [REQ-003] `status_history` MUST be derived deterministically and offline by walking the file's git history (e.g. `git log --reverse` plus reading the `## Status` section at each revision) and emitting one entry each time the parsed status value changes, oldest first. Reuse the `recency.py`/`revisions.py` git boundary (ADR-043); WS5 MUST NOT add a third git touchpoint or import a git library (ADR-045 alternatives).
- [REQ-004] All git-sourced fields MUST degrade to `null` (or, for `status_history`, an empty list) — never raise — when git is unavailable: outside a repository, in a shallow clone where the relevant commits are absent, or for an untracked or uncommitted file. The present `status` still populates from metadata in every case, so an artifact in a non-git directory still reports its status. No exception crosses the service boundary (ADR-045).
- [REQ-005] Provenance fields SHOULD be surfaced in search/explain output where useful, but `get_artifact` is the only required surface this release.
- [REQ-006] Full PR-reviewer extraction — squash-merge attribution, review-thread mining, any GitHub PR-API plumbing — is explicitly out of scope for v0.23.0. Provenance is git-and-metadata only; no network call, no key, no fifth tool.

## Acceptance Criteria

- The `provenance` object populates for this release's dogfooded ADRs (ADR-065,
  ADR-066), including a multi-entry `status_history`.
- A test in a throwaway repository asserts each git-sourced field matches the
  known commit, and a second asserts that outside a repo (and in a shallow clone
  missing the history) every git field is `null`/empty while `current_status`
  still populates from metadata.
- The pre-WS5 `get_artifact` keys are byte-identical; a contract test asserts
  the addition is purely additive (ADR-007), consistent with the WS6 agreement
  test over the four serializers.

## Success Metrics

- An agent can cite the accountable original author and the current status of a
  decision directly from `get_artifact` output, with no AI and no network.

## Risks

- Git plumbing can balloon, and per-commit status reconstruction is O(commits
  touching the file). Mitigation: limit fields to those in REQ-001, walk history
  once per artifact through the existing boundary, and defer all PR-reviewer
  extraction (REQ-006).
- `status_history` reflects history rewriting (rebase/squash moves commit time),
  as ADR-045 already accepts for recency. Accepted: "when the status last
  changed in history" is the intent, not forensic authorship.

## Assumptions

- Git history plus parsed status metadata carry enough provenance for this
  release without any PR-API integration (roadmap WS5 assumption, ADR-045).
- The existing `recency.py`/`revisions.py` git boundary can host the
  author/history reads without a new dependency.

## Related Decisions

- adr-045
- adr-050
- adr-025

## Related Requirements

- rac-artifact-trust-model

## Related Roadmaps

- v0.23.0-hardening
