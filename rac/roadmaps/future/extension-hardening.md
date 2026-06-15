---
schema_version: 1
id: RAC-KV6ESC5GQ55C
type: roadmap
tags: [sdk, typescript, editor, enforcement]
---
# RAC Extension Hardening

## Status

Planned

## Context

The VS Code / Cursor extension (see `typescript-sdk-vscode`) shipped an MVP:
live validation, hover, and go-to-definition, all as a thin client over the
`rac` CLI (ADR-063). That makes it useful; it does not yet make it
*distinctively RAC*, nor production-grade.

Two gaps stand out. First, the MVP validates each file in isolation, but RAC's
value is cross-artifact — "enforcement is the product" (ADR-049). A reference to
a missing or **retired** decision (ADR-051) is exactly what RAC exists to catch,
and surfacing it where it is authored is the headline feature still missing.
Second, an extension destined for a marketplace needs robustness work — scoped
activation, version-skew handling, caching, a real output channel — before
anyone installs it.

This roadmap formalizes the full hardening backlog discussed for the extension,
in one place, so the work is scoped before it is scheduled. It is unscheduled:
it follows the in-flight repository restructure and v0.20.1. Every item remains
a thin client over `rac`'s stable contracts (ADR-063) — no engine
reimplementation.

## Outcomes

- The extension surfaces cross-artifact violations — broken and retired-target
  references — live, at the reference site, not just per-file structural issues.
- Authoring is ergonomic: ID completion, section quick-fixes, and artifact
  scaffolding from inside the editor.
- Navigation is complete: status-aware hover, find-all-references, document
  links, an outline, and workspace-symbol jump-to-artifact.
- The corpus is legible at a glance: a health indicator in the status bar and
  workspace-wide diagnostics, not only for open files.
- The relationship graph is viewable in-editor, reusing the existing `lore-web`
  viewer and `rac export`.
- The extension is robust for public use: it activates only in RAC workspaces,
  detects `rac` version skew, caches lookups, and logs to a dedicated channel.
- Every feature is backed by a stable `rac` contract; nothing reimplements the
  engine (ADR-063).

## Initiatives

### Initiative 1 — Cross-artifact enforcement in the editor (headline)

Surface relationship findings at the reference site: a declared reference that
does not resolve, and a reference to a **retired** (Superseded/Deprecated)
artifact (ADR-051), drawn distinctly. Backed by `rac relationships --validate`
and `rac review`, with target status from `rac resolve` / `rac export`. This is
what makes the extension RAC rather than a generic Markdown linter (ADR-049,
`rac-cross-artifact-enforcement`).

### Initiative 2 — Authoring ergonomics

- ID / alias **completion** in relationship sections (`Related Decisions`, …),
  sourced from `rac find` / the repository index.
- **Quick-fix code actions** for structural findings — insert a missing
  recommended section — from `rac improve --template` / `rac schema`.
- A **"New RAC artifact"** command that scaffolds via `rac new`, plus per-type
  section **snippets**.

### Initiative 3 — Navigation

- **Hover enrichment**: show the target's lifecycle status (e.g. ⚠ Superseded)
  and a body snippet, so hover answers "is this still current?".
- **Find-all-references** (incoming links) via `rac relationships` / the MCP
  `get_related` shape.
- **Document links** (clickable IDs), an **Outline** (document symbols over
  `##` sections), and **workspace symbols** (jump to any artifact by ID/title).

### Initiative 4 — Ambient awareness

- A **status-bar** item showing the corpus health score and valid/invalid count
  (`rac review`), click-through to the review.
- **Workspace-wide diagnostics** on activation (`rac validate <dir>`), so the
  Problems panel reflects the whole corpus, not just open documents.

### Initiative 5 — Corpus visualization

- A **"RAC Explorer" webview** embedding the existing `lore-web` viewer, fed by
  `rac export` — the relationship graph in an editor side panel. Reuses the
  static viewer's assets and the stable export contract.

### Initiative 6 — Robustness and DX (pre-publish hardening)

- **Scoped activation**: only in RAC workspaces (`workspaceContains` a
  `.rac/config.yaml`), so non-RAC repositories are untouched.
- **Version-skew detection**: compare the installed `rac` `schema_version` with
  what the SDK expects and warn on mismatch.
- **Caching**: an in-memory index of resolve/find results, invalidated on
  document change, so hover and completion do not spawn `rac` per interaction.
- A dedicated **"RAC" output channel** for errors (replacing console logging),
  and **marketplace / OpenVSX packaging** metadata (icon, categories, changelog).

## Constraints

- Thin client only (ADR-063): every feature is backed by a stable `rac` contract
  (`--json`, `export`, MCP); no reimplementation of parse/classify/validate.
- Additive JSON consumption (ADR-007); never depend on private internals.
- Desktop editors (subprocess-based); web VS Code stays out of scope until/unless
  a native engine exists.
- Performance: lookups are cached and debounced; the extension must stay
  responsive on a large corpus without spawning `rac` on every keystroke or hover.

## Non-Goals

- A native in-process engine or browser/edge execution (deferred by ADR-063).
- An authoring framework beyond scaffolding and quick-fixes; artifact creation
  stays `rac new`.
- A long-lived LSP server. The features here can later be refactored behind one,
  but an LSP is not required to deliver them and is not in scope.
- Re-exposing agent capabilities that MCP already provides.

## Implementation Contract

- Relationship findings are mapped to the source token inside the declared
  relationship section (relationship issues carry `source_path` but no line, so
  the extension locates the target text); retired-target references are
  distinguished from unresolved ones.
- Completion and hover are backed by `rac find` / `rac resolve`, served from the
  in-memory cache and refreshed on document change.
- The RAC Explorer webview consumes `rac export --json` (the `lore-web` shape).
- The extension activates only when a `.rac/config.yaml` is present in the
  workspace, and writes diagnostics/logs without telemetry.

## Success Measures

- A reference to a missing or retired artifact shows a diagnostic at that
  reference, consistent with `rac relationships --validate` / `rac review`.
- Typing in a relationship section offers artifact-ID completions; accepting one
  resolves cleanly.
- The status bar reflects `rac review`'s health score and updates as artifacts
  change.
- The RAC Explorer panel renders the corpus relationship graph from `rac export`.
- On a large corpus, repeated hover/completion is served from cache without a new
  `rac` process each time.

## Risks

- Relationship issues lack a line/anchor, so placing the diagnostic requires
  locating the target token within the relationship section. Mitigated by that
  section-scoped search; if it proves brittle, a small additive `--json`
  line/anchor on `rac relationships` is a separate, scoped change.
- `rac` spawn latency for completion/hover/enforcement at scale. Mitigated by
  caching, debouncing, and an index refreshed on change; an LSP server is the
  escape hatch if the subprocess model hits a ceiling.
- Webview coupling to `lore-web`. Mitigated by consuming the stable export
  contract (ADR-007), exactly as the static viewer does.

## Assumptions

- `rac relationships --validate` and `rac review`, together with status from
  `rac resolve` / `rac export`, expose enough to identify broken and retired
  references; any finer signal needed is a small additive `rac` change scoped
  separately.
- The repository restructure settles the `typescript/` home before this work is
  scheduled.

## Related Decisions

- adr-007
- adr-008
- adr-015
- adr-049
- adr-051
- adr-063

## Related Requirements

- rac-cross-artifact-enforcement

## Related Roadmaps

- typescript-sdk-vscode
