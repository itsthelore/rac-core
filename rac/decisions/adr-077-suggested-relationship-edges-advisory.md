---
schema_version: 1
id: RAC-KVSNP0M66V2V
type: decision
---
# ADR-077: Suggested Relationship Edges Are Advisory and Never Auto-Applied

## Context

RAC's relationship graph is authoritative because every edge is *declared* in a
`## Related <Type>` section and *validated* — the export surfaces "RAC's
validated decision graph rather than one inferred from prose" (ADR-074). That
property is the product: agents and backends trust the graph precisely because a
human wrote and reviewed each edge (ADR-065 — artifact content is untrusted
until human PR review makes it authoritative).

But the same property leaves a gap. Artifacts constantly name each other in
prose — an ADR id, a requirement, a design slug — without a matching declared
edge. The link is real and intended; the graph just doesn't carry it. `rac
doctor` already finds orphans (nothing links *to* an artifact) but cannot find a
link the author plainly meant and merely forgot to promote.

A tempting fix is to do what general agent-memory tools (e.g. GBrain) do:
deterministically scan text and *auto-wire* the edges. RAC must not — auto-wired
edges are exactly the "inferred from prose" graph ADR-074 rejects, and they
would bypass the human-review trust boundary (ADR-065). Equally, RAC must not
reach for an LLM to judge whether two artifacts are related: the core is
AI-optional and offline (ADR-002), and grounding stays deterministic with no
embeddings or LLM judge (ADR-066). The open question is how to close the gap
*without* crossing either line.

## Decision

RAC adds a deterministic detector that surfaces **mentioned-but-unlinked
references** — body references to other artifacts that are not present in the
source artifact's declared `## Related` sections — as **advisory suggestions**,
under three firm boundaries:

- **Suggest, never apply.** The detector reports a candidate edge and the
  `## Related <Type>` line that would capture it. It never creates, writes, or
  modifies an edge. A human promotes a suggestion through normal review. The
  declared `## Related` sections remain the single source of truth for the graph
  (ADR-074); what is inferred is a *suggestion*, never an *edge*.
- **Deterministic, no AI.** Matching reuses the existing reference resolver and
  token-boundary matching (ADR-037): canonical ids, declared aliases, and
  filename-style references only. No model, embedding, or network call enters
  the path (ADR-002, ADR-066). Identical corpora produce byte-identical
  findings.
- **Advisory, never a gate.** Findings are warnings that exit zero. A
  mentioned-but-unlinked reference does not fail `rac validate` or
  `rac relationships --validate` and cannot block a merge on its own, so an
  intentional prose mention is never *forced* to become a declared edge.

## Consequences

The validated graph gains a completeness signal — a worklist of links the text
already implies — without losing the property that makes it trustworthy: every
edge that exists is still human-declared and validated. The detector is the
deterministic, in-domain half of what auto-wiring tools do, kept on RAC's side
of the inference line.

Trade-offs accepted: the detector can produce false positives (a body may name
an artifact it is not "related" to in the graph sense); this is mitigated by
high-precision id/alias/filename matching and by advisory-only severity, so a
false positive costs a glance, never a bad edge. Title-based matching is
deliberately out of scope at first because titles are prose-like and noisy (a
deferred question, not a hard exclusion). Because suggestions are not applied,
the graph never improves on its own — closing a suggestion is always a human
edit, which is the point.

## Status

Proposed

## Category

Architecture

## Alternatives Considered

- **Auto-create the edges from prose.** Rejected: this is the "inferred from
  prose" graph ADR-074 rejects, and it bypasses the human-review trust boundary
  (ADR-065). An edge nobody reviewed is not a validated edge.
- **Use an LLM to suggest related artifacts.** Rejected: non-deterministic and
  contrary to the AI-optional, offline core (ADR-002) and the no-embeddings,
  no-LLM-judge grounding stance (ADR-066). Deterministic id/alias matching is
  the reusable, testable piece RAC is uniquely placed to own.
- **Make a mentioned-but-unlinked reference a validation error.** Rejected: it
  would force every prose mention to become a declared edge, erasing the
  author's intent (a body may legitimately name an artifact without a graph
  relationship) and turning a helpful nudge into a merge blocker (against the
  gate discipline of ADR-075).
- **Do nothing; rely on manual review.** Rejected: the orphan check already
  shows the value of surfacing graph gaps, and this gap — a link the author
  already wrote in prose — is the most recoverable of all. Leaving it manual
  forgoes a deterministic, low-cost win.

## Related Decisions

- adr-074
- adr-065
- adr-066
- adr-002
- adr-037

## Related Requirements

- rac-unlinked-reference-detection

## Related Designs

- mentioned-but-unlinked-detection

## Related Roadmaps

- v0.28.0-link-suggestions
