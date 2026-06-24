---
schema_version: 1
id: RAC-KVSF2ZC1BFC5
type: design
---
# Lore Frontend Optionality

## Status

Proposed

Exploratory — this records the reasoning from a frontend-optionality exploration
so it lives in the corpus, not a tool's scratch space (ADR-047). It is not an
accepted build. It surveys the option space, recommends a priority order, and
leaves the editor question recorded as a weighed conclusion rather than a closed
decision.

It was subsequently extended after a red-team with **Thread E — authoring /
capture**, which reframes the editor question as a *capture-and-structure*
problem for non-technical authors and reorders the priorities so capture ranks
at the top, ahead of grounding.

## Context

"What should Lore's frontend be?" is the wrong question, because Lore is not
greenfield. It already ships five human- and agent-facing surfaces:

- the `rac` CLI — the canonical surface (ADR-005);
- the read-only stdio MCP server `lore` — five deterministic tools for agents
  (ADR-029, ADR-030);
- a Textual TUI Explorer — keyboard-first terminal browsing (ADR-028);
- `rac-localview` — a single-file React Portal (`rac export --html`) with a
  force-directed graph view; and
- the `lore-vscode` extension — in-editor validation, navigation, and an
  embedded graph webview (the v0.21.x editor series).

So the real question is **optionality**: which *thin shell over the stable
contract* earns further investment, and what — if anything — Lore should borrow
from the current crop of local-first and agentic tools. This design was prompted
by six such projects:

- **Pake** (github.com/tw93/pake) — a Tauri/Rust wrapper that turns a webpage
  into a small native desktop app.
- **Flashtype** (github.com/opral/flashtype.ai) — an Electron markdown editor
  for Claude/Codex whose thesis is "Agents edit. You review the diff. Nothing
  lands without you," built on lix.
- **ZenNotes** (github.com/ZenNotes/zennotes) — a local-first markdown vault
  (Electron + CodeMirror 6, optional Go backend) that ships its own MCP server.
- **lix** (github.com/opral/lix) — an embeddable, in-process change-control
  engine for any file format, with entity-level semantic diffs and a SQL query
  layer.
- **Orca** (github.com/stablyai/orca) and **Fusion** (github.com/Runfusion/Fusion)
  — agent-orchestration environments (ADEs) that run many coding agents in
  isolated worktrees.

A five-angle research pass (with sources, contested claims flagged inline) backs
the synthesis below. The unifying finding: **Lore's frontend strategy is "thin
shells over a stable contract, meet users where they already are" — not owning
an app surface.** Every thread lands back on the same recorded decisions —
non-Python clients are thin clients over the published contract (ADR-063), RAC is
not a content store (ADR-024), and the trust boundary is human PR review
(ADR-065).

## User Need

Three audiences sit behind "frontend," and they want different things:

- **Agents** grounding a task need *authority* — the exact, current wording of
  what the team has decided, addressable by ID and auditable. This is what the
  `lore` MCP server already serves.
- **Humans** reading recorded knowledge need *navigation* — to browse, search,
  and follow relationships without a build step or a server. This is what the
  Explorer and `rac-localview` already serve.
- **Maintainers** authoring artifacts need a *low-friction edit→validate→commit
  loop* — without Lore having to become the editor they live in.
- **Non-technical authors** — the product managers who *own the source
  knowledge* but work in Word, Google Docs, Confluence, and Jira — need a way to
  get knowledge into the corpus *at all*, without learning git, markdown, or an
  IDE. The original draft under-served this audience; it is the subject of
  Thread E.

The need this design weighs is **where the next unit of frontend effort buys the
most**, given those three audiences and Lore's recorded identity.

## Design

The six tools cluster into four threads (A–D). A red-team of this design then
surfaced a fifth — **Thread E, authoring / capture** — that the tool survey had
hidden behind Thread B; it is recorded after the four and ranks *first* in the
revised priority order. Each thread maps onto Lore differently.

### Thread D — Grounding inside agent IDEs *(the recommendation)*

The highest-leverage "frontend" for Lore is not a UI at all — it is being the
**cited authority of record inside the agent IDEs people already use**.

- MCP reached production scale in 2026 (on the order of 10k+ public servers; a
  cross-vendor standard across Claude Code, Cursor, Codex, Copilot, Zed,
  Windsurf). A single stdio server registers once and plugs into all of them at
  ~child-process latency — which is exactly the shape `rac mcp` already has.
- Claude Code's project-scoped `.mcp.json` makes "commit a knowledge MCP server
  to the repo, shared across the team" a *first-class, already-supported*
  pattern. Orca (stablyai/orca) exposes MCP config as a first-class extension
  surface with per-project/session scoped leases — a natural host. Fusion's MCP
  support is undocumented in its README (plausible but unverified).
- The "fuzzy find → deterministic verify" loop Lore already designed for
  (`lore-supermemory-interplay`) is now a *named, published* architecture
  pattern (e.g. REGAL's non-interference: "interpretation may depend on computed
  artifacts, but computation must not depend on interpretation").
- The defensibility argument: citation hallucination runs roughly 14–95% across
  models; grounding measurably cuts errors but never to zero, so an
  ID-addressable, validated authority an agent must resolve against is a genuine
  trust differentiator. *(Caveat: "authority of record = durable moat" is a
  forward-looking bet, not a market-proven position.)*

This thread is distribution and positioning of a surface Lore already ships, not
a new build. That is precisely why it ranks first.

### Thread B — Authoring / editing surface *(stay bring-your-own-editor)*

The editor question was held open going in; the evidence resolves it to a clear
**weighed recommendation: do not build a homegrown editor.**

- A production text/rich-text editor is a perpetual sink — mature editors
  represent tens to hundreds of person-years, and maintenance cost meets or
  exceeds build cost indefinitely. The decisive cost is opportunity cost:
  engineering spent on text entry is not spent on Lore's differentiator
  (classification, validation, relationships, grounding).
- The instructive counterexample reinforces the same point. GitHub — whose
  identity *is* the git repo — added in-browser editing by **embedding VS Code**
  (`github.dev`), not by building an editor. Owning the authoring loop can be
  right; building the editor yourself is not.
- The convergent low-regret pattern is **delegate-and-validate**: edit in the
  user's own tool (`$EDITOR`/VS Code), validate on save via a file-watcher, make
  commit easy. Lore already does this — the extension validates in-editor and the
  Explorer opens `$EDITOR` ("Explorer is not an editor",
  `explorer-editor-integrations`).
- The genuinely transferable idea from Flashtype is *not* "an editor" but the
  **review-the-diff-before-it-lands ritual** — which Lore already gets for free
  from git PRs (ADR-065). Plain-markdown portability ("file over app") is a
  load-bearing trust argument that an in-app editor monopoly would *undercut*.

If Lore ever invests in authoring, it should be *flow enrichment* —
richer templates (`rac new`), validate-on-save, and surfacing the
diff/validation at commit time — never a homegrown editor competing with the
one the maintainer already loves.

### Thread A — Desktop wrapper (Pake / Tauri) *(optional, low priority)*

- Tauri v2 wraps an existing React SPA close to drop-in (point `frontendDist` at
  the build output; a static viewer needs no React changes), and ships far
  smaller than Electron. The headline "≈20× smaller" is trivial-wrapper
  marketing, though — the only first-party *production*-migration figure found was
  roughly 3×.
- The real risk is the Linux webview: **WebKitGTK is maintainer-acknowledged
  unstable** ("getting worse each release"), and macOS WebKit is pinned to the OS
  version. For a viewer expected to run across arbitrary distros this is the
  exposure. Pake itself is a quick-wrapper, not a product framework — a
  first-party product should use **Tauri v2 directly**.
- The marginal value of a desktop shell over `rac export --html` (which already
  opens in any browser) is modest. The one *compelling* variant is a **live**
  local app — watch the repo, re-export on change — turning a static export into
  a living viewer. Only that variant earns a release slot.

### Thread C — lix change-control model *(inspiration, not dependency)*

- lix is genuinely interesting: in-process change control for *any* format with
  entity-level semantic diffs and a SQL history layer. But it is pre-1.0 (v0.7),
  its **markdown plugin is beta**, its shipping SDK is JavaScript (the Rust core
  is still landing), and visible production usage is essentially Opral's own apps
  (Flashtype, inlang) — no clear third-party shipper.
- For an **already git-native, markdown-only, PR-reviewed** corpus, lix largely
  *duplicates* git. Its net-new value appears only for non-line-diffable formats
  (DOCX/XLSX/PDF), sub-file semantic diff/merge, or embedded in-app review where
  shelling out to git + GitHub is not viable. Adopting it would cut against
  recency-from-git (ADR-045), file-first pipelines (ADR-011), and PR-as-trust-
  boundary (ADR-065).
- Record it as a **watch** item. The transferable concept — review at the level
  of *meaning* — is real, but Lore's entities are artifacts and its review
  surface is the pull request.

### Thread E — Authoring / capture *(the cold-start precondition — added on red-team)*

Threads A–D were drafted as if the corpus already exists; a red-team exposed
that assumption. **Grounding (D) is leverage on an asset that has to be authored
first** — an agent cannot ground against a decision nobody captured — and the
people who own the source knowledge (product managers) live in Word, Docs,
Confluence, and Jira, not in an IDE or an agent harness. The original draft
under-weighted this by collapsing authoring into Thread B and then correctly
dismissing the *wrong* UI: the barrier is **not** *editing markdown* (an editor
question, answered "don't build one"), it is **capture-and-structure** — getting
unstructured knowledge out of a PM's head and tools into a typed, validated
artifact. Capture is therefore reframed as a first-class thread and ranked above
grounding, because **grounding's authority-of-record moat is hostage to how
complete and current the corpus is**: a thin or stale record grounds agents on
confidently-wrong guidance, which is worse than no record.

The shape that stays inside the recorded decisions:

> **Capture** (where the author already is) → **Structure** (a template-driven
> form or an agent interview, with any AI *outside* the deterministic core) →
> **Save** (a commit) → **Promote** (the PR review boundary into the trusted
> corpus).

- **The interpretation step lives outside core (ADR-002, ADR-067).** Format
  conversion is deterministic (markitdown, ADR-072); turning *freeform prose*
  into a *typed, sectioned, linked* artifact requires classification, which the
  deterministic core must not perform. The AI-assisted draft is a companion —
  the same one-way pattern as `lore-supermemory-interplay`, never engine code.
- **Save is a commit; only promotion to the trusted corpus is a PR (refines
  ADR-065).** ADR-065 places the trust boundary at human PR review *into the
  agent-grounding corpus*, and explicitly treats "unreviewed branches" and
  "machine-ingested documents not yet merged" as legitimate — merely *untrusted*
  — states. So a capture surface may **commit drafts freely** to a working branch
  or a `drafts/` area with no PR ceremony; the PR gate is reserved for the moment
  a draft is *promoted* into the reviewed corpus an agent grounds against. This
  keeps authoring low-friction without weakening the boundary.
- **Capture knowledge, not work (ADR-017).** A connector extracts the durable
  decision or long-lived requirement (ADR-020) from a ticket or doc; it never
  mirrors owners, sprints, or workflow state.

Four implementation options, cheapest first:

1. **Agent-interview authoring** *(ship first; near-zero build)* — a skill/prompt
   ("record a decision") that interviews the author in plain language, dedupes
   via `search_artifacts`, drafts against the template (ADR-021), and commits the
   draft or opens the promotion PR. Reuses `rac-artifacts` / `rac-import`,
   templates, and the `lore` MCP. The author talks, reviews, and approves —
   never touching markdown or git. Compounds with Thread D (the same surface now
   also *seeds* the corpus).
2. **Self-serve ingestion** *(meet them in Word)* — make `rac ingest`
   self-service via an `/intake` GitHub Action (drop a `.docx` / `.pdf` →
   markitdown → an AI classify-and-structure companion → a draft commit /
   proposal). Reuses the `rac-ingest` skill and the already-designed
   `explorer-import-workflow` (detect → review → confirm).
3. **Guided web capture** *(the real non-technical front door; bigger build)* —
   extend `rac-localview` from viewer to viewer + capture: pick a type, fill a
   **template-driven form** (the form *is* the template, ADR-021 — not a freeform
   editor, which sidesteps the person-years cost), preview, and commit / propose
   via the GitHub API. The GitBook middle path the research endorsed; git stays
   the source of truth (ADR-024).
4. **Tracker connectors** *(defer; ADR-gated)* — one-way knowledge extraction
   from Jira / Linear / Confluence in `lore-connectors`, extracting durable
   knowledge only. This is the easiest place to breach ADR-017, so it requires an
   explicit new ADR reaffirming the knowledge-not-work boundary before it is
   built.

### Recommended priority order

1. **Authoring / capture (E)** — the cold-start precondition. Start with the
   near-zero-build agent-interview skill and the `/intake` action. Without it the
   corpus stays thin and there is little for Thread D to serve.
2. **Grounding distribution (D)** — highest leverage *once there is a corpus to
   ground against*; near-zero build, reinforces identity. E and D compound — the
   same surface that grounds can also capture.
3. **Authoring-flow enrichment, not an editor (B)** — for IDE-resident
   maintainers, stay BYO-editor; if anything, templates + validate-on-save +
   diff-at-commit.
4. **Live desktop wrapper (A)** — optional; Tauri v2 directly, repo-watching
   variant only, Linux as the risk surface.
5. **lix (C)** — inspiration / watch only; do not adopt.

## Constraints

- **Thin clients over the contract (ADR-063).** Any frontend consumes the
  published CLI/JSON/MCP surfaces; none reimplements the engine. This is why
  `rac-localview` and the extension are viable and why a homegrown editor is not.
- **RAC is not a content store (ADR-024).** Frontends view, navigate, ground, and
  link back to artifacts on disk; they do not become the canonical home of
  content.
- **The trust boundary is human PR review *into the corpus* (ADR-065) — but a
  save is a commit, not a PR.** ADR-065 names "unreviewed branches" and
  not-yet-merged drafts as legitimate, untrusted states, so a capture surface may
  commit drafts freely; the PR gate applies only to *promoting* a draft into the
  reviewed corpus an agent grounds against. The "review the diff before it lands"
  ritual belongs to that promotion PR, not to an in-app editor's own approval
  flow.
- **Recency and history come from git (ADR-045), pipelines are file-first
  (ADR-011).** A second change-control engine (lix) is redundant for markdown and
  conflicts with these.
- **The MCP surface is read-only and tools-only (ADR-029, ADR-030).** The
  grounding thread is distribution of that surface, not new write capability.
- **Brand and topology (ADR-068).** Installed surfaces are `lore-*`; the engine
  and build-coupled internals are `rac-*`. A desktop wrapper or distribution
  bundle is a `lore-*` product, not engine code.
- **The export contract grows only additively (ADR-007).** Wrappers and grounding
  bundles depend on the stable export shape, never on private internals.
- **No homegrown editor.** Treated here as a strong recommendation (see Status),
  grounded in build/maintenance cost and the git-source-of-truth identity — not
  an absolute prohibition.

## Rationale

Three independent lines of reasoning point the same way.

First, **leverage-per-build**. Thread D reuses a surface Lore already ships and
only needs distribution and positioning; it is the cheapest path to the largest
strategic payoff. Threads A and C are net-new builds whose value is conditional;
Thread B's most valuable form is *not building* the obvious thing.

Second, **identity coherence**. Lore's whole differentiator is a deterministic,
auditable, git-backed system of record. A surface that strengthens that — being
the cited authority an agent verifies against — compounds the identity. A surface
that competes with it — owning the editor, or running a second change-control
engine — dilutes it. For a tool whose source of truth lives in the user's git
repo, owning the editor is strategically incoherent unless the editor strictly
improves the git round-trip, which delegate-and-validate already achieves.

Third, **cost honesty**. The editor question feels like a product gap, but the
evidence is lopsided: editors are among the most expensive surfaces to build and
maintain, and even GitHub chose to embed rather than build. The friction the
editor question is really about — the edit→validate round-trip — is better solved
at the access layer (validate where the user already works) than by adding a new
surface the user has to move into.

The trade-off accepted: Lore declines to own the most visible, demo-friendly
surface (a polished standalone app) in exchange for keeping its effort on the
contract, the validation, and the grounding that actually differentiate it.

## Alternatives

- **Build a homegrown markdown editor (Flashtype/ZenNotes shape) — rejected.**
  Perpetual maintenance cost, opportunity cost against the real differentiator,
  and a direct tension with "file over app" portability and ADR-024. The
  delegate-and-validate pattern captures the benefit (low edit→validate friction)
  without the cost.
- **Adopt lix as a change-control layer — rejected.** For markdown in a git repo
  reviewed by PR, lix duplicates git while adding a pre-1.0 dependency with a beta
  markdown plugin; it conflicts with ADR-045, ADR-011, and ADR-065. Kept as a
  watch item for a future, non-markdown, in-app-review need.
- **Pake quick-wrap of the Portal — rejected as a product path.** Fine as a
  personal convenience, but for a first-party surface use Tauri v2 directly; Pake
  is a wrapper, not a maintainable product framework.
- **A static-only desktop shell — rejected.** It adds little over
  `rac export --html` opening in a browser. Only a *live*, repo-watching variant
  would justify the surface.
- **Treat authoring as an editor problem (the original draft's framing) —
  rejected on red-team.** Asking "should Lore build an editor?" answers the wrong
  question and dismisses the wrong UI; the non-technical author's barrier is
  capture-and-structure, not text entry. Thread E replaces this framing.
- **Do nothing (the honest baseline).** Lore's five surfaces already cover the
  agent, human-reader, and IDE-maintainer audiences. Acceptable *only* if the
  corpus is already being authored — but the red-team's point is that the
  non-technical author is locked out today, so for a cold-start corpus "do
  nothing" silently bets the corpus stays the domain of a few technical
  maintainers.

## Accessibility

- **Provenance legibility (grounding surface).** As with
  `lore-supermemory-interplay`, results an agent or operator consumes must never
  blur authority: Lore's verbatim, ID-addressed, lifecycle-stamped text stays
  distinct from any associative or model-rewritten copy.
- **Local-graph-first framing (viewer).** Research on full force-directed graphs
  is consistent: past roughly 200 nodes a global graph becomes a "hairball" that
  is pleasant but navigationally weak. *(Contested — defenders value it for small
  vaults and cluster-spotting.)* The defensible, accessible value is the **local
  graph** (a node's neighborhood) plus orphan / unresolved-target detection.
  `rac-localview` should lead with local views, not the global hairball.
- **Keyboard-first parity.** Any new surface should match the Explorer's
  keyboard-first conventions (ADR-028) rather than assume a pointer.

## Style Guidance

- Name installed surfaces under the `lore-*` brand and keep engine/build-coupled
  internals `rac-*` (ADR-068); a distribution bundle or desktop wrapper is a
  Lore-brand product, not engine code.
- Vocabulary keeps the layers honest: Lore *grounds* and is *authoritative*;
  fuzzy or semantic companions *recall* and are *associative*. A viewer *displays*
  artifacts; it does not own them.
- Wrappers and grounding bundles depend only on the published, additively-growing
  contract (ADR-007) — `id`, `type`, `status`, and the documented export shape
  (`corpus-export-shape-contract`) — never on private internals.
- Where a claim is load-bearing, cite the source in prose (as here) and carry its
  caveat; prefer an honest "contested / forward-looking" flag over a promotional
  certainty.

## Open Questions

- Does the **live desktop wrapper** (Thread A) earn a release slot at all, or is
  "open the HTML export in a browser" the right permanent answer?
- What is the **minimal `.mcp.json` distribution story** per host — Claude Code
  (committed project scope), Cursor, Codex, Orca — and should Lore ship a
  documented snippet (or a `rac mcp init` helper) for each?
- If authoring-flow enrichment is ever pursued, what is its exact scope —
  templates only, or validate-on-save plus a commit-time diff/validation surface —
  and where does it live (`lore-*` surface vs engine affordance)?
- Should Thread D's distribution work be promoted to a non-versioned
  `rac/roadmaps/future/` item once there is evidence agents are under-grounded for
  lack of easy registration?
- For **capture (Thread E)**, where do drafts live before promotion — a
  `drafts/` path, an `/intake` branch, or a fork — and what is the lightest
  review that still satisfies ADR-065's boundary for a solo maintainer versus a
  team?
- How good must the freeform→typed **classify pass** be before self-serve
  ingestion (Options 2–3) is trustworthy enough to expose to a non-technical
  author, and how are its mistakes surfaced for human review rather than hidden?
- Does Thread E warrant its own dedicated design and a future roadmap item, or
  does recording it here as the top-priority thread suffice until a build is
  scheduled?

## Related Decisions

- ADR-002
- ADR-005
- ADR-006
- ADR-007
- ADR-011
- ADR-017
- ADR-020
- ADR-021
- ADR-024
- ADR-028
- ADR-029
- ADR-030
- ADR-044
- ADR-045
- ADR-063
- ADR-065
- ADR-067
- ADR-068
- ADR-072

## Related Roadmaps

- lore-supermemory-grounding
- repo-extraction-programme
