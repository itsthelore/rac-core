---
schema_version: 1
id: RAC-KVSQ2BANG6HS
type: design
---
# Note-Tool Ingest Sources

## Context

This design is the *how* for the `rac-note-tool-ingest-sources` requirement and
the boundary ADR-079 draws: ingest Obsidian, Logseq, Notion, and Roam exports by
normalising their already-Markdown notes into RAC-shaped artifacts, through the
ADR-072 converter registry, without touching markitdown or the core.

`services/ingest.py` already defines a converter abstraction — a converter
declares the sources it handles and turns a source into Markdown, and "new
sources are added by registering" one. This design adds a converter *family* for
note tools that normalises rather than parses-from-binary, and handles a
directory of interlinked notes rather than a single file.

## User Need

A team adopting Lore has its decisions, specs, or product notes in Obsidian,
Logseq, Notion, or Roam. They want one command that turns that export into a set
of reviewable RAC drafts — with the links they already drew between notes carried
in as candidate relationships, not flattened to plain text — so adoption is an
import, not a rewrite. They need it deterministic and lossless, so the review
step starts from a complete, faithful draft.

## Design

### Registration and selection

Each tool is a registered converter behind an optional extra
(`ingest-obsidian`, `ingest-logseq`, …), sitting in the ADR-072 registry beside
the markitdown converters. Selection is by export shape (a detected vault
layout / marker file) or an explicit `--from <tool>` flag, so a directory is
routed to the right normaliser deterministically. The markitdown path for binary
documents is untouched.

### Directory in, artifact set out

`rac ingest <export-dir>` walks the export and treats each note as a candidate
artifact. Each note flows through the same normalisation steps and the existing
artifact-draft path; nothing is written that would overwrite an existing
artifact, and the output is a set of drafts for human review, not committed
artifacts.

### Normalisation steps (deterministic, per note)

- **Wikilinks → resolvable references.** `[[Note]]`, `[[Note|alias]]`, and
  heading/block references are parsed and resolved against the other notes in the
  same export. A resolved target becomes a **candidate `## Related` reference**
  (typed by the target's eventual artifact type where known); an unresolved or
  ambiguous link is reported and left inline, never guessed and never written as
  an asserted edge (ADR-079, ADR-074, ADR-065).
- **Frontmatter mapping.** Known tool frontmatter keys map to RAC's shape where a
  deterministic mapping exists; unmapped keys are preserved in the body so
  nothing is lost (lossless by default).
- **Body normalisation.** Tool-specific Markdown dialect (callouts, embeds,
  block ids) is normalised to plain Markdown or preserved verbatim when there is
  no faithful mapping — never dropped.

### Per-tool specifics (the registry isolates these)

- **Obsidian** — a vault of `.md` files; `[[wikilinks]]`, `![[embeds]]`, YAML
  frontmatter.
- **Logseq** — Markdown/outliner pages and journals; block references, page
  links.
- **Notion** — a Markdown + CSV export with hashed filenames; database CSVs and
  the folder structure carry relationships.
- **Roam** — a JSON or Markdown graph export; block-reference graph.

Each is its own converter with its own tests, so one tool's export drift cannot
break another or the core.

### Boundary with the rest of the corpus

The candidate `## Related` references this produces are exactly the kind of
suggestion the relationship-completeness work surfaces — an imported wikilink is a
mention the human promotes to a declared edge. Ingest stops at the draft and the
candidate; promotion and validation stay human (ADR-074, ADR-065).

## Constraints

- Deterministic and offline (ADR-002): identical export yields byte-identical
  drafts; no model, no network; never overwrites an existing artifact.
- Lossless by default: unmapped content is preserved verbatim, never discarded.
- Registry, not core (ADR-072): note-tool converters are registered extras; the
  engine core and the markitdown path are unchanged.
- Edges are candidates, never asserted (ADR-074, ADR-065): wikilinks become
  suggested references for human promotion.

## Rationale

Normalisation, not markitdown, is correct because the input is already Markdown
and the value is in the *links*, which markitdown would discard. Per-tool
converters behind the existing registry isolate format drift and keep the core
clean, exactly as ADR-072 intended for new sources. Carrying wikilinks in as
candidate relationships — rather than dropping them or auto-asserting them — keeps
the import inside RAC's declared-and-reviewed graph model while still delivering
the connectivity the source already had.

## Alternatives

- **markitdown for everything.** Rejected (ADR-079): no binary to parse, and it
  flattens the link graph.
- **One universal wikilink importer.** Rejected: the tools differ enough that a
  single importer becomes special-case soup; per-tool converters are cleaner.
- **Auto-create edges from resolved wikilinks.** Rejected: unreviewed edges are
  not validated edges (ADR-074, ADR-065).

## Accessibility

Ingest output is plain-text Markdown drafts, diffable and reviewable in any
editor; the import summary (notes converted, links resolved, ambiguities to
review) is plain text with a `--json` form, no reliance on colour or a GUI.

## Style Guidance

The import summary leads with what converted and what needs human attention
(unresolved links, unmapped metadata), in the scannable style of existing
`rac ingest` output. Copy frames imported links as *candidates to promote*, never
as edges the tool has asserted.

## Open Questions

- Whether vault-internal link resolution should also propose the *inverse*
  candidate edge on the target note, or only the forward one.
- How Notion database CSVs map — as artifact metadata, as relationships, or as
  separate artifacts.
- Whether detection of export shape is automatic, flag-driven (`--from`), or both.

## Related Decisions

- adr-079
- adr-072
- adr-074
- adr-065
- adr-002

## Related Requirements

- rac-note-tool-ingest-sources

## Related Roadmaps

- v0.30.0-note-tool-ingest-sources
