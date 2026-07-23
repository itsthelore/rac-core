---
schema_version: 1
id: RAC-KVJK92SM2A1R
type: decision
---
# ADR-072: Document Ingestion Parser Is markitdown

## Context

RAC's `rac ingest` converts a rich source document (DOCX, PDF, HTML, PPTX,
XLSX) into Markdown so it can be classified and restructured into artifacts.
Per ADR-010, ingestion is *conversion only* — its job is to turn a document
into Markdown text that preserves structure (headings, lists, tables), and
nothing more. It does not judge artifact type or extract semantics.

Today that conversion uses **markitdown** (Microsoft, MIT). It is wired as an
*optional, pure-Python* dependency: the core install pulls none of it, and the
format support ships as granular extras (`ingest`, `ingest-pdf`,
`ingest-office`, `ingest-all`). It is isolated behind the `DocumentConverter`
Protocol in `src/rac/services/ingest.py` — a single `MarkItDownConverter`
registered in `_CONVERTERS`, returning `IngestResult.markdown: str`. DOCX, HTML,
PPTX, and XLSX are converted natively in Python. No prior ADR pins the parser,
so the choice is open.

The maintainer asked whether to swap markitdown for **liteparse**
(run-llama/liteparse, Apache-2.0). On inspection liteparse is a different class
of tool:

- It is a **TypeScript/Node.js** project. Its PyPI package shells out to a Node
  CLI, so using it from Python **requires a Node.js runtime** on the host.
- For the office and HTML formats RAC relies on most, it requires
  **LibreOffice** and **ImageMagick** as external system binaries; PDF is native
  (bundled PDFium) with OCR via bundled Tesseract.
- Its strengths are **layout-aware/spatial PDF extraction** (bounding boxes),
  **OCR of scanned documents**, and page screenshots for agents. Its own
  documentation steers complex documents toward the cloud LlamaParse service and
  notes that "Markdown reconstruction quality varies with document complexity."

Those strengths target a problem RAC's ingest does not have. RAC ingests
born-digital product documents (PRDs, decision records) where the need is clean
document→Markdown text, not OCR or spatial reconstruction.

## Decision

Keep **markitdown** as RAC's document-ingestion converter. Do not adopt
liteparse as the default parser.

Preserve the `DocumentConverter` Protocol seam (`src/rac/services/ingest.py`) so
that, *if* PDF extraction quality ever becomes a real need, a liteparse-backed
converter can be added as an **optional, PDF-only** converter behind its own
extra — registered ahead of markitdown for `.pdf` only — without replacing
markitdown or disturbing the native-Python office/HTML path. That is a future
option, explicitly not taken now.

This decision records the parser choice; it changes no code, dependency, or
packaging. `src/rac/services/ingest.py` and `pyproject.toml` are unchanged.

This is distinct from ADR-059, which governs reuse of a single *internal*
markdown-it-py parser instance for parsing RAC's own artifacts. ADR-059 is about
reading RAC Markdown; this ADR is about the *ingest* converter that turns
foreign documents into Markdown. The two parser decisions should not be
conflated.

## Consequences

### Positive

- Keeps RAC a **pure-Python `pip install`** (ADR-005): no Node.js runtime and no
  LibreOffice/ImageMagick system binaries are introduced.
- DOCX, HTML, PPTX, and XLSX continue to convert **natively in Python**; the
  common DOCX path does not regress to requiring LibreOffice.
- Conversion stays **deterministic** — no OCR variability enters the pipeline.
- markitdown remains *optional* and granular per format, so the core tool and
  Markdown pass-through work with no ingest extra installed.
- The decision and its evaluation are now durable corpus knowledge, so the
  liteparse question does not have to be re-litigated from memory.

### Negative / trade-offs

- markitdown's PDF extraction is plainer than a layout-aware parser; RAC accepts
  simpler PDF fidelity in exchange for the lighter, all-Python footprint.
- RAC forgoes liteparse's OCR and spatial-extraction features — acceptable,
  since ADR-010 scopes ingest to structure-preserving text only.

### Risks

- markitdown could become unmaintained or fall behind on a format. Mitigation:
  the `DocumentConverter` Protocol makes the parser swappable at one seam, and a
  per-format converter (including an opt-in liteparse PDF converter) can be added
  without touching the rest of the pipeline.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

### Swap markitdown for liteparse

Rejected. It would add a Node.js runtime plus LibreOffice and ImageMagick system
binaries to a pure-Python CLI, and would regress the common DOCX/Office path from
native Python to a LibreOffice shell-out — all to gain OCR and layout-aware
extraction that RAC's ingest (ADR-010) does not use. The footprint cost is real
and the benefit does not apply to RAC's inputs.

### Add liteparse now as an optional PDF-only converter

Deferred. The `DocumentConverter` Protocol makes this clean, and it would keep
markitdown as the default while offering stronger PDF parsing on opt-in. But it
still drags in the Node.js + Tesseract footprint for that extra, and there is no
evidence yet that markitdown's PDF output is a practical limitation. Revisit only
if PDF quality becomes a recurring complaint.

### Drop rich-document ingest entirely

Rejected. Removing document conversion would contradict ADR-006 (Ingestion Over
Rewrite): RAC must meet users where their knowledge already lives rather than ask
them to rewrite documents by hand.

## Related Decisions

- adr-005
- adr-006
- adr-008
- adr-010
- adr-011
- adr-059

## Review Date

Revisit if PDF or scanned-document extraction quality becomes a recurring
complaint from users, or if markitdown becomes unmaintained or drops a format
RAC depends on.
