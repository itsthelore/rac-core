# lore-verify — agent session context

This file is the router for agent sessions working in the `verify/` subproject
(`lore-verify`). It is **separate from the rac-core `CLAUDE.md`**: when you are
working under `verify/`, this product's rules apply, not the engine's. Canonical
guidance lives in `verify/rac/prompts/`, where the LV corpus gates validate it. Do
not add rules here — add them to the prompt artifacts and they load through the
imports below.

`lore-verify` is a **contract consumer of Lore, not an extension of the engine**
(LV-ADR-001). The one-line boundary: **Lore records and reports verification;
`lore-verify` produces and runs the evidence.**

## Loaded every session

@rac/prompts/lv-agent-session-start.md
@rac/prompts/lv-agent-commit-guidelines.md

## Working corpus

This subproject has its **own** RAC corpus under `verify/rac/` with repository key
`LV`. Validate it independently:

- `rac validate verify/rac/`
- `rac relationships verify/rac/ --validate`

Do **not** validate it against, or merge it into, the rac-core `rac/` corpus — they
are separate corpora with separate lifecycles (LV-ADR-004).

## The boundary (do not cross)

- **Consume the published RAC contract only** — `rac export --graph` (the
  `asset_edges` worklist, RAC ADR-084); the `lore` MCP read tools for
  artifact-level reads. Never import `rac` internals or read the host `.rac/`
  namespace (RAC ADR-063, LV-ADR-001).
- **Write back only by proposing** a human-reviewed `## Verified By` PR that passes
  the corpus gates (RAC ADR-065, design `verified-by-write-back`).
- **Security binds every runtime change** to LV-ADR-003: untrusted target,
  fail-closed sandbox, redact secrets/PII before persisting, fail-closed
  production safety.

## Settled decisions (lore-verify)

Do not re-open or contradict these; read the artifact before proposing a change
that touches one.

- **LV-ADR-001** — lore-verify Identity and Boundary
- **LV-ADR-002** — The Test Runner Is a Pluggable Interface
- **LV-ADR-003** — Runtime Threat Model and Agent-Execution Trust Boundary
- **LV-ADR-004** — CI Topology for the verify/ Subproject Inside rac-core

## Governing rac-core decisions (consumed, not owned)

These rac-core decisions govern the seam from the Lore side; cite them, do not edit
them from here:

- **RAC ADR-083** — Autonomous QA Agents Extend Lore as Out-of-Core Consumers
- **RAC ADR-084** — Asset-Reference Edges Are a Separate `asset_edges` List
- **RAC ADR-063** — Non-Python Clients Are Thin Clients Over the Contract
- **RAC ADR-065** — Artifact Content Is Untrusted; the Trust Boundary Is Human PR Review
- **RAC ADR-071** — Apache-2.0 relicense and DCO (sign-off required)
- **RAC ADR-064** — Multi-Repo Extraction Strategy (the verify/ → lore-verify cutover)
