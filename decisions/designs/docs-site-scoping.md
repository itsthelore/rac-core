---
schema_version: 1
id: RAC-KTYW08RYZ4WV
type: design
---
# Docs Site Scoping — Lore Documentation Website

## Context

Lore's documentation currently lives in two places: a long README that acts
as the only public entry point, and nine task-oriented guides under `docs/`
that are readable only as raw Markdown on GitHub. A documentation website
gives the product a real front door — a landing page modelled on
openspec.dev's structure (hero → what it is → install → links into docs) and
a browsable docs section with navigation and search — built from the same
repository Markdown that is already reviewed with code.

The site is itself managed under Lore's own artifact model: this design
artifact scopes the work, requirement artifacts (Phase 2) will govern it, and
nothing is built until those artifacts are approved. Dogfooding is a hard
requirement of the project, not a nice-to-have.

Decisions fixed before scoping (not re-evaluated here):

- Static site generator: MkDocs with the Material theme.
- Content source: the existing `docs/` Markdown files, unrewritten. Nav
  reorganization and a new index page are allowed.
- Shape: one landing page plus one docs section with sidebar nav and search.
- Deployment: GitHub Actions workflow → GitHub Pages, from this repository.

Two places where the project brief and the repository disagree; the
repository is the source of truth:

1. **The brief described five docs pages; `docs/` contains nine** —
   `quickstart.md`, `cli.md`, `mcp.md`, `artifacts.md`, `relationships.md`,
   plus `repo-workflow.md`, `testing.md`, `examples.md`, and `ecosystem.md`.
   All nine go into the site nav.
2. **The brief asked for a README reduced to badges, one paragraph, install,
   and a site link.** That conflicts with ADR-022 and
   REQ-Documentation-Structure (FR-001), which require the README doorway to
   also carry intended users, a minimal usage example, common commands, and
   project status. The maintainer has ruled: ADR-022's README shape stands;
   the brief's stricter minimization is overridden. The README diff plan
   below reflects this.

ADR-022 names its own review trigger — "when introducing external
documentation hosting" — and this project fires it. The site does not change
where canonical documentation lives (repository Markdown remains
authoritative; the site is a generated view), but Phase 2 MUST include an
ADR-022 amendment or companion decision recording the hosting model and the
drift-prevention policy defined here.

Roadmap placement: the corpus convention is one roadmap artifact per release
in `rac/roadmaps/v0.10.x-guide/`. Slots v0.10.4–v0.10.6 are taken (the
"next up: v0.10.4" note in CLAUDE.md is stale), so Phase 2 should target
**v0.11.1** for this work (in the `v0.11.x-portal` series; v0.10.7 was the
original slot before the v0.11.0 portal release renumbered it).

## User Need

- **A prospective user** evaluating Lore needs to understand what it is, who
  it is for, and how to install it within a minute — without reading raw
  Markdown on GitHub. The landing page serves this need.
- **A new user** following the README's doorway needs a guided path —
  quickstart, MCP setup, CLI reference — with navigation and search instead
  of jumping between blob URLs.
- **The maintainer** needs README and site to stay consistent without manual
  reconciliation, and needs the site governed by the same artifact model as
  everything else in the repository.

## Design

### Site map

Every page on the site, its source file, and its nav position. Nav is flat
(one docs section), ordered by user journey: get started, connect the agent,
look things up, go deeper, contribute.

| Nav position | Nav label | Page H1 | Source file |
| --- | --- | --- | --- |
| 1 (Home) | Home | Lore landing page | `docs/index.md` (new) |
| 2 | Quickstart | Quickstart | `docs/quickstart.md` |
| 3 | MCP Server | RAC Guide — MCP Server | `docs/mcp.md` |
| 4 | CLI Reference | CLI Reference | `docs/cli.md` |
| 5 | Artifacts | Artifacts | `docs/artifacts.md` |
| 6 | Relationships | Relationships | `docs/relationships.md` |
| 7 | Repository Workflow | Repository Workflow | `docs/repo-workflow.md` |
| 8 | Examples | Examples | `docs/examples.md` |
| 9 | Ecosystem | Ecosystem | `docs/ecosystem.md` |
| 10 | Testing & Contributing | Testing & Contributing | `docs/testing.md` |

Positions 2–4 mirror the README's current Documentation list order
(quickstart, mcp, cli) so the doorway and the site agree on what matters
first. No existing page is renamed, split, or rewritten.

### Landing page wireframe (`docs/index.md`)

Material-themed home page; stock theme capabilities first, custom HTML/CSS
only if an acceptance criterion is unreachable without it. Section order,
top to bottom:

1. **Hero.** The Lore header art — light and dark variants
   (`lore-header-light.png` / `lore-header-dark.png`, served from
   `docs/images/`, shown per the active color scheme) — with the existing
   alt text ("Lore — agents that know why. Deterministic. Read-only. No
   RAG, no guessing.") and the existing tagline as the headline: *"Give
   your coding agent the decisions your team already made — so it stops
   re-doing things you ruled out."*
2. **Install.** `pip install requirements-as-code` in a copyable code block,
   with the `uv tool install` alternative and the Python 3.11+ requirement
   on one line beneath.
3. **What it is.** Two short paragraphs relocated from the README: the
   agent-grounding value proposition, and the Lore-product / RAC-engine
   naming (per ADR-036: Lore is the product, RAC is the engine, everything
   ships under the `rac` name).
4. **Three primary links.** Quickstart, MCP Server, CLI Reference — the
   above-the-fold paths into the docs section.
5. **Why this works.** Relocated from the README's "Why this works" section.
6. **How this relates to spec-driven development.** Relocated from the
   README: the SDD positioning paragraph and the Lore/Spec Kit/OpenSpec
   comparison table, including its sources comment.
7. **How Lore earns trust.** Relocated from the README's trust section
   (read-only server, no AI in core, dogfooding, output contracts,
   opt-in telemetry).
8. **Footer links.** GitHub repository, project status one-liner,
   CONTRIBUTING, MIT license.

Sections 1–4 constitute the above-the-fold contract at desktop width; 5–8
are the below-the-fold depth that the README sheds.

### File-level change list

Every file created or modified:

| File | Change | Purpose |
| --- | --- | --- |
| `mkdocs.yml` | new | Site config: site name, `site_url` `https://tcballard.github.io/requirements-as-code/`, `repo_url`, Material theme with light/dark palettes, built-in search, explicit nav per the site map. |
| `.github/workflows/docs.yml` | new | Build `mkdocs build --strict` on push to `main` and deploy to GitHub Pages via the official `actions/configure-pages`, `upload-pages-artifact`, `deploy-pages` actions; strict mode fails the build on broken nav or links. |
| `docs/index.md` | new | The landing page per the wireframe above. |
| `README.md` | modified | Reduced to the ADR-022 doorway per the diff plan below. |
| `docs/images/lore-header-light.png` | new (copy) | Hero art must live under `docs/` because MkDocs serves only the docs dir; copied from `rac/assets/images/`, which stays canonical for the README. |
| `docs/images/lore-header-dark.png` | new (copy) | Dark-scheme variant of the above. |
| `docs/ecosystem.md` | modified (links only) | Three `../` links out of the docs tree (`rac/`, `.claude/skills/`, `examples/guide/`) become absolute GitHub URLs so the strict build passes. |
| `docs/mcp.md` | modified (link only) | One `../examples/guide/` link becomes an absolute GitHub URL. |
| `docs/repo-workflow.md` | modified (link only) | One `../rac/decisions/adr-022...` link becomes an absolute GitHub URL. |
| `docs/testing.md` | modified (links only) | Two `../rac/...` links become absolute GitHub URLs. |
| `rac/` (Phase 2) | new artifacts | Requirements, relationships, v0.11.1 roadmap entry, and the ADR-022 amendment — scoped in Phase 2, listed here only for traceability. |

The seven link conversions across four docs files are the only edits to
existing docs content, and they change link targets, not prose. No other
docs page is touched.

### README diff plan

Measured against ADR-022's required doorway contents (product summary,
intended users, installation, minimal usage example, common commands, links
to deeper documentation, project status).

**Stays in README:**

- H1, `mcp-name` comment, hero `<picture>` element, all four badges.
- The tagline blockquote and a condensed product summary (what Lore does,
  one short paragraph) including the Lore/RAC naming sentence.
- Install: `pip install requirements-as-code`, the `uv tool install`
  alternative, Python 3.11+.
- Minimal usage example: the agent-connection snippet
  (`claude mcp add lore -- rac mcp` plus the `mcpServers` JSON block).
- Common commands: the three-line CLI block
  (`rac validate` / `rac inspect` / `rac review`).
- "Who it's for" (intended users), condensed to its three bullets.
- A Documentation section that links to the site: one prominent site link,
  plus the three primary entry points (Quickstart, MCP Server, CLI
  Reference) as site URLs rather than GitHub blob URLs.
- Project status and License.

**Moves to the site (landing page):**

- "Why this works" — wireframe section 5.
- "How this relates to spec-driven development" with the comparison table
  and its sources comment — wireframe section 6.
- "How Lore earns trust" — wireframe section 7.
- The long-form "Grounding your agent" narrative (the step framing and the
  worked soft-delete example); the README keeps only the bare connection
  snippet, and the full walkthrough remains `docs/mcp.md`.
- The 90-second-demo placeholder link — wireframe section 1 territory,
  added when the demo exists.

**Deleted from README (already owned elsewhere, not moved):**

- The "Supported artifact types" five-bullet list — `docs/artifacts.md` owns
  this; the README's product summary keeps the one-line enumeration of the
  five types.
- Per-page GitHub blob links to docs files — replaced by site links.

### Phase 2 handoff

The requirement artifacts expected from this scope, for the Phase 2 agent
(final grouping is Phase 2's call, bounded by this list):

1. Landing page (wireframe sections, branding assets, above-the-fold
   contract).
2. Docs site (Material theme, nav per site map, search, sourced from
   `docs/` unrewritten).
3. Publish pipeline (Actions → Pages, strict build as the gate).
4. README doorway + drift policy (ADR-022 shape, including the ADR-022
   amendment/companion decision).

## Constraints

- MkDocs + Material only; no other generators, plugins beyond the built-in
  search, or Python dependencies beyond `mkdocs` and `mkdocs-material`
  (pinned). A custom home template (`overrides/`), one theme stylesheet, and
  self-hosted fonts are permitted — they add no plugins or pip dependencies.
- The landing page adopts the **lore-web visual identity** (amber on warm
  near-black, JetBrains Mono, dashed terminal chrome, lamplighter mascot),
  rendered in an OpenSpec-style hero. The site ships a single dark scheme;
  the identity defines no light palette. (Maintainer decision, 2026-06-13,
  superseding the original "stock Material" cap.)
- **GATE-1 publish sequencing:** that identity is the pre-launch Lore brand,
  shared with the `lore-web` surface held behind GATE-1 (nothing public until
  external-communications review). Enabling Pages is the go-public gate and
  MUST wait for that review; merging the work publishes nothing on its own.
- Existing `docs/` pages are not rewritten; the only permitted edits are the
  seven link conversions the strict build requires.
- One landing page and one docs section. No blog, versioned docs, analytics,
  custom domain, or i18n (see Deferred items).
- Deployment exclusively via GitHub Actions to GitHub Pages from this
  repository; no external hosting, no `gh-pages` branch.
- ADR-022 documentation boundaries hold: README = doorway, `docs/` =
  user documentation (now also the site source), `rac/` = product knowledge
  corpus, which the site does not publish.
- Repository Markdown remains authoritative; the site is a generated view
  and is never edited directly.
- **Drift-prevention policy:** the site is generated only from `docs/`. The
  README contains nothing that also appears on the site except the install
  command, the tagline, and the minimal usage example and common commands
  that ADR-022 requires the doorway to carry. The README's documentation
  links point only at the site, so site nav changes cannot strand README
  links. Every section relocated from the README lives in exactly one place
  (`docs/index.md`) and must not regrow in the README. Phase 2 encodes this
  policy in the ADR-022 amendment so it is enforceable, not folklore.

## Rationale

- **ADR-022's README shape over the brief's stricter cut:** recorded
  decisions take precedence over inferred or imported conventions, and the
  maintainer confirmed the ruling. The README stays a doorway a reader can
  absorb in a minute, but a doorway with a usage example converts better
  than a bare link.
- **Flat nav over grouped nav:** ten pages do not need section headers, and
  a flat sidebar matches the "one docs section" constraint with zero
  configuration cleverness.
- **Link conversion to absolute GitHub URLs** (rather than excluding pages
  or copying `rac/` content into `docs/`): keeps the strict build green
  without violating either the no-rewrite constraint or the ADR-022 boundary
  that the corpus is not user documentation.
- **Vendoring brand assets into `docs/`** (mascot, fonts) rather than
  pointing the site at raw GitHub URLs or a CDN: site assets build from the
  docs dir so the build is self-contained, strict mode can verify them, and
  the page makes no external requests — consistent with the product's
  no-network ethos. The fonts ship with their OFL license under `docs/fonts/`.
- **Adopting the lore-web identity over a neutral Material look:** the repo
  already has a WCAG-AA-checked design system (`lore-web/`); reusing its
  tokens keeps the docs site consistent with the eventual public surface
  instead of inventing a parallel palette. The cost is GATE-1 exposure,
  resolved by the publish-sequencing constraint above.

## Alternatives

- **Brief-literal minimal README** (badges, one paragraph, install, link):
  rejected — conflicts with ADR-022 and REQ-Documentation-Structure;
  maintainer ruled for the recorded decision.
- **Stock Material landing page** (the original plan): rejected after review
  — the default article layout rendered flat. Chosen instead: an
  OpenSpec-style splash (custom home template + one stylesheet) in the
  lore-web identity. Custom code stays bounded to `overrides/home.html` and
  `docs/stylesheets/extra.css`; no plugins or pip dependencies are added.
- **Neutral / amber-only identity without the pre-launch brand:** considered
  to avoid GATE-1 exposure, rejected by the maintainer in favour of full
  lore-web consistency, with publishing gated on the comms review instead.
- **`mkdocs gh-deploy` / `gh-pages` branch deployment:** rejected — the
  official Pages actions deploy from a build artifact, need no long-lived
  branch, and match GitHub's current recommended model.
- **Publishing `rac/` on the site** for maximum dogfooding: rejected —
  ADR-022 explicitly rejected exposing the corpus as user documentation;
  the site dogfoods by being governed by artifacts, not by publishing them.

## Accessibility

- The mascot carries descriptive alt text; the install command and tagline
  are real text, never baked into images.
- The lore-web palette is WCAG-AA-checked (every text/surface pair ≥ 4.5:1,
  verified by `lore-web/scripts/contrast-report.mjs`); the docs theme reuses
  those exact token values, so contrast holds on the single dark scheme.
- The install card's copy button is keyboard-operable and labelled; search
  and nav remain Material built-ins.

## Style Guidance

- Per ADR-036: the landing page leads with **Lore**; docs pages keep their
  existing RAC voice and titles unedited. The site title is "Lore"; the
  repository link makes the `rac` package identity visible.
- The lore-web identity governs the look, from `lore-web/src/styles/tokens.css`
  and `lore-web/DESIGN.md`: three warm-near-black surfaces (`#121212` /
  `#1a1a18` / `#242420`), amber as the only decorative hue (`#f5a623`,
  bright `#ffb84d`), teal `#4ec9b0` for commands/links, JetBrains Mono
  (weights 400/700), dashed borders for container chrome, sharp corners.
  The hero shows the lamplighter mascot; the headline is the tagline and the
  subhead is the brand line "Agents that know why."
- Copy relocated from the README moves verbatim; the landing page is
  assembled from existing sentences, not rewritten marketing.

## Open Questions

1. **pyproject `Homepage` URL** — should it change from the GitHub repo to
   the new site once live? It alters published package metadata, so it is
   the maintainer's call and is not assumed in scope.
2. **Unused visual assets** — `docs/images/explorer-hero.svg` and
   `docs/images/rac-explorer-walkthrough.gif` are currently unreferenced.
   Should either appear on the site (e.g., the walkthrough GIF on the
   landing page), or do they stay dormant? Default if unanswered: dormant.
3. **Repo settings** (not a design question, but a maintainer-only step):
   enabling GitHub Pages with "GitHub Actions" as the source cannot be done
   from a PR and must be performed manually before first deploy — and, per
   the GATE-1 constraint, not before the lore-web comms review clears.

Resolved since first draft: the light/dark question — the site ships a
single dark scheme (the lore-web identity defines no light palette).

## Deferred Items

Out of scope by decision; one sentence each:

- **Blog** — no news/announcement surface until there is a publishing cadence
  to justify one.
- **Versioned docs** — a single "latest" site is sufficient pre-v1.0.
- **Analytics** — no usage measurement on the site; telemetry posture stays
  as ADR-040/ADR-041 define it for the product.
- **Custom domain** — the site lives at the default
  `tcballard.github.io/requirements-as-code` address.
- **Internationalization** — English only.

## Related Requirements

- rac-documentation-structure

## Related Decisions

- adr-022
- adr-018
- adr-036
- adr-001
