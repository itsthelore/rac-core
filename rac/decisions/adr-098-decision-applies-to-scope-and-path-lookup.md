---
schema_version: 1
id: RAC-KWGKWKEXP1TJ
type: decision
---
# ADR-098: Decision Applies-To Scope and Path Lookup

## Context

A decision often governs a specific part of the repository, but says so only
in prose, so "which decisions govern the file I am editing?" is unanswerable
— gap 7 of the traceability audit (`rac-decision-applies-to-scope`) and the
lead item of the `decision-to-code-proximity` roadmap (Tranche A, rank 1 of
the `deterministic-substrate` programme). The corpus holds two precedents for
non-artifact references that this decision must reconcile: the gap
requirements say repo-path references are existence-checked by
`rac relationships --validate`, while the shipped external-reference family
(ADR-087 tickets, ADR-096 `verified_by`) is exempt from resolution and never
touches the disk. A further hard constraint discovered in implementation
planning: `rac relationships --validate` fails on ANY recorded issue
regardless of severity, so an existence signal that enters the issue list
would silently become a merge-gate blocker.

## Decision

### The `## Applies To` section, decisions only

Decisions accept an optional `## Applies To` relationship section, one entry
per line. Entries are either repo-root-relative POSIX **path globs** or free
**component labels**. The edge is registered as `applies_to` in the
relationship-type registry — external (`external=True`, no in-corpus range,
no provider), directional, inverse `governs` — mirroring ADR-096's
`verified_by`. Version 1 is decisions-only; extending the section to other
artifact types is an additive follow-up, not part of this decision.

### Entry grammar and discrimination

After normalisation (strip one surrounding backtick pair, a leading `./`,
and a trailing `/`), an entry is classified deterministically:

1. containing whitespace — a component label ("RAC Core"), recorded and
   never resolved or checked;
2. else containing `/` or a glob metacharacter (`*`, `?`, `[`) — a path
   glob;
3. else — a component label (`rac-core`).

A repository-root file opts into path-hood explicitly by the `./` prefix
(`./pyproject.toml`).

### Format lint, offline and blocking

`rac validate` lints path-classified entries with a new
`malformed-applies-to` error: absolute paths, backslashes, `.` or `..`
segments, empty segments, unbalanced `[`, or an entry that normalises to
empty. The lint is purely syntactic — no filesystem access, no
configuration — in the style of the ADR-087 ticketing lint. Component
labels are never linted.

### Matching semantics

`governs(path, scope)` is true when `fnmatch.fnmatchcase(path, scope)` or
`fnmatch.fnmatchcase(path, scope + "/*")` holds over POSIX-normalised,
repo-root-relative strings. `fnmatchcase` — never `fnmatch` — so matching is
case-sensitive and platform-independent, matching git's view of paths. In
this dialect `*` crosses `/` (so a directory scope governs its whole
subtree via the second clause) and `**` behaves as `*`; the dialect is
pinned by a test battery so any standard-library drift fails loudly.

### Existence is advisory, never blocking

An `## Applies To` path scope that matches nothing in the working tree is
surfaced as an ADVISORY: a new `advisories` list on the relationship
validation result (additive JSON key, present only when non-empty, excluded
from `ok` and the exit code) and a warning-severity `rac doctor` finding
(`applies-to-unmatched-path`). It never enters the blocking issue list, is
kept out of SARIF, and is skipped entirely when no repository root can be
discovered (no `.rac/config.yaml` above the corpus). This satisfies the gap
requirement's "checked by `rac relationships --validate`" while honouring
ADR-096's exemption precedent — a moved path is the drift signal the
freshness gate consumes, not a merge blocker.

### The path lookup, CLI and MCP

A deterministic lookup returns the live decisions whose declared path
scopes govern a queried path, with their status and the matching scopes:

- CLI: `rac decisions PATH [DIRECTORY] [--json]` — read-only; exit 2 on a
  bad directory, exit 0 on any completed query including an empty result.
- MCP: a sixth pinned tool, `decisions_for_path`, on the lore server. The
  tool surface grows from five to six — an ADR-030 contract change recorded
  here. The payload mirrors `find_decisions` (`schema_version`, `path`,
  `type`, `filter: "live-decisions"`, `match_count`, `matches` with
  `id`/`type`/`title`/`status`/`path`/`scopes`) and inherits the ADR-033
  response budget with whole-item truncation.

The lookup returns bindings and status, never verdicts (ADR-067): it asserts
which live decisions bind a path, not that a change is wrong. Liveness and
status come from the same seam the agent-rules export uses, so the two
surfaces can never disagree.

## Consequences

### Positive

- Scoped grounding: an agent (or human) in `src/auth/` deterministically
  retrieves the decisions that govern it, at the point of work.
- The declared decision→code join the freshness/drift gate requires now
  exists as validated data.
- Both corpus precedents survive intact: format-linted like ADR-087,
  resolution-exempt like ADR-096, with existence as a visible advisory.

### Negative

- Path scopes drift as code is refactored; by design this surfaces as an
  advisory and, later, a freshness "suspect" signal — never silent rot, but
  also never an automatic fix.
- The MCP tool surface grows by one pinned description that must remain
  stable (ADR-030).

### Risks

- Free component labels are unresolvable by construction; mitigated by the
  path form carrying all checkable semantics and labels being recorded
  verbatim for humans.
- The fnmatch dialect could shift under a future Python; mitigated by the
  pinned dialect test battery at the supported floor (3.11).

## Status

Accepted

## Category

Technical

## Alternatives Considered

### Blocking existence check in `rac relationships --validate`

Rejected: the merge gate would depend on tree state outside `rac/`, and any
code refactor would break the corpus gate until artifacts caught up.
Advisory-first mirrors the recorded enforcement instinct — a guard that
cries wolf is worse than none (ADR-067).

### Format-lint only, no tree check

Rejected: scopes could rot silently until the freshness gate ships, and the
gap requirement's explicit "checked by `rac relationships --validate`"
would be unmet.

### A new section name distinct from `## Applies To`

Rejected: gap 7 already proposed `## Applies To` for exactly this scope;
one vocabulary serves both the relationship-vocabulary and
deterministic-substrate programmes instead of two overlapping mechanisms.

### Extending `rac find` with a path flag

Rejected: the token-ladder topic search and a glob-governance lookup have
different matching, result shapes, and evidence semantics; overloading one
command muddies both contracts.

## Relationship to Other Decisions

- ADR-016 / ADR-019: declared references, never inferred; the asset-style
  validation instinct realised for code scopes.
- ADR-087 / ADR-096: the external-reference family this edge joins;
  format-linted, resolution-exempt.
- ADR-074: the edge type derives from the relationship registry and appears
  typed in the graph export.
- ADR-067: the lookup stays on the context-supply side of the boundary —
  bindings, never verdicts.
- ADR-030 / ADR-033: the sixth pinned tool and its response budget.
- ADR-007: every surface change is additive.

## Related Decisions

- adr-016
- adr-019
- adr-087
- adr-096
- adr-074
- adr-067
- adr-030
- adr-033
- adr-007

## Related Requirements

- rac-decision-applies-to-scope

## Related Roadmaps

- decision-to-code-proximity
- deterministic-substrate
- relationship-vocabulary
