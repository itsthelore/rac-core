---
schema_version: 1
id: RAC-KV6KFK645AMN
type: requirement
tags: [user-facing, security, trust, mcp, grounding]
---
# Requirement: Trust Model and Artifact-as-Attack-Surface

## Status

Accepted

Classification: `[user-facing]` — assurance the grounding layer is not an
injection vector. Scoped to the v0.23.0 hardening release (WS11).

## Problem

A coding agent ingests artifact content as authoritative grounding. The
read-only MCP server protects the store, not the agent: a poisoned artifact or a
hostile pull request can carry text engineered to steer the consuming agent away
from recorded decisions. This was the red-team's highest-priority gap — we
assert artifacts are trustworthy without recording why, or giving a consumer any
signal to distinguish a reviewed decision from an unreviewed draft.

Concretely, the `get_artifact` serializer today emits only
`schema_version`, the index entry's `id` / `type` / `title` / `path` /
`aliases`, and the raw `content`; it carries no status or review field, so a
consumer cannot tell an `Accepted` decision from a `Proposed` draft from tool
output. This workstream owns naming the trust model and adding that one
deterministic signal.

## Requirements

- [REQ-001] The release MUST document the trust model in `SECURITY.md`: artifact content is authoritative because it passed human PR review; the read-only MCP server protects the store, not the agent; unreviewed or machine-ingested content is out of scope and MUST NOT be treated as trusted (ADR-065). `SECURITY.md` is scoped to RAC Core / the Lore read-only MCP server in this repository; it documents the trust model and the existing report channel, and MUST NOT promise a vulnerability-response SLA, a sanitizer, or any per-artifact trust verdict (ADR-034, ADR-065).
- [REQ-002] `SECURITY.md` MUST state the threat (a poisoned artifact or hostile PR can attempt to steer the consuming agent — imperative overrides, system/agent/tool impersonation, decision-steering text) and the mitigation (human PR review as the boundary, plus the `rac doctor` injection flag and the `get_artifact` review signal as aids), and MUST state plainly that PR review is the trust boundary and that neither aid is a guarantee or a gate (ADR-065).
- [REQ-003] The `rac doctor` injection-style-content check is owned by WS3 (`rac-doctor-diagnostic-validator`, REQ-004); this requirement MUST NOT re-specify or duplicate it. WS11 owns only the trust model documentation and the `get_artifact` review signal, and references the doctor flag as the authoring-time aid `SECURITY.md` points to.
- [REQ-004] `get_artifact` MUST surface a review/trust signal additively and backward-compatibly (ADR-007): a `status` string under a nested `provenance` object (the single object get_artifact's additive fields share; WS5 adds author/date/status-history there), sourced deterministically from the artifact's `## Status` section as already parsed by Core (no new front-matter field, no PR-API call), so a consumer can distinguish a reviewed-`Accepted` decision from a `Proposed`/draft artifact. The signal MUST be derived from repository bytes plus git only and MUST be byte-identical across repeated calls on an unchanged corpus (ADR-032); when the status cannot be determined the field MUST be present with an explicit empty/unknown value rather than omitted.
- [REQ-005] The review signal is a reported fact, not a verdict: `get_artifact` MUST NOT compute or return a "trustworthiness" score, a pass/fail trust judgement, or any per-artifact safety verdict (ADR-034). It surfaces status (and, where WS5 provenance lands, the author/reviewer facts) and leaves the trust judgement to the human reviewer and the consuming agent.
- [REQ-006] Nothing in this release may auto-edit, sanitize, rewrite, or filter artifact content; the trust boundary remains human PR review and the read-only surface stays byte-stable (ADR-065, ADR-032).

## Acceptance Criteria

- The trust model is documented in `SECURITY.md`, within the scope of REQ-001,
  and states plainly that PR review is the boundary and the doctor flag and
  review signal are aids, not guarantees.
- `get_artifact` exposes a `provenance.status` field (nested under `provenance`), verified by a test, as an
  additive backward-compatible field that is byte-identical across repeated
  calls on an unchanged corpus and present-but-empty when status is
  indeterminate.
- The injection-style-content flag itself is exercised by WS3's tests, not
  duplicated here; WS11's tests cover only the `SECURITY.md` claims and the
  `get_artifact` review signal.
- No code path in this release writes, rewrites, or filters artifact content;
  the MCP surface stays exactly four read-only tools with additive output only.

## Success Metrics

- A user can articulate, from the docs, exactly what the read-only guarantee
  does and does not protect.
- A consumer can tell reviewed decisions apart from drafts via the `status`
  field in `get_artifact` output.

## Non-Goals

Explicit descopes for this release, so the boundary against ADR-034 and the
sibling workstreams stays legible:

- No per-artifact trust score, safety verdict, or pass/fail trust judgement on
  any tool — the signal is reported status, not a verdict (ADR-034).
- No content sanitizer, rewrite, redaction, or filtering on the serving path;
  the read-only surface stays byte-stable (ADR-065, ADR-032).
- No fifth MCP tool, no write capability, no PR-API / review-thread plumbing
  this release; the review signal is derived from repository bytes plus git
  only.
- WS11 does not re-implement the `rac doctor` injection check (owned by WS3,
  `rac-doctor-diagnostic-validator`) nor the author/date/status-history
  provenance fields (owned by WS5, `rac-provenance-surfacing`); it consumes
  them and supplies the trust narrative and the `status` signal.

## Risks

- A reader mistakes the doctor flag or the `status` signal for a guarantee.
  Mitigation: `SECURITY.md` states plainly that PR review is the boundary and
  both are aids, not gates (ADR-065).
- The `status` field collides or overlaps with the WS5 provenance fields and the
  WS3 doctor output on `get_artifact`. Mitigation: WS11 adds only the top-level
  `status` string; WS5 adds the author/date/status-history fields; the two are
  additive and namespaced so they compose without duplication (ADR-007).

## Assumptions

- The `## Status` section parsed by Core, plus the provenance fields (WS5),
  carry enough signal to power the review/trust distinction without PR-API
  plumbing this release; status is not a front-matter field today and this
  release does not make it one.

## Related Decisions

- adr-065
- adr-030
- adr-032
- adr-034

## Related Requirements

- rac-provenance-surfacing
- rac-doctor-diagnostic-validator

## Related Roadmaps

- v0.23.0-hardening
