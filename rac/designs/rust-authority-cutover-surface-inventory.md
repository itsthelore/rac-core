---
schema_version: 1
id: RAC-KXWVF13DS53R
type: design
tags: [architecture, rust, migration, distribution, ci]
---
# Rust Authority Cutover Surface Inventory

## Context

ADR-118 retires the Python engine rather than maintaining the ADR-116
two-engine arrangement indefinitely. Deletion is safe only when every current
runtime, library, install, CI, and compatibility surface has an explicit owner
and disposition.

This inventory was taken from `itsthelore/rac-core` `main` at commit
`ffb8ffcd6e4efbd9619340fab039989a7aab9e5a` on 2026-07-19. The external
`itsthelore/rac-ci` capability list was inspected from its `main` README on the
same date. Both repositories are moving quickly; an implementation PR must
refresh the affected rows rather than treating this document as live discovery.

## User Need

Users need one RAC product, not a visible assembly of engine implementations and
repositories. An existing Markdown corpus must work with the native `rac`
installation alone. A user who wants initial corpus conversion and external
connectors must be able to install the supported local toolchain with one
command. A maintainer must be able to remove the Python engine without silently
dropping a command, SDK contract, Action, platform, or migration route.

## Design

### Runtime and API Surfaces

| Surface | Baseline owner/state | End state | Disposition and gate |
| --- | --- | --- | --- |
| Root help, no command, unknown command, `--version` | Python console script decides whether to dispatch | Native `rac` | **Port/retain.** Golden stdout/stderr/exit-code fixtures must cover parse-level behavior before dispatcher removal. |
| Covered CLI commands | Rust implements the ADR-116 parity set; Python dispatcher execs bundled binaries | Native `rac` | **Retain Rust, remove Python duplicate.** Conformance, dogfood, and mutation gates become blocking. |
| `retrieve` CLI | Implemented in Rust but intentionally hidden from the mainline choice list | Native `rac` when its contract is adopted | **Adopt contract-first.** Add language-neutral vectors and update help in the same change; no permanent Python implementation is required after authority cutover. |
| `mcp` stdio | Rust `rac-mcp`; Python dispatcher can select it | Native `rac-mcp` | **Retain Rust.** Six tools and protocol/error frames remain golden-tested. |
| `mcp` HTTP | Rust transport and audit path exist | Native `rac-mcp` | **Retain Rust.** Concurrency, audit, authentication/profile, and HTTP parity fixtures are release gates. |
| `ingest` | Python services inside `src/rac`; MarkItDown extras and note-tool normalisers | `packages/rac-ingest/`, PyPI `rac-ingest`, executable `rac-ingest` | **Split package, same repository.** Preserve golden conversion fixtures, deterministic drafts, warnings, and no-overwrite behavior. Native `rac ingest` is at most an exec shim. |
| Explorer | Python/Textual optional extra | No product surface | **Remove.** Delete command, dependencies, tests, assets, and docs; a bounded deprecation message may precede removal. |
| Python import API (`rac.__all__`) | In-process Python engine API in `rac-core` | `rac-sdk/py`, subprocess client over native JSON contracts | **Replace.** Publish old-to-new method mapping; no FFI, engine imports, or behavior reimplementation. |
| Dispatcher and `RAC_ENGINE` | Python routes covered commands and supplies universal fallback | No dispatcher or engine selector | **Remove.** `RAC_ENGINE=python`, automatic fallback, and platform-wheel routing disappear after the deprecation release. |
| Shared artifact registry | Vendored under `src/rac/spec`, embedded by Rust | Language-neutral `spec/` or equivalent | **Relocate.** Byte-preserving move plus pinned `rac-spec` sync gate before `src/rac` deletion. |
| Templates, skills, hooks, Portal assets | Several canonical copies live beneath `src/rac` | Language-neutral `assets/` embedded by Rust | **Relocate.** Replace Python-copy equality tests with neutral-source integrity tests. |
| Final Python oracle | Live merge-blocking comparison | Recoverable historical tag and scheduled evidence only | **Freeze then retire.** Every parity basket needs an independent fixture owner before deletion. |

The covered CLI row must be regenerated from `src/rac/dispatch.py`,
`rust/rac-engine/src/cli.rs`, and current conformance case lists. At the baseline,
the native set includes validation, inspection, relationships, review, policy,
index/search, export, portfolio, agent integration, telemetry, scaffolding,
migration, and lifecycle commands; `ingest` and Explorer are deliberate gaps,
not accidental missing ports.

### Local Installation and Distribution

| Surface | End state | Required evidence |
| --- | --- | --- |
| GitHub Releases | Signed or provenance-backed native archives for the supported platform matrix, plus checksums | Extracted-artifact CLI/MCP/version smoke tests |
| Homebrew `rac` | Native runtime only; no Python dependency | Clean-machine install, `rac --version`, corpus validation, MCP smoke |
| Homebrew `rac-ingest` | Isolated Homebrew Python environment with pinned resources | Document and vault fixture conversion; system Python remains untouched |
| Homebrew `rac-connectors` | Isolated Python environment containing shipped connector CLIs and supported provider dependencies | Command/version tests and deterministic missing-credential behavior |
| Homebrew `rac-full` | Meta-formula depending on `rac`, `rac-ingest`, and `rac-connectors` | One transaction exposes `rac`, `rac-mcp`, `rac-ingest`, and `rac-connect` |
| PyPI `rac-core` | Bounded transition only; no permanent Python engine distribution | Deprecation release followed by retirement/redirect decision |
| PyPI `rac-ingest` | Independent package sourced from `packages/rac-ingest/` | Native `rac validate` integration against generated drafts |
| `rac-sdk` Python member | Developer-installed thin client | Injected-runner tests plus supported native-binary integration matrix |
| Container | Native multi-stage image with no Python runtime | Final-image smoke, SBOM/provenance, no Python executable present |

`rac-sdk` is not installed by `rac-full`: it is a developer library, not a local
product command. `rac-ci` is also not a formula dependency because its Actions
are consumed remotely.

### CI Delivery

At the baseline, `rac-ci` exposes these capability/platform members:

| Capability | Current command | End state |
| --- | --- | --- |
| Watchkeeper/GitHub | `rac watchkeeper` | Shared native setup, then thin command/annotation wrapper |
| Gatekeeper/GitHub | `rac gate --sarif` | Shared native setup, then thin SARIF/exit-code wrapper |
| Registrar/GitHub | `rac validate --sarif` | Shared native setup, then thin SARIF/exit-code wrapper |
| Herald/GitHub | `rac decisions-for --json` | Shared native setup, then thin PR-comment wrapper |
| Recordkeeper | Placeholder | Not shipped until its own contract and acceptance evidence land |

One setup implementation must resolve a pinned RAC release, select the platform
archive, verify its checksum, cache safely, and place `rac` on `PATH`. No Action
may install the retired PyPI engine or independently implement policy.

The user-facing bootstrap is:

```bash
rac ci init github
```

It previews or writes a deterministic workflow with pinned `rac-ci` and
`rac-version` references, refuses to overwrite by default, and requires no
network merely to render the template. Historical in-core `action.yml`,
`validate-action/`, and `pr-gate-action/` paths remain available only through
frozen compatibility tags or explicit migration documentation; they are not a
second actively maintained Action suite.

### Transition Milestones

| Milestone | State |
| --- | --- |
| R0 | ADR-118 accepted; this inventory and repository roadmap land |
| R1 | Independent contract ledger covers every live Python/Rust parity basket |
| R2 | Ingest package and thin Python SDK are published; Explorer is removed |
| R3 | Rust/conformance/dogfood gates are authoritative; Python oracle advisory |
| R4 | Native archives, `rac`, `rac-full`, container, and `rac-ci` native setup ship |
| R5 / Release N | Rust authoritative/default; Python engine and API deprecated |
| R6 / Release N+1 | Python engine, fallback, in-core API, and Python core packaging removed |

## Constraints

- Rust output, ordering, errors, and mutation behavior remain governed by
  language-neutral contracts; performance does not authorize behavior drift.
- `rac` alone must remain sufficient for an existing Markdown corpus.
- Python in `packages/rac-ingest/` cannot import, bind, or recreate engine logic.
- Connector SDKs and network behavior remain outside the offline engine.
- Generated ingest output is untrusted until human review and native validation.
- Homebrew Python formulae use isolated, pinned environments and never modify
  system Python at install or first run.
- No destructive corpus write, workflow overwrite, or inferred relationship is
  introduced by migration convenience commands.
- Supported platform gaps block fallback removal or are documented through a new
  decision; they never silently reactivate Python authority.

## Rationale

The design separates *runtime authority* from *optional tooling language*.
Python is not inherently the maintenance problem; maintaining a second engine
is. Keeping a narrow converter package preserves the mature MarkItDown ecosystem
without putting Python on the query, validation, CI, or serving path.

The installation topology likewise separates implementation from experience.
Independent formulae keep dependencies testable and upgradeable, while
`rac-full` gives users one command. Remote CI remains a repository concern but
is made discoverable from the installed product rather than represented by a
meaningless local formula.

## Alternatives

- Keep both engines: rejected by ADR-118 because contract evidence can replace
  permanent pairwise maintenance.
- Put ingest in `rac-connectors`: rejected because it produces draft artifacts
  rather than consuming stable exports, and it tracks the core artifact contract.
- Create another repository for ingest: rejected until independent ownership or
  cadence justifies the operational cost.
- Install every component from `rac`: rejected because a native-only user should
  not inherit Python and provider SDKs.
- Add a `rac-ci` formula: rejected because the current product is remotely
  consumed Actions, not a local executable.

## Accessibility

This change adds no graphical interface. CLI help, errors, dry-run previews, and
generated workflow messages must remain understandable without color, preserve
machine-readable alternatives, and write diagnostics to the documented stream.
Removing Explorer must not be presented as replacing an accessible terminal
surface with an inaccessible web-only requirement.

## Style Guidance

Use one product vocabulary across channels: `rac` is the native runtime,
`rac-full` is the complete local toolchain, `rac-ingest` creates reviewable
drafts, `rac-connect` integrates external systems, and `rac-ci` supplies remote
automation. Avoid describing optional packages as additional engines.

## Open Questions

- Which Linux and Windows targets are release-blocking for fallback removal?
- Which connector providers are sufficiently shipped and dependency-compatible
  to enter the first `rac-connectors` Homebrew formula?
- Do historical in-core Action paths receive redirect documentation only, or a
  final compatibility tag with a deprecation notice?
- Does `rac ingest` remain as a permanent executable shim after one migration
  release, or is `rac-ingest` the sole long-term command?
