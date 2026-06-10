# Changelog

User-visible changes to RAC, by release. Follows the spirit of
[Keep a Changelog](https://keepachangelog.com/): user impact over implementation
details, release history over commit history.

## Unreleased

### Added

- Explorer navigation (v0.8.1): browse every artifact grouped by type, open
  any artifact's context view (identity, validation state, completeness,
  relationships, diagnostics), and reach anything through the `/` command
  surface — `open`, `find`, `browse`, `home`, `help`, `quit`, with bare text
  treated as a search using `rac resolve` / `rac find` semantics.
- Explorer first-run onboarding (v0.8.1): launch states derive from
  repository content (existing, empty, or invalid repository); returning
  users skip onboarding via a marker under the XDG state directory — the
  only state Explorer persists.
- `rac explorer` now defaults to the `rac/` root when present (ADR-018),
  falling back to the current directory (v0.8.1).
- `rac explorer [directory]` — interactive terminal Explorer application
  shell (Textual): loads a repository without blocking the interface, shows
  live progress and a repository summary (artifact counts, relationships,
  diagnostics, health score), and recovers from failures in place with
  reload. Ships as the optional `explorer` extra
  (`pip install 'requirements-as-code[explorer]'`); without it the command
  prints an install hint (v0.8.0).
- First-class repository model in the service layer: `load_repository`
  composes index, validation, relationships, and portfolio over a single
  corpus walk into one navigable object (artifacts, relationships with
  resolution outcomes, unified diagnostics) for Explorer and future
  consumers; no CLI or JSON output changes (v0.8.0).
- Operation primitives for long-lived consumers: progress reporting and
  cooperative cancellation across repository loading, validated against
  1000+ artifact corpora (v0.8.0).
- CI battery integrity (v0.7.14): eight test files (~1,300 lines, including
  all coverage for `rac new` and `rac migrate`) were missing from the CI
  battery matrix and never ran; they are restored, and a new guard test
  fails the suite if any test file is ever orphaned again.
- Static quality gates (v0.7.14): ruff (lint + format) and mypy now gate CI;
  pull requests run the gates plus a fast smoke battery (ADR-027 amended),
  while the full battery grid stays merge-gated on `main`. CLI output is
  unchanged — all golden files are byte-identical.
- Test coverage is reported on every CI run (report-only, currently 97%)
  (v0.7.14).

### Changed

- Repository corpus traversal is defined once in core (`walk_corpus`) and
  consumed by every repository command — behavior and output unchanged
  (v0.7.14).

- `rac migrate metadata <directory>` — migrate existing recognized artifacts
  onto canonical frontmatter identity: idempotent, byte-preserving, with
  `--dry-run` preview; unrecognized documents are reported, never guessed at
  (v0.7.13).

- `rac resolve <ID>` — resolve any artifact ID (canonical or legacy alias) to
  its type, title, and path; duplicates are reported with every path, never
  silently resolved (v0.7.12).
- `rac find <query>` — deterministic artifact search by ID, title, filename,
  or path, with `--type` filtering and JSON output (v0.7.12).
- `rac relationships` human output resolves references to human-friendly
  labels — `Title (type · ID)` — while JSON keeps stored references unchanged
  (v0.7.12).
- `rac index` entries gain an additive `aliases` field: every identifier an
  artifact answers to, canonical first (v0.7.12).

- `rac init` — establish the repository identity namespace
  (`.rac/config.yaml` with a `repository_key`); idempotent, and an
  established key is never silently changed (v0.7.11).
- Hybrid artifact metadata: a leading YAML frontmatter block
  (`schema_version`, `id`, `type`, `relationships`) is parsed, strictly
  schema-validated, and exposed as canonical machine-operational metadata;
  artifacts without frontmatter remain fully supported (v0.7.11).
- System-assigned opaque artifact IDs (e.g. `RAC-01JY4M8X2QZ7`): branch-safe,
  offline, stable across renames, moves, and type changes; `rac new` assigns
  one automatically and `rac index` reports it (v0.7.11).
- Identity validation: conflicting frontmatter/legacy identity and duplicate
  canonical IDs are deterministic errors — RAC never silently picks one
  (v0.7.11).
- Relationship references resolve against legacy identity aliases (`## ID`
  values, filename prefixes, stems), so adopting canonical IDs does not break
  existing human-readable references; RAC's own corpus now carries canonical
  frontmatter identity (v0.7.11).
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
