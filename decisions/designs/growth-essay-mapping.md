---
schema_version: 1
id: RAC-KTYBHY87XKV8
type: design
---
# Growth Essay Mapping: Article Claims to Corpus Capabilities

## Context

The maintainer is writing a product-knowledge essay series. Article 1's
premise: tacit PM knowledge is built from unrecorded observable
decisions. No draft of Article 1 exists in this repository at the time
of writing, so the claims below derive from that premise rather than
from published text. The requirement `rac-growth-essay-bridge`
(REQ-002) requires every article-to-capability mapping to be recorded
as a corpus artifact, not in the article. This design is that record.

Nothing in this artifact is prose intended for publication. Titles and
premises below are structural working labels for the maintainer to
accept, rewrite, or discard.

## User Need

The maintainer needs, before drafting and at review time, a single
place that answers: which RAC capability or corpus artifact answers
the problem each article names, where (if anywhere) a link to it can
sit without turning the essay into marketing, and which claims have no
counterpart yet. Integration reviewers need the same table to check
REQ-001 and REQ-003 of `rac-growth-essay-bridge` against any draft.

## Design

### Mapping table — Article 1 claims to corpus counterparts

Each counterpart below was verified against this repository on
2026-06-12. "Placement" names the single least promotional place a
link could live; per REQ-003 the product never appears in a title,
opening, or thesis statement.

| # | Claim (derived from premise) | RAC counterpart (verified) | Least promotional placement |
| --- | --- | --- | --- |
| 1 | Product decisions are observable events, but most teams never record them | Decision artifacts: `rac/decisions/` (38 ADRs, `adr-001` to `adr-038`); artifact model in `adr-004` | A parenthetical link to one real ADR file, only where the worked example cites that decision by id |
| 2 | The "why" behind a product is tacit because the record does not survive the people who made it | Decisions as versioned Markdown in Git (`adr-001` markdown-first, `adr-013` leverage existing source control); this corpus under `rac/` is the standing instance | A single unannotated repository link in a closing footnote |
| 3 | Unrecorded decisions cannot be consulted at the moment of work — by people or by agents | MCP grounding tools `get_summary`, `search_artifacts`, `get_artifact`, `get_related` (`docs/mcp.md`; `adr-029`, `adr-030`); runnable example in `examples/guide/` | Inside the late worked example only: a grounded agent session over a real corpus, the tool named once |
| 4 | Recorded decisions form a web, not a list — each constrains or supersedes others | `rac relationships <path> --validate` (`docs/cli.md`; `adr-016`); `## Related <Type>` and `## Supersedes` sections | A figure caption crediting the corpus a relationship graph was drawn from |
| 5 | Knowledge already written into documents stays tacit while it is unstructured | `rac ingest` (`adr-006` ingest-over-rewrite) and `rac inspect` classification (`docs/cli.md`) | No link in Article 1; row retained for later series planning only |
| 6 | Capture has to happen at the moment a decision is observed — in conversation — or it does not happen | **No existing counterpart.** RAC converts existing documents (`rac ingest`) and serves recorded artifacts; it has no capture-at-source from conversation or meeting streams | None until a counterpart exists; the absence itself is honest essay material |

Claim 6 is the only flagged absence. Whether it warrants new
capability is deferred to Open Questions; no requirement is created
here.

### Proposed article slots — the dogfood story as the essay

At most five slots where "we ran RAC's growth plan in RAC and here is
what it could not express" is itself the subject. Titles and
one-sentence premises only; all publication is gated (see
Constraints).

1. **What the growth plan could not say** — running RAC's own growth
   programme as RAC artifacts surfaced every relationship the schema
   cannot express, each now a recorded, designable gap.
2. **Thirty-eight decisions later** — what a decision corpus looks
   like once its primary reader is a coding agent rather than a
   colleague.
3. **The gate that had to live in prose** — publication gates had no
   schema field, so blocked status became a body line under
   `## Status`: a precise, observed failure of expressiveness.
4. **Superseded in public** — what keeping dead decisions visible
   through `## Supersedes` chains, instead of deleting them, does to a
   team's record of why.
5. **A corpus that argues back** — structural validation as editor of
   record: what `rac validate` and `rac review` refused to accept in
   the corpus that governs the tool itself.

## Constraints

Blocked: GATE-1 (employer external-communications / IP review) — covers
publication of every mapped article and every article slot above; the
mapping table itself is internal corpus material and not gated.

- Agents produce structure only; no sentence in this artifact or its
  successors is written for publication in the maintainer's voice.
- REQ-003 of `rac-growth-essay-bridge`: the product appears, if at
  all, as a worked example in the closing portion of a piece — the
  placement column is a ceiling, not a target, and "no link" is always
  acceptable.
- ADR-036 naming governs any worked example: Lore is the product, RAC
  is the engine, the relationship stated once per surface.
- The article side of each mapping row cannot be a validated corpus
  reference: the schema has no way to reference external or
  unpublished documents (recorded as a gap by this programme).

## Open Questions

- Claim 6 (capture at the moment of observation): does it warrant a
  future capability — for example, ingest from conversation exports —
  or is the honest position that RAC begins where a team chooses to
  write a decision down? Deferred to a future roadmap discussion; not
  expanded into requirements here.
- When Article 1's draft exists, do its actual claims match the six
  derived here? The table must be reconciled against the draft before
  the article is mapped as published.
- Where should the published-article register live once GATE-1 clears,
  given the schema cannot reference external documents?

## Related Requirements

- rac-growth-essay-bridge
- rac-growth-positioning

## Related Decisions

- adr-036
- adr-016
