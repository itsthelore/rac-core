---
schema_version: 1
id: RAC-KTYXDR8V88GY
type: requirement
---
# REQ-Docs-Site-Publish-Pipeline

## Status

Accepted

## Problem

A docs site that is published manually, or that publishes broken links,
is worse than no site: it drifts from the repository the moment someone
forgets a deploy, and ADR-042 makes the repository Markdown authoritative.
Publishing must be automatic on merge to `main`, and a build with broken
navigation or links must never reach production.

## Requirements

- [REQ-001] A GitHub Actions workflow at `.github/workflows/docs.yml` MUST build and deploy the site on every push to `main`.

- [REQ-002] The build step MUST run `mkdocs build --strict`, so any MkDocs warning — including broken links and nav entries — fails the workflow and blocks deployment.

- [REQ-003] Deployment MUST use the official GitHub Pages actions (`actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`). A `gh-pages` branch MUST NOT be created, and generated HTML MUST NOT be committed to the repository.

- [REQ-004] The workflow MUST declare least-privilege permissions: `contents: read`, `pages: write`, `id-token: write`, and nothing more.

- [REQ-005] Action versions SHOULD be pinned to at least a major version tag; the MkDocs dependencies installed in the workflow MUST be the same pinned versions REQ-Docs-Site-Platform requires.

- [REQ-006] Enabling GitHub Pages with "GitHub Actions" as the source is a repository setting only the maintainer can change; the implementation MUST document it as a manual step and MUST NOT attempt to automate it.

- [REQ-007] Because the landing page carries the pre-launch Lore brand identity (shared with the `lore-web` surface held behind GATE-1 pending external-communications review), enabling Pages MUST NOT occur before that review clears. The manual enable-Pages step is the go-public gate; merging the implementation publishes nothing on its own.

## Acceptance Criteria

- `.github/workflows/docs.yml` exists, parses as valid workflow YAML, and
  triggers on `push` to `main` only.
- The workflow runs `mkdocs build --strict`; introducing a deliberate
  broken link in a scratch branch fails the build step (demonstrated once
  during implementation, then reverted).
- The deploy job uses the three official Pages actions and no third-party
  deploy action.
- `git branch -r` shows no `gh-pages` branch, and the repository contains
  no committed `site/` output.
- The workflow's `permissions` block matches REQ-004 exactly.
- The implementation PR lists "enable Pages, source: GitHub Actions" as a
  manual maintainer step.

## Success Metrics

- After the maintainer enables Pages, every merge to `main` that touches
  `docs/` or `mkdocs.yml` results in the live site updating with no manual
  action.
- No broken-link report against the live site can outlive the next merge,
  because strict mode blocks regressions at build time.

## Risks

- The first deploy depends on the manual Pages setting; until then the
  workflow's deploy job fails or skips — expected and documented, not a
  defect.
- Pinned action major versions still move minor releases; a breaking
  change in the official actions would surface as a workflow failure on
  `main`, visible immediately.

## Assumptions

- The repository remains public, so GitHub Pages is available on the
  current plan without configuration beyond the source setting.
- CI policy (ADR-027) tolerates one additional, independent workflow that
  runs only on `main` pushes and does not gate PRs.

## Related Requirements

- rac-docs-site-platform

## Related Decisions

- ADR-042
- ADR-027

## Related Designs

- docs-site-scoping

## Related Roadmaps

- v0.11.1-docs-site
