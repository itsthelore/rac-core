---
schema_version: 1
id: RAC-KVJJ8T5ARA28
type: roadmap
---
# Lore × Supermemory — Complementary Grounding (Future)

## Status

Planned

Unscheduled — captured as future intent, not yet on a release. This is a
considered direction gated on adoption signal; it must not displace nearer-term
committed work.

## Context

The agent-memory field — Supermemory, Mem0, Zep, Letta — is converging on
*fuzzy* memory: vector recall, LLM-rewritten "memories", recency decay. All of
it trades determinism for associative reach. Lore is the opposite: a
deterministic, auditable system-of-record for the decisions a team has already
made (ADR-066, ADR-002), built on the open-source RAC engine and shipped under
the Lore brand (ADR-036, ADR-039, ADR-068).

That contrast is the opportunity. Rather than compete with memory tools, Lore
can be **the authority they ground against** — the layer a fuzzy memory cites so
its agents stop guessing. Supermemory (MIT, self-hostable, with an MCP server
and SDKs) is the natural first partner: an agent can co-mount both, recall
loosely from Supermemory, then verify verbatim in Lore.

The companion design `lore-supermemory-interplay` works out the *how* and
settles the safe shape: a one-way RAC → Supermemory ingest adapter plus a
"fuzzy find, deterministic verify" agent loop, with re-rank and memory-router
couplings explicitly rejected because they would put a non-deterministic
component in Lore's serving path. This roadmap records the *what and why*: the
product intent and the positioning, kept as recorded intent rather than a
scheduled release.

## Outcomes

- Agents gain semantic recall over a team's recorded decisions — closing Lore's
  keyword-search paraphrase gap (ADR-037, ADR-038) — **without** losing the
  determinism and auditability that are Lore's whole value.
- Lore is positioned in the memory market as the deterministic system-of-record
  that fuzzy memory tools ground against, not as one more memory tool (ADR-024,
  ADR-017) — owning the correctness/governance axis the category lacks.
- A shippable, low-effort integration (a `lore-*` companion, ADR-068) lets Lore
  ride a partner's distribution while reinforcing its own authority niche.

## Initiatives

### Initiative 1 — One-way ingest adapter (a `lore-*` companion)

Build `lore-supermemory`: read `rac export --json` and push each artifact into
Supermemory (`add` with `containerTag` and `metadata` carrying the canonical
`id`, `type`, `status`), re-syncing on change. Outbound-only — RAC never depends
on or reads back from Supermemory, and `rac-core` needs no change. The
implementation contract lives in the design `lore-supermemory-interplay`.

### Initiative 2 — Positioning and the co-marketing recipe

Publish an integration recipe ("ground Supermemory in your team's decisions")
and the positioning that frames Lore as *the authority memory tools cite*. The
wedge: ride Supermemory's larger distribution while sharpening Lore's distinct
category — **"memory you can audit."** Vocabulary stays disciplined: Lore
*grounds* and is authoritative; memory tools *recall* and are associative.

### Initiative 3 — Deferred: re-rank / memory-router experiment

Recorded as considered and **deferred**, not adopted. A semantic re-rank of
Lore's results, or a memory-router proxy in the model's serving path, was
rejected for the determinism cost (see the design's Alternatives). Revisit only
as a fenced `lore-*` experiment, never in core, and only if Initiative 1's
parallel-surface recall proves insufficient in practice.

## Constraints

- The integration is a `lore-*` companion, never engine code in `rac-core`
  (ADR-068); RAC stays the deterministic, AI-optional core (ADR-002).
- Data flows one way (RAC → Supermemory). RAC gains no dependency on, and no
  read path from, the memory layer.
- RAC is not a content store (ADR-024); the embedded copy lives in Supermemory,
  and authoritative text is always re-fetched from Lore.

## Non-Goals

- Re-ranking or reordering Lore's served results with a semantic model — it
  breaks determinism and desyncs from the grounding-eval (ADR-066).
- A memory-router proxy that puts a fuzzy/AI component in the model's serving
  path (contra ADR-002, ADR-067).
- Serving or shadowing decision reads *from* Supermemory instead of Lore.
- Embeddings, vector indexing, or an LLM judge inside `rac-core` (ADR-066).

## Success Measures

- An agent can recall a relevant recorded decision from a paraphrased,
  zero-keyword-overlap query and then verify it verbatim in Lore.
- Evidence (usage signal or user research) that agents miss decisions for lack
  of semantic recall — the signal that would schedule Initiative 1 out of
  `future/`.
- The integration ships without any change to `rac-core`'s engine, contract, or
  determinism guarantees.

## Assumptions

- `rac export --json` remains a stable, additive contract carrying `id`, `type`,
  and `status` (ADR-007, ADR-063).
- Supermemory (or an equivalent semantic-memory layer) stays self-hostable and
  exposes an ingest API, so the integration imposes no cloud dependency on
  adopters.
- The paraphrase gap in Lore's keyword search is a real adoption friction worth
  closing — to be confirmed before scheduling.

## Risks

- **Staleness / dual copy.** Supermemory holds a rewritten copy that can drift
  from the corpus; mitigated by re-sync on change and by treating its copy as a
  pointer, with verify-in-Lore as the authoritative step.
- **Discipline drift.** The benefit depends on agents following the
  fuzzy-find/deterministic-verify loop; if they cite Supermemory's rewritten
  text directly, authority is lost. Mitigated by metadata carrying the canonical
  `id` and by prompt/skill guidance.
- **Positioning blur.** Marketing Lore alongside memory tools risks it being
  mistaken for one; mitigated by holding the "authority, not memory" line
  (ADR-024, ADR-017).

## Related Decisions

- ADR-002
- ADR-017
- ADR-024
- ADR-036
- ADR-039
- ADR-066
- ADR-068

## Related Designs

- lore-supermemory-interplay
