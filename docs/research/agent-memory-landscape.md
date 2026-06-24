# Agent Memory for Team Knowledge — Competitive Landscape & Lessons for Lore

> **Status: research document, not a RAC artifact.** Per ADR-010 ("Documents Are
> Not Artifacts") and ADR-024 ("RAC Is Not a Content Store"), this is reference /
> working material, not part of the validated `rac/` corpus. Its *actionable*
> conclusions are captured as corpus artifacts — see "What this produced" below.
>
> **Scope:** products and projects positioned as "agent memory for a team's
> knowledge" — systems that turn docs, chats, tickets, code, or decisions into a
> queryable store an AI agent reads — and where Lore (RAC) sits among them.
> **Method:** two multi-angle web-research passes with adversarial verification
> (3-vote, 2/3 to kill) and evidence-vs-marketing tagging; a second pass closed
> the coverage gaps (Cognee, Glean, Dust, native assistant memory) the first left
> open. Confidence and primary sources cited inline.
> **Date:** 2026-06.

---

## Executive summary

The space splits on one axis, and Lore sits cleanly on the under-served side:
**LLM-distilled mutable stores** vs **human-reviewed versioned knowledge.** The
overwhelming majority — Mem0, Zep/Graphiti, Cognee, Letta, OB1, and the native
memory in ChatGPT, Claude, Cursor — use an LLM to *extract* facts at ingest into a
mutable database, vector index, or knowledge graph, and are **per-agent or
per-user**. None routes knowledge through human review before it becomes
authoritative. That is the right design for personal recall and the wrong design
for a shared team source of truth, where a confidently-distilled stale "fact" is
the exact failure mode the category cannot police.

Only a thin **git-native, human-reviewed** band overlaps Lore's positioning, and
it has just two real occupants — **Mainline** and **Kage** — both of which appeared
recently and neither of which governs a *typed* requirements/decisions corpus with
ratified supersession. The convenient "only git-native team-knowledge engine" line
is therefore no longer true and must be retired.

One-sentence positioning that the research supports:

> **Lore is the git-native, human-ratified source of truth for a team's *typed*
> decisions and requirements — knowledge that is authored and accepted by people,
> not distilled by a model — winning on the trust axis (deterministic supersession
> and provenance) that every LLM-distilled memory store structurally cannot own.**

---

## The axis

| | LLM-distilled mutable store | Human-reviewed versioned knowledge (Lore) |
|---|---|---|
| How knowledge is made | LLM extracts facts at ingest | authored + ratified by a human |
| Source of truth | database / vector / graph store | files in git, `main` |
| Determinism | non-deterministic (model-dependent) | deterministic, reproducible |
| Supersession | model-judged or in-place overwrite | explicit, typed, history retained |
| Scope | mostly per-agent / per-user | shared team corpus |
| Review gate | none (agent writes autonomously) | pull-request review (ADR-065) |

---

## Category findings

### 1. LLM-distilled mutable stores

*Mem0, Zep/Graphiti, Cognee, Letta, OpenBrain/OB1, Collaborative Memory.*

- **Zep / Graphiti** is the most sophisticated foil: an LLM extracts and resolves
  entities/relationships at ingest into a **temporally-aware knowledge graph** (Neo4j
  default; also FalkorDB, Neptune), with a bi-temporal model that *invalidates*
  superseded facts (sets `t_invalid`) rather than deleting them, and avoids LLMs at
  query time (~300ms P95). Storage is a graph DB, not git. [high]
  ([arXiv 2501.13956](https://arxiv.org/abs/2501.13956),
  [Graphiti](https://github.com/getzep/graphiti))
- **Mem0** uses LLM-driven extraction into a hybrid vector+graph+KV store and updates
  facts **in place** via an LLM-decided ADD/UPDATE/DELETE/NOOP — no temporal validity
  windows. Scoped per `user_id`/`agent_id`/`session`: episodic memory, not a shared
  source of truth. [high]
  ([arXiv 2504.19413](https://arxiv.org/abs/2504.19413), [repo](https://github.com/mem0ai/mem0))
- **Cognee** is an open-source (Apache-2.0) "AI memory platform for agents." Its
  **Extract-Cognify-Load** pipeline uses an LLM (Instructor-powered structured output)
  to build a typed knowledge graph at ingest, stored in graph + vector + metadata DBs
  (Kuzu / LanceDB / SQLite) — **non-deterministic, no human-review workflow** on
  agent-added knowledge. Self-hostable; commercial cloud tier exists. [high]
  ([repo](https://github.com/topoteretes/cognee),
  [grounding AI memory](https://www.cognee.ai/blog/deep-dives/grounding-ai-memory))
- **Letta Context Repositories** are genuinely git-backed (every memory change
  auto-committed; agents clone the repo; subagents merge via worktrees) — but memory
  is **per-agent** and managed by **LLM "sleep-time" reflection subagents**, with no
  human-ratification gate. Architecturally close to Lore's medium, opposite on trust.
  [high] ([Letta](https://www.letta.com/blog/context-repositories/))
- **OB1 (OpenBrain)** uses LLM "schema-aware routing" to distribute text into a
  **PostgreSQL/pgvector** store (Supabase or self-hosted); it does track provenance /
  derivation chains, but the source of truth is a DB, not git. [high]
  ([repo](https://github.com/NateBJones-Projects/OB1))
- **Collaborative Memory** (Accenture research, not a product) is notable for two
  Lore-relevant ideas in an otherwise LLM-distilled mutable store: **private + shared
  tiers** with access control, and **immutable provenance metadata** per fragment
  (creation time, contributing user/agents, resources accessed). [high]
  ([arXiv 2505.18279](https://arxiv.org/html/2505.18279v1))

> Note for Lore: even the best supersession in this camp (Graphiti's bi-temporal
> invalidation) is *model-judged at ingest*. Lore's supersession is human-ratified
> and typed — the difference between "the model decided this fact is stale" and "a
> reviewer accepted that this decision supersedes that one."

### 2. Git-native human-reviewed knowledge — Lore's real neighbours

*Mainline, Kage; Letta Context Repositories (per-agent, see above); Semiont
(positioning-adjacent).*

- **Mainline** is the closest *paradigm* match: deterministic, git-native, **no DB /
  no vectors / no LLM distillation / no embeddings**. It stores agent intent and
  decisions as **Git refs and notes** alongside code, collaborates via fetch/branch/
  merge, and binds decisions to the commits that produced them (commit-level
  provenance). [high] ([mainline.sh](https://mainline.sh/),
  [repo](https://github.com/mainline-org/mainline))
- **Kage** is the closest match to Lore's *positioning*: git-native ("no account, no
  API key, no database — just files in git"), **reviewed in the same pull request as
  the code**, with strong provenance/staleness handling — citations validated against
  the repo at capture (hallucinated citations refused), stale memory withheld when its
  cited file is deleted, and `kage pr check` warns when a change invalidates team
  knowledge before the PR lands. [high, single vendor source]
  ([kage-core.com](https://kage-core.com/))
- **Semiont** (AI Alliance) targets the trusted/provenance/human-governed framing
  ("AI proposes, domain experts review"; W3C Web Annotation provenance) — but it uses
  an LLM to *propose*, and verification **refuted** its git-source-of-truth and
  direct-"agentic-memory" claims. Treat as positioning-adjacent, not git-native. [medium]
  ([repo](https://github.com/The-AI-Alliance/semiont))

> Note for Lore: Mainline and Kage capture **agent intent / lessons**; Lore governs a
> **typed requirements/decisions corpus** with ratified supersession and a validated
> graph (ADR-049, ADR-061, ADR-074). That is the narrower, defensible distinction now
> that "only git-native" is gone.

### 3. Enterprise RAG / search assistants — adjacent, not competitors

*Glean, Dust.*

- **Glean** is enterprise "Work AI": a permissions-aware **knowledge graph + vector
  store** over indexed company content, with LLM-distilled retrieval. A search /
  knowledge-discovery product, not a versioned source of truth. [high]
  ([Glean KG](https://www.glean.com/resources/guides/glean-knowledge-graph))
- **Dust** is **RAG at query time**: semantic search over connected data sources feeds
  retrieved docs + the question into an LLM. No ingest-time fact distillation, no
  versioned corpus — an agent platform over company data. [high]
  ([Dust RAG](https://docs.dust.tt/docs/understanding-retrieval-augmented-generation-rag-and-the-search-method-in-dust))

### 4. Native assistant memory — per-user, mostly distilled, no shared gate

*ChatGPT, Claude, Cursor, Continue.*

- **ChatGPT** memory builds a persistent, LLM-distilled **user profile**. **Claude**
  memory is LLM-distilled for Teams/Enterprise (a wiki-style doc auto-updated on a
  cycle, **no human-ratification gate**); consumer Claude instead retrieves over **raw
  conversation history** with no AI-generated summaries. All per-user. [high]
  ([Claude memory](https://simonwillison.net/2025/Sep/12/claude-memory/))
- **Cursor / Continue rules** (`.cursor/rules/*.mdc`, `.cursorrules`) are the one
  native feature sharing Lore's *medium*: **human-authored, git-versioned, team-shared
  files reviewed in the normal PR flow.** But they are **free-form instructions**, not
  a typed, validated, supersession-aware corpus. [high]
  ([Cursor rules](https://cursor.com/docs/context/rules))

> Note for Lore: Cursor/Continue rules prove the substrate (git + PR review) is an
> accepted industry pattern, not a compromise — but they stop at free-form prose. The
> typed artifact model + deterministic validation is the layer above them.

---

## Cross-cutting evidence

- **No agent-memory system ships a human-review promotion gate.** A direct survey
  finding: "no system natively implements [a human-review step]; all assume the agent
  has authority to update memory directly." This is the gap Lore's two-gate capture
  model (ADR-077) and PR trust boundary (ADR-065) fill. [high]
- **Deterministic supersession beats LLM-judgment — measured.** A 2026 preprint
  reports that replacing LLM-judgment with a candidate-extraction + `max(serial)`
  pipeline for memory freshness/conflict resolution yields **+10.8 points on the FC-SH
  benchmark (67.2 → 78.0)**, and that LLMs degrade at tracking which knowledge version
  is current — external support for Lore's deterministic stance (ADR-066, ADR-080).
  [medium — recent preprint, cite as supporting evidence, not settled]
  ([arXiv 2606.01435](https://arxiv.org/abs/2606.01435))

---

## Where each player lands (verdict)

| Player | Camp | Overlap with Lore |
|---|---|---|
| Zep / Graphiti | distilled mutable (graph) | adjacent — strongest supersession, but model-judged, DB-backed |
| Mem0 | distilled mutable (hybrid) | adjacent — per-user episodic |
| Cognee | distilled mutable (graph+vector) | adjacent — no human gate |
| Letta Context Repos | git-backed, LLM-managed | adjacent — per-agent, no human gate |
| OB1 | distilled mutable (Postgres) | adjacent — DB source of truth |
| **Mainline** | **git-native, human-reviewed** | **direct paradigm overlap** — agent intent, not typed corpus |
| **Kage** | **git-native, human-reviewed** | **direct positioning overlap** — agent lessons, not typed corpus |
| Semiont | LLM-assisted, human-governed | positioning-adjacent (git claim refuted) |
| Glean / Dust | enterprise RAG | adjacent — retrieval, not a corpus |
| ChatGPT / Claude memory | distilled, per-user | adjacent — personal memory |
| Cursor / Continue rules | git-native, human-authored | closest medium — free-form, not typed |

---

## Honest caveats & open questions

1. **The two surviving differentiators are narrow but real:** (a) no LLM distillation
   of judgment, and (b) a human-ratification gate over a *typed* corpus with explicit
   supersession. Mainline and Kage do PR review of agent intent/lessons; none ratifies
   typed decision/requirement artifacts the way Lore does.
2. **"Only git-native" is retired.** Mainline and Kage occupy the same substrate; the
   defensible claim is human-ratified + typed, not git-native exclusivity.
3. **Refuted claims (excluded):** Kage having an explicit supersession command with a
   newest-wins retain-both policy (1-2); Semiont being git-backed (0-3) or a direct
   "agentic memory" overlap (1-2); Cognee's temporal handling being *merely* an
   optional Graphiti add-on (0-3). Do not repeat these.
4. **Vendor sourcing:** Mainline, Kage, and Semiont positioning rests substantially on
   self-description (appropriate for *what a product claims*, not independently
   audited). The durable third-party facts are the Graphiti/Mem0 papers, the
   deterministic-supersession preprint, and Cursor's own rules docs.
5. **Fast-moving space:** most sources are 2025-2026; Mainline, Kage, Mem0 V3, Letta
   Context Repositories, and OB1 are all recent. Treat named feature deltas as
   perishable; lead with the durable trust-model distinction.
6. **Tooling note:** the second research pass's auto-synthesis step failed (returned a
   placeholder); these findings were recovered from the verified-claim layer beneath
   it (24 confirmed, 1 killed), not from a broken top-level summary.

---

## What this produced (captured as corpus)

The competitive *positioning* conclusions were distilled into a growth-positioning
requirement (this document is the reference behind it):

- `rac/requirements/rac-growth-agent-memory-positioning.md` (`RAC-KVWHTV28J65S`) —
  relate Lore to the agent-memory category on a `docs/` comparison page (deliberately
  not the corpus README); name Mainline and Kage; retire "only git-native"; state the
  human-ratified + typed differentiator; and acknowledge the adjacents (Glean, Dust,
  ChatGPT, Claude, Cursor, Continue) honestly.

It complements the broader `team-scale-landscape.md` in this folder, which covers the
adjacent decision/spec/portal/wiki categories and the freshness-gap thesis.
