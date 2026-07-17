---
schema_version: 1
id: RAC-KTYXDQ7JGDVR
type: requirement
---
# REQ-Docs-Site-Platform

## Status

Accepted

## Problem

Lore's nine user-facing guides under `docs/` are readable only as raw
Markdown on GitHub: no navigation, no search, no rendered front door. New
users either bounce between blob URLs or never find the deeper pages at
all. The docs need a browsable site — without forking the content, moving
the files, or violating the ADR-022 boundary that keeps the `rac/` corpus
out of user documentation.

## Requirements

- [REQ-001] The site MUST be built with MkDocs and the Material theme. The `mkdocs` and `mkdocs-material` versions MUST be pinned, and no dependencies or plugins beyond those two packages, their transitive dependencies, and MkDocs' built-in search plugin may be introduced. A custom theme directory (`custom_dir`), a single extra stylesheet, and self-hosted fonts are permitted, as they add neither plugins nor Python dependencies.

- [REQ-002] `mkdocs.yml` MUST declare an explicit nav in exactly this order: Home, Quickstart, MCP Server, CLI Reference, Artifacts, Relationships, Repository Workflow, Examples, Ecosystem, Testing & Contributing.

- [REQ-003] All nine existing `docs/` pages (`quickstart.md`, `mcp.md`, `cli.md`, `artifacts.md`, `relationships.md`, `repo-workflow.md`, `examples.md`, `ecosystem.md`, `testing.md`) MUST be served from their current paths, unrenamed and unmoved.

- [REQ-004] The prose of existing `docs/` pages MUST NOT be rewritten. The only permitted edits are the seven link-target conversions from `../` relative paths to absolute GitHub URLs: three in `ecosystem.md`, one in `mcp.md`, one in `repo-workflow.md`, and two in `testing.md`.

- [REQ-005] Built-in search MUST be enabled and MUST index every page in the nav.

- [REQ-006] `site_url` MUST be `https://tcballard.github.io/requirements-as-code/` and `repo_url` MUST point at the GitHub repository.

- [REQ-007] Every asset the site serves MUST live under `docs/` (the header-art copies land in `docs/images/`); the site MUST NOT reference raw-GitHub or other external URLs for its own assets.

- [REQ-008] The site MUST NOT publish content from `rac/` — the corpus stays behind the ADR-022 boundary.

- [REQ-009] The site MUST present the lore-web visual identity: a single dark scheme driven by the lore-web tokens (warm near-black surfaces, amber accent, teal for commands/links), JetBrains Mono self-hosted under `docs/fonts/` with `theme.font: false`, and no external font or CDN requests.

## Acceptance Criteria

- `mkdocs build --strict` exits 0 with no warnings.
- The rendered sidebar lists the ten nav entries in the REQ-002 order.
- `git diff` for the nine existing pages touches exactly the seven link
  lines named in REQ-004 and nothing else.
- Searching "validate" and "MCP" on the built site each return at least
  one result from the docs pages.
- The built site uses the single dark scheme with JetBrains Mono, and the
  rendered pages issue no external font/CDN requests (`theme.font: false`,
  fonts served from `docs/fonts/`).
- The built `site/` output contains no page generated from a source file
  outside `docs/`.
- `pip install` of the pinned versions plus `mkdocs build` succeeds from a
  clean environment with no additional packages.

## Success Metrics

- Every page reachable today as a GitHub blob URL is reachable on the site
  through at most two clicks from the landing page.
- The site builds reproducibly from a clean checkout with only the two
  pinned dependencies.

## Risks

- `cli.md` is 823 lines; Material renders long pages fine, but its
  right-hand table of contents is the only mitigation in scope.
- Strict mode may surface link issues beyond the seven known conversions;
  any such finding stops work on that criterion and is reported, not
  silently patched (per the Phase 3 contract).

## Assumptions

- The nine docs pages' internal links to each other are all relative `.md`
  links that MkDocs resolves natively (verified in scoping; only the seven
  outbound links break).
- GitHub Pages serves the site from the project path
  `/requirements-as-code/`, which `site_url` reflects.

## Related Requirements

- rac-documentation-structure
- rac-docs-site-landing-page
- rac-docs-site-publish-pipeline

## Related Decisions

- ADR-022
- ADR-001
- ADR-042

## Related Designs

- docs-site-scoping

## Related Roadmaps

- v0.11.1-docs-site
