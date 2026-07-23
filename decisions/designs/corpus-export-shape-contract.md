---
schema_version: 1
id: RAC-KVJX3P88JSCA
type: design
---
# Corpus Export Shape for External Memory and RAG

## Status

Proposed

Exploratory — the implementation contract for the export *shape* under the
unscheduled umbrella `corpus-export-to-rag-backends`. The first target is
**Supermemory** (a documents/memory backend), so the `--documents` projection is
the immediate deliverable and `--graph` is specified for later graph backends.
Complements the interplay design `lore-supermemory-interplay` (the one-way,
fuzzy-find/deterministic-verify shape this serializes for).

## Context

The umbrella roadmap commits to a one-way export of the corpus to external
memory, vector, and context-graph backends. This design fixes the wire contract.

Grounding in what `rac export` emits today matters, because the RAG shape is
**not** just the existing JSON:

- `build_corpus_export` (`src/rac/services/export.py`) produces a deterministic
  `CorpusExport` (`schema_version "1"`), already offered in four modes — default
  JSON, `--html` (Portal), `--okf` (one-Markdown-per-artifact bundle, ADR-050),
  and `--agent-rules`. Adding a mode is the established, ADR-007-clean pattern.
- Per artifact it carries `id`, `aliases`, `type`, `status`, `title`, `path`,
  and **`body_html`** — the Markdown body rendered to HTML for the viewer.
- Its `relationships` are flattened to a single untyped **`relates-to`** edge.
  The code reserves richer typing as "a future decision, not an export
  invention", even though the *typed* edges already exist via
  `extract_relationships_full` + `relationship_types.REGISTRY`
  (`supersedes`, `related_decisions`, … with direction and acyclicity).

Two consequences shape this contract:

1. A RAG/memory backend must embed **text, not HTML** — `body_html` is wrong for
   ingestion, so the documents projection emits the **Markdown body** (a new
   field; the raw body is already available via `split_frontmatter`).
2. The graph projection **surfaces the typed edges** — it is exactly the "future
   decision" the export code anticipated, and the differentiator behind "hand
   GraphRAG the real decision graph instead of an inferred one".

## User Need

- **The Supermemory adapter (first target)** needs a stable, ingestion-shaped
  export it can push without re-deriving anything from raw Markdown: one record
  per artifact, clean text, and metadata carrying the canonical `id`, `type`, and
  `status` — so the verify-in-Lore loop can re-fetch the authoritative artifact
  and retired decisions stay filterable on read.
- **A graph backend (later — Neo4j / Graphiti / Cognee)** needs typed nodes and
  edges so it receives RAC's real, validated decision graph rather than one an
  LLM infers from prose.

## Design

Two additive projection modes, beside `--okf` / `--html` / `--agent-rules`. The
v1 viewer JSON (`CorpusExport.to_dict`) is left untouched (ADR-007); each new
projection carries its own `schema_version` and grows only additively.

### `--documents` — the immediate, Supermemory-first deliverable

JSONL (the de-facto ingestion shape), one object per artifact:

```json
{"schema_version":"1","id":"RAC-KVJK92SM2A1R","type":"decision","status":"Accepted",
 "title":"ADR-072: Document Ingestion Parser Is markitdown",
 "text":"## Context\n…(Markdown body, frontmatter stripped)…",
 "metadata":{"path":"rac/decisions/adr-072-…md","aliases":["ADR-072"],"tags":[],"source":"rac"}}
```

- `text` is the **Markdown body**, not `body_html`.
- **One document per artifact — no chunking.** The artifact is the atomic
  knowledge unit (ADR-004, ADR-010); chunking is the embedder's job and keeping
  the unit whole stays deterministic.
- `id` is the canonical opaque RAC identity (ADR-026) — the hook the
  verify-in-Lore loop re-fetches by; `status` rides along so a retired or
  superseded decision is filterable on read.
- **All classified artifacts are included**, with `status` stamped — not dropped
  — so the export stays complete; a stale hit is safe because the verify step
  re-fetches and the status is present.
- Determinism is preserved exactly as the existing export: sorted-path order, no
  timestamps (ADR-002).

#### Supermemory mapping (the first adapter)

Each JSONL line maps to `add({ content: text, containerTag: source,
metadata: { id, type, status, title, path } })`. The connector is a module in the
shared `lore-connectors` companion (ADR-073), outbound-only; embeddings live in
Supermemory, never in RAC (ADR-002, ADR-066).

### `--graph` — later, for graph backends (not Supermemory)

```json
{"schema_version":"1","source":"rac",
 "nodes":[{"id":"RAC-…","type":"decision","status":"Accepted","title":"ADR-072: …"}],
 "edges":[{"source":"RAC-072","target":"RAC-059","type":"related_decisions","directed":false},
          {"source":"RAC-new","target":"RAC-old","type":"supersedes","directed":true}]}
```

- Edge `type` comes straight from `relationship_types.REGISTRY`; `directed` from
  `edge_spec.directional` (`supersedes` directed, `related_*` undirected).
- Resolved targets become canonical-id edges; unresolved references keep their
  literal target with `resolved:false` (no phantom nodes), mirroring how the
  current export preserves unresolved targets verbatim.
- Surfacing typed edges is the reserved "future decision", so this projection
  carries **its own short ADR** when it is scheduled — it is out of scope for the
  Supermemory-first phase.

## Constraints

- Additive only (ADR-007, ADR-063): new modes, stable lowercase-snake field
  names, a `schema_version` per projection; the viewer JSON contract is unchanged.
- Deterministic and offline; no embeddings, vectors, or LLM in RAC
  (ADR-002, ADR-066).
- One-way: the connector is a module in the `lore-connectors` companion
  (ADR-073); RAC does not store, serve, or re-import the embedded copy (ADR-024).
- Text only for the first phase; asset references (ADR-019) are out of scope.
- Unknown-type files are skipped; invalid-but-recognizable artifacts export as
  classified — the same gate the existing export applies.

## Rationale

- JSONL, one document per artifact, is the lingua franca of memory/vector/RAG
  ingestion and keeps RAC's atomic unit and determinism intact.
- Markdown over HTML: backends embed text; HTML tags are noise that pollutes
  retrieval.
- Include-all-with-status over a live-only default: completeness and determinism,
  and the verify-in-Lore loop already makes a stale hit safe; the `status` field
  lets the adapter or agent filter when it wants live-only.
- Separate modes over extending the viewer JSON: mirrors `--okf` / `--html`, and
  protects the locked viewer contract from churn.
- Lead with `--documents` because the first target, Supermemory, consumes
  documents, not a graph; the graph projection composes in later without
  reworking the documents one.

## Alternatives

- **Reuse the existing `--json` payload directly** — rejected: its body is HTML
  and its edges are untyped `relates-to`; both are wrong for ingestion.
- **Chunk per section** — rejected for the first phase: non-atomic, less
  deterministic, and the embedder's job; revisit only if whole-artifact
  embedding proves too coarse for recall.
- **Drop retired artifacts (live-only default)** — rejected as the default: loses
  completeness; offered instead as an opt-in (`--live-only`, an open question).
- **One combined mode emitting documents and graph together** — rejected:
  different consumers (memory vs graph); separate modes compose better and
  Supermemory needs only documents.

## Accessibility

This is primarily a machine contract, but the accessibility concern is
*provenance legibility*: every record carries the canonical `id` and `status`, so
a human auditing what an agent recalled can always trace a memory back to the
authoritative, current Lore artifact rather than to the backend's rewritten copy.

## Style Guidance

- JSONL for `--documents` (one UTF-8 JSON object per line, stable key order);
  `--graph` emits a single whole-graph JSON object.
- Field names are lowercase snake_case and grow only additively (ADR-007).
- Mode naming stays consistent with the existing flags
  (`--documents`, `--graph` beside `--okf` / `--html` / `--agent-rules`).

## Open Questions

- A `--live-only` opt-in to drop retired/superseded artifacts for recall-focused
  ingests.
- Whether `--documents` metadata should also carry an artifact's outgoing typed
  edges (its related ids), so a single memory knows its neighbours, or whether
  that stays solely in `--graph`.
- The `--graph` output format (single JSON vs JSONL with a `kind` discriminator)
  and unresolved-edge handling — settle when that projection is scheduled.
- The typed-edge ADR (surfacing `REGISTRY` edge types) — author when `--graph`
  lands.
- The `containerTag` / `source` scheme for multi-repo ingestion (per-repo vs
  per-series).

## Related Requirements

- rac-agent-context-guide

## Related Decisions

- ADR-002
- ADR-004
- ADR-007
- ADR-010
- ADR-019
- ADR-024
- ADR-026
- ADR-050
- ADR-055
- ADR-063
- ADR-066
- ADR-068
- ADR-073

## Related Roadmaps

- corpus-export-to-rag-backends
- lore-supermemory-grounding
