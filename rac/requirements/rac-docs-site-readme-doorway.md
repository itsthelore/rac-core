---
schema_version: 1
id: RAC-KTYXDSA1HT7T
type: requirement
---
# REQ-Docs-Site-README-Doorway

## Status

Proposed

## Problem

The README currently carries both the doorway (what Lore is, install, who
it's for) and the depth (comparison tables, trust argument, long
walkthrough) because it has been the only public surface. Once the landing
page exists, that depth lives in two places and the copies will drift.
ADR-022 defines the README as a doorway readable in about a minute;
ADR-042 adds the hosting model and drift policy. This artifact governs the
README's reduced shape and makes the drift policy enforceable.

## Requirements

- [REQ-001] The README MUST retain the ADR-022 doorway contents and nothing more: the H1 and `mcp-name` comment; the hero `<picture>` element; the four badges; the tagline blockquote; a condensed product summary including the Lore-product / RAC-engine naming and a one-line enumeration of the five artifact types; install instructions (`pip`, the `uv tool install` alternative, Python 3.11+); the agent-connection snippet as the minimal usage example; the common-commands CLI block (`rac validate` / `rac inspect` / `rac review` / `rac export`); the "Who it's for" bullets; a Documentation section; project status; and license.

- [REQ-002] The Documentation section MUST contain one prominent link to the site plus the three primary entry points (Quickstart, MCP Server, CLI Reference) as site URLs. Per-page GitHub blob links to `docs/` files MUST be removed.

- [REQ-003] The sections "Why this works", "How this relates to spec-driven development" (including the comparison table and its sources comment), "How Lore earns trust", "Sharing the corpus (the Portal)", and the long-form "Grounding your agent" narrative MUST be removed from the README and MUST exist solely on the landing page.

- [REQ-004] The "Supported artifact types" five-bullet list MUST be deleted from the README; `docs/artifacts.md` owns that content.

- [REQ-005] Drift policy: the README MUST NOT contain content that also appears on the site, except the install command, the tagline, the condensed product summary, and the minimal usage example and common-commands block that ADR-022 requires the doorway to carry.

- [REQ-006] The site MUST be generated only from `docs/`; no site content may be authored in the README, the wiki, or any other location.

## Acceptance Criteria

- The README contains exactly the elements listed in REQ-001, in a
  reviewable order, and no section heading from REQ-003 appears in it.
- Every documentation link in the README points at
  `tcballard.github.io/requirements-as-code` URLs; `grep` finds no
  `github.com/.../blob/main/docs/` links.
- The comparison table, sources comment, trust bullets, and "Why this
  works" prose each appear exactly once in the repository's public
  surfaces: on `docs/index.md`, not in `README.md`.
- The resulting README is at most half its pre-change line count
  (≤ 82 lines against the current 163), as a measurable proxy for
  ADR-022's one-minute readability.
- The implementation PR shows the README diff as pure removal/relocation:
  no new prose beyond the site links.

## Success Metrics

- A reader who only opens the README can install Lore, connect an agent,
  and find the site without scrolling past one screen of depth content.
- Six months of README history after this change shows no regrowth of the
  relocated sections (the drift policy holding in practice).

## Risks

- The line-count ceiling is a proxy, not the goal; if ADR-022's required
  contents cannot fit in 82 lines without harming clarity, the criterion
  is amended through this artifact rather than quietly missed.
- External links into removed README anchors (e.g. from old issues) will
  land at the top of the README instead of the moved section; accepted.

## Assumptions

- The site is live (or its URL structure is final) before the README
  switches its links from GitHub blob URLs to site URLs — both land in the
  same implementation PR, so links go live together.
- ADR-042 is accepted, making the drift policy normative rather than
  advisory.

## Related Requirements

- rac-documentation-structure
- rac-docs-site-landing-page

## Related Decisions

- ADR-022
- ADR-042

## Related Designs

- docs-site-scoping

## Related Roadmaps

- v0.10.7-docs-site
