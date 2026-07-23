---
schema_version: 1
id: RAC-KV6KFGA4PY4C
type: requirement
tags: [user-facing, retrieval, explainability, mcp]
---
# Requirement: Explainable Retrieval

## Status

Accepted

Classification: `[user-facing]` — the user sees *why* the agent grounded. Scoped
to the v0.23.0 hardening release (WS2).

## Problem

When Lore returns a search result, the consuming agent — and the human watching
— sees *that* an artifact was retrieved but not *why*. "No guessing" is a claim
we cannot currently show. Without a deterministic explanation of the match, a
result is opaque: a user cannot tell whether a title, a tag, the body, or a
relationship edge surfaced it, which undermines trust in the grounding.

## Requirements

- [REQ-001] Each `search_artifacts` result MUST carry a deterministic, non-empty `evidence` structure stating which field matched (id / title / path / heading / body), the matched term(s), and the retrieval tier. This `evidence` object is additive on each `search_artifacts` / `rac find` match and its shape is fixed: `field` (string — the winning tier, exactly one of `id` / `title` / `path` / `heading` / `body`, the matcher's existing rank `_RANK_ID`..`_RANK_BODY` (0–4) projected to its tier name, no new computation); `terms` (array of strings — the query terms that matched, in query order, each as the already-tokenized casefolded form the matcher compared, never empty since AND semantics guarantee every term matched somewhere); and `tier` (integer 0–4 — the numeric rank, so a consumer can sort or compare without re-deriving it from `field`). For a `heading` or `body` win, `evidence` MUST NOT duplicate the existing `section` / `snippet` fields; those stay where they are and `evidence` references the same data. For an `id` / `title` / `path` win there is no snippet and `evidence` carries `field` + `terms` + `tier` only.
- [REQ-002] `get_related` results SHOULD carry evidence identifying the relationship edge (section and target) that surfaced the artifact: `direction` (`incoming` / `outgoing`), `relationship` (the section name, e.g. `related_decisions`), and `target` (the reference as stored). This is the edge the serializer already filters on, surfaced rather than recomputed; no term/tier fields apply (a relationship is not a text match).
- [REQ-003] The `evidence` structure MUST be an additive, backward-compatible field on the existing tool output; the response schema and tool count MUST NOT otherwise change (ADR-007, ADR-030). Present keys keep their names, types, and order; the metadata-match JSON shape stays byte-identical to today except for the added `evidence` key. The MCP surface stays read-only with no tool added or removed (ADR-030). `evidence` is always present on a match (it is never null/absent), unlike the conditional `section`/`snippet`.
- [REQ-004] RAC MUST provide a `rac find --explain` mode that prints per-stage match attribution for a query. Human mode appends one indented attribution line per match — `field=<tier> terms=<t1,t2> [section: snippet]` — under the existing match row, leaving the non-`--explain` output unchanged. `--explain` with `--json` MUST emit the same `evidence` object the MCP path emits (one source of truth); the two faces never diverge.
- [REQ-005] The explanation MUST be a faithful description of the real match reason, derived from the existing token-tier match data (ADR-037, ADR-038), not a separate heuristic. It is read off the existing matcher (`_Match.rank` and its matched terms) — not a second heuristic, not a re-scan, not a relevance score. The matched-terms set the matcher already computes (today discarded) is surfaced; no new matching logic is introduced.
- [REQ-006] `--explain` MUST be compatible with `--type`, `--decisions`, `--top-level`, and `--recursive`. `rac find` MUST keep returning exit 0 for an empty result (a query always succeeds); `--explain` adds no new exit codes and does not change exit 2 (usage) for a bad directory.
- [REQ-007] `evidence` MUST be deterministic and offline: a pure function of (corpus snapshot, query), byte-stable across repeated runs on an unchanged corpus, with no clock, randomness, network, or model in the path (ADR-002, ADR-034). Term order follows query order; `field`/`tier` follow the fixed ladder.

## Acceptance Criteria

- Every search match carries a non-empty `evidence` object whose `field`/`tier`/`terms`
  are asserted to equal the matcher's actual winning rank and matched terms; a
  test pins the id/title/path/heading/body cases and the empty-result case.
- A test asserts the metadata-match JSON is byte-identical to the pre-change
  shape except for the additive `evidence` key, and that the MCP `--json`
  evidence equals the `rac find --explain --json` evidence for the same query.
- `rac find --explain` prints per-match attribution; without `--explain` the
  output is unchanged; `--explain` composes with `--type` / `--decisions`.
- Existing MCP contract and golden tests still pass with the additive field
  present (backward compatibility verified).

## Descope

- No relevance score, ranking weight, or confidence number — `evidence`
  describes the structural match only (ADR-034, ADR-066).
- No new field on `get_artifact` (that is WS5 provenance, a separate
  requirement) and no fifth MCP tool (ADR-030).
- No multi-term match map — `terms` is a flat list, not a per-field
  attribution; the winning tier is the artifact's best rank, matching how
  the matcher already ranks. Per-term-per-field attribution is out of scope.
- No body-snippet change — snippet extraction stays exactly ADR-038's
  whole-line rule; `evidence` references it, never alters it.

## Success Metrics

- A user inspecting a result can name the field and term that caused it without
  reading the matcher's source.

## Risks

- Evidence text could be mistaken for a relevance verdict. Mitigation: it
  describes the structural match (field, term, tier), never a semantic judgment
  (ADR-034).

## Assumptions

- The existing matcher (`_match_entry` in `services/resolve.py`) already computes
  the winning rank, the matched-terms set, and the heading/body section+snippet;
  `evidence` surfaces this existing data rather than recomputing it. The
  matched-terms set is computed today but discarded — this work returns it.
- `get_related`'s serializer already carries the relationship section and target
  per edge; `evidence` names the existing edge, adding no traversal.

## Related Decisions

- adr-037
- adr-038
- adr-007
- adr-030

## Related Requirements

- rac-grounding-eval-benchmark

## Related Roadmaps

- v0.23.0-hardening
