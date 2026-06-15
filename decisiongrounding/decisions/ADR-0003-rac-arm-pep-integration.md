---
schema_version: 1
id: DG-ADR-0003
type: decision
tags: [rac-arm, corpus, retrieval, supersession]
---

# ADR-0003: Make the `rac` Arm Runnable on the Real Corpus

## Status

Accepted

## Category

Architecture

## Context

ADR-0002 added the first real corpus (the PEP 386 → 440 supersession) as
verbatim PEP text. Wiring the **`rac` arm** — the grounding layer the whole
benchmark exists to test — to that corpus surfaced two blockers, both verified
against the installed `rac` CLI (`rac 0.1.dev…`):

1. **Content classification.** `rac` classifies artifacts by their *content*
   (deterministic classification is RAC's core thesis), not by a front-matter
   `type`. A file that is just a verbatim PEP classifies as `unknown`, so
   `rac find --type decision` skips it and the arm retrieves nothing. A decision
   is recognised only when it carries the canonical sections
   (`Status`/`Context`/`Decision`/`Consequences`).
2. **Relationship + query shape.** `rac relationships --json` identifies each
   artifact by `path` (no `id` field) and exposes a directional edge only from a
   `## Supersedes` section of bare artifact IDs — undirected `## Related
   Decisions` prose does not resolve. Separately, `rac find` is a
   case-insensitive **substring** search over ID/title that narrows on
   multi-word queries, so passing the whole task sentence as the query matched
   nothing.

The arm's pre-existing `_extract_supersedes_edges` also read `art["id"]` (always
absent), so every supersedes edge was silently dropped — it had never actually
followed a supersession against the real CLI.

## Decision

Make the corpus RAC-native and fix the arm's CLI integration, changing nothing
about the held-constant answering model or scaffold (CONTRIBUTING.md rule 4).

- **Ingest emits RAC `decision` artifacts.** `ingest/peps.py` wraps each verbatim
  PEP (preserved under a `## Source Text` section, still byte-for-byte
  hash-verified) in a decision envelope whose every value is *derived from the
  PEP's own headers*: `Status` from the PEP `Status`, and a directional
  `## Supersedes: - PEP-XXXX` from the PEP `Replaces` header (only for targets
  present in the corpus, so no reference dangles). The envelope is structural
  scaffolding; it does not editorialise the PEP's technical content.
- **Edge extraction reads the real JSON.** `_extract_supersedes_edges` derives
  the source id from the artifact `path` stem (the arm writes the corpus as
  `<id>.md`), keeping an explicit `id` path for forward compatibility.
- **Keyword-union retrieval.** The arm queries `rac find` one salient task term
  at a time and unions the hits, ranking by how many terms hit each decision —
  a deterministic topic search that fits `rac find`'s substring surface — then
  follows `supersedes` to replace a retrieved superseded decision with its live
  successor.

All arms see the identical corpus files; the `rac` arm's only advantage is that
it *parses and follows* the typed edge that `naive_rag` embeds and `context_dump`
merely dumps. The supersedes edge is PEP 440's own `Replaces: 386`, not ours.

## Consequences

### Positive

- The `rac` arm runs end-to-end on the real corpus and demonstrably follows the
  supersedes edge: on the pilot it supplies the live PEP 440 and drops the
  superseded PEP 386 (covered by a test that runs against the real `rac` CLI).
- The corpus passes `rac relationships --validate` (the reference resolves), so
  the benchmark dogfoods the same relationship-integrity gate RAC ships.
- The verbatim PEP is unchanged and still hash-verified; reproducibility holds.

### Negative

- Corpus artifacts are now RAC-shaped wrappers rather than raw PEP files; the
  verbatim payload is one `## Source Text` section down.
- The arm issues one `rac find` per salient term. Fine for a `compare` run;
  callers running the large crossover sweep with the `rac` arm should expect more
  subprocess calls.

### Risks

- **`rac` output drift.** The arm depends on `rac find` / `rac relationships`
  JSON shape. Mitigation: extraction is defensive about both shapes, and the
  integration is pinned by tests that skip cleanly when `rac` is absent.
- **The synthetic `scenarios/` corpora still use undirected prose** for
  supersession, so the `rac` arm does not follow their edges. Out of scope here
  (they are never reported as results); flagged for a follow-up that re-encodes
  them with `## Supersedes`.

## Alternatives Considered

- **Give the `rac` arm the scenario's `supersedes` edges directly.** Rejected:
  the arm must *discover* relationships through `rac`, like the layer it models;
  handing it the answer is the special treatment rule 4 forbids.
- **Drop `--type decision` and retrieve unknowns.** Rejected: classification is
  RAC's contract; representing decisions as decisions is the honest corpus.

## Related Decisions

- ADR-0001 — Harness Foundation (the `rac` arm gets no special treatment).
- ADR-0002 — Real-Corpus Pilot (this makes its corpus runnable by the `rac` arm).

## Success Measures

- `rac relationships scenarios_real/.../corpus --validate` resolves with no
  issues, and the `rac` arm supplies the live successor on the pilot.
- The held-constant answering model and scaffold are unchanged; only grounding
  assembly differs across arms.

## Review Date

Revisit when re-encoding the synthetic corpora for the `rac` arm, or if a `rac`
release changes the `find` / `relationships` JSON contract.
