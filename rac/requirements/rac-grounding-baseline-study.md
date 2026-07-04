---
schema_version: 1
id: RAC-KWNYXB150JEE
type: requirement
---
# Requirement: Grounding Baseline Study

## Status

Proposed

Classification: `[internal]` — the head-to-head evidence the paper needs.
Initiative 2 of the `decision-grounding-paper` roadmap; extends the
`external-benchmark-evidence` programme's "none / RAG / rac-corpus" arm
design. Scopes a study, not a CI gate.

## Problem

ADR-081 records the open question directly: *"no published proof that
curated decision context lifts agent task success."* The existing grounding
eval (ADR-066, ADR-097, `rac-grounding-eval-benchmark`) proves deterministic
*retrieval* quality on a 12-query fixture corpus against labelled
relevant / must-not-return sets — a regression guard, not a head-to-head and
not a task-success measure. It has no semantic/RAG arm and no downstream
outcome. A credible paper needs a study that holds the retrieved corpus
constant while varying only the grounding method, and measures whether the
agent actually *does the task better* — while keeping the deterministic eval
contract intact.

## Requirements

- [REQ-001] The study MUST compare at least three arms differing only in grounding: (a) none (ungrounded), (b) semantic/RAG retrieval over the same source knowledge, (c) the deterministic rac-corpus retrieval — the arm design recorded in `external-benchmark-evidence`.
- [REQ-002] The semantic/RAG arm, and any optional LLM-judged scoring, MUST be reported as comparative evidence only and MUST NEVER enter the scored or gated path of the deterministic eval (ADR-066, ADR-097); the deterministic retrieval metrics (P@k, R@k, MRR, hard-negative violations, conformance) remain the gated contract.
- [REQ-003] The study MUST include a DOWNSTREAM task-success outcome — the metric ADR-081 calls unproven — scored by executable tests where possible (e.g. the GitChameleon version-conditioned tasks named in `external-benchmark-evidence`) or by a pre-registered human rubric where not.
- [REQ-004] The study MUST use a study-grade query/task set materially larger and more realistic than the current 12-query fixture set, with a declared relevant set and a declared must-not-return (supersession / rejected-approach) set, so the hard-negative head-to-head (RAC vs RAG) is measurable.
- [REQ-005] The study MUST be deterministic and reproducible where it is gated, and every non-deterministic arm MUST pin its harness version, model version, embedding model, and index build, reported alongside results (per the `external-benchmark-evidence` reproducibility posture).
- [REQ-006] The study MUST report its result faithfully, including a null or partial outcome: it does not assume the deterministic arm wins, and a non-lift result is a publishable finding, not a failure to suppress.
- [REQ-007] The study MUST NOT introduce embeddings, vector search, or an LLM judge into `rac-core` itself (ADR-066, ADR-080); the semantic arm is an external comparator built in the benchmarks repository (ADR-092), not an engine feature.

## Acceptance Criteria

- A runnable study harness produces, for the three arms on the same source
  knowledge, the deterministic retrieval metrics for the rac arm plus the
  downstream task-success outcome for all arms, on the study-grade set.
- The rac-core CI eval is unchanged: no embeddings, no LLM judge, no network
  in its gated path; the study's semantic arm lives outside it.
- Re-running the deterministic arm reproduces its numbers exactly; the
  semantic arm reports its pinned model/index versions and its run-to-run
  variance.
- The hard-negative / supersession delta (RAC vs RAG surfacing a
  superseded or rejected decision) is reported as a headline comparison.
- The result is reported whichever way it falls, with the honest framing
  REQ-006 requires.

## Success Metrics

- The study answers ADR-081's open question with third-party-credible
  evidence — a measured task-success delta (in either direction) between
  deterministic decision grounding, semantic RAG, and no grounding — on a
  set a reviewer would accept.

## Risks

- The semantic arm is tuned weakly and the comparison looks like a straw
  man. Mitigation: pin and document a competent, current embedding retriever
  and report its configuration; invite replication via the benchmarks repo.
- Executable task coverage is thin, weakening the downstream outcome.
  Mitigation: REQ-003 allows a pre-registered human rubric where executable
  scoring is unavailable, declared in advance.
- Scope creep turns a paper study into an open-ended benchmark programme.
  Mitigation: this requirement scopes one comparative study for the paper;
  the broader benchmark tables stay in `external-benchmark-evidence`.

## Assumptions

- The `external-benchmark-evidence` "none / RAG / rac-corpus" arm and
  GitChameleon executable scoring are a sound base to extend rather than a
  new harness to invent.
- A version-conditioned or decision-governed task set exists or can be
  curated where the *right* answer depends on a recorded decision an
  ungrounded agent would miss.
- Running a semantic/RAG comparator outside `rac-core` (in the benchmarks
  repository) does not compromise the engine's no-embeddings posture.

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
