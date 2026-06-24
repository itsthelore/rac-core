---
schema_version: 1
id: RAC-KVW05R49X701
type: decision
tags: [product, open-core, commercial, agents, verification, boundary]
---
# ADR-083: Autonomous QA Agents Extend Lore as Out-of-Core Consumers; the Commercial Surface Is Verification Governance, Not Test Runtime

## Context

An autonomous QA direction is under consideration: an agent given real developer
tools (a browser, a terminal) that develops against a product, converts the
working session into durable end-to-end tests committed to the repository, runs
them across targets (dev, production) and operating systems, and emits replayable
video/trace artifacts — so a reviewer can verify an agent's work purely by
looking at the test and its output. The open question is *where* this lives
relative to Lore, and what — if anything — is the commercial surface "beyond the
open-source core model."

Several recorded decisions fence the answer and must not be contradicted:

- **ADR-012 (Open Core)** keeps the CLI, schemas, validation, formats, import /
  export, inspection, and machine-readable outputs open, and locates commercial
  value in *repository-scale intelligence and organisational capabilities* —
  hosted repositories, multi-repo aggregation, governance and audit, enterprise
  reporting, AI context services. Its litmus test for the core: "does this improve
  the creation, understanding, or governance of product knowledge?"
- **ADR-081 (Competitive Positioning)** states Lore deliberately *does not compete
  on agent runtime and code generation*. A browser/terminal-driving test runtime
  is squarely agent runtime.
- **ADR-017 (Knowledge, Not Work)** and **ADR-024 (Not a Content Store)** keep
  execution, scheduling, and content (videos, traces, test output) out of the
  engine. **ADR-002 / ADR-035** keep the core AI-optional and offline, with no
  mandatory RAC-operated inference or cloud.
- **ADR-069 (Wayfinder)** is the precedent for an adjacent runtime concern: it
  became a *separate, independent product* consuming nothing of RAC at runtime,
  rather than a feature of the engine. **ADR-068** sets the naming principle —
  `lore-*` for an installable product, `rac-*` for the engine — and **ADR-063 /
  ADR-067** fix how external surfaces consume RAC: as thin clients over the
  published contract and the `lore` MCP read tools, with RAC supplying context and
  enforcing structurally after the fact, never executing the work.

Without a recorded boundary, the QA direction risks pulling a runtime, inference,
and a content store into the engine — eroding the clearest claims the product
makes — or, conversely, being dismissed as out of scope when in fact a genuine,
in-domain open-core capability and a genuine commercial surface both exist.

## Decision

Split the autonomous-QA direction along the open-core line and the
knowledge-versus-work line, in three parts:

1. **The verification *evidence and coverage* capability stays in the open-source
   core.** A capability (a requirement, ADR-020) may declare a human-declared
   verifying-evidence reference (an asset reference, ADR-019) to external test or
   trace evidence, and `rac coverage` reports — deterministically, offline, and
   advisorily — which live capabilities lack it. This is recorded in
   `rac-capability-verification-evidence` and sequenced in
   `capability-verification-coverage`. It passes ADR-012's litmus (it improves the
   understanding and governance of product knowledge), adds no execution or
   inference, and keeps every link human-declared (ADR-074, ADR-065, ADR-082).

2. **The QA *runtime* does not enter `rac-core`, and Lore-the-product does not
   become it.** Driving a browser and a terminal, running tests across targets and
   operating systems, capturing video/trace artifacts, and converting a working
   session into a durable test are *work*, *content*, and *agent runtime* — out of
   bounds by ADR-017, ADR-024, ADR-002/035, and ADR-081. This capability lives as
   a **separate consuming product**, the Wayfinder precedent (ADR-069): it consumes
   `rac export` and the `lore` MCP read tools (ADR-063, ADR-067) to learn which
   capabilities to verify, and proposes verifying-evidence references back into the
   corpus through normal human PR review (ADR-065) — it never writes the corpus
   directly. If it is an installed product it takes a `lore-*` name (ADR-068).

3. **The commercial surface is verification *governance*, not test execution.**
   Per ADR-012, the paid layer is repository-scale and organisational, additive
   over the open core, and never gates the free path (ADR-035): hosted multi-repo
   aggregation of capability → evidence coverage; audit and enterprise reporting on
   which capabilities are verified, across which environments, over time; and the
   hosted runner/VM fabric plus the faithful session-to-test conversion and
   flake-elimination service that make an emitted test *trustworthy*. The product
   sells trust in the artifact and org-scale coverage of intent — not the local act
   of running a test, which stays consumable for free over the open contract.

The boundary, stated once: **RAC records and reports verification; a separate
product produces and runs the evidence; the commercial layer aggregates and
governs it at organisational scale.** Local, single-repo verification coverage is
free forever (ADR-012).

## Consequences

### Positive

- Lore's clearest claims hold: the engine stays deterministic, offline,
  knowledge-only, and AI-optional, and the product does not drift into the agent
  runtime ADR-081 says it does not compete on.
- A genuine open-core capability (evidence + coverage) and a genuine commercial
  surface (governance + hosted verification fabric) are both recorded, so the QA
  direction is neither smuggled into the engine nor lost as "out of scope."
- The consuming-product split reuses a proven precedent (ADR-069) and the existing
  contract surfaces (ADR-063, ADR-067), so no new integration pattern is invented.

### Negative / trade-offs

- A further product to name, position, and (if pursued) build and operate, beyond
  RAC, Lore, and Wayfinder. Accepted: it is additive and optional, and the open
  core stands alone without it.
- The line between "trustworthy emitted test" (commercial) and "run a test
  locally" (free) must be held honestly so the open path is never quietly starved
  to push the paid one (ADR-012's "additive, never restrictive" rule).

### Risks

- Scope creep pulls runtime or inference into `rac-core` for convenience.
  Mitigation: the boundary is recorded here and in
  `rac-capability-verification-evidence` REQ-007.
- The commercial framing outruns the open core's value. Mitigation: the open
  capability (evidence + coverage) is independently useful and ships first
  (`capability-verification-coverage`); the commercial layer is explicitly
  downstream of it.

## Status

Proposed

## Category

Product

## Alternatives Considered

### Build the QA runtime into `rac-core`

Add browser/terminal drivers, a test runner, and artifact capture to the engine.
Rejected: it drags execution, content, and inference into a knowledge engine,
breaking ADR-017, ADR-024, and ADR-002/035, and contradicting ADR-081's stance
that Lore does not compete on agent runtime.

### Make Lore-the-product the autonomous QA tool

Position Lore itself as the agent that drives browsers and runs tests. Rejected:
same ADR-081 conflict; it re-aims the product away from the durable-decisions
whitespace ADR-081 says it owns, into a crowded agent-runtime lane.

### Keep verification entirely external; add nothing to the core

Let an external tool own the whole thing and leave RAC untouched. Rejected: the
*evidence-and-coverage* half is genuinely in-domain (it governs product
knowledge, ADR-012) and is the hook that makes the external product valuable —
omitting it forgoes a low-cost, deterministic win and the integration seam.

### A fully proprietary QA platform

Build the whole direction closed. Rejected by ADR-012: the artifact model and
local tooling stay open; commercial value is repository-scale and organisational,
layered additively over the open core, not a closed replacement for it.

## Related Decisions

- adr-012
- adr-081
- adr-069
- adr-068
- adr-067
- adr-063
- adr-035
- adr-017
- adr-024
- adr-002
- adr-019
- adr-074
- adr-065
- adr-082
- adr-020

## Related Requirements

- rac-capability-verification-evidence

## Related Designs

- capability-verification-evidence

## Related Roadmaps

- capability-verification-coverage

## Review Date

Revisit when a verification consuming-product is first actively built (triggering
the `lore-*` naming and contract-consumer decisions of ADR-068 / ADR-063), or when
a commercial verification-governance offering is first actively considered (the
ADR-012 review trigger).
