---
schema_version: 1
id: RAC-KVTRP81ZWA57
type: roadmap
---
# RAC — Freshness Signals and Drift Detection (Future)

## Status

Planned

Unscheduled — captured for future consideration from the team-scale (20+) market
research. It is the highest-leverage finding of that research and graduates out of
`future/` into a versioned series when prioritised.

## Context

The strongest, best-evidenced finding from researching knowledge tools at team
scale: **staleness leading to trust collapse is the number-one cause of
abandonment** — once a reader hits one wrong page, they distrust the whole corpus
and revert to Slack or reading source. And the evidence is empirical, not
folklore: a study of 27,772 pull requests across 714 repositories found only
~0.8% of PRs update the README and ~21.5% of changes that should have updated it
did not; DORA finds high-quality documentation more than doubles the odds of
hitting performance targets.

The sharp, uncomfortable corollary: **git + PR review is necessary but
proven-insufficient to keep knowledge fresh** — the docs-as-code literature itself
concedes there is no evidence drift decreases at scale, and the PR data shows
reviewers routinely miss documentation updates. So Lore's PR-review trust boundary
(ADR-065) alone will not keep the corpus trustworthy.

What every serious tool at the high end *does* ship is a freshness mechanism:
enterprise requirements tools (Jama, IBM DOORS, Siemens Polarion) all flag
downstream items as **"suspect"** when an upstream item changes; team wikis bolt on
owner + expiry-clock verification. By contrast, the AI agent-context tools
(Cursor, Amp, Continue, Augment) ship *no* freshness tooling at all — a gap Lore
can own. Lore already holds the raw material to do a deterministic, git-native
version: recency derived from git (ADR-045) and a validated relationship graph
(ADR-074). This item is that capability.

## Outcomes

- Git-derived staleness is surfaced **loudly** wherever the corpus is read — the
  CLI, the MCP responses, the TUI — so decay is visible, not silent.
- A deterministic **drift gate** flags an artifact as "suspect" when something it
  governs or references changes but the artifact itself did not — the git-native
  equivalent of enterprise "suspect links," with no database and no AI.

## Initiatives

### Initiative 1 — Loud freshness signals

Surface git-derived recency on reads — last-touched date, the commit/PR that last
changed an artifact, and a staleness indicator — across `rac` CLI output, the MCP
`get_artifact`/search responses (additively, ADR-007), and the Explorer. Recency
stays derived from git, never stored in frontmatter (ADR-045).

### Initiative 2 — Deterministic drift gate ("suspect" detection)

When an artifact references a target — another artifact, or (with the
decision-to-code-proximity work) a code path it governs — and that target changes
in a commit while the artifact does not, flag the artifact "suspect" for review.
Pure git-diff over the validated relationship graph; no model, no embeddings. It
can run advisory in `rac doctor`/`review` or as a CI gate (ADR-075), the team's
choice.

### Initiative 3 — Freshness biases surfacing

A stale-flagged artifact is surfaced for review (in `review`/`doctor`/coverage) and
can be de-prioritised in retrieval until refreshed — so the freshness signal
actually changes what readers and agents see.

## Constraints

- Deterministic and git-derived (ADR-045): staleness is computed from commit
  history, never a stored "verified" flag that would duplicate git state.
- No database, no AI/embeddings (ADR-066): drift detection is git-diff plus the
  declared relationship graph.
- PR review remains the human attestation (ADR-065); this *augments* it with the
  machine-checkable signal the evidence says review alone lacks.

## Non-Goals

- Auto-fixing staleness: decision rationale cannot be regenerated, so Lore detects
  and surfaces drift, it does not silently rewrite an artifact.
- A frontmatter "last verified" checkbox: that duplicates state git already holds
  and invites the self-clicked-verify theatre wikis rely on.

## Success Measures

- A reader or agent can see, at the point of use, when an artifact was last
  touched and whether it is suspect.
- Changing a target without updating an artifact that references it produces a
  deterministic "suspect" finding, reproducibly.
- No new datastore is introduced; the signal is a pure function of git history and
  the relationship graph.

## Assumptions

- Trust collapse from staleness is the dominant abandonment driver at 20+, so a
  visible, automated freshness signal is the single highest-leverage adoption
  lever — and one no agent-context competitor ships.
- A git-native "suspect links" mechanism delivers the value enterprises pay
  six-figure sums for, without their cost or lock-in.

## Risks

- Over-flagging (every upstream edit marks everything suspect) trains people to
  ignore it. Mitigation: scope "suspect" to declared references and meaningful
  target changes; make it advisory before it is ever a gate.
- A freshness signal could imply a freshness *guarantee*. Mitigation: frame it as
  "review recommended," an input to human judgement (ADR-065), never proof of
  correctness.

## Related Decisions

- adr-045
- adr-065
- adr-074
- adr-066

## Related Requirements

- rac-traceability-coverage-report
- rac-doctor-diagnostic-validator
