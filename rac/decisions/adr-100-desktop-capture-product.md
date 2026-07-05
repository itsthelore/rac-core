---
schema_version: 1
id: RAC-KWRSFV26HZVK
type: decision
---
# ADR-100: Start the Desktop Capture Product — Cross-Platform Tauri Overlay

## Status

Accepted

## Category

Product

## Context

Capture-at-the-moment is the corpus's recorded absent capability
(`growth-essay-mapping`, Row 6), and the capture architecture is already
settled: under the two-gate write model (ADR-077) an author answers an
interview and confirms fidelity — validation runs mechanically inside the
loop and ratification is an independent pull-request merge — so authoring
never requires writing Markdown or iterating against a validator. What
remained undecided was the host surface that reaches the intended audience:
non-technical knowledge owners, people who will not author through MCP
servers, coding-agent harnesses, or agents in Slack.

The `lore-overlay` roadmap records a desktop overlay as future intent,
explicitly gated on "the decision to start a desktop product", and a staging
spike (rac-core PR #202) validated the two-gate capture core behind trait
seams. The spike also exposed the real adoption barrier for this audience:
not the capture UX but the setup — a bring-your-own model gateway and a
GitHub App are not things a non-technical author will configure.

## Decision

Start the desktop capture product. Specifically:

- **The gate is ratified.** The desktop host is a committed product
  direction, not exploratory intent. Scheduling remains with its roadmap and
  execution epic; it must not displace already-scheduled engine work.
- **Tauri v2, cross-platform from the outset.** The product targets
  availability across setups, not macOS-first-then-Windows: macOS and
  Windows are both first-class targets of the initial release cycle. Linux
  stays deferred (portal/compositor unevenness, per the roadmap's
  non-goals).
- **Admin-provisioned deployment.** An administrator configures the model
  gateway, the GitHub App identity, and the target repository once
  (composing with the ADR-088 profile-scaffold pattern); the author-facing
  surface is only hotkey → interview → "is this what you decided?".
- **Own repository, engine untouched.** A separate product repository
  slugged `rac-overlay` per ADR-092's `rac-*` naming, with the Lore brand
  carried at the organisation/marketplace level; the product name
  ("overlay") remains a working title. The app is a thin client over the
  `rac` contract (ADR-063); no AI enters the engine (ADR-002).
- **The two-gate model is non-negotiable.** The app's GitHub identity
  proposes draft pull requests only and can never approve or merge
  (ADR-065, ADR-077).

## Consequences

- Lore gains a capture surface for the audience the skill and MCP hosts
  cannot reach, and a second installable host that proves the
  skill-is-brain / host-is-interface model. Whether it works is measurable:
  the artifact-completeness benchmark's residual gives a before/after
  signal for corpus completeness.
- Cross-platform from day one costs more than the previously drafted
  macOS-first path: two signing pipelines (Developer ID notarization and
  Authenticode/SmartScreen reputation) and two OS integration surfaces
  before the first release, in exchange for not excluding Windows-based
  authors at launch.
- Admin-provisioning documentation becomes part of the product's
  deliverable, not an afterthought — the product's reach depends on a
  technical administrator's one-time setup being genuinely one-time.
- A desktop product carries an ongoing support surface (updates, signing
  renewals, OS changes) that a repo-resident skill does not.

## Alternatives Considered

- **macOS-first, Windows fast-follow** (the roadmap's prior sequencing) —
  rejected: the product's aim is availability across setups; sequencing by
  operating system delays exactly the authors it targets.
- **Slack bot first** — reaches some non-technical users but not the stated
  audience: people not comfortable with agents in Slack, and organisations
  where such bots are restricted.
- **Skill/MCP surfaces only (no product)** — leaves the capture gap open
  for everyone who is not already in a coding-agent context.

## Related Decisions

- adr-002-ai-optional
- adr-063-non-python-clients-are-thin
- adr-065-artifact-content-untrusted
- adr-068-extension-sdk-and-brand-architecture
- adr-077-two-gate-capture-write-model
- adr-088-enterprise-profile-scaffold
- adr-092-repository-topology

## Related Roadmaps

- lore-overlay

## Related Designs

- lore-capture-overlay
- lore-capture-surfaces
