---
schema_version: 1
id: LV-KVW5PZCJ67G0
type: design
---
# Verified-By Write-Back Mechanism

## Status

Proposed

Exploratory — the *how* for the one loop `lore-verify` exists to prove: turning a
passing, faithful test into a merged `## Verified By` reference on a Lore
capability, by **proposing** a PR a human ratifies (LV-ADR-001, RAC ADR-065). This
is half the contract seam (the read half is RAC ADR-084 / `rac export --graph`) and
the literal v0.1.0 success criterion.

## Context

After Run accepts a faithful test (`faithful-session-to-test`), `lore-verify` must
record that evidence against the capability it verifies. Per LV-ADR-001 and RAC
ADR-065 it does this **only by proposing** a pull request — it never writes a Lore
corpus directly. The mechanism was asserted as policy across five artifacts but
designed nowhere; an unspecified Markdown edit can silently break the host corpus's
`rac validate` / `rac relationships --validate` gates (editing an untrusted human
file, RAC ADR-065 in reverse — here *we* are the untrusted writer the human
reviews).

## User Need

- A **capability owner** wants a PR that adds a clear, correct `## Verified By`
  line pointing at the new test, that merges green through the corpus gates, and
  that they can review by reading the line and the test it points at.
- `lore-verify` needs a deterministic way to map a capability id (read off
  `rac export --graph`) to the file to edit, and to insert the reference without
  corrupting frontmatter or other sections.

## Design

### From worklist to target file

`lore-verify` reads unverified capabilities from `rac export --graph` — the
`nodes[]` give the canonical id, type, and path of each capability; the
`asset_edges` (RAC ADR-084) show which already carry evidence. A capability with no
`verified-by` asset edge is a worklist item. The node's `path` is the file to edit;
`lore-verify` does **not** guess paths from ids.

### The edit

For each verified capability, `lore-verify` adds a Markdown link line under a
`## Verified By` section in that artifact:

```markdown
## Verified By

- [checkout-flow e2e](../../tests/e2e/checkout.spec.ts)
```

- If the section exists, append the line; if not, create the section in the
  artifact's conventional position (after the body sections, beside the other
  `## Related *` sections — the exact placement fixed by the RAC-side design
  `capability-verification-evidence`, which owns the declaration site).
- The link **text** is the human-readable evidence label; the **target** is the
  test path (or CI/trace URL). When pointing at a specific case, it uses a stable
  `#<case-name>` anchor per the resolved RAC-side rule
  (`capability-verification-evidence`, *Target and anchor grammar*) — consumed
  here, not redefined.
- The edit **MUST NOT** touch the YAML frontmatter, the artifact id, or any other
  section. Only the `## Verified By` section is created or appended.

### Gate-clean by construction

The produced PR MUST round-trip clean through the host corpus gates: after the
edit, `rac validate <file>` and `rac relationships <corpus> --validate` MUST pass,
so the PR is mergeable green. `lore-verify` runs these locally before opening the
PR and refuses to open one that would red the gates — it never hands a human a
corpus-breaking PR. (Evidence references are advisory and never themselves a gate
failure per `rac-capability-verification-evidence` REQ-005; this requirement is
about not corrupting *other* validation.)

### Batching (v0.2.0)

A multi-capability Drive session (v0.2.0-breadth Initiative 4) groups all its
verified capabilities into **one** PR: one branch, one edit per affected artifact,
each adding its `## Verified By` line, with the attached redacted traces
(`evidence-redaction-and-secret-hygiene`) as the review surface.

### Mechanics

The PR is opened against the consuming repo via its host's API (e.g. a GitHub
branch + PR, or a fork-and-PR where `lore-verify` lacks push). The exact host
integration is an implementation detail; the invariants above (propose-only,
section-scoped edit, gate-clean, redacted evidence attached) are the contract.

## Constraints

- **Propose-only** (LV-ADR-001, RAC ADR-065): never a direct corpus write; a human
  reviews and merges.
- **Section-scoped, non-corrupting edit**: only `## Verified By` is created/
  appended; frontmatter and other sections are untouched.
- **Gate-clean**: the PR passes `rac validate` / `rac relationships --validate`
  before it is opened; `lore-verify` refuses to open a corpus-breaking PR.
- **Id→path via the export**, never guessed (RAC ADR-084 `nodes[].path`).
- **Redacted evidence only** is attached (`evidence-redaction-and-secret-hygiene`).
- **Anchor grammar is consumed, not defined** here (owned by the RAC-side design).

## Rationale

Mapping id→path off the export (rather than parsing the corpus ourselves) keeps
`lore-verify` a thin contract consumer (RAC ADR-063) and avoids re-implementing
resolution. Running the gates before opening the PR makes "mergeable green" a
property of the tool, not a hope, and keeps the human review about *the evidence's
validity* rather than *fixing our Markdown*. Scoping the edit to one section is what
lets an automated writer touch a human-owned file safely.

## Alternatives

- **Write the reference directly into the corpus (no PR).** Rejected by LV-ADR-001
  / RAC ADR-065: an unreviewed write is not a ratified edge.
- **Guess the file path from the capability id / slug.** Rejected: brittle; the
  export already carries the authoritative `path`.
- **Open the PR without running the gates first.** Rejected: hands the human a
  possibly-corpus-breaking PR and pushes our hygiene burden onto review.
- **Edit the whole artifact / reformat on write.** Rejected: maximises the chance
  of corrupting a human-owned file; the edit is strictly additive and
  section-scoped.

## Open Questions

- Host-integration specifics (push vs fork-and-PR; how `lore-verify` authenticates
  to the consuming repo) — an implementation detail to settle at build time.
- Whether a re-verification (the test changed) updates the existing line or adds a
  new one, and how superseded evidence is retired.

## Related Decisions

- lv-adr-001-product-identity

## Related Requirements

- faithful-session-to-test
- evidence-redaction-and-secret-hygiene
