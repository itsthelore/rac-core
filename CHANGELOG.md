# Changelog

User-visible changes to RAC, by release. Follows the spirit of
[Keep a Changelog](https://keepachangelog.com/): user impact over implementation
details, release history over commit history.

## Unreleased

### Changed

- The TypeScript stack moved out of this repository (v0.22.5). The client SDK
  now lives in `itsthelore/rac-sdk-ts`, published to npm as
  `@itsthelore/rac-sdk`, and the VS Code extension in `itsthelore/lore-vscode`,
  consuming that published package instead of the former in-repo
  `file:../rac-sdk` path. The in-repo `typescript/` directory and its CI
  (`typescript.yml`, `sdk-release.yml`, `extension-release.yml`) are removed.
  The `rac` engine, CLI, and PyPI package (`requirements-as-code`) are
  unchanged.

### Added

- Extension robustness for release (v0.21.6 milestone). The extension now
  **activates only in RAC workspaces** (a `.rac/config.yaml` is present),
  **caches** resolve/export lookups (cleared on save) so hover/completion stay
  responsive, **warns** once on `rac` schema-version skew, logs to a dedicated
  **"RAC" output channel** (no telemetry), and carries Marketplace/OpenVSX
  packaging metadata (`repository`, `bugs`, `keywords`) and an **icon** (the RAC
  lore-explorer mascot). Only the actual publish step remains manual. This
  completes the `v0.21.x-editor` series.

- RAC Explorer in the extension (v0.21.5 milestone). A **RAC: Open Explorer**
  command renders the corpus relationship graph in a webview — the self-contained
  Portal viewer produced by `rac export --html` (the `lore-web` build with the
  corpus injected, offline). Re-run to refresh. The SDK gains `exportHtml(dir,
  path)`. (Graph↔editor click-through is deferred — the standalone viewer doesn't
  message a host.)

- Ambient corpus awareness in the extension (v0.21.4 milestone). A **status-bar
  health score** (`rac review`, click for the Problems panel) and
  **workspace-wide diagnostics** (`rac validate <dir>`) so issues in unopened
  artifacts are visible. The live per-file diagnostics own open files; the
  workspace scan covers the rest, so nothing is double-reported.

- Editor navigation in the extension (v0.21.3 milestone). Hover now shows the
  target's lifecycle status (⚠ for retired) and a snippet; **find-all-references**
  lists every artifact that references the one under the cursor (from the export's
  resolved edges); artifact aliases are **clickable links**; and the corpus is
  navigable via the **Outline** (an artifact's sections) and **workspace symbols**
  (jump to any artifact by title). All from the cached `rac export` (ADR-063).

- Authoring aids in the editor extension (v0.21.2 milestone). Inside a
  relationship section, the extension now offers **artifact-alias completion**
  (human aliases like `adr-007`, from a cached `rac export`); **quick-fixes**
  insert a missing `## Section` to clear a `missing-<section>` finding; and a
  **RAC: New Artifact** command scaffolds an artifact of any type via `rac new`.
  The SDK gains `schema(type)` and `createArtifact(type, path)`.

- Cross-artifact enforcement in the editor extension (v0.21.1 milestone). The
  extension now flags references that don't resolve, and references to **retired**
  (superseded/deprecated) artifacts, at the reference site — drawn distinctly
  (an unresolved reference is an error, a retired one a warning). Findings come
  from `rac relationships --validate`; the engine's `relationship-target-*` codes
  map to editor diagnostics, anchored to the target token inside the source
  artifact's relationship section. This is what makes the extension RAC rather
  than a generic Markdown linter (ADR-049, ADR-051). Relationship diagnostics
  refresh on save/activation (relationship validation reads files from disk).

- TypeScript SDK and editor extension (v0.21.0 milestone — TypeScript-only; the
  Python package is unchanged and versions independently). `@rac/sdk` is a thin
  Node client that shells out to the installed `rac` CLI and returns typed results
  over the stable `--json` contracts (ADR-063): validate a file, a directory, or
  in-memory text (via `rac validate -` on stdin), plus resolve, find,
  relationships, review, stats, and export — all under one `RacError` root, with
  an injectable runner seam for testing. A VS Code / Cursor extension built on it
  validates RAC artifacts in-editor (live as you type, plus on open/save) and
  offers hover and go-to-definition on artifact IDs/aliases. Both packages live
  under `typescript/` at 0.1.0; a TypeScript CI workflow builds and tests them.
  The `v0.21.x` series (`rac/roadmaps/v0.21.x-editor/`) scopes the follow-on
  releases — cross-artifact enforcement, authoring aids, navigation, awareness,
  visualization, and release hardening.

### Changed

- **License: RAC is now under the Apache License 2.0 (previously MIT).** The
  package, CLI, and TypeScript stack carry `Apache-2.0` metadata, and a `NOTICE`
  file ships alongside `LICENSE`. Apache 2.0 adds an express patent grant and an
  explicit trademark non-grant over MIT; it remains a permissive license, so
  existing usage rights are unaffected. Contributions now require a Developer
  Certificate of Origin sign-off (`git commit -s`); there is no CLA. Distribution
  names are unchanged (PyPI `requirements-as-code`, CLI `rac`, server identity
  `lore`). See `rac/decisions/adr-071-apache-2-relicense-and-dco.md`.

## v0.19.0 — 2026-06-15

The kitchen-sink release. Everything since v0.7.3 lands at once. Over this
stretch RAC grew from a requirements validator into a product-knowledge
system: the Explorer TUI, canonical frontmatter identity and opaque IDs, the
relationship graph and its integrity checks, repository intelligence
(`rac portfolio`, `rac watchkeeper`), the Portal and OKF interop exports,
per-type standards enforcement, and a GitHub Action that brings all of it to
pull requests. This entry collects the whole arc into one formal release — the
individual `(vX.Y.Z)` markers below trace where each capability landed.

### Added

- Roadmap "Achieved" lifecycle status (v0.19.0): a roadmap whose scope has
  shipped can declare `## Status: Achieved`, a validated *live terminal* state
  (ADR-061) — the intent was delivered, so the roadmap reads as done without
  being treated as retired, and inbound references to it are not flagged as
  pointing at a superseded target. `rac schema roadmap` lists it among the
  allowed statuses; the roadmap enum is now Planned / Achieved / Superseded /
  Abandoned.

- Validate GitHub Action (v0.17.2): a composite action
  (`tcballard/requirements-as-code/validate-action@<ref>`) runs
  `rac validate --sarif` and uploads the result to GitHub Code Scanning, so RAC
  findings annotate a pull request inline. A thin wrapper over the CLI (ADR-058):
  errors fail the check, warnings (including findings downgraded in
  `.rac/config.yaml`) annotate without failing — warnings-first onboarding. Docs
  cover the workflow, the `security-events: write` permission, and the
  custom-types/edges extensibility boundary (deferred, ADR-052/ADR-055).

- Per-type standards enforcement (v0.17.1): `rac validate` now lints requirement
  *quality* against the standards RAC cites — BCP-14 keyword discipline
  (`requirement-normative-keyword`, error: only uppercase MUST/SHALL/SHOULD/MAY are
  normative), ISO 29148 singularity (`requirement-not-singular`, warning), and EARS
  (`requirement-non-ears` / `requirement-ears-clause`, warnings). Roadmaps gain an
  optional, validated `## Horizon` (now/next/later or a quarter) and an
  advancement-linkage warning. All checks are deterministic (no AI in core) and
  overridable per the v0.15.2 model. Severity overrides are now **repository-wide**
  (ADR-053 revised): a rule downgraded in `.rac/config.yaml` is downgraded for
  `rac review`/`watchkeeper`/`portfolio` too, not only `rac validate` — so a
  warnings-first policy is consistent across every surface.

- Relationship-graph integrity (v0.16.0): `rac relationships --validate` now
  validates the corpus as a graph (ADR-055). A `## Related <Type>` reference that
  resolves to the wrong artifact type is reported as
  `relationship-target-type-mismatch` (untyped-document targets are exempt,
  ADR-010), and a cycle in `supersedes` as `relationship-cycle`. Lifecycle status
  is generalized to all five artifact types (ADR-051): each type has an optional,
  validated `## Status` enum and a retired set, so the "nothing live points at a
  retired artifact" rule (`relationship-target-superseded`) now covers
  requirements, designs, roadmaps, and prompts, not just decisions — status stays
  a knowledge lifecycle, never work state (ADR-017). The MCP `get_summary` tool
  (and `rac portfolio`) gain an additive `validation_status` block reporting the
  repository gate; the four read-only MCP tools are unchanged in count. The edge
  vocabulary (`related_*` + `supersedes`) and existing issue codes are unchanged;
  custom relationship types remain deferred (ADR-052).

- Validation severity overrides + SARIF output (v0.15.2): a repository may declare
  an optional `validation` section in its committed `.rac/config.yaml` to downgrade
  or silence findings — per rule code (`error|warning|off`) and per artifact type
  (`error|warning` ceiling), with the per-rule entry winning over the type ceiling.
  This makes warnings-first onboarding possible: a team can point `rac validate` at
  a legacy repo, keep CI green, and tighten the gate over time. Overrides apply to
  `rac validate` only (review/watchkeeper/portfolio are unchanged); an absent
  section is a no-op, so the default gate stays strict. Also adds
  `rac validate <dir> --sarif`, emitting a deterministic, offline SARIF 2.1.0
  document (core validation + OKF conformance findings) for GitHub Code Scanning;
  `--sarif` is mutually exclusive with `--json` and applies to directory validation.

- OKF v0.1 conformance check (v0.15.1): `rac validate <dir>` now enforces OKF
  conformance as a write-time gate, not just on export. It reports, per typed
  artifact, `okf-unmapped-type` (a `type` with no OKF mapping) and
  `okf-reserved-filename-collision` (a typed artifact named `index.md`/`log.md`),
  and fails the run when the corpus could not produce a conformant bundle. Untyped
  documents are excluded (ADR-010); the directory `validate` JSON gains an additive
  `okf` section (no `schema_version` bump). Per ADR-052, `rac-core` stays the
  code-defined OKF-superset envelope — no JSON Schema files, no new dependency.

- OKF frontmatter superset (v0.15.0): RAC artifacts may now declare an optional
  `tags: [...]` list (the OKF-reserved descriptive field ADR-025 anticipated),
  validated for shape and additive — no `schema_version` bump. `rac export --okf`
  carries `tags` from source plus `created`/`updated` derived from git history
  (first and last commit) in each bundle artifact, so the OKF bundle is
  timestamped while the source stays date-free (recency is git-derived, ADR-045).
  RAC deliberately does not add frontmatter `title`/`description` or make `type`
  mandatory (ADR-050). The JSON export contract is unchanged.

- Status-consistency validation (v0.14.1): `rac relationships --validate` now
  reports a relationship from a live artifact to a decision the team has retired
  (`Superseded` or `Deprecated`) as `relationship-target-superseded` — so nothing
  live points at a superseded artifact. The `supersedes` edge by which a replacing
  decision references the one it replaces is exempt, as is a reference from a
  retired decision (historical chains). Decision-only for now, since lifecycle
  status lives on decisions. Existing issue codes are unchanged.

- Edge-legality validation (v0.14.0): `rac relationships --validate` now reports a
  `## Related <Type>` (or `## Supersedes`) section that the artifact's type does
  not support, instead of silently dropping it. Such a section produces no graph
  edge today; the new `relationship-edge-unsupported` issue surfaces it (and fails
  the validate exit code) so authors learn the link did nothing. Opens the
  enforcement series that makes deterministic cross-artifact validation RAC's core
  (ADR-049). Existing relationship issue codes are unchanged.

- OKF bundle export (v0.13.6): `rac export <dir> --okf [--out <dir>]` writes a
  derived Open Knowledge Format (OKF v0.1) bundle — one Markdown file per typed
  artifact with its OKF `type` projected (decision→ADR, requirement→Requirement,
  and so on), plus a generated `index.md` (progressive disclosure) and `log.md`
  (git-derived, date-grouped). Resolved relationships render as `# Citations`
  body links so they survive for permissive OKF consumers, while the typed front
  matter and `## Related` sections stay authoritative. Parallel to `--json` and
  `--html`; existing exports and validation are unchanged. See
  `docs/okf-profile.md`.

- OKF carrier profile recorded (ADR-048 + `rac-okf-carrier-profile`): RAC
  adopts Google's Open Knowledge Format (OKF v0.1 Draft) as an informative
  carrier profile and a derived export target — never a foundation. RAC repos
  are conformant OKF bundles (RAC `type` maps to OKF `type`: decision→ADR,
  requirement→Requirement, and so on), and the derived OKF bundle view
  (`rac export --okf`, above) joins the JSON/Portal export. RAC's normativity is unchanged — `rac validate`
  and `rac relationships --validate` keep rejecting what they reject today. The
  profile is documented in `docs/okf-profile.md`; the dependency is informative
  and pinned to OKF v0.1, with no code or package dependency on OKF tooling.

- Watchkeeper GitHub Action and reusable workflow (v0.12.3): a composite
  `action.yml` at the repository root (`uses:
  tcballard/requirements-as-code@<tag>`) and a callable
  `.github/workflows/watchkeeper.yml` bring product knowledge review to
  pull requests — failed check per the `fail-on` policy, inline
  annotations on the artifacts needing attention, and a step-summary
  report. The action is logic-free (install RAC, resolve the base ref,
  run one `rac watchkeeper --format github`, propagate the exit code) and
  this repository's own PR checks run it from source as the live
  end-to-end test. Pin exact release tags; no moving major tag is
  published (setuptools-scm derives versions from git tags). See
  `docs/watchkeeper.md`.

- Watchkeeper review verdict, GitHub format, and CI policy (v0.12.2):
  `rac watchkeeper` now ends with a deterministic review recommendation —
  validation regressions, broken relationships, and clarity-regression
  findings recommend human review with Core-owned reasons; ambiguity and
  unlinked scope inform but never recommend alone. `--fail-on
  error|warning|none` turns the verdict into CI policy, and `--format
  github` writes a Markdown step-summary report to stdout and
  workflow-command annotations (with repository-relative paths) to stderr
  — no GitHub API involved. JSON gains an additive `review` block.

- Watchkeeper intent analysis (v0.12.1): the `rac watchkeeper` report now
  ends with deterministic intent findings — specificity regressions
  (numbers vanishing from requirements), ambiguous wording arriving,
  mandatory language weakening or disappearing, acceptance criteria or
  success measures being removed, new scope with no relationships, and
  the relationship impact of modified or removed artifacts. Every check
  is token-boundary text matching or parsed-section comparison — no
  semantic scoring — and each finding carries a one-sentence detail plus
  diff-style evidence. JSON gains an additive `findings[]` array.

- Watchkeeper repository comparison (v0.12.0): `rac watchkeeper [directory]
  --base REF [--head REF] [--json]` reviews product knowledge changes
  between two repository states — added/modified/removed artifacts (with
  requirement-level diffs), validation deltas (including newly invalid
  artifacts), relationship deltas (including references broken purely by a
  removal elsewhere), and per-type artifact count deltas. Base and head
  each accept a git revision or a plain directory; revisions are
  materialized read-only via `git archive` (ADR-043) and nothing ever
  mutates the repository. JSON output is a stable contract
  (`schema_version: "1"`) that grows additively across the v0.12.x series
  (intent findings and review recommendations follow).

- Portal export (v0.11.0): `rac export` turns a repository's corpus
  into shareable artifacts. The default mode prints a deterministic
  JSON payload to stdout — artifacts with stable ids, aliases, type,
  status, title, path, and CommonMark-rendered bodies (raw HTML in
  sources arrives escaped), plus relationships as `relates-to` edges
  with unresolved references preserved verbatim — a stable contract for
  anyone building their own viewer. `rac export --html` writes the
  Portal: one self-contained HTML file with search, type/status
  filters, citation cross-links, and a related-artifacts panel, opening
  from `file://` with zero network requests — attach it to a release or
  send it to a stakeholder. The viewer shell is vendored from the
  repository's own `lore-web` source with provenance recorded, and a
  drift-guard test fails the build if the viewer source changes without
  re-vendoring. No timestamps and stable ordering keep two exports of
  the same tree byte-identical; both output modes are pinned by golden
  and round-trip tests. No new dependencies.

- Anonymous usage sharing (v0.10.6, opt-in): `rac telemetry on|off|status`
  and a one-time, TTY-only consent question at `rac init` (default No).
  With consent, `rac mcp` sends at most one anonymous daily ping — a random
  install id, the RAC version, and a 30-day active-repo count; never paths,
  queries, or repository content. The payload is pinned by ADR-041, the
  network surface is a single module enforced by tests, and a build without
  an endpoint key sends nothing at all.

- Bundled agent skills (v0.10.5): the package now carries three
  Claude Code skills as resources — `rac-artifacts` (author and maintain
  artifacts with the CLI), `rac-review` (work `rac review` findings
  worst-first until validation passes), and `rac-ingest` (convert DOCX,
  PDF, HTML, PPTX, XLSX, or Markdown documents into valid, linked
  artifacts). `rac skill install` drops all three into a project's
  `.claude/skills/` discovery path in one command — all-or-nothing, never
  overwriting; `rac skill install` with a skill name adds just that one,
  and `rac skill list` shows what is bundled. Installation works from the
  installed wheel alone: no repository checkout, no network, no AI. Human
  and `--json` output are pinned by golden tests, and each packaged skill
  is kept byte-identical to the repository's own dogfood copy by test.

- Growth programme corpus and comparison (growth-programme): the
  repository's own growth plan now lives in the corpus as seven
  requirements, two designs, and an umbrella roadmap — including the
  spec-driven-development comparison that backs the README's new "How
  this relates to spec-driven development" section (GitHub Spec Kit and
  OpenSpec, every claim cited to the tool's own documentation), a
  `docs/ecosystem.md` seed list, and a consolidated traceability gap
  report written from real authoring friction
  (`.agent-context/GAPS_TRACEABILITY.md`).

- Opt-in Guide telemetry (v0.10.4): `rac mcp --telemetry` records tool-call
  counts and metadata — never arguments or repository content — to a local
  log under `$XDG_STATE_HOME/rac/`; off by default and announced on stderr
  when on. Tool responses are byte-identical with telemetry on and off. A
  new `rac mcp-stats` command summarizes the log (`--json` is the shareable
  export; `--share` prints a prefilled GitHub usage-report issue URL you
  review and submit yourself — RAC contains no network code).

- Explorer knowledge-graph grammar (v0.8.13): the Explorer's **Links** tab
  now renders relationships in the designed terminal grammar — a vertical
  dependency chain from the artifact to what it relates to (each `↓` carrying
  the relationship kind), an **Impact Analysis** block that frames a change
  ("Changing: … / May affect: …"), and a `↓`-joined lineage chain for
  supersession. The relationships are unchanged — only their presentation —
  so "why does this exist?", "what depends on this?", and "what happens if
  this changes?" read directly. Presentation only; no Core, adapter, or
  state change.

- Explorer mascot interaction (v0.8.12): selecting the mascot in the
  Explorer — a click, or keyboard focus then Enter — returns a small
  response beneath the figure: a default acknowledgement, occasional
  reminders of why product knowledge is worth keeping, gentle guidance
  toward existing commands, and one rare line on repeated selection.
  Responses appear inline with no popup, dialog, or notification, and
  nothing is hidden behind them — the mascot surfaces functionality, it
  does not contain it. A new `mascot_interaction` preference (default on,
  cycled in `/settings`) turns it off independently of the mascot and
  animation toggles, and selection works with animations off. No Core or
  service changes.

- Review impact and the first-run editor (v0.8.11): every `rac review`
  finding now carries an `impact` sentence — why it matters — owned by Core
  and present in the JSON contract (additive field; `schema_version`
  unchanged), so the CLI, automation, and the Explorer all read identical
  text. Explorer onboarding gains one optional editor step after the
  welcome: Enter accepts (an empty value keeps the `$VISUAL`/`$EDITOR`
  fallback), typing persists the `editor` preference, Esc skips — and
  returning users never see it.

- Explorer creation, stats, and the directory view (v0.8.10): the sidebar
  now mirrors the repository's actual directory structure by default —
  directories as collapsible nodes (name, trailing `/`, artifact count),
  nested exactly as on disk, with expansion and cursor surviving reloads at
  any depth and `/open` revealing a nested artifact along its filesystem
  path; the `artifact_grouping` setting cycles `folders` | `type` | `flat`.
  `/new <type> <path>` creates an artifact from its canonical template:
  preview first, `y` confirms, the ID is minted by the same Core service as
  `rac new`, and nothing ever overwrites — on success the Explorer reloads
  and opens the new file, ready for `e`. `/stats` opens a portfolio
  dashboard (per-type validity, requirement and quality totals, decision
  status and category breakdowns, relationship counts), collected off the
  UI thread. `/browse <type>` now lists that type in the filterable results
  view in every grouping mode; bare `/browse` focuses the sidebar.

- Explorer live workspace and validation depth (v0.8.9): the Explorer now
  watches the repository and reloads itself when artifacts change on disk —
  a cheap path/mtime comparison every two seconds, with the sidebar keeping
  its expansion, the open artifact keeping its tab and scroll position, and
  the health chip updating; the watcher holds while a terminal editor owns
  the screen and rescans the moment the Explorer resumes, so a saved edit
  shows immediately. Invalid artifacts now explain themselves where they
  are shown: a health attention item opens the artifact on its Inspection
  tab — whose badge counts the validation diagnostics — and a
  recommendation opens the artifact's Findings tab, which also gains an
  Improvement group from the improve service (one suggestion per missing
  section, with the schema's guidance question as the action; rendered,
  never applied). The command surface deepens: `/schema` lists the
  registered artifact types and `/schema <type>` renders the expected
  structure; the palette offers the last artifacts you opened in this
  repository before you type a character (Enter reopens one); and artifact
  results can be narrowed by type with `f` — all → each type present → all.

- Explorer command palette and settings (v0.8.8): pressing `/` summons a
  command palette — an input with a live, navigable menu below it that lists
  every command when empty, filters and completes them as you type, and
  quick-opens matching artifacts for any other text; `Esc` dismisses it and
  `?` opens help. `/settings` (alias `preferences`) changes everything in
  place — theme with live preview, mascot, animations, artifact grouping,
  and a new default-editor command; terminal editors (vim, nvim, emacs,
  nano, …) now run with the Explorer suspended and resume it on exit.
  Reading is first-class: the Content tab takes the keyboard (`j`/`k`
  scrolls, capped reading width), artifact references inside the rendered
  document open in place so the corpus reads like a wiki, and the Links and
  Findings tabs carry count badges. The mascot animates through per-state
  frame sequences (searching plays while loading; static with animations
  off), the sidebar leads with artifact titles and marks invalid artifacts
  `✗`, keeps its expansion across reloads, and opens the highlighted
  artifact in your editor with `e`; resume restores the last view as well as
  the last artifact, and `Esc` always has somewhere to go (home, at worst).

- Explorer visual overhaul (v0.8.7): one persistent workspace frame replaces
  the screen-per-view shell — a navigation sidebar of type-tagged artifacts
  (`REQ` `ADR` `RMP` `PRM` `DSG`, grouped with counts or flat by preference),
  a context panel whose views swap in place with `Esc` unwinding history, an
  always-visible `/` command bar, and a status line of key chips with the
  health score. Opening an artifact now shows the document itself: a tabbed
  context view with the rendered Markdown first (read-only), then Inspection,
  Links (the relationship traversal moved in here), and Findings. Ships the
  rac-lantern theme — lantern amber on near-black, from the Explorer mascot's
  palette — as the default; the `theme` preference selects any Textual theme,
  and every state keeps its text label under any palette. Key meanings are
  unchanged (`/`, `Enter`, `Esc`, `h`, `r`, `.`, `g`, `e`, `x`, `y`, `q`),
  and the sidebar hides below 80 columns so narrow terminals keep reading
  room.

- Explorer maturity (v0.8.6): workspace continuity — Explorer remembers recently
  opened repositories and the last artifact per repository, and `.` / `/resume`
  reopens it; optional file-based preferences (`theme`, `mascot`, `animations`,
  `artifact_grouping`) under XDG config with `/preferences` to view them; and a
  lantern-carrying mascot in the welcome and empty states. Disabling the mascot
  or animations loses no information (every state carries text), and nothing
  requires login, cloud, or sync.
- Explorer relationship navigation (v0.8.5): `g` from a context view (or
  `/relationships <ref>`) opens a knowledge-graph view — the artifact's
  outgoing relationships, its impact ("what depends on this?"), and its lineage
  (Supersedes / Superseded By). Connected artifacts are selectable, so the graph
  can be traversed one hop at a time. Rendered from Core's relationship model;
  Explorer infers nothing.
- Explorer action workflows (v0.8.4): open the current artifact in your editor
  (`e`, via `$VISUAL`/`$EDITOR`; Explorer never edits — ADR-024); a guided
  `/import <source> [target]` that converts a document through the ingest
  service, previews the Markdown, and writes only on confirmation (never
  overwriting); and `x` to export recommendations to a Markdown file with the
  same preview-and-confirm flow. Conversions report progress.
- Explorer recommendations (v0.8.3): `/recommendations` (or `r` from the health
  view) presents RAC Core's review findings grouped by category (Validation,
  Relationships, Repository Health, Quality), each with its impact, a suggested
  `rac` command, and navigation to the affected artifact. Severities map to
  Critical / Warning / Suggestion. Advisory only — Explorer applies nothing and
  invents no findings.
- Explorer health view (v0.8.2): `h` or `/health` opens a repository health
  screen — Core's score with a text label, the four health areas
  (Completeness, Relationships, Validation, Coverage), and a prioritized
  attention list whose items open the affected artifact's context view.
  Explorer adds no scoring; every value comes from existing Core results.
- Explorer navigation (v0.8.1): browse every artifact grouped by type, open
  any artifact's context view (identity, validation state, completeness,
  relationships, diagnostics), and reach anything through the `/` command
  surface — `open`, `find`, `browse`, `home`, `help`, `quit`, with bare text
  treated as a search using `rac resolve` / `rac find` semantics.
- Explorer first-run onboarding (v0.8.1): launch states derive from
  repository content (existing, empty, or invalid repository); returning
  users skip onboarding via a marker under the XDG state directory — the
  only state Explorer persists.
- `rac explorer` now defaults to the `rac/` root when present (ADR-018),
  falling back to the current directory (v0.8.1).
- `rac explorer [directory]` — interactive terminal Explorer application
  shell (Textual): loads a repository without blocking the interface, shows
  live progress and a repository summary (artifact counts, relationships,
  diagnostics, health score), and recovers from failures in place with
  reload. Ships as the optional `explorer` extra
  (`pip install 'requirements-as-code[explorer]'`); without it the command
  prints an install hint (v0.8.0).
- First-class repository model in the service layer: `load_repository`
  composes index, validation, relationships, and portfolio over a single
  corpus walk into one navigable object (artifacts, relationships with
  resolution outcomes, unified diagnostics) for Explorer and future
  consumers; no CLI or JSON output changes (v0.8.0).
- Operation primitives for long-lived consumers: progress reporting and
  cooperative cancellation across repository loading, validated against
  1000+ artifact corpora (v0.8.0).
- CI battery integrity (v0.7.14): eight test files (~1,300 lines, including
  all coverage for `rac new` and `rac migrate`) were missing from the CI
  battery matrix and never ran; they are restored, and a new guard test
  fails the suite if any test file is ever orphaned again.
- Static quality gates (v0.7.14): ruff (lint + format) and mypy now gate CI;
  pull requests run the gates plus a fast smoke battery (ADR-027 amended),
  while the full battery grid stays merge-gated on `main`. CLI output is
  unchanged — all golden files are byte-identical.
- Test coverage is reported on every CI run (report-only, currently 97%)
  (v0.7.14).

### Changed

- The Explorer's persistent bottom command bar is gone (v0.8.8): `/` summons
  the palette instead, returning two rows to the content. The `/preferences`
  command became `/settings` (the old spelling still routes), status chips
  use one casing everywhere (`✓ Valid`, `! Warning`, `✗ Error`), key hints
  live only in the status-line chips, sidebar rows show artifact titles
  rather than opaque IDs, and the app bar shows the short version with
  `~`-contracted paths.

- Explorer command results, lookups, help, and preferences now render inside
  the context panel instead of a modal overlay, so the layout never jumps
  (v0.8.7). The default Explorer theme preference is `rac-lantern` (was
  `textual-dark`); set `theme` in `$XDG_CONFIG_HOME/rac/explorer.json` to
  keep a different one.

- Repository corpus traversal is defined once in core (`walk_corpus`) and
  consumed by every repository command — behavior and output unchanged
  (v0.7.14).

- `rac migrate metadata <directory>` — migrate existing recognized artifacts
  onto canonical frontmatter identity: idempotent, byte-preserving, with
  `--dry-run` preview; unrecognized documents are reported, never guessed at
  (v0.7.13).

- `rac resolve <ID>` — resolve any artifact ID (canonical or legacy alias) to
  its type, title, and path; duplicates are reported with every path, never
  silently resolved (v0.7.12).
- `rac find <query>` — deterministic artifact search by ID, title, filename,
  or path, with `--type` filtering and JSON output (v0.7.12).
- `rac relationships` human output resolves references to human-friendly
  labels — `Title (type · ID)` — while JSON keeps stored references unchanged
  (v0.7.12).
- `rac index` entries gain an additive `aliases` field: every identifier an
  artifact answers to, canonical first (v0.7.12).

- `rac init` — establish the repository identity namespace
  (`.rac/config.yaml` with a `repository_key`); idempotent, and an
  established key is never silently changed (v0.7.11).
- Hybrid artifact metadata: a leading YAML frontmatter block
  (`schema_version`, `id`, `type`, `relationships`) is parsed, strictly
  schema-validated, and exposed as canonical machine-operational metadata;
  artifacts without frontmatter remain fully supported (v0.7.11).
- System-assigned opaque artifact IDs (e.g. `RAC-01JY4M8X2QZ7`): branch-safe,
  offline, stable across renames, moves, and type changes; `rac new` assigns
  one automatically and `rac index` reports it (v0.7.11).
- Identity validation: conflicting frontmatter/legacy identity and duplicate
  canonical IDs are deterministic errors — RAC never silently picks one
  (v0.7.11).
- Relationship references resolve against legacy identity aliases (`## ID`
  values, filename prefixes, stems), so adopting canonical IDs does not break
  existing human-readable references; RAC's own corpus now carries canonical
  frontmatter identity (v0.7.11).
- `rac new <type> <output-path>` — create a valid artifact from its canonical
  bundled template; deterministic, AI-free, and never overwrites an existing
  file (v0.7.10).
- `rac templates` — list the canonical artifact templates available to
  `rac new`, with `--json` for tools (v0.7.10).
- `rac validate <directory>` — validate every recognized artifact in a tree in
  one command; unrecognized documents are skipped, not failed.
- `rac review <directory>` — full repository review: validation, relationship
  integrity, and completeness as one prioritized worklist (invalid artifacts
  first, then broken relationships, then advisory findings), each finding with
  a concrete suggested action. Exits `1` only on blocking issues.
- CI trust gates: RAC's own `rac/` corpus must pass `rac validate`,
  `rac relationships --validate`, and `rac review` (dogfood battery), and CLI
  output is pinned byte-for-byte by golden tests.
- README build badge, "How RAC earns trust" section, CHANGELOG.md, and
  CONTRIBUTING.md.
- `rac portfolio --json` now lists `artifacts.unknown_paths` (additive).
- `rac index` — flat artifact inventory (id, type, title, path) for tools and
  agents (v0.7.5).

- Documentation restructured around task-focused guides under `docs/`
  (quickstart, CLI reference, artifacts, relationships, repository workflow,
  testing); README simplified to an overview (v0.7.6–v0.7.7).

### Fixed

- RAC's own planning corpus now passes its own validation: one invalid roadmap
  repaired and all cross-artifact references resolve.

## v0.7.3 — 2026-06-06

### Added

- `rac portfolio` — one-screen repository intelligence: counts by type,
  validity, completeness, relationship coverage, attention list, health score.

## v0.7.2 — 2026-06-06

### Added

- `rac relationships --validate` — resolve every cross-artifact reference and
  report broken, ambiguous, self-referencing, or duplicate-identifier findings.

## v0.7.1 — 2026-06-06

### Added

- `rac relationships` — discover and report the explicit references artifacts
  declare to each other.

## v0.7.0 — 2026-06-06

### Added

- Relationship metadata: artifacts can declare `## Related Requirements`,
  `## Related Decisions`, and similar sections that RAC recognizes and counts.

## v0.6.3 — 2026-06-05

### Added

- Design artifact type: validate and inspect product-design documents.

## v0.6.2 — 2026-06-05

### Added

- Prompt artifact type: validate and inspect reusable AI prompts.

## v0.6.1 — 2026-06-05

### Added

- Guided improvement for roadmaps (`rac improve` understands roadmap sections).

## v0.6.0 — 2026-06-05

### Added

- Roadmap artifact type: validate and inspect roadmap documents.

## v0.5.2 — 2026-06-05

### Added

- `rac schema` — show the expected structure of any artifact type, with
  `--template` to emit a starting document.

## v0.5.0 — 2026-06-05

### Added

- `rac improve` — actionable suggestions (and templates) for incomplete
  artifacts.

## v0.4.2 — 2026-06-05

### Added

- Decision (ADR) artifact type with status/category metadata.
- `rac inspect` — classify a document and report its completeness.

## v0.3.1 — 2026-06-04

### Added

- More ingest formats (HTML, PPTX, XLSX).

## v0.3.0 — 2026-06-03

### Added

- `rac ingest` — convert DOCX/PDF documents into RAC-compatible Markdown.

## v0.2.0 — 2026-06-02

### Added

- `rac stats` — summarize a directory of artifacts: counts, quality signals,
  missing recommended sections.

## v0.1.0 – v0.1.3 — 2026-06-01

### Added

- Initial release: `rac validate` and `rac diff` for requirement documents,
  human and `--json` output, stable exit codes (`0` ok, `1` validation failed,
  `2` usage error).
