---
schema_version: 1
id: RAC-KW47GDXPQSQ2
type: decision
---
# ADR-085: Enterprise Adoption Is Configuration and Distribution, Not a Mode

## Status

Proposed

## Category

Architecture

## Context

Enterprise interest pushes for an "enterprise mode" that reconfigures Lore for a
multi-repo, federated, Atlassian-and-pipeline world — a posture distinct from the
standards the project has imposed: a single canonical corpus (ADR-018, ADR-080),
not a content store (ADR-024), local-per-developer with no hosted service,
content-free telemetry (ADR-040, ADR-041), and a one-artifact onboarding scaffold
(ADR-044).

A semantic mode is the expensive answer. It forks the product: a permanently
doubled test matrix, a "does this still hold under enterprise mode?" tax on every
future decision, and two trust stories for one tool. The recorded invariants are
not obstacles to enterprise adoption; they are the product an enterprise is
buying. The question is the shape of "enterprise" that delivers the asks without
forking the engine.

## Decision

Enterprise adoption is delivered as **configuration plus distribution, never a
semantic operating mode**.

- A named profile (`rac init --profile enterprise`, ADR-088) is pure sugar over
  knobs that already exist — enforcement policy (ADR-049), validation severity
  overrides (ADR-053), `.mcp.json`, the telemetry kill-state (ADR-086). It adds
  no code path a solo developer cannot also reach.
- Network, SDK, and write-back capabilities live in satellites that consume only
  published contracts (ADR-064, ADR-073, ADR-090), never engine internals.
- Each genuinely-new capability is decided by its own ADR, for **everyone**,
  never gated behind an "enterprise" label.

This yields a reusable rule for classifying any future "should this be a mode?"
question:

- **Invariant test** — changes a recorded invariant (ADR-024, ADR-018/080,
  ADR-002, ADR-040/041, ADR-065/077)? Its own ADR, decided for everyone, never
  gated.
- **Preset test** — only sets values for knobs that already exist and are
  committed and versioned? A profile (config-only, no runtime branch).
- **Network test** — makes a network, SDK, or third-party call? A satellite; the
  engine never gains a second network import outside the fenced `mcp/ping.py`.
- **Content test** — records artifact content (queries, returned IDs, paths)? A
  separate, local-only, opt-in, default-off artifact under its own ADR
  (ADR-084).
- **Write-back test** — any write into a document platform is propose-only via
  human pull-request review (ADR-077), satellite-resident, or it is not built.
- **Cultural backstop** — does the bundle add any code path the solo developer
  cannot also reach? If yes, it is a mode; refuse. A profile must emit exactly
  the files a careful admin would hand-write.

Bright lines that no flag may ever cross: the content-store rule (ADR-024); the
single canonical root and git-main-as-truth (ADR-018, ADR-080); deterministic,
offline, Git-native resolution — external state never enters `rac validate`
(ADR-002, ADR-016, ADR-055); content-free telemetry and the single fenced ping
(ADR-040, ADR-041); the human-PR-review trust boundary (ADR-065, ADR-077); the
one-artifact scaffold bound (ADR-044); and the standing red lines (no SSO on a
shared MCP, no RBAC on MCP tools, no web editing UI, no hosted multi-tenant
service).

## Consequences

### Positive

- One product, one trust story: the OSS solo developer and the regulated
  enterprise run the same engine, configured differently.
- A durable decision rule governs the whole enterprise programme (ADR-084,
  ADR-086 through ADR-091) and future asks, so each is scoped consistently.
- Zero behavioural fork means no doubled test matrix and no per-ADR "enterprise
  mode" tax.

### Negative

- "Just turn on these flags" demands discipline: a named profile (ADR-088) and
  good docs do the work a mode would otherwise centralise.
- Carry shifts to satellites and to export-contract conformance (ADR-073), which
  must be invested in rather than assumed free.

### Risks

- A profile slips into a mode by accumulating behaviour. Mitigation: the cultural
  backstop above is the test — a profile may add no code path the solo developer
  cannot reach.
- A capability is gated behind "enterprise" for commercial reasons. Mitigation:
  the invariant test routes any rules-change to its own ADR for everyone.

## Alternatives Considered

### A real semantic enterprise mode

A distinct operating mode that changes invariants (repo structure, content-store
rules, trust model).

#### Disadvantages

- Forks the product: doubled test matrix, a per-ADR tax, and two trust stories.
  Rejected unanimously by the design council.

### Additive flags only, no named profile

Ship every capability as an independent flag and rely on documentation.

#### Disadvantages

- At scale, a doc you must apply has materially worse adherence than a command
  you run, and an auditor wants one committed artifact, not nine toggles per
  machine. The profile (ADR-088) earns its place on adherence, not capability.

Configuration plus distribution, never a mode, is selected.

## Relationship to Other Decisions

- Governs the enterprise programme: ADR-084 (audit recorder), ADR-086 (air-gap
  and telemetry lock), ADR-087 (external-reference relationships), ADR-088
  (profile scaffold), ADR-089 (federation), ADR-090 (satellite topology),
  ADR-091 (observability boundary).
- ADR-024, ADR-018, ADR-080, ADR-002, ADR-040, ADR-041, ADR-065, ADR-077: the
  invariants the bright lines protect.
- ADR-036, ADR-039, ADR-068: the product and brand identity a single,
  unforked product preserves.

## Related Requirements

- rac-trust-transparency
