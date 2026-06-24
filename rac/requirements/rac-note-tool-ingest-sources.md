---
schema_version: 1
id: RAC-KVSQ28PK9A5P
type: requirement
---
# Note-Tool Ingest Sources

## Problem

`rac ingest` turns rich documents into RAC artifacts through markitdown
(ADR-072): DOCX, PDF, HTML, PPTX, XLSX, Markdown. But a large share of the
product knowledge teams already hold lives in personal-knowledge-management (PKM)
and note tools — Obsidian, Logseq, Notion, Roam — whose exports markitdown does
not meaningfully handle. Those exports are *already* Markdown (or Markdown plus
CSV/JSON), organised as a linked *graph of notes*, using wikilink syntax
(`[[Note]]`, `[[Note|alias]]`) rather than standard Markdown links, with
tool-specific frontmatter.

The result is a gap on the front door of adoption: a team with a decision log in
Obsidian or a Notion workspace cannot bring it into Lore without hand-rewriting
every note. And the wikilink graph they already maintain — which is exactly the
relationship signal RAC values — is lost on the way in. The affected users are
new adopters with existing knowledge bases: ingest is their first impression, and
right now it stops at office documents.

## Requirements

- [REQ-001] RAC SHALL ingest note-tool / PKM exports — at minimum Obsidian, Logseq, Notion, and Roam — converting each note into a RAC-shaped Markdown document for the existing artifact pipeline.
- [REQ-002] Ingest SHALL accept a directory export (a vault or graph), not only a single file, and process each note in the export as a candidate artifact.
- [REQ-003] Ingest SHALL normalise PKM wikilink syntax (`[[Note]]`, `[[Note|alias]]`, heading/block references) into resolvable references and surface the targets as candidate `## Related` links, never silently dropping them and never auto-asserting an edge.
- [REQ-004] Ingest SHALL map tool-specific frontmatter and metadata to RAC's shape where a deterministic mapping exists, and preserve unmapped metadata in the body rather than discarding it.
- [REQ-005] Note-tool sources SHALL be added through the existing converter registry (ADR-072) as registered converters / optional extras, without changing the engine core or the markitdown path for rich binary documents.
- [REQ-006] Ingestion SHALL remain deterministic and offline (ADR-002): identical input yields identical output with no model or network call, and SHALL never overwrite an existing artifact.
- [REQ-007] Conversion SHALL be lossless by default: content that cannot be mapped is preserved verbatim in the output so a human always reviews a complete draft.

## Success Metrics

- An Obsidian vault and a Notion export each convert to valid RAC Markdown drafts
  (`rac validate` passes after the human review step) with no content silently
  dropped.
- Wikilinks in the source become candidate `## Related` references in the output,
  so the imported graph's connectivity is offered for promotion rather than lost.
- Re-running ingest on the same export produces byte-identical drafts.

## Risks

- **Format drift.** PKM export formats change and vary by version. Mitigation:
  per-tool converters with their own tests, isolated behind the registry so one
  tool's drift cannot break the others or the core.
- **Wikilink ambiguity.** A `[[Name]]` may not resolve to a unique note.
  Mitigation: deterministic resolution with reported ambiguity, surfaced as a
  candidate for human resolution — never a guessed edge.

## Assumptions

- PKM exports are predominantly Markdown with predictable, parseable link and
  frontmatter conventions, so deterministic normalisation is feasible without a
  model.
- Teams hold real product knowledge in these tools and will adopt Lore faster if
  importing it is a command rather than a rewrite.

## Related Decisions

- adr-079
- adr-072
- adr-002

## Related Designs

- note-tool-ingest-sources

## Related Roadmaps

- v0.30.0-note-tool-ingest-sources
