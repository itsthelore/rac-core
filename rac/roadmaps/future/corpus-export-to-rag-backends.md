---
schema_version: 1
id: RAC-KVJMA3FF260P
type: roadmap
---
# Corpus Export to External Memory and RAG Backends (Future)

## Status

Planned

Unscheduled — captured as future intent, not yet on a release. This is the
umbrella that generalizes the `lore-supermemory-grounding` item: Supermemory
becomes the first reference adapter under a broader export capability. Gated on
adoption signal; it must not displace nearer-term committed work.

## Context

The agent ecosystem has many places teams push knowledge into "for reference":
fact-extracting memory layers (Supermemory, Mem0, Zep, Letta, Cognee), raw
vector stores (Pinecone, Weaviate, Qdrant, Chroma, Milvus, pgvector, LanceDB),
knowledge-graph / GraphRAG systems (Microsoft GraphRAG, Neo4j, Zep's Graphiti,
Cognee), and managed RAG pipelines (LlamaIndex / LlamaCloud, LangChain, R2R,
Ragie, Vectara). Almost all of them accept the same ingestion shape —
*documents = text + metadata + id* — and the graph-native ones additionally
accept *nodes + typed edges*.

RAC already emits the deterministic source for this: `rac export --json` is a
stable, additive contract (ADR-007, ADR-063), and RAC additionally owns a typed,
validated relationship graph (ADR-055: artifacts are nodes, `supersedes` /
`related_*` are edges). The differentiator is exactly that graph: GraphRAG-style
systems spend LLM effort *inferring* a knowledge graph from raw prose and get it
fuzzily, whereas RAC can hand them the curated, validated decision graph
directly.

So the capability is not "build N backend integrations into the engine" — that
would fight thin-client (ADR-063), not-a-content-store (ADR-024), and
companion-repo (ADR-068) decisions. It is: make the *export* the product (one
stable, ingestion-shaped projection for documents and one for nodes/edges), ship
a small number of reference `lore-*` adapters, and let everyone else consume the
contract. The interplay design `lore-supermemory-interplay` already works out the
one-way, "fuzzy find / deterministic verify" shape this generalizes.

## Outcomes

- RAC can export its corpus — and its relationship graph — to external memory,
  vector, and context-graph backends, one-way, via a stable export contract plus
  reference `lore-*` adapters, with no engine dependency on any backend (ADR-002,
  ADR-068).
- **Published documentation names the supported export targets explicitly, by
  name** (which memory layers, vector stores, and graph/RAG systems an adapter or
  the documented export shape covers), so a reader knows exactly what they can
  push to — never a vague "works with vector databases".
- **Published documentation explains the post-recall validation loop**: how, once
  an agent has used Supermemory (or any backend) for fuzzy recall, it gets the
  "real" answer — re-fetching the authoritative, current artifact from Lore by its
  canonical `id` and filtering retired decisions, so the backend's
  (possibly LLM-rewritten) copy is only ever a pointer, never the citation.
- The graph-native projection (nodes + typed edges) is a first-class output, so
  GraphRAG/Neo4j/Graphiti/Cognee users get RAC's real decision graph instead of
  an inferred one.

## Initiatives

### Initiative 1 — Ingestion-shaped export projections

Provide a stable export suited to ingestion: a flat *documents* projection
(`{ id, type, status, content, metadata }`, JSONL-friendly) for memory/vector/RAG
backends, and a *nodes + edges* projection for graph backends, both derived from
the existing deterministic export (ADR-007). Embeddings are never computed in RAC
— they live in the target (ADR-002, ADR-066).

### Initiative 2 — Reference connectors in one `lore-connectors` companion

Ship a small, honest set of reference connectors as modules in a **single**
`lore-connectors` companion (ADR-073), not one repo per provider and not an
exhaustive matrix: Supermemory first (per `lore-supermemory-grounding`), plus at
least one graph-native target (e.g. Neo4j / Graphiti / Cognee) to prove the
nodes+edges projection. Each is outbound-only; RAC never reads back. A provider
graduates to its own `lore-<provider>` repo only if it becomes an installable
product with independent cadence (the ADR-073 escape hatch).

### Initiative 3 — Documentation that names targets and the validation loop

A published documentation page is part of the deliverable, not an afterthought.
It must:

- **enumerate the supported export targets by name**, grouped (memory layers,
  vector stores, graph/RAG systems), stating for each whether it is covered by a
  shipped adapter or by the documented generic export shape;
- **document the "verify-in-Lore" loop** end to end: fuzzy recall from the
  backend → re-fetch the authoritative artifact from Lore by canonical `id` →
  retired-decision filtering → act on Lore's verbatim text. The doc makes explicit
  that the backend provides recall and RAC provides the authoritative answer, and
  that RAC does not validate the backend's store — verification happens on read,
  in Lore.

## Constraints

- One-way / outbound only: RAC never depends on, calls, or reads back from any
  backend; the engine stays AI-optional and deterministic (ADR-002, ADR-066).
- Adapters are `lore-*` companions, never engine code (ADR-068); RAC does not
  store, serve, or re-import the embedded copy (ADR-024).
- Export grows only additively over the published contract (ADR-007, ADR-063).
- Claims are honest: documentation does not imply RAC verifies or syncs the
  backend's contents; the only guarantee is that the authoritative answer is
  re-fetched from Lore on read.

## Non-Goals

- Building bespoke backend clients into `rac-core` (a maintenance trap and
  contrary to ADR-063 / ADR-024).
- Re-ranking, serving from, or otherwise depending on any backend at read time —
  carried over as a non-goal from `lore-supermemory-grounding` (it breaks
  determinism and the grounding-eval guarantee, ADR-066).
- Computing or storing embeddings inside RAC (ADR-066).

## Success Measures

- A reader of the published docs can name, without ambiguity, every backend the
  capability exports to and which are shipped adapters vs generic-export targets.
- An agent can complete the documented loop: recall a candidate from a backend,
  re-fetch the authoritative artifact from Lore by `id`, and detect a retired
  decision — with the doc's steps alone.
- A graph backend ingests RAC's nodes+edges projection and reflects the real
  `supersedes` / `related_*` topology, not an inferred one.
- The whole capability ships without an engine dependency on any backend.

## Assumptions

- `rac export --json` remains a stable, additive contract carrying `id`, `type`,
  `status`, and the relationship graph (ADR-007, ADR-055, ADR-063).
- The "documents + metadata + id" ingestion shape remains the de-facto common
  denominator across memory/vector/RAG backends, so one documents projection
  serves most targets.
- Adoption signal justifies the build before it is scheduled out of `future/`.

## Risks

- **Target sprawl.** Chasing every backend is unbounded. Mitigation: ship reference
  adapters only; make the documented export shape the product, named targets
  notwithstanding.
- **Staleness across the boundary.** An exported copy drifts from the corpus.
  Mitigation: re-sync on change and the verify-in-Lore loop, which makes the
  exported copy a pointer rather than a source of truth.
- **Over-claiming in docs.** Readers may assume RAC validates the backend.
  Mitigation: the documentation explicitly scopes verification to on-read
  re-fetch from Lore (a named outcome above).

## Related Decisions

- ADR-002
- ADR-007
- ADR-024
- ADR-055
- ADR-063
- ADR-066
- ADR-068
- ADR-073

## Related Roadmaps

- lore-supermemory-grounding

## Related Designs

- lore-supermemory-interplay
