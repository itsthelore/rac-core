---
schema_version: 1
id: RAC-KVSQ2A0BB9XF
type: decision
---
# ADR-079: Note-Tool Exports Are Ingested by Normalisation, Not markitdown

## Context

ADR-072 settled that document ingestion parses through markitdown: a rich binary
document (DOCX, PDF, PPTX, XLSX, HTML) is converted to Markdown, and new sources
are "added by registering" converters. That is the right tool for office
documents, where the job is extracting Markdown from a binary format.

Note-tool / PKM exports — Obsidian, Logseq, Notion, Roam — are a different shape.
They are *already* Markdown (or Markdown plus CSV/JSON), exported as a directory
of interlinked notes, using wikilink syntax (`[[Note]]`, `[[Note|alias]]`) and
tool-specific frontmatter. Feeding them through markitdown is wrong on two
counts: there is no binary to parse, and markitdown would pass the wikilinks
through as literal text, discarding the link graph — the very relationship signal
RAC exists to preserve.

So the question is not "which parser," but "how does a source that is already
Markdown, and is a *graph* rather than a document, enter the pipeline."

## Decision

Note-tool exports are ingested by **normalisation**, added through ADR-072's
converter registry as a distinct converter family — not by extending markitdown.

- **Registry, not core.** Each tool (Obsidian, Logseq, Notion, Roam) is a
  registered converter behind an optional extra, sitting beside the markitdown
  converters in the ADR-072 registry. The engine core and the markitdown path for
  binary documents are unchanged.
- **Normalise, don't parse-from-binary.** A note-tool converter takes Markdown in
  and emits RAC-shaped Markdown: it rewrites wikilink syntax into resolvable
  references, maps known frontmatter, and preserves everything it cannot map
  verbatim (lossless by default). markitdown is not in this path.
- **A vault is a set, not a document.** Ingest accepts a directory export and
  treats each note as a candidate artifact, so the unit of import is the graph,
  not a single file.
- **Wikilinks become candidate edges, never asserted ones.** A `[[Note]]` that
  resolves to another imported note is surfaced as a candidate `## Related`
  reference for human promotion — consistent with RAC's rule that edges are
  declared and reviewed (ADR-074, ADR-065), not inferred and written by a tool.
  Ambiguous links are reported, never guessed.
- **Deterministic and offline (ADR-002).** Normalisation is pure text
  transformation: identical export, identical drafts; no model, no network; never
  overwrites an existing artifact.

## Consequences

A team's existing knowledge base in Obsidian, Logseq, Notion, or Roam becomes a
single `rac ingest` away from a reviewable set of RAC drafts, with its link graph
carried in as candidate relationships rather than flattened to plain text — a
materially better first impression for adopters than "office documents only."
The converter-registry boundary (ADR-072) keeps each tool's quirks and
dependencies isolated and individually testable, and keeps them out of the core.

Trade-offs accepted: this is per-tool work — each export format is its own
converter with its own drift risk — rather than one universal importer; the
registry contains that risk. Wikilink resolution can be ambiguous; the decision
is to report ambiguity for human resolution, never to guess, which means some
imported links land as candidates a human must still confirm — the correct cost
under ADR-074/ADR-065. This refines ADR-072's "register new sources" extension
point for a source class that is already Markdown; it does not change the
markitdown decision for binary documents.

## Status

Proposed

## Category

Architecture

## Alternatives Considered

- **Run PKM exports through markitdown like any other source.** Rejected: there is
  no binary to parse, and markitdown passes wikilinks through as literal text,
  losing the link graph that is the point of importing a PKM tool.
- **One universal "Markdown-with-wikilinks" importer.** Rejected: Obsidian,
  Logseq, Notion, and Roam differ in link syntax, frontmatter, and export layout
  enough that a single importer becomes a tangle of special cases; per-tool
  converters behind the registry are cleaner and independently testable.
- **Auto-create `## Related` edges from resolved wikilinks.** Rejected: an
  imported edge nobody reviewed is not a validated edge (ADR-074, ADR-065).
  Wikilinks enter as candidates for promotion, not as asserted edges.
- **Keep ingest to office documents; tell PKM users to convert manually.**
  Rejected: it leaves real, common knowledge bases outside the front door and
  forgoes the link graph they already maintain.

## Related Decisions

- adr-072
- adr-074
- adr-065
- adr-002

## Related Requirements

- rac-note-tool-ingest-sources

## Related Designs

- note-tool-ingest-sources

## Related Roadmaps

- v0.30.0-note-tool-ingest-sources
