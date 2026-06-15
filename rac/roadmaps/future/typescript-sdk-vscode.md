---
schema_version: 1
id: RAC-KV6ADX50HFPF
type: roadmap
tags: [sdk, typescript, editor]
---
# RAC TypeScript SDK and VS Code / Cursor Extension

## Status

Planned

## Context

The Python SDK (v0.20.0) makes RAC importable as a library, and the MCP server,
the GitHub Actions, and `rac … --json` already give agents, CI, and scripts
language-neutral access. The `lore-web` viewer shows TypeScript consuming the
`rac export` payload today. The surface none of these reaches is the one where a
human authors decisions and requirements: the **editor**. A maintainer writing a
roadmap or an ADR in VS Code / Cursor gets no inline feedback — they must drop to
a terminal and run `rac validate`.

A TypeScript SDK plus a VS Code / Cursor extension closes that gap: validation
squiggles as you write, hover/peek on artifact IDs, go-to-definition, and "this
references a retired decision" surfaced in the editor. Per ADR-063 the SDK is a
**thin client** — it shells out to the installed `rac` binary and deserializes
the stable JSON contracts (ADR-007); it reimplements none of the engine, so it
cannot drift from Python's deterministic classification and validation. This is
the Ruff / ESLint editor-extension pattern.

This item is unscheduled. It sits behind the in-flight work (the planned
repository restructure and v0.20.1). It is recorded now so the architecture
decision (thin, not native — ADR-063) and the scope are fixed before
implementation begins.

## Outcomes

- A maintainer authoring RAC Markdown in VS Code / Cursor sees validation
  findings inline (squiggles + Problems panel) without leaving the editor.
- Artifact IDs and aliases are navigable: hover shows the target, go-to-definition
  jumps to it, and a reference to a retired artifact is flagged where it is typed.
- A published npm package (`@rac/sdk` or similar) wraps the `rac` CLI with typed
  results and one error root, mirroring the Python SDK's curated, flat surface,
  reusable by any Node consumer (the extension is its first client).
- Behaviour matches the CLI by construction — the extension runs the same engine,
  so findings are identical to `rac validate` / `rac review`.
- The extension degrades gracefully when `rac` is absent: a clear "install RAC"
  prompt, never a broken or silent state.

## Initiatives

### Initiative 1 — TypeScript client package

A Node package that locates and invokes the `rac` binary, runs commands with
`--json`, and returns typed result objects. Surface mirrors the Python SDK
subset: `validate`, `review`, `stats`, `resolve`, `find`, `relationships`,
`export`. One error root (e.g. `RacError`) covering "rac not found", non-zero
exits, and malformed output. The result types extend the contracts `lore-web`
already declares (`lore-web/src/viewer/types.ts`) rather than inventing new ones.

### Initiative 2 — `rac` discovery, versioning, and lifecycle

Locate the binary (extension setting → `PATH` → workspace virtualenv), check its
`schema_version` against what the SDK expects, and surface a graceful, actionable
state when `rac` is missing or too old. The SDK never bundles a divergent engine;
it only ever calls the user's `rac` (ADR-063).

### Initiative 3 — Extension MVP: inline validation

On save and on debounced change, run `rac validate <file> --json` for the edited
artifact and map issues to editor diagnostics (severity, message, line). The
Problems panel mirrors `rac validate`. Validate the edited file, not the whole
corpus, to keep edits responsive.

### Initiative 4 — Editor intelligence: IDs and relationships

Hover and peek on artifact IDs / aliases via `rac resolve` / `rac find`;
go-to-definition to the target file; and surface relationship findings (a
reference to a retired or missing artifact) via `rac relationships` / `rac
review`, drawn where the reference is authored.

### Initiative 5 — Packaging and contract conformance

Marketplace / OpenVSX packaging for VS Code and Cursor, and a contract test
asserting the SDK's TypeScript types match the live `rac … --json` /
`rac export` shapes, so a drift in the *contract* is caught in CI even though the
engine never forks.

## Constraints

- Thin client only (ADR-063): no native TypeScript reimplementation of parse,
  classification, or validation. All analysis stays in the Python engine.
- Consume only stable contracts — `--json`, `export`, exit codes, MCP (ADR-007).
  Never depend on private internals or undocumented output.
- Desktop editors only at first: the extension uses a subprocess, so web VS Code
  (vscode.dev) is out of scope until/unless a native engine exists.
- The extension requires `rac` to be present; it surfaces its absence rather than
  shipping a second engine.

## Non-Goals

- A native in-process TS engine, browser/edge execution, or an interactive
  `lore-web` — explicitly deferred by ADR-063; revisit only if zero-install or
  in-browser becomes a priority, and only behind shared specs + a conformance
  suite.
- An LSP server. The MVP uses direct, debounced CLI invocations; a long-lived
  language server is a possible later refinement, not part of this scope.
- Authoring/scaffolding beyond the CLI: artifact creation stays `rac new` / the
  editor; the extension surfaces findings and navigation, it is not an authoring
  framework.
- Re-exposing agent capabilities already covered by MCP.

## Implementation Contract

- A published Node package wraps the `rac` CLI with typed results and a single
  error root; its types extend the existing `lore-web` contract types.
- The extension reports `rac validate` findings as editor diagnostics for the
  edited artifact, on save and on debounced change.
- ID hover / go-to-definition is backed by `rac resolve` / `rac find`; relationship
  findings by `rac relationships` / `rac review`.
- `rac` is located via setting → `PATH` → workspace; a missing or stale binary
  yields an actionable prompt, never a silent failure.
- A CI contract test pins the TS types to the live `--json` / `export` shapes.

## Success Measures

- Editing an invalid artifact in VS Code / Cursor shows the same findings as
  `rac validate` on that file, inline, without a terminal.
- Hovering an artifact ID resolves it; go-to-definition opens the target; a
  reference to a retired artifact is flagged in the editor.
- With `rac` absent, the extension shows an install prompt and no errors.
- The contract test fails if the TS types and `rac … --json` / `export` diverge.

## Risks

- `rac` missing or version-skewed on the user's machine. Mitigated by discovery
  order, a `schema_version` check, and graceful "install/upgrade RAC" UX.
- Subprocess latency per keystroke. Mitigated by debouncing and validating the
  single edited file rather than the whole corpus.
- The TS types drift from the JSON contract over releases. Mitigated by the CI
  contract test (Initiative 5) and ADR-007's additive guarantee.
- Scope creep toward a native engine. Mitigated by ADR-063, which fixes the thin
  boundary and makes native an explicit, guarded exception.

## Assumptions

- The `rac … --json` and `export` contracts are stable enough (ADR-007) to be the
  SDK's machine surface without rework.
- Target users are developers who have, or can `pip install`, `rac` — acceptable
  for a desktop editor extension.
- The planned repository restructure will settle the home for a `typescript/` (or
  equivalent) sub-project before this is scheduled; placement follows the
  examples-sub-project convention recorded for v0.20.1.

## Related Decisions

- adr-002
- adr-007
- adr-008
- adr-015
- adr-062
- adr-063

## Related Roadmaps

- v0.20.0-python-sdk-foundation
- v0.20.1-python-sdk-docs
