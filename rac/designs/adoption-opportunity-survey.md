---
schema_version: 1
id: RAC-KWQAJG8WDSN1
type: design
---
# Adoption Opportunity Survey

## Status

Proposed

Exploratory — this records the output of a grounded adoption-opportunity
discovery pass so the reasoning lives in the corpus, not a session's scratch
space (ADR-047). It is not an accepted build. It surveys net-new adoption
levers, states each one's honest overlap with already-recorded work, and
leaves a recommended priority order rather than a closed decision. It states
positioning already recorded in ADR-036 and ADR-081; it does not alter it.

## Context

The prompt behind this survey was "review the codebase and identify 10x
products and features that would increase adoption." Run naively, that prompt
re-discovers work already planned or already shipping — because it has no step
that grounds each idea against the record first. So this survey did the
grounding first, and the honest headline is: **most of the obvious adoption
space is already recorded.** The roadmap and ADRs already own activation (the
`<5min` / `<30s` cold-start contract, `rac quickstart`, zero-config
`pipx`/`uv` install, the demo GIF — `rac-growth-adoption`, ADR-044),
positioning (`rac-growth-positioning`, the `decision-grounding-paper`),
capture surfaces (`lore-slack-bot`, `lore-overlay`, the agent-interview skill
and `/intake` action in `lore-frontend-optionality` Thread E), distribution
and CI reach (SARIF, `ci-report-formats`, `agnostic-surfaces`, `rac-editors`,
`oci-image`, `integration-recipe-factory`), RAG and enterprise
(`corpus-export-to-rag-backends`, `corpus-sync`, `lore-at-team-scale`,
`lore-supermemory-grounding`), and ecosystem (`rac-growth-extensibility`,
`rac-growth-ecosystem-list`, `artifact-family-factory`).

The single most important finding is a meta-one: `lore-frontend-optionality`
already concluded that the highest-leverage move is **distribution of the MCP
surface Lore already ships** (Thread D), and it sits there as an unbuilt Open
Question. The biggest lever is not undiscovered; it is un-scheduled.

What remains after grounding is a short, honest set of net-new levers,
recorded here so a future session inherits both the map and the ideas.

## User Need

- The **maintainer** deciding where the next unit of adoption effort buys the
  most, given how much is already recorded.
- **Future sessions**, which need the "already decided / already shipping" map
  as much as the ideas — the grounding step is what stops the next discovery
  pass from re-proposing (or re-building) settled work, the exact failure that
  produced a duplicated `freshness-and-drift-detection` build in the session
  that authored this survey.
- **Contributors** looking for a well-scoped, net-new place to help.

## Design

Five opportunities survived grounding. Each is stated as a card: the thesis,
the adoption lever and the mechanism that moves it, the evidence and the
net-new check against the record, a rough effort/risk, and the smallest proof
that would validate or kill it. They are ordered by (impact × confidence) ÷
effort.

### Opportunity 1 — Decisions-on-PR surfacing *(the recommendation)*

- **Thesis.** A PR that edits governed code gets one comment naming the
  decisions that govern it — "this touches code governed by ADR-081:
  [one-line summary] — still current?" — so the record surfaces at the moment
  a human or agent would otherwise ignore it.
- **Lever + mechanism.** Distribution *and* retention. It is visible on every
  PR in every adopting repo (passive proof the tool is working), and it
  delivers Lore's core payoff — stop re-doing what was ruled out — at the
  decision point rather than buried in a corpus.
- **Evidence / net-new.** It rides two just-shipped capabilities: the
  `rac decisions` path→decisions lookup and the `## Applies To` scope
  (`decision-to-code-proximity`, `code-scope-consumption`). Today no PR
  surface does this — the shipped CI actions surface *validation and
  relationship errors* as annotations, never the governing decisions for the
  code under review. It is on-thesis with ADR-067 (post-edit context supply,
  not pre-edit interception) and ADR-034 (report the decisions as facts, never
  a verdict).
- **Effort / risk.** Low–medium: a CI action that runs `rac decisions` over a
  PR's changed paths and posts one deduplicated comment. The hardest unknown
  is relevance tuning — an over-eager comment trains reviewers to ignore it
  (the same over-flagging lesson `freshness-and-drift-detection` records).
- **Smallest proof.** Run `rac decisions` over the changed paths of five recent
  real PRs in this repo and eyeball whether the surfaced decisions would have
  genuinely helped the reviewer.

### Opportunity 2 — Corpus status badge for adopters' READMEs

- **Thesis.** A shields-style badge — `Lore · 42 decisions · validated` — that
  an *adopting* repo displays in its README, generated from the corpus.
- **Lever + mechanism.** Distribution / virality — the classic open-source
  badge loop (build and coverage badges): every adopter's README becomes
  passive social proof and a link back.
- **Evidence / net-new.** The underlying counts already exist
  (`rac portfolio` / `rac review`). This is distinct from RAC's *own* CI and
  coverage badges (`rac-trust-transparency` FR-6/FR-7), which sign this
  repository's build — not a feature adopters render for their corpus.
- **Effort / risk.** Near-zero: a shields-compatible JSON shape plus a
  documented snippet. Risk: a stale or misleading badge; mitigated by deriving
  it live from the corpus, never a stored value (ADR-045 posture).
- **Smallest proof.** Emit the shields JSON for this corpus, render one badge,
  place it in the README, and judge whether it reads as credible.

### Opportunity 3 — Graduate MCP grounding distribution *(schedule the record's own #1)*

- **Thesis.** `rac mcp init` writes the host snippet (`.mcp.json` for Claude
  Code, the Cursor/Codex equivalents), and `lore` is listed in the MCP
  registries, so any team plugs the flagship surface in without hand-wiring.
- **Lever + mechanism.** Distribution — the record argues MCP is a
  cross-vendor standard at scale; registration is the cheapest path to the
  largest strategic payoff and reinforces the authority-of-record identity.
- **Net-new check.** This is **already recorded** as `lore-frontend-optionality`
  Thread D plus an Open Question — it is not a discovery. It is included here
  only to flag that the record's own top-ranked lever is unbuilt; the honest
  action is to graduate it to a roadmap item, not to re-derive it.
- **Effort / risk.** Low. The risk is coordination, not build (see Open
  Questions on parallel threads).
- **Smallest proof.** Ship the `rac mcp init` snippet for one host and submit
  one registry listing; measure installs.

### Opportunity 4 — Zero-install evaluator playground

- **Thesis.** An evaluator writes or pastes a decision and instantly sees it
  validated and classified, with a shareable permalink, without installing
  anything.
- **Lever + mechanism.** Activation — it removes the install barrier entirely.
  `rac-growth-adoption` optimizes the install *path* (five-minute cold start)
  but never eliminates it; every minute before first value still loses
  evaluators. A shareable permalink adds a distribution loop.
- **Net-new check.** Distinct from `rac-localview` (a *local* single-file
  viewer) and the Thread E capture *form* (for authors getting knowledge in).
  A public *evaluator* surface is not recorded — net-new, but adjacent.
- **Effort / risk.** High, and the reason it ranks below the cheap wins. The
  engine is Python; a browser surface needs either a hosted `rac` endpoint or a
  Pyodide/WASM build. It must stay a thin client over the contract (ADR-063)
  and never a content store (ADR-024) — the pasted text is ephemeral.
- **Smallest proof.** A hosted endpoint that runs `rac validate -` /
  `rac inspect` on pasted text behind a trivial page; measure paste→result
  completion.

### Opportunity 5 — Shareable public decision pages *(recorded honestly as an overlap)*

- **Thesis.** Render a decision as a clean, linkable, embeddable public page —
  a distribution surface, not a capture one.
- **Net-new check.** This substantially overlaps `rac-localview` (local HTML
  export) and the docs site. The genuinely net-new sliver — hosted,
  embeddable, public decision permalinks as distribution — is thin enough that
  it is better folded into Opportunity 1 (a PR comment links a rendered
  decision) or Opportunity 4 (the playground's permalink) than pursued
  standalone. Recorded here for completeness, not ranked.

### Recommended priority order

1. **Decisions-on-PR surfacing (1)** — best leverage-per-build, genuinely
   net-new, and the most on-thesis idea available; it makes the core promise
   visible at the decision point and compounds capability shipped this week.
2. **Corpus status badge (2)** — the near-zero-effort quick win; a cheap
   distribution loop over output that already exists.
3. **Graduate MCP distribution (3)** — the record's own #1 lever, sitting
   unbuilt; schedule it rather than re-discover it.
4. **Evaluator playground (4)** — the highest-ceiling activation lever, but a
   real build with a hosting question to settle first.
5. **Public decision pages (5)** — fold into 1 or 4; do not build standalone.

## Constraints

- **Thin clients over the contract (ADR-063).** Every surface here consumes the
  published CLI/JSON/MCP output; none reimplements the engine. The badge, the
  PR comment, and the playground all read `rac`'s existing output.
- **RAC is not a content store (ADR-024).** The playground's pasted text and
  the badge's counts are ephemeral projections; artifacts stay on disk.
- **Facts, not verdicts (ADR-034); post-edit, not interception (ADR-067).** The
  PR comment names governing decisions and recommends review; it never blocks
  an edit or renders a judgement, and it augments the human PR trust boundary
  (ADR-065) rather than replacing it.
- **Additive contracts only (ADR-007).** Any new JSON (a shields shape, a
  playground response) is additive; `schema_version` is unchanged.
- **Brand and topology (ADR-068).** Installed surfaces (a hosted playground, a
  badge service) are `lore-*` products; engine affordances (`rac mcp init`, a
  `rac decisions --changed` mode) are `rac-*`.
- **Positioning is stated, not altered (ADR-036, ADR-081).** None of these
  repositions Lore or proposes the spec-as-source / codegen direction ADR-081
  refuses.

## Rationale

Two lines of reasoning shaped the ranking. First, **grounding before ideation
is the whole method** — it is what let this survey report five net-new items
honestly instead of ten padded ones, and it is exactly the step the original
prompt lacked. Second, **distribution of existing surfaces beats new builds**,
the same conclusion `lore-frontend-optionality` reached: the two cheapest wins
(the PR comment and the badge) turn output Lore already produces into reach,
and they compound capability that already shipped. A new build (the playground)
earns a lower rank precisely because its value is real but conditional on a
hosting decision.

## Alternatives

Deliberately excluded as re-discoveries — grounding is what kept them out:

- **MCP-as-frontend / grounding distribution** — recorded
  (`lore-frontend-optionality` Thread D); surfaced above only as "schedule it."
- **Any capture or non-technical authoring surface** — recorded (Thread E:
  agent-interview skill, `/intake` action, guided web-capture form).
- **A homegrown editor** — explicitly rejected (`lore-frontend-optionality`
  Thread B) on build/maintenance cost and the git-source-of-truth identity.
- **Semantic / RAG recall** — recorded (`corpus-export-to-rag-backends`,
  `lore-supermemory-grounding`).
- **Benchmarks and the paper** — recorded (`external-benchmark-evidence`,
  `decision-grounding-paper`, `artifact-completeness-benchmark`).
- **Enterprise / team scale** — shipped (`lore-at-team-scale`).
- **Editor / OCI / GitLab reach** — recorded (`rac-editors-buildout`,
  `oci-image`, `ci-report-formats`).

## Accessibility

Not a user interface. The bar is legibility of the analysis: each opportunity
traces its net-new claim to the record it was checked against (by roadmap
codename, design, or ADR id), so a reader can verify the grounding without
re-running the pass. Any surface that graduates from here inherits the
recorded accessibility constraints of its kind — keyboard-first parity for a
viewer (ADR-028), provenance legibility for a grounding surface.

## Style Guidance

Honest, non-promotional register — no "revolutionary" or "blazing." An
opportunity earns its rank with evidence and a falsifiable smallest-proof, and
overlaps with recorded work are stated plainly (Opportunity 3 and 5 lead with
their overlap). Cite recorded decisions by ADR id and related work by codename.

## Open Questions

- Should any of Opportunities 1–4 graduate to a `future/` roadmap item now, or
  stay recorded here until a build is scheduled?
- For the **playground (4)**: hosted `rac` endpoint or a Pyodide/WASM build,
  and where does it live under the `lore-*` brand (ADR-068)?
- For the **badge (2)**: is a static shields JSON shape enough, or is a small
  hosted endpoint warranted, and how is staleness communicated?
- **Coordination.** This repository has heavy parallel-agent activity; before
  any of these is built, re-run the claim check (open PRs, active branches) so
  a graduated item is not drafted twice — the discipline this survey exists to
  encode.

## Related Decisions

- adr-007
- adr-024
- adr-034
- adr-036
- adr-045
- adr-063
- adr-065
- adr-067
- adr-068
- adr-081

## Related Roadmaps

- growth-programme
- decision-to-code-proximity
- integration-recipe-factory

## Related Requirements

- rac-growth-adoption
- rac-growth-positioning
