---
schema_version: 1
id: RAC-P61BA5EDE7A0
type: decision
tags: [performance, freshness, rust, incremental]
---
# ADR-119: Base-Plus-Delta Serving Generations

## Status

Accepted

## Context

The native freshness tracker parses changed files incrementally, but it still
rebuilds every derived structure for each change. After compaction it also
sheds the parsed snapshot, so the first later edit reparses the entire corpus.
Those choices cap resident memory, but make mutation latency scale with corpus
size even when one file changed.

P6 needs a stable correctness boundary before search postings, graph indexes,
scope rows, and summaries can become incremental independently. Without that
boundary, partially updated structures could leak into serving or disagree
about which corpus generation they represent.

## Decision

The native tracker adopts an immutable base-plus-delta generation model:

`live documents = (base documents - tombstoned base docids) + delta upserts`

- A generation contains one immutable base, cumulative upserts, cumulative
  tombstones, a base generation number, a serving generation number, and a
  canonical sorted changed-path set.
- A rename is a tombstone for the old path plus an upsert for the new path.
- A candidate generation is staged away from the served generation. It is
  published only after every structure required by that slice has completed.
- Canonical manifest order remains docid order and therefore preserves the
  existing path tie-breaks and byte-parity contract.
- Compaction writes a complete replacement base, opens it successfully, then
  atomically promotes the overlay. Failure keeps serving the prior complete
  in-memory generation; incomplete incremental parsing falls back to a fresh
  full parse and derive.
- The parsed base remains resident after P6 compaction, removing snapshot shed
  from the P6 path so the first later edit stays change-bound.

P6 is delivered in referee-gated slices. P6.1 implements the document overlay
and generation publication boundary behind an explicit preview constructor. It
still derives the complete read model from live documents and is not used by
the default CLI or MCP server. Later slices may incrementally maintain:

1. identity, path, aliases, status, and point resolution;
2. token vectors, postings, and exact global search statistics;
3. graph edges, adjacency, and inbound counts;
4. scope rows, live-decision state, and portfolio summary counters; and
5. durable compaction without snapshot shedding.

P6.2 implements item 1 behind the same preview boundary. Identity and status
rows are shared across generations, changed rows and tombstones are staged in
the overlay, and exact point resolution reads the published identity generation.
The complete derived model remains a referee and the default serving path is
still unchanged.

P6.3 implements item 2. Token rows and compacted postings are immutable shared
bases; changed rows and tombstones form the search overlay. Candidate discovery,
filters, field vectors, and exact corpus-global BM25 statistics read that
overlay. Inbound graph counts still come from the complete referee until item 3.

No slice becomes the default until mutation referees show byte-identical output
against a fresh whole-corpus rebuild and scale tests show bounded regression.

## Consequences

P6.1 makes the publication and lifecycle rules executable without changing
production behavior. Add, edit, delete, rename, compaction, and first-edit-after-
compaction tests compare the preview's persisted segments byte-for-byte with a
fresh derivation.

P6.2 adds identity/status and exact-resolution referees for those mutation
classes, including casefolded aliases and duplicate identities. Staging shares
the compacted base maps and clones only the bounded overlay; compaction reuses
unchanged identity rows.

P6.3 extends the same mutation referee to complete search payloads, including
prefix/AND candidates, duplicate query tokens, type/tag/live filters, snippets,
scores, ranks, and ordering. Staging shares the compacted token and posting
bases and clones only the bounded overlay.

The first slice does not claim mutation-latency improvement for derivation: it
still materializes live documents and rebuilds all derived structures. Its
performance win is limited to keeping parsing change-bound after compaction.
The intended latency gains arrive as the later derived overlays replace that
full referee one structure family at a time.

Keeping the parsed base resident trades memory for predictable mutation
latency. Compaction thresholds and scale measurements must bound both the
overlay lookup cost and the retained memory before default adoption.

## Alternatives Considered

### Mutate the currently served structures in place

Rejected. A failure could expose a generation where identity, search, graph,
and summary disagree.

### Make P6.1 the default immediately

Rejected. The first slice establishes architecture and correctness but still
pays full derivation cost and retains more memory.

### Keep snapshot shedding and reparse after every compaction

Rejected for the P6 path. It makes the first edit after compaction depend on
total corpus size, contradicting the change-bound target.

## Related Decisions

- ADR-099
- ADR-103
- ADR-104
- ADR-105
- ADR-107
- ADR-116
- ADR-118
