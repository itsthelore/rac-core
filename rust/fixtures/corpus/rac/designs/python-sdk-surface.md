---
schema_version: 1
id: RAC-KV5DJX7Q5BTQ
type: design
tags: [sdk, api, packaging, architecture]
---
# Design: Python SDK Public Surface

## Context

RAC's layered architecture (ADR-008, ADR-015) already separates pure analysis
(`rac.core`) from reusable capabilities behind the service gate (`rac.services`)
from thin interfaces (CLI, MCP, Explorer). Everything an SDK needs exists —
typed dataclass results with `to_dict()` JSON contracts (ADR-007), src-layout
packaging, optional `explorer` / `ingest*` extras — but there is no public
*surface*: `import rac` exposes only `__version__`, service exceptions have no
common root, and nothing marks public versus internal.

ADR-062 fixes the boundary (the public surface is `rac.__all__`; one exception
root; additive results; `1.0` semantics deferred). This design is the *how*: the
concrete symbol list, the exception hierarchy, and the extras mapping the
foundation release (v0.20.0) implements.

## User Need

A Python author embedding RAC — a CI script, an internal tool, an editor
integration, an agent runtime — needs to:

- import RAC capabilities from one obvious place, not deep private module paths;
- catch RAC failures with a single `except`, without enumerating every service's
  exception types;
- read results programmatically with a contract that will not silently break;
- know which names are stable to depend on and which are internal.

The need is *library ergonomics*, not new analysis behaviour: the SDK re-exposes
existing services, it does not compute anything the CLI does not already.

## Design

### 1. Flat public namespace (`rac.__all__`)

The top-level package re-exports a curated set, grouped by purpose. `import rac`
imports the service tree eagerly (accepted in ADR-062). The set:

- **Core authoring primitives:** `Product`, `Issue`, `parse`, `parse_file`,
  `classify`, `validate`, `has_errors` — Markdown ↔ Product AST.
- **Validation services:** `validate_product` (single parsed artifact, with
  repository severity overrides), `validate_directory` (a corpus),
  `validate_relationships`.
- **Portfolio / repository intelligence:** `collect_stats`, `build_review`,
  `build_portfolio_summary`, `build_repository_index`, `summarize_relationships`,
  `build_relationship_report`, `relationships_from_corpus`, `artifact_recency`,
  `build_watchkeeper_report`.
- **Lookup:** `resolve_artifact`, `find_artifacts`.
- **Authoring / lifecycle:** `create_artifact` (+ `CreatedArtifact`),
  `quickstart`, `init_repository`, `improve_product`, `build_inspection`,
  `inspect_directory`, `ingest`, `diff_artifacts`, `migrate_metadata`,
  `build_corpus_export`.
- **Errors:** `RACError`.

`rac.services.__all__` mirrors the service-layer subset, so
`from rac.services import build_review` is equally valid; `from rac import
build_review` is the canonical form. The `diff` service is re-exported as
`diff_artifacts` to avoid a too-generic top-level name.

Curation principle: export the capabilities a consumer drives, not every public
function in the service tree. Internal helpers (`report_from_corpus`,
`index_from_corpus`, the `*_from_corpus` snapshot variants) stay reachable by
explicit module import but are out of `__all__` — internal, free to change.

### 2. Exception hierarchy rooted at `RACError`

`rac/errors.py` owns a single base, `class RACError(Exception)`. Every
service/core exception that can propagate out of a public function re-roots under
it, keeping its own name, message, and module home:

| Module | Exceptions |
| --- | --- |
| `services.create` | `OutputPathExists`, `OutputDirectoryMissing`, `MissingRepositoryConfig`, `IdGenerationExhausted` |
| `services.ingest` | `ConversionError`, `UnsupportedDocument` (already chains `ConversionError`) |
| `services.init` | `InvalidRepositoryKey`, `RepositoryKeyConflict`, `MalformedRepositoryConfig` |
| `services.quickstart` | `CorpusNotEmpty` |
| `services.hook` | `NotAGitWorkTree`, `HookFileExists` |
| `services.skill` | `SkillFileExists` |
| `services.revisions` | `NotAGitRepository`, `RevisionNotFound` |
| `core.templates` | `TemplateNotFound`, `TemplateResourceMissing` |
| `core.skills` | `SkillNotFound`, `SkillResourceMissing` |
| `core.hooks` | `HookNotFound`, `HookResourceMissing` |
| `core.operations` | `OperationCancelled` |
| `explorer.launch` | `ExplorerUnavailable` |
| `output.portal` | `PortalShellMissing`, `PortalSeamMissing` |

`rac.errors` imports nothing from `rac`, so re-rooting introduces no import
cycle. The change is backward compatible: `RACError` is an `Exception`, so
existing `except ConcreteError` clauses are unaffected and `except RACError`
becomes the generic catch.

### 3. Extras mapping

The SDK keeps the core install light and gates heavy dependencies behind extras,
matching the lazy-import discipline already in the codebase:

| Install | Pulls | Powers |
| --- | --- | --- |
| `requirements-as-code` (core) | `markdown-it-py`, `pyyaml`, `mcp` | parse/validate/stats/review/relationships/resolve/index/portfolio, MCP |
| `[explorer]` | `textual>=1.0` | `rac.explorer` TUI; `ExplorerUnavailable` if absent |
| `[ingest]` / `[ingest-pdf]` / `[ingest-office]` / `[ingest-all]` | `markitdown[...]` | `ingest` converters; `UnsupportedDocument` if the needed extra is absent |

`ingest` and the explorer launcher import their heavy dependency lazily inside
the call path, so `import rac` succeeds on a core-only install and a missing
extra surfaces as a typed `RACError` subclass with an install hint, never an
`ImportError` traceback.

## Constraints

- Additive only (ADR-007): result `to_dict()` contracts gain fields, never lose
  or repurpose them; `schema_version` gates breaking shape changes.
- No import cycles: `rac.errors` depends on nothing in `rac`; the top-level
  re-exports pull only from `rac.core`, `rac.services`, and `rac.errors`.
- Pre-1.0 (ADR-062): the surface may change between minor versions, called out in
  release notes; no frozen-API pledge until `1.0` is defined.
- The SDK adds no new analysis — it re-exposes existing services; behaviour
  parity with the CLI is a requirement, not a goal.

## Rationale

A single flat namespace plus one exception root is the smallest change that turns
an internally-layered codebase into a usable library, and it costs almost
nothing because the services already exist and already return typed results. The
curated (not maximal) export list keeps the stable surface small enough to
maintain, while explicit module imports remain available for the internal
helpers power users occasionally need. Re-rooting exceptions is mechanical and
backward compatible, so it buys generic error handling at no migration cost.

## Alternatives

- **Generated `__all__` from a registry.** Rejected: the public surface is an
  editorial decision, not a mechanical one; an explicit hand-maintained list is
  the artifact that records intent.
- **A separate `rac-sdk` distribution.** Rejected: the SDK is the same code as
  the CLI behind the same gate; a second package would duplicate packaging and
  diverge. One distribution, one surface.
- **Export result classes for every service.** Rejected: consumers can use
  results via duck typing and `to_dict()`; exporting only the most-annotated
  types keeps the surface lean. More can be added additively if demand appears.

## Accessibility

Not applicable — this is a code-level API surface with no user-facing UI. Docs
(v0.20.1) follow the repository's existing readable-prose conventions.

## Style Guidance

- Public functions keep verb-first names (`build_*`, `validate_*`, `collect_*`)
  consistent with the existing service vocabulary.
- Exception names stay noun phrases describing the condition
  (`OutputPathExists`, `CorpusNotEmpty`).
- Docstrings on `rac/__init__.py`, `rac/errors.py`, and `rac/services/__init__.py`
  state the public-surface contract so the boundary is discoverable from the code.

## Open Questions

- What `1.0` freezes, and whether semver then governs the surface (deferred by
  ADR-062) — decided when the `1.x` line is defined.
- Whether more result dataclasses (e.g. `DirectoryValidation`, `PortfolioStats`)
  should join `__all__` for type-annotation convenience; added additively if
  consumers ask.
- Whether a typed `py.typed` marker and published stubs are needed for downstream
  type-checking (likely yes; scoped with the v0.20.1 docs work).
