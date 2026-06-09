# Changelog

User-visible changes to RAC, by release. Follows the spirit of
[Keep a Changelog](https://keepachangelog.com/): user impact over implementation
details, release history over commit history.

## Unreleased

### Added

- `rac new <type> <output-path>` — create a valid artifact from its canonical
  bundled template; deterministic, AI-free, and never overwrites an existing
  file (v0.7.10).
- `rac templates` — list the canonical artifact templates available to
  `rac new`, with `--json` for tools (v0.7.10).
- `rac validate <directory>` — validate every recognized artifact in a tree in
  one command; unrecognized documents are skipped, not failed.
- `rac review <directory>` — full repository review: validation, relationship
  integrity, and completeness as one prioritized worklist (invalid artifacts
  first, then broken relationships, then advisory findings), each finding with
  a concrete suggested action. Exits `1` only on blocking issues.
- CI trust gates: RAC's own `rac/` corpus must pass `rac validate`,
  `rac relationships --validate`, and `rac review` (dogfood battery), and CLI
  output is pinned byte-for-byte by golden tests.
- README build badge, "How RAC earns trust" section, CHANGELOG.md, and
  CONTRIBUTING.md.
- `rac portfolio --json` now lists `artifacts.unknown_paths` (additive).
- `rac index` — flat artifact inventory (id, type, title, path) for tools and
  agents (v0.7.5).

### Changed

- Documentation restructured around task-focused guides under `docs/`
  (quickstart, CLI reference, artifacts, relationships, repository workflow,
  testing); README simplified to an overview (v0.7.6–v0.7.7).

### Fixed

- RAC's own planning corpus now passes its own validation: one invalid roadmap
  repaired and all cross-artifact references resolve.

## v0.7.3 — 2026-06-06

### Added

- `rac portfolio` — one-screen repository intelligence: counts by type,
  validity, completeness, relationship coverage, attention list, health score.

## v0.7.2 — 2026-06-06

### Added

- `rac relationships --validate` — resolve every cross-artifact reference and
  report broken, ambiguous, self-referencing, or duplicate-identifier findings.

## v0.7.1 — 2026-06-06

### Added

- `rac relationships` — discover and report the explicit references artifacts
  declare to each other.

## v0.7.0 — 2026-06-06

### Added

- Relationship metadata: artifacts can declare `## Related Requirements`,
  `## Related Decisions`, and similar sections that RAC recognizes and counts.

## v0.6.3 — 2026-06-05

### Added

- Design artifact type: validate and inspect product-design documents.

## v0.6.2 — 2026-06-05

### Added

- Prompt artifact type: validate and inspect reusable AI prompts.

## v0.6.1 — 2026-06-05

### Added

- Guided improvement for roadmaps (`rac improve` understands roadmap sections).

## v0.6.0 — 2026-06-05

### Added

- Roadmap artifact type: validate and inspect roadmap documents.

## v0.5.2 — 2026-06-05

### Added

- `rac schema` — show the expected structure of any artifact type, with
  `--template` to emit a starting document.

## v0.5.0 — 2026-06-05

### Added

- `rac improve` — actionable suggestions (and templates) for incomplete
  artifacts.

## v0.4.2 — 2026-06-05

### Added

- Decision (ADR) artifact type with status/category metadata.
- `rac inspect` — classify a document and report its completeness.

## v0.3.1 — 2026-06-04

### Added

- More ingest formats (HTML, PPTX, XLSX).

## v0.3.0 — 2026-06-03

### Added

- `rac ingest` — convert DOCX/PDF documents into RAC-compatible Markdown.

## v0.2.0 — 2026-06-02

### Added

- `rac stats` — summarize a directory of artifacts: counts, quality signals,
  missing recommended sections.

## v0.1.0 – v0.1.3 — 2026-06-01

### Added

- Initial release: `rac validate` and `rac diff` for requirement documents,
  human and `--json` output, stable exit codes (`0` ok, `1` validation failed,
  `2` usage error).
