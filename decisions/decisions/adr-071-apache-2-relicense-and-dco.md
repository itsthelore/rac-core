---
schema_version: 1
id: RAC-KVCJFDSTMPH9
type: decision
---
# ADR-071: Apache 2.0 Relicensing and DCO Contribution Sign-Off

## Context

Every RAC artifact ships MIT today: the engine package
(`requirements-as-code`), the TypeScript SDK, and the editor extension all
declare MIT. The multi-repo extraction programme (ADR-064, ADR-068) is about
to create five sibling repositories under the `itsthelore`
organisation — `decisiongrounding`, `rac-sdk-ts`, `lore-vscode`,
`lore-gatekeeper`, `lore-watchkeeper` — alongside the renamed `rac-core`
engine. We want one deliberate licensing posture set across the whole org
*before* those repos start attracting outside contributors, while the
maintainer is still effectively the sole copyright holder and a relicense
costs no consent-gathering.

MIT has two gaps that matter at this stage:

- **No express patent grant.** MIT conveys no patent licence and no
  retaliation clause. Apache 2.0 grants contributors' patents to users and
  terminates the grant for anyone who brings a patent suit (§3) — the single
  most common reason organisations prefer Apache over MIT, and a protection
  for users and the project rather than a commercial lever.
- **Silence on trademarks.** As the `lore` / `rac` brand identity is built
  out (ADR-036, ADR-039, ADR-068), Apache 2.0's explicit trademark non-grant
  (§6) keeps the marks reserved; MIT says nothing.

Apache 2.0 is also the license enterprise legal policies most reliably
whitelist, which aids the broad adoption ADR-012 optimises for.

A licensing change must not be mistaken for a commercial moat. ADR-012
(Open Core) already locates commercial value in a *separate* repository-scale
or hosted layer, not in restricting the core. Apache 2.0 is permissive: it
grants hosting and commercial use to everyone, exactly like MIT. The moat in
ADR-012 is architectural, and this decision does not change it.

The genuine "if needed" lever is retaining the right to relicense later. A
permissive license plus external contributors and no contribution agreement
removes the ability to dual-license down the road, because the maintainer no
longer holds or controls all rights. That is a contribution-process question,
not a license-text question, so it is decided here alongside the relicense.

## Decision

Relicense the entire `itsthelore` org from MIT to the **Apache License 2.0**,
and adopt a **Developer Certificate of Origin (DCO)** sign-off on all
contributions. No CLA at this time.

- **Scope.** `rac-core` (engine, including the in-process MCP server and all
  shipped skills, templates, and hooks) and every extracted repo —
  `decisiongrounding`, `rac-sdk-ts`, `lore-vscode`, `lore-gatekeeper`,
  `lore-watchkeeper`.
- **Mechanics.** Each repo carries the Apache 2.0 `LICENSE` text plus a
  `NOTICE` file; SPDX identifier `Apache-2.0` in `pyproject.toml` and every
  `package.json`; README license badges updated. Per-file Apache header
  blocks are permitted but not required.
- **Contributions.** Require a DCO `Signed-off-by` line (`git commit -s`).
  A CLA is explicitly *not* adopted now.
- **Identity unchanged.** Distribution names stay frozen (ADR-036, ADR-039):
  PyPI `requirements-as-code`, CLI `rac`, server identity `lore`. This
  changes license terms, not identity.
- **Open-core posture unchanged.** This complements ADR-012; it does not
  alter which capabilities are open. Commercial value remains a separate
  repository-scale / hosted layer, never a restriction of the core.

## Consequences

### Positive

- Express patent grant and retaliation clause protect users and the project.
- Explicit trademark non-grant reserves the `lore` / `rac` marks as the brand
  is established.
- Enterprise-friendly: the license most corporate legal reviews pre-approve.
- One consistent posture across all six repos.
- Done while the maintainer is effectively sole copyright holder, so the
  permissive-to-permissive relicense needs no contributor consent thicket —
  cheapest it will ever be.
- DCO keeps contribution provenance clean at near-zero friction.

### Negative / trade-offs

- Apache 2.0 is more ceremony than MIT: `NOTICE` files and the header
  convention to maintain across repos.
- It creates no competitive moat — intentionally; that is ADR-012's job, not
  the license's.
- DCO without a CLA means no unilateral future relicense once external
  contributors land. Accepted: if true dual-licensing optionality is later
  required, a CLA is the follow-up lever, recorded as its own decision.

### Risks

- License/`NOTICE`/header drift across six repos. Mitigation: a fixed
  per-repo checklist applied in the same change as the metadata update.
- Package metadata mismatch (SPDX vs `LICENSE`). Mitigation: update SPDX in
  `pyproject.toml` / `package.json` in the same commit as the `LICENSE` swap.

## Status

Proposed

## Category

Process

## Alternatives Considered

### Stay on MIT

Simplest and already in place. Rejected: it forgoes the patent grant and the
trademark non-grant, and it misses the pre-contributor window in which a
relicense is essentially free.

### Source-available (BSL / SSPL) or copyleft (AGPL) for "commercial protection"

Would genuinely restrict third-party commercial/hosted reuse. Rejected: it
directly contradicts ADR-012's adoption thesis (the Git → GitHub,
Terraform → Terraform Cloud pattern), chilling ecosystem growth and standard
adoption. The intended moat is the separate hosted layer, not a restrictive
license on the core.

### Apache 2.0 with a CLA now

Maximises future optionality (the maintainer could dual-license later). Deferred:
a CLA adds contributor friction and asks for a copyright-assignment trust step
that is premature at this stage. DCO is chosen as the low-friction default; a
CLA is revisitable when a commercial offering is first actively considered —
the same trigger ADR-012 sets for its own review.

## Related Decisions

- adr-012
- adr-036
- adr-039
- adr-064
- adr-068

## Review Date

Revisit when a commercial or dual-license offering is first actively
considered (aligning with ADR-012's review trigger), or if a contribution
arrives whose provenance a DCO cannot adequately cover.
