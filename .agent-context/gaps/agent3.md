# Agent 3 — traceability gap audit (existing corpus)

Audit date: 2026-06-12, corpus at v0.10.3. Method: full survey of
`rac/decisions/` (38 ADRs), `rac/requirements/` (6), `rac/designs/` (14),
`rac/roadmaps/` (10 series + archive + future), grepping for `## Related`,
`## Supersedes`, `## Status`, supersession prose, and repo-path references.
The only linking mechanisms today are untyped `## Related <Type>` sections
(corpus-internal, by id) and `## Supersedes` on decisions. Each record below
is a relationship or capability the schema cannot express, evidenced from
the live corpus.

## Gap: typed edge semantics (implements / satisfies / depends-on / derived-from)

All relationship meaning collapses into untyped `Related <Type>` lists.
Authors already need the distinction and improvise it with unvalidated
sub-headings.

- Instance: `rac/decisions/adr-028-explorer-surface.md` (lines 128–134)
  invents `### Implements` and `### Related` sub-headings inside a
  non-schema `## Related Artifacts` section to say the decision implements
  the Explorer requirement — none of it is extracted or validated.
- Instance: `rac/requirements/rac-product-knowledge-navigator-explorer.md`
  (lines 332–338) invents `### Depends On` under `## Related Artifacts`
  ("Portfolio Intelligence", "Relationship Navigation") — dependency
  semantics with no schema home.
- Instance: `rac/roadmaps/v0.10.x-guide/v0.10.3-search-quality.md`
  (lines 164–172) lists ADR-037/ADR-038 (decisions this milestone
  implements) and ADR-007/ADR-027 (standing constraints it merely operates
  under) in the same flat `## Related Decisions` list — an agent cannot
  tell which decisions the milestone delivers and which it must not break.
- Instance: `rac/decisions/adr-029` through `adr-034` each list
  `rac-agent-context-guide` under `## Related Requirements`; the actual
  semantics (each decision constrains how that requirement is satisfied)
  is unrecoverable from the untyped edge.
- Minimal schema addition that would have sufficed: validated optional
  edge-label sub-headings (`### Implements`, `### Depends On`,
  `### Satisfies`) inside existing `Related <Type>` sections, defaulting
  to untyped when absent.
- Motivates: a relationship-semantics milestone in a post-v0.10 series;
  directly improves `rac relationships` output and the Guide MCP
  `get_related` answer quality (ADR-016 territory).

## Gap: supersession outside decisions (roadmap and roadmap-series supersession)

`## Supersedes` is decision-only. Roadmap replanning is expressed by
moving files to `archive/` or by prose, leaving duplicate version
identities with no machine-readable edge between old and new plans.

- Instance: `rac/roadmaps/archive/v0.8.0-service-api.md` and
  `rac/roadmaps/v0.8.x-explorer/v0.8.0-explorer-foundation.md` both claim
  the v0.8.0 identity with disjoint scope; the archived artifact carries
  no superseded marker of any kind.
- Instance: the entire archived v0.9 plan
  (`archive/v0.9.0-explorer-foundation.md`, `v0.9.1-explorer-experience.md`,
  `v0.9.2-knowledge-operations.md`, `v0.9.3-intelligence-views.md`) was
  replaced by the live `rac/roadmaps/v0.9.x-watchekeeper/` series
  (`v0.9.0-repository-review.md`, …) — a series-level supersession only
  expressible as a directory move.
- Instance: `rac/roadmaps/v0.10.x-guide/v0.10.0-guide-foundation.md`
  (line 24): "This milestone supersedes the earlier `v1.2-mcp-server`
  future stub" — prose only, and the stub has since been deleted from
  `rac/roadmaps/future/`, so the reference now dangles invisibly.
- Instance (decision-side variant): `rac/decisions/adr-029-guide-delivery-surface.md`
  (line 71) records a *prospective* supersession condition in prose
  ("…supersedes this one") because `## Supersedes` can only point
  backwards from a newer artifact.
- Minimal schema addition that would have sufficed: permit `## Supersedes`
  on roadmap artifacts (validated for target existence, including
  archived targets) exactly as on decisions.
- Motivates: roadmap-lifecycle work in a future planning-hygiene
  milestone; makes `archive/` queryable instead of conventional.

## Gap: machine-readable status / lifecycle on requirements

Decisions have a validated `Status` enum (Proposed | Accepted |
Superseded | Deprecated). Requirements have a `## Status` section by
convention only — no enum, no validation, and no blocked/gated state.

- Instance: `rac/requirements/rac-product-intent-ci-watchkeeper.md`
  (line 10) carries Status "Deferred" — a value outside any defined
  vocabulary; `rac validate` accepts it silently.
- Instance: all five remaining requirements
  (`rac-agent-context-guide.md`, `rac-documentation-structure.md`,
  `rac-product-knowledge-navigator-explorer.md`,
  `rac-repository-review-mode.md`, `rac-trust-transparency.md`) read
  "Proposed" although several are implemented and shipped (e.g. the
  documentation structure and the Guide MCP surface are live) — no
  Accepted/Implemented transition exists to record.
- Instance: this programme's gate convention (BRIEF.md, GATE-1/GATE-2)
  must encode a blocked state as a free-text body line
  (`Blocked: GATE-2 (CLA not yet in place)`) under `## Status`, as now
  done in `rac/requirements/rac-growth-contribution-policy.md`, because
  no blocked/gated status exists in the schema.
- Minimal schema addition that would have sufficed: a validated Status
  vocabulary for requirements (Proposed | Accepted | Implemented |
  Deferred | Blocked) with an optional single reason line for Blocked.
- Motivates: the review-engine line (`rac/roadmaps/future/v1.1-review-engine.md`,
  deterministic checks first) and CI Watchkeeper intent analysis, both of
  which need lifecycle state to reason about.

## Gap: links from artifacts to non-artifact repo files

Links are corpus-internal by id. Artifacts that govern README sections,
docs pages, CI workflows, or source layout can only name them as inert
prose paths; renames break the artifact silently.

- Instance: `rac/requirements/rac-documentation-structure.md` places
  testable requirements on `README.md`, `docs/quickstart.md`,
  `docs/cli.md`, `docs/artifacts.md`, `docs/relationships.md`,
  `docs/repo-workflow.md`, `docs/testing.md`, and `CONTRIBUTING.md`
  (lines 42–247) — none of these targets is resolvable or
  existence-checked.
- Instance: `rac/decisions/adr-027-ci-test-topology.md` (lines 18–61)
  governs `.github/workflows/tests.yml`, `ci.yml`, `python-publish.yml`,
  and `pr-checks.yml` by bare path.
- Instance: `CLAUDE.md` imports `rac/prompts/rac-agent-session-start.md`
  and `rac/prompts/rac-agent-commit-guidelines.md` into every agent
  session; the corpus has no way to record that these prompt artifacts
  are wired into the agent harness, nor which file consumes them.
- Instance: `rac/requirements/rac-growth-contribution-policy.md`
  (this programme) must state that its policy text lands in
  `CONTRIBUTING.md` once live — only expressible as prose.
- Minimal schema addition that would have sufficed: an optional
  `## Related Files` section of repo-relative paths, validated for
  existence by `rac relationships --validate`.
- Motivates: workspace analysis (`rac/roadmaps/future/v1.0-workspace-analysis.md`)
  and Guide grounding — "which artifacts govern this file?" is exactly
  the question agents ask.

## Gap: relationship directionality and back-reference validation

Edges are stored one-way on whichever artifact happened to be written
last. Nothing reports that A lists B while B does not know about A, so
inbound knowledge is invisible at the target.

- Instance: `rac/decisions/adr-036-lore-product-identity.md` lists
  `v0.10.2-guide-grounding-demo` under `## Related Roadmaps`;
  `rac/roadmaps/v0.10.x-guide/v0.10.2-guide-grounding-demo.md` contains
  no reference to ADR-036 — the product-identity decision is invisible
  from the milestone that shipped it.
- Instance: `rac/requirements/rac-agent-context-guide.md` (lines 238–251)
  lists ADR-002, ADR-007, ADR-008, ADR-012, ADR-015 and ADR-026; those
  six ADRs contain zero `## Related` sections, so every one of these
  edges is one-way (most pre-v0.7 ADRs, adr-001 through adr-016, have no
  Related sections at all).
- Instance: `rac/roadmaps/v0.10.x-guide/v0.10.3-search-quality.md` lists
  `rac-agent-context-guide` under `## Related Requirements`, while that
  requirement's `## Related Roadmaps` stops at v0.10.2 — an asymmetry no
  tooling can flag today.
- Minimal schema addition that would have sufficed: an advisory
  `rac relationships --validate` finding class for asymmetric edges
  (A references B, B does not reference A), without requiring symmetry.
- Motivates: relationship-inspection hardening in the trust line
  (successor to v0.7.1/v0.7.2 work) and Explorer graph quality
  (`rac/designs/explorer-knowledge-graph.md`).

## Gap: scoping / applies-to for constraint-style decisions

Several accepted ADRs are standing constraints on a specific component,
directory, or surface. The schema cannot record scope, so "which
decisions constrain this path?" is unanswerable mechanically.

- Instance: `rac/decisions/adr-018-rac-directory-as-root.md` applies to
  the `rac/` directory specifically.
- Instance: `rac/decisions/adr-023-clean-break-internal-refactors.md`
  (line 62) states "This decision governs **internal Python import paths
  only**" — scope is `src/rac/` internals, recorded only as bold prose.
- Instance: `rac/decisions/adr-027-ci-test-topology.md` applies to the
  `.github/workflows/` CI surface.
- Instance: `rac/decisions/adr-033-guide-response-budget.md` applies to
  Guide MCP tool responses only (per-response 10,000-character budget);
  nothing marks its scope as the Guide surface rather than the CLI.
- Minimal schema addition that would have sufficed: an optional
  `## Applies To` section on decisions listing component names or
  repo-relative paths.
- Motivates: Guide/Watchkeeper grounding — an agent editing a file should
  be able to ask for the decisions scoped to it (extends ADR-034's
  reasoning-boundary model with deterministic scope lookup).

## Gap: unrecognised relationship sections fail silently (no strict mode, no display-name resolution)

Sections outside the schema's `Related <Type>` vocabulary are ignored by
extraction and validation rather than flagged, so real links written
under improvised headings — often by display name instead of id — are
silently lost while CI stays green.

- Instance: `## Related Artifacts` (not a schema section) appears in at
  least eight artifacts: `rac/decisions/adr-028-explorer-surface.md`,
  `rac/requirements/rac-product-knowledge-navigator-explorer.md`,
  `rac/requirements/rac-trust-transparency.md`,
  `rac/designs/explorer-action-workflows.md`,
  `rac/designs/explorer-recommendations.md`,
  `rac/designs/explorer-editor-integrations.md`,
  `rac/roadmaps/archive/v0.9.0-explorer-foundation.md`,
  `rac/roadmaps/archive/v0.9.1-explorer-experience.md`.
- Instance: targets inside those sections are display names, not
  resolvable ids — "Requirement: Product Knowledge Navigator (Explorer)"
  (`explorer-action-workflows.md` line 99), "Design: Explorer Terminal
  Experience" (`archive/v0.9.0-explorer-foundation.md` line 254) — and
  `DESIGN-editor-integration` / `DESIGN-recommendations` match no id
  scheme in the corpus.
- Instance: `rac/requirements/rac-trust-transparency.md` (lines 172–175)
  links to "Roadmap items for repository structure, CI, fixtures, and
  test coverage" — a whole-category reference that resolves to nothing
  and is never reported.
- Minimal schema addition that would have sufficed: a validation finding
  (advisory or strict-mode) for sections matching `Related *` that are
  outside the schema vocabulary, and for entries that resolve to no
  artifact id.
- Motivates: audit-hardening follow-up to v0.7.14 and the review engine
  (`future/v1.1-review-engine.md`) — these are exactly the deterministic
  checks it promises.
