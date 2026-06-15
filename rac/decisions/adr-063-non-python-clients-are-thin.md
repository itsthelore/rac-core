---
schema_version: 1
id: RAC-KV6ADYFGC3H4
type: decision
tags: [sdk, typescript, architecture, clients]
---
# ADR-063: Non-Python Clients Are Thin Clients Over the Contract

## Context

RAC's analysis engine — Markdown parse, deterministic classification, and
structural validation — lives in Python under `rac.core` (~2,100 LOC, spec- and
regex-driven, depending only on `markdown-it-py` and `pyyaml`). Its outputs are
stable, language-neutral contracts: the `rac … --json` payloads (additive,
`schema_version`-gated, ADR-007), the `rac export` corpus payload the `lore-web`
viewer already consumes from TypeScript, exit codes, and the MCP tool surface.

RAC's product promise is determinism: a corpus classifies and validates the same
way every time, so an agent (or a human) can trust "the team already decided X."
That promise rests on there being **one** engine. The `lore-web` viewer
demonstrates the pattern in practice — it is a thin TypeScript client over the
exported JSON and reimplements none of the engine.

A TypeScript SDK (to power a VS Code / Cursor extension) raises the question
directly: should non-Python clients consume RAC's contracts, or reimplement its
engine natively in each language? A native port would unlock zero-install,
in-browser, instant-feedback experiences, but it creates a second source of truth
for classification and validation that must be kept in lockstep — exactly the
drift the determinism promise cannot afford.

## Decision

RAC clients in languages other than Python are **thin clients over RAC's stable
contracts** — the `--json` outputs, the `export` payload, exit codes, and MCP.
They do not reimplement parse, classification, or validation. There is one
deterministic engine (Python), and every other surface defers to it.

Concretely, a thin client shells out to the installed `rac` binary (or speaks to
its MCP server), deserializes the stable JSON into typed results, and surfaces
them — the same way the Ruff, ESLint, and Pylint editor extensions wrap their
underlying tool rather than re-implement it. The TypeScript SDK and the VS Code /
Cursor extension built on it follow this rule.

A **native reimplementation** of the engine in another language is an explicit
exception, not the default. It is undertaken only when a concrete need (zero
Python install, browser execution, in-editor latency) outweighs the cost, and
only under two guards: the artifact specs (`ARTIFACT_SPECS`) are first extracted
to a shared, language-neutral data file both engines read, and a cross-language
**conformance fixture suite** proves output parity. No native port is undertaken
now.

## Consequences

Non-Python clients are cheap, fast to build, and **cannot drift** — they run the
same engine by construction, so a rule added in Python is immediately reflected
everywhere. The contract surface (`--json`, `export`, exit codes, MCP) becomes
the thing that must stay stable (already required by ADR-007), and a client's job
shrinks to typed deserialization plus presentation.

Trade-offs accepted: a thin client requires the `rac` binary to be present
(install or bundle), cannot run where there is no subprocess (web VS Code,
edge/browser), and pays a small per-call subprocess cost — mitigated by
debouncing and validating the edited file rather than the whole corpus. These are
the same trade-offs the established editor-tool extensions accept. The richer
zero-install / in-browser experience stays available later through the guarded
native-port exception, without blocking the thin client now.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

- **Native engine port per language (now).** Best end-state experience
  (instant, zero-install, browser-capable). Rejected for now: a second engine is
  a second source of truth for classification/validation, the precise drift the
  determinism promise forbids; only justified behind shared specs and a
  conformance suite when a concrete need demands it.
- **Hybrid: native-light parse/classify, delegate validation to `rac`.**
  Rejected: a partial reimplementation has the worst of both — a real drift
  surface (parse/classify still forks) plus a Python dependency for validation —
  and the most moving parts.
- **No non-Python clients; expose only the CLI and MCP.** Rejected: a typed TS
  SDK is what makes an editor extension ergonomic; the CLI/MCP are surfaces a
  client wraps, not a substitute for one.

## Related Decisions

- adr-002
- adr-007
- adr-008
- adr-015
- adr-062

## Related Roadmaps

- typescript-sdk-vscode
