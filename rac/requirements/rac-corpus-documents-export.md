---
schema_version: 1
id: RAC-KVK19KCJDCY6
type: requirement
tags: [user-facing, export, rag, ingestion, determinism]
---
# Requirement: Corpus Documents Export

## Status

Accepted

Classification: `[user-facing]` — get the corpus into external memory/RAG
backends. Delivered in v0.25.0 (WS1): `rac export --documents`. A deterministic,
ingestion-shaped JSONL projection derived from the existing export; no AI,
additive output (ADR-007).

## Problem

`rac export` today produces a viewer-shaped payload: each artifact's body is
rendered to HTML (`body_html`) and offered for the Portal. That is the wrong shape
for an external memory or RAG backend, which ingests **text** plus metadata, not
HTML. A team that wants its recorded decisions available to an agent's memory tool
(Supermemory first, then any vector/RAG store) has no clean, stable way to feed
them in — they would have to scrape raw Markdown and re-derive identity and status
themselves. RAC should emit an ingestion-ready projection so the backend handles
recall and Lore remains the authoritative source the agent verifies against.

## Requirements

- [REQ-001] RAC MUST provide an additive `rac export --documents` mode that emits one record per classified artifact as JSON Lines (one object per line), deterministically and offline, without altering the existing default export payload — the v1 viewer contract (ADR-007, ADR-002).
- [REQ-002] Each record MUST carry the artifact's canonical opaque `id` (ADR-026), its `type`, its canonicalized `status`, its `title`, and a `text` field containing the artifact's Markdown body (frontmatter stripped) — not rendered HTML — so a backend embeds clean text.
- [REQ-003] Each record MUST carry metadata sufficient for the verify-in-Lore loop and for namespacing: at least the canonical `id`, `type`, `status`, source `path`, `aliases`, `tags`, and a corpus `source` name, so an agent can re-fetch the authoritative artifact from Lore by `id` and a retired `status` is distinguishable on read.
- [REQ-004] The export MUST emit one record per artifact as the atomic unit (ADR-004, ADR-010); it MUST NOT chunk artifacts into sub-records — chunking is the embedder's responsibility.
- [REQ-005] All classified artifacts MUST be included with their `status` stamped — retired and superseded artifacts are not dropped — so the projection is complete and the agent or connector filters on read; unknown-type files are skipped, exactly as the existing export gate behaves.
- [REQ-006] Output MUST be deterministic: identical corpus bytes produce a byte-identical projection across runs (sorted order, no timestamps), with no AI/LLM/embeddings and no network in the export path (ADR-002, ADR-066).
- [REQ-007] The projection MUST NOT embed RAC-side embeddings or vectors; it carries text and metadata only, leaving embedding to the consuming backend (ADR-066).

## Acceptance Criteria

- `rac export --documents` over a fixture corpus emits valid JSONL, one line per
  classified artifact, each line carrying `id`, `type`, `status`, `title`, `text`
  (Markdown, not HTML), and the metadata block.
- The default `rac export` (viewer JSON) output is unchanged byte-for-byte —
  `--documents` is purely additive.
- Two runs over an unchanged corpus produce byte-identical output; no network
  access occurs.
- A superseded decision appears in the output with `status` reflecting that, not
  omitted.

## Success Metrics

- A maintainer pipes `rac export --documents` into a backend's ingestion
  (Supermemory first) with no RAC-side per-provider code, and an agent completes
  the verify-in-Lore loop from the resulting memories.

## Risks

- The projection drifts from the viewer contract or accidentally changes it.
  Mitigation: REQ-001 makes it a separate additive mode; the viewer JSON is
  asserted unchanged.
- Output is non-deterministic (ordering, timestamps). Mitigation: REQ-006 and
  byte-stable goldens.

## Assumptions

- The existing export already resolves `id`/`type`/`status` and the Markdown body
  is recoverable (frontmatter split), so the projection needs no new schema.
- The "documents + metadata + id" shape is the common ingestion denominator across
  memory/vector/RAG backends.

## Related Decisions

- adr-002
- adr-004
- adr-007
- adr-010
- adr-026
- adr-050
- adr-063
- adr-066

## Related Designs

- corpus-export-shape-contract

## Related Roadmaps

- v0.25.0-connect
