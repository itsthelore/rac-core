---
schema_version: 1
id: RAC-KVZVXNCR0FQQ
type: decision
---
# ADR-085: Proofkeeper Drives an HTTP/API Modality as Verification Evidence

## Context

ADR-083 scopes Proofkeeper's autonomous agent to real developer tools — "a browser and a
terminal" — and fences the product to producing verification evidence, with a Non-Goal
against becoming a coding agent, a codegen tool, or a general-purpose runtime. ADR-084
records that the verification links Proofkeeper writes back are external-target
relationships (`verified_by`).

A competitive review of autonomous-QA agents (Factory DROID, QA Wolf, Playwright Test
Agents) found that **API/HTTP** is a third, first-class way these tools drive and verify a
product: Factory's QA agent "calls endpoints" (via `curl`), and service-backed capabilities
are often best verified by issuing a request and asserting the response rather than by
driving a UI. Proofkeeper can already do this indirectly — the terminal modality runs
`curl` — but an ergonomic, deterministic HTTP request/assert tool would let the agent verify
a capability that *is* an API contract directly.

The question this records: is a first-class HTTP modality within Proofkeeper's scope, given
ADR-083 names only "a browser and a terminal"? Because the named surface is explicit, adding
a third modality is a scope decision, not an implementation detail — it must be recorded
before the driver is built (the roadmap's discipline against silent scope drift).

## Decision

Proofkeeper MAY drive and assert over an **HTTP/API modality** as a first-class tool
surface, alongside the browser and the terminal. This ADR **amends ADR-083's tool surface**
to add HTTP as a third modality. It widens that surface deliberately — it does not claim the
modality was always implied. The extension is safe because it stays inside ADR-083's mandate:

- It produces **verification evidence and nothing else** (ADR-083's mandate): the agent
  issues an HTTP request and asserts on the response (status, body, headers); it does not
  generate or review product code.
- It drives the product through its **real external interfaces, as a user or client would** —
  the same test that admits the browser and the terminal. This is the load-bearing scope
  boundary: it excludes reaching past those interfaces (reading source, querying the database
  directly, or calling internal functions), and a future modality is in scope only if it
  meets this same test.
- It is the formalization of an ability the terminal modality already grants (`curl`), made
  deterministic and reviewable as a compiled test step. The dedicated tool is not merely
  ergonomic: it invites HTTP as a primary drive modality, which is the behavioral shift this
  amendment authorizes.
- The runtime stays in the sibling product. No model or inference enters the engine
  (ADR-002, ADR-035, ADR-069); the engine still only records the resulting `verified_by`
  links (ADR-084), and the trust boundary remains human pull-request review (ADR-065).

This is recorded as an **amendment**, not a reinterpretation. ADR-083 named its tool surface
explicitly and paired it with anti-scope-drift discipline, so honesty requires stating that
this ADR moves that fence — not that the fence was always elsewhere. What keeps the move
principled is that the boundary shifts from a literal two-tool list to the
external-interfaces / evidence-only test above, a test the HTTP modality plainly meets. The
Non-Goals of ADR-083 are unchanged and continue to bind: no code review, no codegen, no
general-purpose automation.

## Consequences

### Positive

- API-backed capabilities can be verified directly and deterministically, widening coverage
  without driving a UI as a proxy.
- The agent's three modalities (browser, terminal, HTTP) all reduce to recorded, compiled,
  fidelity-gated test steps — one consistent evidence model.
- The decision is recorded before implementation, preserving the anti-scope-drift discipline
  ADR-083 established.

### Negative

- A third modality to maintain in the sibling product's recorder, emitter, and tool surface.
- "What is in scope" now rests on the external-interfaces / evidence-only test rather than the
  literal two-tool phrasing, so future modalities must each be judged against that test.

### Risks

- A first-class HTTP tool could be stretched toward general API automation beyond
  verification. Mitigation: it is constrained to request-and-assert that yields a committed
  test, must act through the product's real external interfaces (not internal calls or direct
  data access), and ADR-083's Non-Goals continue to bind.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

### Keep HTTP to the terminal modality (`curl`) only

Verify APIs by running `curl` through the existing terminal tool and asserting on its
output.

#### Disadvantages

- Brittle and non-ergonomic: the agent must construct `curl` invocations and parse text
  output, and assertions on JSON bodies or status codes are awkward. A first-class tool is
  deterministic and reviewable. (Still available as a fallback; this ADR does not remove it.)

### Treat HTTP as out of scope, deferring to a future sibling

Leave API verification to some other product.

#### Disadvantages

- API verification is squarely "produce verification evidence", the exact mandate of
  Proofkeeper (ADR-083); carving it into a separate product would fragment the verification
  surface for no boundary benefit. Rejected.

### Add the modality silently, without a decision

Just build the HTTP tools because they seem in scope.

#### Disadvantages

- ADR-083 names the tool surface explicitly and warns against scope drift; extending it
  without a record is exactly what that discipline forbids. Rejected in favour of this ADR.

## Related Decisions

- adr-083
- adr-084
- adr-065
- adr-002
- adr-035
- adr-069

## Related Roadmaps

- proofkeeper-autonomous-verification
