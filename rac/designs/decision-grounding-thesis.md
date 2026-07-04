---
schema_version: 1
id: RAC-KWNYX97WSFBV
type: design
---
# Design: Decision-Grounding Paper Thesis

## Status

Proposed

The durable argument behind the `decision-grounding-paper` roadmap: the gap
taxonomy, the thesis, the section outline, and a draft arXiv abstract. This
is the paper's design, not the manuscript; the manuscript is its output and,
being external, is referenced in prose (there is no corpus edge for an
unpublished document — see `growth-essay-mapping`). It states the positioning
recorded in ADR-036 and ADR-081; it does not alter it.

## Context

Two families of tooling now feed context to AI coding agents, and they fail
the same way from opposite ends:

- **Spec-driven development** (GitHub Spec Kit, AWS Kiro, Tessl, the Spec
  Growth Engine, arXiv:2606.27045) couples specs to *code*. Böckeler's
  survey separates the field into *spec-first* (specs guide an initial
  generation, then are discarded), *spec-anchored* (specs kept in sync with
  code), and *spec-as-source* (code generated from specs). Every point on
  that axis is code-bound and per-repo; the spec describes a codebase, not a
  product decision, and is ephemeral (Kiro deletes it) or generative
  (spec-as-source inherits MDA's nondeterminism).
- **Agent-memory / RAG** (Mem0, Zep/Graphiti, Cognee, Letta, plus rules
  files and vector search) retrieves relevant *text*. It is nondeterministic,
  untyped, LLM-distilled at ingest, and unable to assert "this is settled."

Both miss the durable product *decision* — the why, the rejected
alternatives, the accepted constraints — as a first-class, typed, validated,
deterministically-retrievable artifact. The observable cost is agents
re-litigating settled decisions and drifting from product intent. ADR-081
records the exact open question: *"no published proof that curated decision
context lifts agent task success."* The corpus already holds the positioning
(ADR-081, `rac-growth-positioning`, `rac-growth-agent-memory-positioning`)
and a deterministic evaluation (ADR-066, ADR-097). This design turns that
into a paper.

## User Need

Three audiences. The **research/practitioner community** needs the missing
layer named and located, so the field stops conflating decision knowledge
with code specs or with fuzzy memory. **Adopters and evaluators** need
third-party-credible evidence that deterministic decision grounding lifts
agent outcomes — the claim ADR-081 marks unproven. The **maintainer** needs
a citable artifact that strengthens the recorded positioning (ADR-036,
ADR-081) without repositioning it, and that clears GATE-1.

## Design

### The thesis

Grounding coding agents on product knowledge should be **deterministic and
typed, not semantic and fuzzy**; the **decision record is the substrate**;
and this layer is **orthogonal to — composes underneath — spec-driven
development**. Lore (built on the RAC engine) is the reference
implementation: typed artifact families, classification separated from
validation, a validated relationship graph, git-native with no database,
human-PR-ratified, served to agents deterministically over CLI and MCP with
no embeddings and no LLM judge (ADR-066, ADR-034, ADR-080).

### The gap taxonomy (the paper's central figure)

Two axes locate the empty quadrant:

- **Code-coupling** — does the artifact describe *code* (spec-driven, per
  repo) or *product decisions* (durable, cross-repo)?
- **Determinism** — is retrieval a *deterministic, typed* function of the
  corpus, or a *semantic/LLM-distilled* guess?

Spec-driven tools sit in `code × deterministic-ish`; agent-memory/RAG in
`text × semantic`. The unserved quadrant is **`decisions × deterministic`**
— durable product decisions, retrieved deterministically, typed and
human-ratified. That is the layer, and it is where Lore sits (ADR-081's
"deterministic source of truth for product decisions").

### Draft arXiv abstract

> AI coding agents accelerate implementation but repeatedly re-introduce
> approaches their teams already rejected and drift from product intent. We
> argue this is not a context-quantity problem but a context-*kind* problem:
> the two dominant ways of grounding agents both omit the durable product
> decision. Spec-driven development couples specifications to code — bound
> to one repository, and either discarded after generation or used as a
> nondeterministic source. Agent-memory and retrieval-augmented systems
> distil knowledge with an LLM into a mutable store, trading determinism,
> typing, and auditability for recall. Neither can assert that a decision is
> settled. We name the missing layer — *deterministic, typed, human-ratified
> decision grounding* — and locate it on a two-axis map (code-coupling ×
> determinism) whose fourth quadrant no surveyed tool occupies. We present
> Lore, an open-source engine that models product decisions, requirements,
> and roadmaps as typed Markdown artifacts in git, validated deterministically
> in CI and served to agents with no embeddings and no LLM judge. We evaluate
> whether deterministic decision grounding improves agent task success
> against an ungrounded and a semantic-RAG baseline on version-conditioned
> programming tasks with executable outcomes, holding the retrieved corpus
> constant across arms. [Result sentence — filled at Initiative 2.] The
> contribution is the framing and the evidence, not a new paradigm: the
> mechanisms are established (ADRs, requirements engineering, deterministic
> IR, docs-as-code); the claim is that decision grounding is a distinct,
> measurable, and currently unserved layer of the agent stack.

### Section outline

1. **Introduction** — the two failure modes (re-litigation of settled
   decisions; drift of product intent) that neither camp addresses.
2. **Two structural gaps** — (a) knowledge-as-code-spec loses the *why* and
   is per-repo/ephemeral; (b) knowledge-as-embeddings loses determinism,
   typing, and the "settled" signal.
3. **Established foundations** — ADRs (Nygard), requirements engineering,
   docs-as-code, deterministic IR (BM25-family), typed knowledge graphs;
   "a machine-enforced synthesis, not a new paradigm."
4. **Architecture** — typed artifact families; classification separate from
   validation; the relationship graph; git-native / no database (ADR-080);
   the human-PR-ratified trust boundary (ADR-065); deterministic serving
   (CLI + MCP, response budget).
5. **Determinism as the thesis** — why no-embeddings / no-LLM-judge is a
   feature: reproducibility, auditability, air-gap, and the "settled"
   assertion (ADR-066, ADR-034); the Sourcegraph-reversed-out-of-embeddings
   data point (ADR-081) as external corroboration.
6. **Evaluation** — the none / RAG / rac-corpus grounding-arm study with an
   executable task-success outcome (`rac-grounding-baseline-study`).
7. **Related work** — position off Böckeler's spec-driven axis (via the Spec
   Growth Engine); contrast agent-memory/RAG (the `rac-growth-agent-memory-
   positioning` taxonomy) and requirements-management tools.
8. **Discussion and limits** — single-corpus scope; the external-edge
   limitation; honest treatment of a null or partial result.

## Constraints

- Naming per ADR-036: "Lore (built on the RAC engine)"; state the
  relationship once; do not reposition.
- Consistent with the recorded no-semantic-verdict / no-database posture
  (ADR-034, ADR-066, ADR-080) and the ADR-081 thesis.
- The reported evaluation keeps embeddings and LLM judges out of the
  scored/gated path (ADR-066, ADR-097); the semantic arm is comparative
  evidence only.
- External publication is GATE-1-blocked; nothing here is publication prose.

## Rationale

Leading with a general framing plus evidence — rather than a product
description — is what separates a citable contribution from a vendor blog
post; the Spec Growth Engine survives the same "this is just a synthesis"
critique by owning it. RAC's advantage over that precedent is that it can
bring an *evaluation* (the deterministic grounding eval already exists,
ADR-066/097), addressing exactly the gap ADR-081 records. The ADR corpus
already reads as a design-rationale section, so the paper is substantially
pre-argued.

## Alternatives

- **Position-only paper (no evaluation).** Rejected as the primary plan:
  arXiv would accept it, but it is low-impact and invites the marketing
  critique; the evaluation is RAC's differentiator. Retained as a fallback
  if GATE-1 or eval effort blocks the empirical version.
- **Fold into the growth-essay series.** Rejected: the essays are a
  personal, non-academic genre with their own bridge requirement
  (`rac-growth-essay-bridge`); an academic paper is a distinct artifact and
  audience.
- **A benchmark-only release (numbers into third-party tables).** That is
  the `external-benchmark-evidence` roadmap's job; this paper consumes its
  output rather than replacing it.

## Accessibility

Not a user interface. The accessibility bar is *legibility of the argument*:
a reader can trace every claim in the paper back, in prose, to a recorded
decision (by ADR id) or the eval methodology, without access to this corpus.

## Style Guidance

Academic register, honest and non-promotional. Lore appears as a reference
implementation and worked example, never as the subject. Cite recorded
decisions by ADR id; cite external work (the Spec Growth Engine,
arXiv:2606.01435, Böckeler) in prose. Report the evaluation result
faithfully, including a null or partial outcome.

## Open Questions

- Venue after arXiv: which LLM4SE / agents-for-SE workshop, and on what
  timeline relative to GATE-1.
- Evaluation scale and task set: LongMemEval vs GitChameleon vs a bespoke
  decision-governed set — resolved in `rac-grounding-baseline-study`.
- Authorship and affiliation (maintainer's call), and whether an external
  co-author strengthens credibility.
- How to reference the manuscript from the corpus given no external-document
  relationship type exists — prose only, or wait on that schema work.
- Single-author position-and-evidence papers: is the empirical arm enough
  for a peer venue, or is a larger study needed first.

## Related Requirements

- rac-grounding-baseline-study
- rac-growth-positioning
- rac-growth-agent-memory-positioning

## Related Decisions

- adr-034
- adr-036
- adr-066
- adr-080
- adr-081
- adr-097

## Related Roadmaps

- decision-grounding-paper
- external-benchmark-evidence
- growth-programme
