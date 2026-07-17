---
schema_version: 1
id: RAC-KTYXZ9AGKZRF
type: requirement
---
# Requirement: Portal Citation Links

## Status

Proposed

Drafted to open the discussion; nothing here is scheduled.

## Problem

Citations are the spine of the product: every Guide answer cites a
decision by ID, and the Portal linkifies citations inside artifact
bodies. But how a citation *renders* — and where it *leads* — is
currently the least designed part of the experience:

- In an agent session, a Guide citation surfaces as a bare token
  (`adr-027`, or worse the opaque `RAC-KTQ63DSC8SZW`) or a raw
  repository path. It is not clickable in most chat surfaces, carries
  no title or status, and gives the reader no affordance beyond "go
  look it up".
- In the Portal, body citations and related-artifact links work, but
  they are plain dashed-underline tokens; there is no hover context
  (title, status), and nothing distinguishes a citation to a superseded
  decision from one to an accepted decision.
- Across surfaces there is no shared answer to "what is the canonical
  navigable target of a citation?" — the repository Markdown path (live
  truth, editor-clickable), the Portal hash route
  (`#/artifact/<id>`, snapshot), or a hosted Portal URL (durable,
  shareable, but only meaningful once a Portal has a published home).

Affected: agent users reading Guide responses mid-task, humans reading
an exported Portal, stakeholders receiving a shared export, and anyone
reading a PR or issue where an artifact is cited.

This matters now because v0.11.0 ships the Portal with working hash
deep links: the plumbing for beautiful citations exists, the rendering
and the cross-surface conventions do not.

## Requirements

- [REQ-001] A citation shall render as the artifact's preferred human alias with its title available in the same surface (visible or on hover/expansion) wherever the citation resolves — never the opaque canonical ID alone when an alias exists.

- [REQ-002] Each surface shall link a citation to the target appropriate to that surface: the repository Markdown path in editor and agent contexts; the `#/artifact/<id>` hash route inside the Portal; an absolute URL only when a Portal base URL has been explicitly configured.

- [REQ-003] Citation link generation shall fabricate nothing: when no Portal base URL is configured, no URL is emitted; when a reference does not resolve, it renders verbatim and visibly unresolved, exactly as the export contract already requires.

- [REQ-004] Portal citation rendering shall be state-aware: a citation to a superseded or deprecated artifact is visually distinguishable from a citation to an accepted one, using the existing semantic colour rules (status colours stay semantic, never decorative).

- [REQ-005] Any citation metadata added to Guide tool responses (alias, title, path, optional portal URL) shall be an additive, explicitly versioned change to the pinned output contracts, and identical repository state shall keep producing identical responses.

- [REQ-006] A Portal base URL, if introduced, shall be optional configuration with no zero-config regression: every existing command and tool behaves identically when it is absent.

## Open Questions

- Where does a Portal canonically live — committed file, release
  asset, GitHub Pages? (Determines whether absolute citation URLs are
  ever durable, and is a prerequisite for REQ-002's third target.)
- Should hover context in the Portal be a CSS-only affordance
  (title attribute / tooltip) or a richer preview panel? The aesthetic
  bar is the existing design system: one hue, dashed = container,
  solid = interactive.
- Do agent chat surfaces render Markdown links reliably enough that
  Guide responses should emit `[alias](path)` forms, or does that
  degrade in clients that show raw text?
- Is supersession state available cheaply at citation-render time in
  the Portal, or does it need precomputation in the export payload?

## Success Metrics

- A reader of a Guide answer can reach the cited artifact in one
  action in at least the editor context (clickable path), without
  asking the agent for the location.
- In the Portal, every resolvable citation exposes title and status
  context without navigating away; superseded targets are visibly
  flagged at the citation site.
- Zero fabricated or dead links: a corpus-wide check over an exported
  Portal finds no citation link whose target is absent without the
  "(not in corpus)" marker.
- The Guide JSON contracts remain pinned: any new citation fields ship
  as additive schema changes with golden coverage, and existing
  consumers parse unchanged.

## Risks

- Stale snapshots: Portal links cite a moment in time; a link followed
  after the corpus moved can mislead. Mitigation candidates: surface
  the export's identity in the Portal header (already shown) and keep
  the repository path the primary target in working contexts.
- Client variance: chat surfaces differ wildly in what they render
  (Markdown links, file:// URLs, plain text). A convention that looks
  good in one client may be noise in another; REQ-002's
  surface-appropriate targeting exists to contain this.
- Scope creep towards a hosted product: durable citation URLs pull
  towards hosting the Portal, which the positioning deliberately
  avoids; any hosted home must remain the repository owner's choice
  and infrastructure.
- Contract churn: adding citation metadata to Guide responses touches
  pinned contracts; doing it casually erodes the stability promise
  that makes the contracts trustworthy.

## Assumptions

- The Portal's hash routing (`#/artifact/<id>`) remains the stable
  deep-link mechanism and works from `file://`.
- Aliases remain the human-preferred citation form and stay resolvable
  through Core identity (canonical first, aliases additive).
- The design system's semantic colour rules (teal = links/commands,
  status colours semantic only) continue to govern Portal rendering.
- If a Portal base URL convention emerges, repository configuration
  (not environment guessing) is the acceptable place for it.

## Related Decisions

- ADR-007
- ADR-014
- ADR-029
- ADR-030

## Related Requirements

- rac-agent-context-guide

## Related Roadmaps

- v0.11.0-portal-export
