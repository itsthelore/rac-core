---
schema_version: 1
id: RAC-KWPC5RFTWA8G
type: design
---
# Design: SWE-CompletenessBench — Artifact-Completeness Diagnostic

## Status

Proposed

The design of **SWE-CompletenessBench**, the benchmark recorded by the
`artifact-completeness-benchmark` roadmap. It measures how completely a
recorded corpus specifies a system by reconstructing a component from its
Lore artifacts and reporting the *residual* that cannot be recovered. The
framing is a completeness diagnostic, not a reconstruction scoreboard — the
guardrail that keeps it clear of the spec-as-source lane the corpus refuses
(ADR-081). The harness lives in `rac-benchmarks` (ADR-092); this is its
design, referenced in prose because there is no corpus edge for an
external-repository artifact.

## Context

The corpus records both a thesis and its honest frontier. Thesis: durable,
typed, human-ratified decision knowledge is the layer coding agents miss
(ADR-081). Frontier: tacit product knowledge is built from *unrecorded*
observable decisions, and capture-at-the-moment is the single capability
Lore flags as absent (`growth-essay-mapping`, Row 6 — "the absence itself is
honest essay material"). Nothing measures that frontier. A reconstruction
benchmark can — if it reports the *gap*, not the rebuild.

The design must clear one landmine. "Rebuild the system from the spec" reads
as spec-as-source — code generated from specifications — which the corpus
refuses in four places (ADR-081: "Lore is not an SDD/codegen tool";
`decision-grounding-thesis`; `commercial-layer-positioning` discipline
boundary; ADR-036). The reframe is what makes it safe and on-thesis: the
metric is completeness, the hero number is the residual, and Lore never
generates.

## User Need

The **research/practitioner** audience needs the tacit frontier made
measurable — "how much of a system is knowable from what a team wrote down."
**Teams adopting Lore** need to know which artifact families carry the most
reconstruction signal, so they record what matters. The **maintainer** needs
a completeness pillar to sit beside SWE-DecisionBench's adherence pillar in
the paper, without any claim that Lore generates code.

## Design

### The task

Given a target component and its recorded Lore artifact bundle (the
requirements, decisions, and designs that govern it), an **external,
bring-your-own coding agent** reconstructs the component. Lore's only role is
to *serve* the recorded corpus deterministically (ADR-002, ADR-036) — it does
no generation. The build runs entirely in `rac-benchmarks`.

### The arms (isolate the variable)

Four arms feed the same fixed answering agent with the same scaffold, so only
the knowledge source varies:

- `none` — the task, no recorded knowledge.
- `RAG` — the same artifacts, retrieved semantically (embedding + top-k).
- `rac-corpus` — the same artifacts, served deterministically by Lore
  (typed, whole-artifact, relationship-aware).
- `oracle` — the full original source as a ceiling arm.

### The metrics (deterministic, executable, ADR-066/097-native)

Scoring is the target's own executable tests — no LLM judge, no embeddings in
the scored path, offline, byte-stable metrics, human-gated baseline.

- **Residual = oracle − rac** — the hero metric: the fraction of tested
  behaviour recoverable from full source but *not* from the recorded
  artifacts. This is the measured tacit frontier.
- **Reconstruction pass-rate per arm** — a *proxy* for completeness, reported
  but never the headline (leading with it drifts spec-as-source).
- **Lift = rac − none / rac − RAG** — does recorded knowledge move
  reconstruction toward the ceiling, and does typed deterministic serving
  beat semantic retrieval.
- **Per-artifact-family ablation** — hold out requirements vs decisions vs
  designs to attribute reconstruction signal, answering "what is worth
  recording."

### Family and lineage

A new `rac-benchmarks` subdir under the ADR-097 benchmark-family contract
(shared harness, CLI-only, zero engine imports). It extends the SWE-* lineage
as a fourth node: SWE-bench (issue *resolution*) → SWE-ContextBench (episodic
*context*) → SWE-DecisionBench (governing-*decision* adherence) →
**SWE-CompletenessBench** (*completeness* of the record).

## Constraints

- Lore serves, never generates (ADR-002, ADR-036); the answering agent is
  external and BYO; all building lives in `rac-benchmarks`, never `rac-core`
  (ADR-092).
- Deterministic executable scoring; no embeddings or LLM judge in the scored
  path; byte-stable metrics; human-gated baseline (ADR-066, ADR-097).
- The headline is the residual/completeness; reconstruction pass-rate is a
  proxy. Never a "Lore rebuilds systems" claim (ADR-081).

## Rationale

Reporting the residual instead of the rebuild is the whole design. It turns a
dangerous claim (we generate systems from specs) into an honest one (this is
how much of a system a team's recorded decisions actually pin down), which is
exactly the corpus's own recorded frontier made empirical. It composes with
SWE-DecisionBench without duplicating it: DecisionBench holds the corpus
constant and varies grounding on a per-patch task (adherence lift);
CompletenessBench holds "recorded-only" constant and measures whole-component
completeness (the residual). Together they answer "does recorded knowledge
help" and "how complete is it."

## Alternatives

- **Report reconstruction success rate as the hero number.** Rejected: it
  reads as spec-as-source and forfeits the positioning (ADR-081), regardless
  of internal intent.
- **Put the generator in `rac-core` (a `rac rebuild` command).** Rejected:
  makes Lore the assembler it is positioned beneath (ADR-081,
  `commercial-layer-positioning`); generation is never the engine's job
  (ADR-002).
- **LLM-judged reconstruction similarity.** Rejected: violates the ADR-066
  scored-path posture; executable tests are the deterministic outcome.

## Accessibility

Not a user interface. The bar is argument legibility: a reader can trace the
residual number to the arms and the executable scoring without access to this
corpus, and can see from the framing that Lore served but did not generate.

## Style Guidance

Every external artifact leads with residual / completeness, never
reconstruction success. The answering agent is described as external and BYO.
Cite the SWE-bench family as lineage without implying endorsement. Report the
residual faithfully, including a large gap.

## Open Questions

- Dataset sourcing and N: how far beyond the `rac-core` dogfood MVP (OSS with
  ADRs? synthetic?) before the result is credible.
- Naming: keep **SWE-CompletenessBench**, or foreground recoverability
  (SWE-ArtifactRecoverability) — settle before external publication.
- The external-misread risk: how prominently to state the "not spec-as-source"
  boundary in the benchmark's own local ADR.
- Which answering agent(s) and model versions define the reference run, and
  how the oracle ceiling is bounded fairly.
- Whether the per-family ablation needs its own scored contract or is a
  reported secondary analysis.

## Related Requirements

- rac-artifact-completeness-study

## Related Decisions

- adr-002
- adr-036
- adr-066
- adr-081
- adr-092
- adr-097

## Related Roadmaps

- artifact-completeness-benchmark
- decision-grounding-paper
- external-benchmark-evidence
