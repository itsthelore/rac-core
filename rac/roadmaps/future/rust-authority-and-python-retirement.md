---
schema_version: 1
id: RAC-KXWW4NGN7JYA
type: roadmap
tags: [rust, engine, migration, distribution, ci]
---
# Rust Authority and Python Engine Retirement

## Status

Planned

ADR-118 replaces the permanent two-engine end state with a bounded migration to
one Rust engine. This roadmap owns the authority, surface, distribution, and
deletion lane. Performance work can proceed in parallel and does not keep the
Python engine alive once the correctness and delivery gates below are met.

## Outcomes

- Rust is RAC's sole behavioral authority and implementation.
- An existing corpus runs through `rac` and `rac-mcp` with no Python runtime.
- `rac-ingest` preserves initial document/vault conversion as a separately
  installable Python package under `packages/rac-ingest/`, not a second engine.
- Python developers use the thin `rac-sdk/py` client over native JSON contracts.
- Explorer and the fallback dispatcher are removed.
- `brew install itsthelore/tap/rac-full` installs the complete supported local
  toolchain, while the lean `rac` formula remains Python-free.
- Every shipped `rac-ci` Action installs and invokes a verified native release,
  and `rac ci init github` makes that remote capability discoverable.

## Initiatives

### R0 — Authority and inventory

Land ADR-118 and `rust-authority-cutover-surface-inventory`. Freeze the removal
milestones and supersede the prior permanent-hybrid roadmap.

### R1 — Independent contract evidence

Move canonical specs/assets out of `src/rac`, pin `rac-spec`, map every old
parity basket to language-neutral fixtures or an explicit non-contract, preserve
the final Python environment/tag, and make Rust certifiable without installing
the Python engine.

### R2 — Resolve Python-only surfaces

Extract `packages/rac-ingest/` with byte-identical golden fixtures, publish the
thin Python SDK member in `rac-sdk`, adopt retained native retrieval contracts,
and remove Explorer without replacement. Core keeps at most a process-forwarding
`rac ingest` shim.

### R3 — Rust-authoritative CI

Promote workspace fmt/clippy/test, pinned-spec conformance, mutation, dogfood,
and supported-platform checks to required. Demote the frozen Python oracle to a
scheduled compatibility witness.

### R4 — Native distribution, Homebrew, and `rac-ci`

Ship versioned native archives and container images, publish `rac`,
`rac-ingest`, `rac-connectors`, and `rac-full` formulae, migrate all shipped
`rac-ci` wrappers to one checksum-verifying native setup implementation, and
ship `rac ci init github`.

### R5 — Deprecation release

Release N (`v0.23.0` target) makes Rust authoritative/default and warns only on
the Python engine, fallback selector, and in-process Python SDK entry points.
Publish migration guidance to `rac-ingest`, `rac-sdk/py`, native channels, and
`rac-ci`.

### R6 — Engine deletion

Release N+1 (`v0.24.0` target) removes `src/rac` engine behavior, Python parity
tests, dispatcher/fallback, engine extras, Python core packaging, and obsolete
CI. Preserve neutral assets, ingest package, SDK compatibility map, final oracle
tag, and historical evidence. A delay beyond 2026-09-17 requires a new decision.

## Success Measures

- No supported core command, MCP transport, container, release archive, or
  `rac-ci` Action imports or installs the Python engine.
- Rust passes language-neutral CLI/MCP/output/mutation conformance from a clean
  checkout with no Python RAC package.
- `brew install .../rac` works with Python absent.
- `brew install .../rac-full` exposes `rac`, `rac-mcp`, `rac-ingest`, and
  `rac-connect` in one transaction.
- `rac ci init github` generates a pinned workflow that passes an end-to-end
  fixture repository run without overwriting an existing file.
- Ingest golden fixtures remain deterministic and their reviewed outputs pass
  released native `rac validate`.
- The Python SDK integration suite passes against every supported native release
  platform and contains no engine implementation.
- The Python engine, `RAC_ENGINE=python`, Explorer, and automatic fallback are
  absent by Release N+1.

## Assumptions

- Current parity and fuzz evidence is sufficient to start authority transfer;
  R1 audits coverage rather than restarting the port.
- Native archives can cover the supported user matrix before fallback removal.
- MarkItDown remains appropriate for born-digital document conversion and does
  not need to enter the engine.
- `rac-connectors` can publish a tested Homebrew environment for the subset of
  providers declared shipped at the time.
- The existing `rac-ci` wrappers remain thin enough to share one native setup
  implementation without moving policy into the Actions.

## Risks

- A parity basket may still encode undocumented behavior. Mitigation: R1's
  coverage ledger blocks deletion until every basket has an independent owner.
- Native platform coverage may lag the retirement date. Mitigation: publish the
  matrix early and require a new decision for any schedule exception.
- Co-located Python ingest may be mistaken for a retained engine. Mitigation:
  separate package tree, path-filtered CI, executable boundary, and no imports
  from engine modules.
- `rac-full` may accumulate incompatible or very large provider dependencies.
  Mitigation: include shipped providers only and keep independently testable
  component formulae.
- Historical in-core and current `rac-ci` Action paths may create two active
  suites. Mitigation: freeze old tags and document one supported current path.
- Removing Explorer may surprise existing users. Mitigation: one bounded
  deprecation message and explicit release notes; no replacement promise.

## Related Decisions

- adr-118
- adr-063
- adr-072
- adr-079
- adr-092
- adr-111
- adr-115
- adr-116

## Related Designs

- rust-authority-cutover-surface-inventory

## Related Roadmaps

- native-engine-cutover

## Migration Relationship

The migration replaces the end state described by `native-engine-cutover`.
That roadmap remains resolvable as the historical covered-surface plan; ADR-118
is the normative authority for the new end state.
