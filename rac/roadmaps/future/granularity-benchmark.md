---
schema_version: 1
id: RAC-KWTW1C1C11QZ
type: roadmap
---
# Granularity Benchmark

## Status

Planned

Unscheduled — captured as future intent and being executed in the benchmarks
repository. Records the intent to measure, rather than assert, the retrieval
impact of artifact granularity: one artifact per file (the RAC model) against
a monolithic canon rendering of the same knowledge (every decision
concatenated into one document, every requirement into another).

## Context

ADR-010 records that documents are not artifacts, and the one-artifact-per-
file model rests on it — but its rationale is qualitative, and no benchmark
in the family measures what granularity is worth. Every existing member
holds granularity constant and varies a different axis: the decision-
grounding benchmark varies context assembly over a fixed per-file corpus,
the scale member varies corpus size, and the per-tool benchmarks use one
fixture corpus each.

The engine itself cannot represent a canon file as many artifacts — the
file-size cap, single frontmatter identity, duplicate-section collapse, and
artifact-level relationship resolution all refuse it — so the canon arm is
honestly framed as what teams actually do with monolithic documents: chunk
them by heading and search the chunks lexically.

## Outcomes

- A measured answer to what granularity buys or costs: the same knowledge
  content, rendered per-artifact and as canon documents, queried by the
  same deterministic query set, scored by the same deterministic metrics.
- The supersession defense quantified: whether a monolithic rendering can
  keep superseded decisions out of results at all, at any corpus size.
- A quality-versus-size curve per arm across the one-thousand, ten-thousand,
  and hundred-thousand artifact ladder, aligned with the scale member.
- Evidence attached to ADR-010 that is rerunnable from a seed, in the
  family's scorecard shape.

## Initiatives

- A deterministic corpus builder emitting both renderings from one source
  of truth, with supersession chains and requirement-to-decision references;
  the per-artifact variant passes validation and relationship checks.
- A typed-retrieval arm served warm from the persistent index over the
  per-artifact variant, and a canon arm chunking the monolithic documents
  by heading and ranking chunks with the same lexical scorer.
- Family-contract scoring — precision and recall at cut-offs, mean
  reciprocal rank, and full-list must-not-return violations — reported per
  arm per size as an evidence run, never a merge gate.

## Success Measures

- Two runs on an unchanged corpus produce byte-identical metrics blocks.
- Every metric is reported in both directions honestly, including any the
  canon arm wins; the result table shows the per-size curve for each arm.

## Assumptions

- Scoring stays deterministic and offline — no embeddings, no model judge
  (ADR-066); both arms share one lexical ranking so granularity and typing
  are the only variables.
- The benchmarks repository consumes the engine strictly as an external
  CLI and server on the path, never as an import.

## Risks

- Synthetic vocabulary can understate or overstate the granularity effect;
  the generator's pools and the query classes are recorded with the corpus
  manifest so the construction is auditable, and a real-corpus case can be
  added later without changing the contract.
- A chunking choice that is too naive would strawman the canon arm; the
  chunker follows the canon documents' own heading structure, which is the
  strongest simple treatment such a document supports.

## Related Decisions

- RAC-KTQ63DQ2AEJZ
- RAC-KV6KFCC8MHTM
- RAC-KWFVA38YT2C0
- RAC-KWS8TRXGQWHC

## Related Roadmaps

- single-node-scale
