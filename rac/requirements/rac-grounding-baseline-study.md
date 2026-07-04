---
schema_version: 1
id: RAC-KWNYXB150JEE
type: requirement
---
# Requirement: Grounding Study for Publication

## Status

Proposed

Classification: `[internal]` — the publication-grade evidence the paper
needs. Initiative 2 of the `decision-grounding-paper` roadmap. The multi-arm
head-to-head **already exists** as the `decisiongrounding` benchmark in the
`itsthelore/rac-benchmarks` repository (ADR-092); this requirement scopes the
deltas that take it from a working benchmark to a citable study, not a new
harness. Referenced in prose because there is no relationship type for an
external-repository artifact (the gap recorded in `growth-essay-mapping`).

## Problem

ADR-081 records the open question — *"no published proof that curated
decision context lifts agent task success."* Answering it does **not** require
building a study from scratch: `decisiongrounding` already runs the
head-to-head this paper needs. Per its published description it compares four
arms — `no_grounding`, `naive_rag` (Voyage embeddings + top-k), `rac` (typed
retrieval following supersedes edges), and `context_dump` (paste everything)
— each feeding the **same fixed answering model with the same prompt
scaffold**, so only the grounding method varies. Its primary metric is
**decision-adherence** (did the agent propose a prohibited or superseded
change), scored **deterministically and structurally with no embeddings and
no LLM judge in the scored path** (ADR-066); it sweeps corpus size
(10/50/150/300) and includes a real-corpus pilot (PEP 386→440) with PEP/RFC
distractor pools.

What is missing for a *paper* is narrower than a new study: publication-grade
statistical rigor, a real-corpus arm scaled beyond the pilot, and — optionally
— a downstream executable task-success arm for external legibility. A
construct note governs that last item: `decisiongrounding`'s adherence metric
is the *cleaner* measure of the thesis (following settled decisions) than an
executable task-pass rate, which conflates decision-following with unrelated
code-correctness; executable scoring adds reviewer legibility at some
construct-validity cost, so it is a complementary second study, not the
primary outcome.

## Requirements

- [REQ-001] The paper's evaluation MUST be the existing `decisiongrounding` multi-arm benchmark (the `no_grounding` / `naive_rag` / `rac` / `context_dump` arms over the same knowledge with a fixed answering model), extended for publication — not a re-implemented head-to-head.
- [REQ-002] The deterministic structural adherence metric MUST remain the primary, gated outcome (ADR-066, ADR-097): the `naive_rag` (embedding) arm and any LLM-judge fallback are comparative evidence only and MUST NEVER enter the scored or gated path.
- [REQ-003] The study MUST add publication-grade statistical rigor: a pre-registered hypothesis and analysis, paired significance testing across arms on the same scenarios (e.g. McNemar on adherence pass/fail), and reported effect sizes with confidence intervals — with the corpus-size sweep reported as a curve rather than point estimates.
- [REQ-004] The study MUST mature the real-corpus arm beyond the PEP 386→440 pilot to a study-grade set (scaled PEP/RFC or comparable governing-decision corpora with their distractor pools), so the result generalises past the synthetic scenarios.
- [REQ-005] The study MAY add a downstream executable task-success arm (e.g. version-conditioned tasks scored by upstream unit tests, per `external-benchmark-evidence`) as a COMPLEMENTARY external-legibility study; if added it is explicitly secondary to decision-adherence, and its executable/LLM scoring stays outside `rac-core` (ADR-092), never gating the deterministic path.
- [REQ-006] The study MUST report its result faithfully, including a null or partial outcome: a result where `rac` beats `naive_rag` on stale/prohibited-decision adherence but not on raw task success is a publishable finding, not one to suppress.
- [REQ-007] No embeddings, vector search, or LLM judge MAY be introduced into `rac-core` itself (ADR-066, ADR-080); the `naive_rag` and any executable/judged arm live in `rac-benchmarks` (ADR-092), which drives `rac` as an external CLI.

## Acceptance Criteria

- The `rac` arm's deterministic adherence scoring reproduces exactly on
  re-run; the `naive_rag` arm reports its pinned embedding model, index
  build, answering-model version, and run-to-run variance.
- The published result reports paired-test significance and effect sizes with
  confidence intervals across arms, and the adherence-vs-corpus-size curve.
- The real-corpus arm runs on a set materially larger than the PEP 386→440
  pilot, with its distractor pool documented.
- Any executable task-success arm is reported as a secondary study, clearly
  distinguished from the primary adherence outcome, and built in
  `rac-benchmarks`, not `rac-core`.
- The `rac-core` CI grounding eval (`rac-grounding-eval-benchmark`) is
  unchanged: no embeddings, no LLM judge, no network in its gated path.

## Success Metrics

- The paper cites a publication-grade result from `decisiongrounding` that
  answers ADR-081's open question — a measured adherence delta (in either
  direction) between deterministic decision grounding, semantic RAG,
  context-dump, and no grounding — on a set a reviewer would accept.

## Risks

- The `naive_rag` baseline looks like a straw man. Mitigation: it already uses
  a current embedding model (Voyage) with asymmetric query/document roles;
  publish its configuration and invite replication via `rac-benchmarks`.
- Construct validity — adherence versus task success. Mitigation: keep
  adherence primary (REQ-002) and treat any executable arm as a secondary,
  clearly-labelled study (REQ-005).
- Scope creep turns a paper study into an open-ended benchmark programme.
  Mitigation: this requirement scopes the publication extension of one
  existing benchmark; the broader external-benchmark tables stay in
  `external-benchmark-evidence`.

## Assumptions

- `decisiongrounding` is the right base to extend rather than a new harness to
  build; its four-arm, fixed-answering-model design is sound for the claim.
- A governing-decision corpus at study-grade scale can be curated (PEP/RFC and
  comparable) where the correct action depends on a recorded decision an
  ungrounded or semantically-retrieved agent would miss.
- Running the `naive_rag` and any executable arm outside `rac-core` preserves
  the engine's no-embeddings posture (ADR-066, ADR-080).

## Related Decisions

- adr-066
- adr-081
- adr-092
- adr-097

## Related Roadmaps

- decision-grounding-paper
- external-benchmark-evidence

## Related Requirements

- rac-grounding-eval-benchmark
