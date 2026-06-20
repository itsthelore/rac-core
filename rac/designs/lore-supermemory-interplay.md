---
schema_version: 1
id: RAC-KVJJ8RSWP0SV
type: design
---
# Lore × Supermemory Interplay

## Status

Proposed

Exploratory — this records the implementation approach for a possible
integration so the reasoning lives in the corpus, not a tool's scratch space
(ADR-047). It is not an accepted build; the unscheduled umbrella is the future
roadmap `lore-supermemory-grounding`.

## Context

Supermemory (github.com/supermemoryai/supermemory, MIT) is a semantic memory
and context-management layer for LLM agents: hybrid vector + keyword search, an
ingestion step that uses an LLM to rewrite raw input into extracted "memories",
recency decay, `containerTag` namespacing, an MCP server (`addMemory` /
`search`), Python and TypeScript SDKs, and an OpenAI-compatible memory-router
proxy. It is self-hostable and can run fully offline with local embeddings.

Lore is the agent-facing surface of RAC: five read-only MCP tools
(`get_artifact`, `search_artifacts`, `find_decisions`, `get_related`,
`get_summary`) over a deterministic, byte-stable engine, with stateless reads
(ADR-032) and a bounded response (ADR-033). RAC's recorded decisions draw a hard
line around what the engine may do: no embeddings, vector index, or LLM judge in
the scored/served path (ADR-002, ADR-066); no semantic verdicts in the engine
(ADR-067); RAC is not a content store (ADR-024); non-Python clients are thin
clients over the published contract (ADR-063); companion products live in
`lore-*` repos, not in `rac-core` (ADR-068).

The two products sit at opposite ends of one axis — **determinism**. Lore is the
deterministic system-of-record; Supermemory is fuzzy, associative working
memory. They are therefore complementary, not competing, and the recorded
decisions point to exactly one safe shape: run them side by side and feed Lore's
knowledge *into* Supermemory one-way, never the reverse, and never by putting a
fuzzy component inside Lore's serving path.

## User Need

An agent (and its operator) working a task wants two different things:

- **Authority** — "what has this team already decided about X, in its exact,
  current wording?" That is Lore's job, and its value is that the answer is
  deterministic and auditable.
- **Recall** — "have we touched anything *near* this idea?", asked in loose
  natural language that may share no keywords with the recorded decision. Lore's
  native search is deterministic but token-boundary / keyword-tier
  (ADR-037, ADR-038), so it misses paraphrases and synonyms. Supermemory's
  semantic search closes that gap.

The need is to get recall **without** surrendering authority — to add fuzzy
discovery as a clearly-separate surface, so the agent always knows which results
are authoritative (Lore) and which are merely associative (Supermemory).

## Design

### Topology — co-mount, no coupling

The agent session mounts **both** MCP servers: `lore` (read-only, deterministic)
and `supermemory` (`addMemory` / `search`). This is configuration, not code —
nothing in `rac-core` changes to make it possible. Lore stays the authority;
Supermemory is an associative index alongside it.

### The loop — fuzzy find, deterministic verify

The interaction pattern the whole design optimizes for:

1. The agent asks Supermemory in natural language and gets semantically-near
   candidates, each carrying the canonical Lore artifact `id` in its metadata.
2. The agent re-fetches the authoritative, *current* text from Lore by that `id`
   (`get_artifact`), and uses `find_decisions` so a retired or superseded
   decision can never be mistaken for live guidance.
3. The agent acts on Lore's verbatim text — never on Supermemory's
   LLM-rewritten copy.

Recall comes from the fuzzy layer; correctness is restored by the deterministic
one. Supermemory's stored "memory" is treated strictly as a *pointer/index into
Lore*, never as a source of truth.

### The feed — a one-way ingest adapter

A small companion, `lore-supermemory` (a `lore-*` repo per ADR-068, never inside
`rac-core`):

- runs `rac export --json` (the deterministic `CorpusExport`, a stable additive
  contract per ADR-007 / ADR-063) or reads the Markdown + frontmatter on disk;
- for each artifact, calls Supermemory
  `add({ content, containerTag: <repo>, metadata: { id, type, status } })`;
- re-syncs on change (a CI step or git hook), idempotent on the canonical opaque
  `id` so re-ingesting an edited artifact updates rather than duplicates;
- emits **only** decision/requirement/design/roadmap/prompt content the corpus
  already exposes — it adds no new disclosure surface.

Data flows one way: RAC → Supermemory. RAC never reads back from Supermemory,
never calls it, never depends on it. `rac-core` requires no change; the export
already carries `id`, `type`, and `status`.

## Constraints

- **AI stays optional, determinism stays intact (ADR-002, ADR-066).** The
  embeddings, the LLM rewrite, and the fuzzy ranking all live in Supermemory.
  Lore's served order and text remain a pure function of the corpus; the
  grounding-eval benchmark still scores exactly what Lore serves.
- **No semantic component in Lore's serving path (ADR-067).** The fuzzy layer is
  a *parallel* surface the agent queries directly, never an interceptor or
  re-ranker between Lore and the agent.
- **One-way only.** RAC must not gain a dependency on, or a read path from,
  Supermemory. The trust and determinism guarantees are Lore's alone to keep.
- **Metadata is load-bearing.** Every ingested memory must carry the canonical
  `id` and `status`, or the verify-in-Lore step and the retired-decision filter
  break.
- **Supermemory's copy is non-authoritative by construction.** Its ingest
  rewrites content with an LLM, so its text is an index, never a citation;
  authoritative text is always re-fetched from Lore.
- **Companion, not core (ADR-068, ADR-024).** Any build is a `lore-*` repo. RAC
  does not store, serve, or re-import the embedded copy; it is not becoming a
  content store.

## Rationale

The adapter is the only shape that adds semantic recall while keeping every
recorded guardrail. It is outbound-only and contract-based, so it cannot regress
Lore's determinism, its AI-optional posture, or its auditability. It is also
small: a script over a stable published surface, with no `rac-core` change.

Crucially, it captures the benefit that pulls toward the rejected alternatives —
better recall over recorded decisions — *without* their cost. The real weakness
it addresses is that Lore's keyword search misses paraphrases (ADR-037,
ADR-038); the adapter fixes that by adding a parallel, explicitly-fuzzy surface,
leaving Lore's authoritative output untouched and clearly labelled as the
authority.

## Alternatives

- **Semantic re-rank of Lore's results (rejected).** Let Supermemory reorder
  `search_artifacts` / `get_related` output by semantic similarity before the
  agent sees it. Rejected: it makes the agent-consumed order non-deterministic
  and desynchronized from the grounding-eval (ADR-066 scores the exact order
  Lore serves — a re-ranker means the benchmark scores one order and the agent
  consumes another, varying by model version). It erodes Lore's entire
  differentiator: an answer you can audit and reproduce.
- **Memory-router proxy in the serving path (rejected).** Front the model with
  Supermemory's OpenAI-compatible router, auto-injecting recalled context with
  Lore as one source. Rejected: it places a fuzzy, LLM-rewriting,
  possibly-cloud component on the critical path (contra ADR-002) and inverts the
  dependency so memory becomes the front door and Lore a backend — the opposite
  of Lore's positioning (ADR-036, ADR-039).
- **Serve decisions *from* Supermemory (rejected).** Replace or shadow Lore's
  reads with Supermemory search. Rejected outright: it discards determinism,
  auditability, the retired-decision filter, and ADR-024 in one move.
- **Do nothing (the honest baseline).** Lore already works; the paraphrase gap
  is a real but bounded weakness. Acceptable until evidence shows agents miss
  decisions for lack of semantic recall — which is the signal that would
  schedule the adapter.

The narrow door left open: a re-rank or router *experiment* could be revisited
far later, fenced inside a `lore-*` companion and never in core, only if the
adapter's parallel-surface recall proves insufficient. It is recorded as
deferred-with-rationale in the roadmap, not adopted here.

## Accessibility

This surface is consumed by agents and read by their operators, so legibility
means *provenance* legibility: results must never blur which layer they came
from. Authoritative answers (Lore, by `id`, verbatim, with lifecycle status)
stay visually and structurally distinct from associative candidates
(Supermemory, fuzzy, advisory). An operator auditing an agent's reasoning must
be able to tell, at a glance, that the decision it acted on was the verbatim
Lore artifact, not the rewritten memory.

## Style Guidance

- Name the companion `lore-supermemory` (the `lore-*` brand convention, ADR-068),
  not `rac-*`; it is a Lore-brand integration, not an engine component.
- Vocabulary separates the layers: Lore *grounds* and is *authoritative*;
  Supermemory *recalls* and is *associative*. Never describe Supermemory output
  as a decision or a citation.
- The export the adapter consumes is the published contract surface; it grows
  only additively (ADR-007). The adapter depends on `id`/`type`/`status`,
  nothing private.

## Open Questions

- Sync cadence and idempotency key beyond the canonical `id` — CI step vs git
  hook vs on-demand, and how aggressively to prune memories for deleted
  artifacts.
- Whether to ingest all artifact types or scope to decisions first, given
  decisions are the highest-value recall target.
- How an agent prompt or skill should encode the "verify-in-Lore" discipline so
  the fuzzy-find/deterministic-verify loop is followed reliably rather than by
  convention.
- Whether the eventual `containerTag` scheme should be per-repo, per-series, or
  per-artifact-type.

## Related Requirements

- rac-agent-context-guide

## Related Decisions

- ADR-002
- ADR-007
- ADR-024
- ADR-032
- ADR-037
- ADR-038
- ADR-063
- ADR-066
- ADR-067
- ADR-068

## Related Roadmaps

- lore-supermemory-grounding
