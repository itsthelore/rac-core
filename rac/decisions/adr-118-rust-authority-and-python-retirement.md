---
schema_version: 1
id: RAC-KXWVENM15TF1
type: decision
tags: [architecture, engine, rust, python, distribution, ci]
---
# ADR-118: Rust Is the RAC Engine Authority and the Python Engine Is Retired

## Context

ADR-116 sanctioned the Rust engine as a second implementation under a Python
arbiter. That was the right entry gate: the native engine first had to prove
byte-identical CLI and MCP behavior, shared-spec conformance, cache parity, and
mutation correctness before it could carry product authority. The evidence is
now sufficient, and the operational cost ADR-116 accepted has become the next
constraint: every retained behavior has to be implemented, reviewed, tested,
and released twice for no user benefit.

The remaining Python-only surfaces do not justify two engines:

- document and note-tool ingestion is preprocessing that produces reviewable
  Markdown drafts; it does not validate or serve RAC artifacts;
- Explorer is not required and will be removed rather than ported;
- the supported Python API can be a thin client over native `rac --json`, as
  ADR-063 already requires for other languages;
- Rust already implements the stdio and HTTP MCP transports and the six-tool
  server surface.

Repository and delivery topology also need one recorded answer. ADR-092 places
inbound ingest in `rac-connectors` and keeps the Python SDK inside `rac-core`.
That no longer fits the end state: ingest is tightly coupled to the draft and
artifact contracts but should remain separately installable, while a Python SDK
that reimplements no engine belongs with the other thin clients in `rac-sdk`.
Creating a new repository solely for ingest would increase the constellation's
maintenance burden without establishing an independently owned product.

Finally, installation must not expose the source-repository topology to users.
A lean native install and a single batteries-included Homebrew command are both
required, while `rac-ci` remains a remotely consumed GitHub Actions surface
rather than a local package.

## Decision

RAC adopts Rust as its sole engine authority and retires the Python engine on a
bounded schedule.

1. **One engine, one authority.** The Rust workspace is the only implementation
   of RAC parsing, classification, validation, policy, graph, retrieval, cache,
   CLI, MCP, and output behavior. No third engine is authorized.

2. **The contract outlives the oracle.** `rac-spec`, the shared artifact-spec
   registry, committed conformance vectors, golden output fixtures, mutation
   referees, and Rust regression tests define behavior. Python-vs-Rust parity is
   retained only long enough to prove that every old oracle basket has an
   independent owner. After that audit, Python comparison is scheduled evidence,
   not a merge-blocking authority.

3. **The Python engine freezes.** At the Rust-authority cutover, the Python
   implementation is tagged and frozen. It receives only critical security or
   transition correctness fixes. New product behavior lands in Rust with its
   contract fixtures; routine dual implementation stops immediately.

4. **Remaining Python surfaces are resolved explicitly.**

   - Explorer is removed without replacement.
   - `rac-ingest` is a separately installable Python distribution and executable
     sourced from `packages/rac-ingest/` in the `rac-core` repository. It owns
     MarkItDown-backed document conversion and deterministic Obsidian, Logseq,
     Notion, and Roam normalisation. Its output is an untrusted draft until human
     review and native validation. It cannot implement or import an engine.
   - A native `rac ingest` command may remain only as a discover-and-exec shim
     for `rac-ingest`; it cannot interpret conversion results or fall back to
     the retired Python engine.
   - The Python SDK moves to the `py/` member of `rac-sdk`. It shells out to the
     installed native binary, consumes stable JSON and exit-code contracts, and
     reimplements no engine behavior.
   - The hidden native `retrieve` implementation is adopted only through the
     contract-led surface process; it no longer waits for a permanent Python
     implementation once authority has changed.

5. **Ingest gets a package boundary, not a repository boundary.** Co-location
   keeps the converter fixtures beside the draft/artifact contracts they must
   track. `rac-ingest` keeps independent package metadata, dependencies, tests,
   versioning, and releases. A separate repository is reconsidered only if it
   develops independent ownership, cadence, or a substantial source ecosystem.

6. **Native CI becomes blocking.** Required checks build and test the Rust
   workspace, certify the pinned `rac-spec` revision, replay language-neutral
   conformance and mutation fixtures, dogfood the released command surfaces, and
   smoke-test supported artifacts. The live Python oracle becomes advisory and
   is then removed from normal CI.

7. **`rac-ci` installs native RAC.** Every shipped wrapper in
   `itsthelore/rac-ci` uses one shared setup implementation to download a pinned
   native release, verify its checksum, and place `rac` on `PATH`. Actions remain
   thin wrappers over public CLI contracts. CI onboarding is surfaced by
   `rac ci init github`, which writes a deterministic, non-overwriting workflow
   with pinned `rac-ci` and RAC versions.

8. **Homebrew has lean and complete installations.**

   - `brew install itsthelore/tap/rac` installs the native runtime and requires
     no Python.
   - `brew install itsthelore/tap/rac-full` installs the supported local
     toolchain by depending on `rac`, `rac-ingest`, and `rac-connectors`.
   - `rac-sdk` is a developer library and is not part of `rac-full`.
   - `rac-ci` is remotely consumed and is not represented by an empty Homebrew
     formula; `rac-full` points users to `rac ci init github` instead.

9. **The retirement window is finite.** The next normal minor release is the
   Rust-authoritative release: native behavior is default and the Python engine,
   fallback dispatcher, and in-process SDK are deprecated. The following normal
   minor release removes them. The target is `v0.23.0` for authority and
   `v0.24.0` for removal; if release numbering changes before execution, the
   invariant is still N then N+1, with no indefinite fallback. A delay beyond
   2026-09-17 requires a new recorded decision naming the concrete blocker.

10. **Defects are adjudicated, not copied forever.** A documented Python defect
    may be fixed by updating the language-neutral contract and Rust tests. The
    final Python tag remains recoverable as historical evidence, not normative
    runtime code.

## Consequences

RAC has one implementation to evolve, one performance model, and one runtime
authority. Native installs, MCP servers, containers, and CI no longer require
Python. Users can still import existing material through MarkItDown and use a
typed Python client without keeping a second engine alive. `rac-full` hides the
optional-package topology behind one supported installation command.

The transition is intentionally more work than deleting `src/rac`: behavior
must first be captured in independent fixtures, shared assets must move out of
the Python package, native release channels must exist, `rac-ci` must stop
installing the PyPI engine, and SDK and ingest migration guidance must ship.

Co-locating `rac-ingest` means `rac-core` remains a mixed-language source
repository even though its core runtime is Rust-only. This is accepted because
the Python code has one narrow preprocessing concern and no parity relationship
with the engine. Path-filtered CI and separate packaging keep that boundary
visible.

Removing the fallback can strand unsupported platforms. The supported native
matrix and installation routes therefore become release gates, and unsupported
targets must be documented rather than silently routed to Python.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

### Keep the ADR-116 two-engine arrangement permanently

Rejected. It preserves the exact duplication this decision removes: two engine
implementations, an arbiter relationship, and merge-blocking pairwise tests after
independent contract evidence already exists.

### Bind Rust into the Python package with PyO3

Rejected. It keeps Python mandatory for the primary product, creates an FFI and
wheel matrix as new runtime surface, and does not help native CLI, MCP, Homebrew,
or container delivery.

### Rewrite MarkItDown and every note-tool converter in Rust

Rejected. Conversion is initial corpus preparation rather than engine work. A
rewrite adds parser and fidelity risk without improving the hot path or reducing
engine duplication.

### Move ingest into `rac-connectors`

Rejected for this phase, amending ADR-092's inbound-integration clause.
`rac-connectors` consumes stable RAC exports to publish or verify against
external systems; ingest begins with foreign material and creates reviewable
drafts whose contract changes with RAC artifacts. Co-location with the contract
is the tighter maintenance boundary.

### Create a dedicated `rac-ingest` repository

Rejected now. A separately installable package supplies dependency and release
isolation without adding repository administration and another required project
surface. The ADR-092 independent-ownership/cadence escape hatch remains.

### Put every optional component in the lean `rac` formula

Rejected. It would make Python and provider SDKs mandatory for users who already
have a Markdown corpus. `rac-full` supplies one-command convenience while
preserving a small native base.

## Supersedes

- ADR-116
- ADR-062

## Amends

- ADR-063: its thin-client rule remains; Rust replaces Python as the engine.
- ADR-072: MarkItDown remains; packaging moves from a core extra to `rac-ingest`.
- ADR-092: ingest stays in `rac-core` as a separate package, and Python joins
  the language members in `rac-sdk`.

## Related Decisions

- adr-002
- adr-007
- adr-010
- adr-027
- adr-063
- adr-072
- adr-073
- adr-075
- adr-079
- adr-092
- adr-095
- adr-098
- adr-111
- adr-115
- adr-116

## Related Designs

- rust-authority-cutover-surface-inventory

## Related Roadmaps

- rust-authority-and-python-retirement
- native-engine-cutover
- native-binary-channels
