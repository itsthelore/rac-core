---
schema_version: 1
id: RAC-KWQAZTC4EWBF
type: design
---
# Decisions-on-PR Surfacing

## Status

Proposed

Exploratory — the top-ranked net-new adoption lever from
`adoption-opportunity-survey` (Opportunity 1), split out for independent
consideration. Not an accepted build. It states positioning recorded in
ADR-036 and ADR-081 and honours ADR-034/ADR-067; it does not alter them.

## Context

Lore's core promise is that a coding agent — or a human reviewer — stops
re-doing what a team already ruled out. Today that value is realised only if
someone thinks to query the corpus. At the one moment it matters most — a pull
request editing code a decision governs — nothing surfaces the governing
decision. The shipped CI actions annotate *validation and relationship errors*
("your corpus is malformed"), never *the decisions that govern the code under
review*.

Two capabilities that just shipped make this cheap: the `rac decisions`
path→decisions lookup and the `## Applies To` code-scope declaration
(`decision-to-code-proximity`, mechanism recorded in `code-scope-consumption`).
The lookup answers "which live decisions govern this path" deterministically;
a PR knows its changed paths; the join is a comment.

## User Need

- **Reviewers and agents on a PR** need the governing decisions for the code
  they are changing, in context, without leaving the review — so a settled
  constraint is seen before it is violated, not after.
- **Evaluators and teammates** watching the repo see, on every PR, that Lore is
  doing something useful — passive proof and a link back (the distribution
  half of the lever).

## Design

A CI action (a `lore-*` GitHub Action per ADR-068, or a documented recipe over
the existing `rac` CLI) that, on a pull request:

1. Computes the PR's changed paths.
2. Runs `rac decisions <path>` for each (the same service the CLI and the sixth
   MCP tool already use), collecting the live decisions whose `## Applies To`
   scope covers a changed path.
3. Posts **one** deduplicated comment naming each governing decision by id and
   title, with a one-line summary and a "still current? — review recommended"
   prompt, plus a link to the decision. Re-runs update the same comment rather
   than stacking.

The comment reports the decisions as **facts** — "this PR touches code governed
by ADR-081" — never a verdict on the change and never a merge gate (ADR-034).
It is post-edit context supply, not pre-edit interception (ADR-067). Where a
governed decision has also drifted (the `suspect-artifact` signal,
`freshness-and-drift-detection`), the comment may note it — the two compose.

This also absorbs Opportunity 5 of the survey (public decision pages): the
comment links a rendered, shareable view of each cited decision, so the
"shareable decision page" idea rides here rather than as a standalone surface.

## Constraints

- **Thin client over the contract (ADR-063).** The action shells to `rac
  decisions --json`; it re-derives nothing. A `rac decisions --changed`
  convenience mode (diff-aware) would be an additive engine affordance
  (ADR-007), never new engine logic.
- **Facts, not verdicts (ADR-034); post-edit, not interception (ADR-067).** No
  merge gate ships here; the human PR review stays the trust boundary
  (ADR-065).
- **Advisory quality is the risk, not correctness.** An over-eager comment
  trains reviewers to ignore it — the same over-flagging lesson
  `freshness-and-drift-detection` records. Scope to live decisions with a
  matching declared `## Applies To`; keep the comment terse.
- **Brand/topology (ADR-068).** The Action is a `lore-*` product; any engine
  convenience mode is `rac-*`.

## Rationale

Best leverage-per-build of the surveyed options: it reuses output `rac` already
produces, compounds capability that shipped this week, and puts Lore's core
promise where it is felt — the review. It is on-thesis rather than a new
category, so it strengthens the recorded positioning (ADR-036, ADR-081) instead
of straining it.

## Alternatives

- **A pre-merge gate that blocks PRs touching governed-but-drifted code.**
  Rejected for this phase: gating is post-advisory territory (ADR-075) and
  cuts against ADR-034/ADR-067; advisory-first proves signal quality before any
  gate, exactly as the drift work sequenced it.
- **Surface it only in the IDE (extension), not the PR.** Complementary, not a
  replacement — the PR is where cross-team review and the distribution loop
  live; the extension is the single-author surface.
- **Do nothing / rely on the agent to query.** The status quo; the value stays
  invisible at the decision point, which is the gap this closes.

## Accessibility

The comment is plain Markdown: decision id, title, one-line summary, link.
Provenance stays legible — the verbatim, id-addressed decision text is distinct
from the one-line summary, and the summary never restates a decision as a
verdict.

## Style Guidance

Terse and factual. Lead with the decision id and title; one line of summary;
"review recommended," never "you must." No promotional language. Cite decisions
by id.

## Open Questions

- Ship as a first-party `lore-*` Action, or a documented recipe in
  `integration-recipe-factory` over `rac decisions` that any CI can adopt?
- Is a `rac decisions --changed <base>..<head>` diff-aware mode worth adding to
  the engine, or does the Action compute changed paths itself and call
  `rac decisions` per path?
- How is comment noise tuned — a per-run cap, a relevance threshold, or
  collapsing to "N governing decisions" with a details expander?

## Related Decisions

- adr-007
- adr-034
- adr-063
- adr-065
- adr-067
- adr-068
- adr-081

## Related Roadmaps

- growth-programme
- decision-to-code-proximity
- freshness-and-drift-detection
- integration-recipe-factory
