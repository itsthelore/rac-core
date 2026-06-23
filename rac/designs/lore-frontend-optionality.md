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

The need this design weighs is **where the next unit of frontend effort buys the
most**, given those three audiences and Lore's recorded identity.

## Design

The six tools cluster into four threads. Each maps onto Lore differently; the
recommended priority order follows.

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

### Recommended priority order

1. **Grounding distribution (D)** — highest leverage, near-zero build, reinforces
   identity. The recommendation.
2. **Authoring-flow enrichment, not an editor (B)** — stay BYO-editor; if
   anything, invest in templates + validate-on-save + diff-at-commit.
3. **Live desktop wrapper (A)** — optional; Tauri v2 directly, repo-watching
   variant only, Linux as the risk surface.
4. **lix (C)** — inspiration / watch only; do not adopt.

## Constraints

- **Thin clients over the contract (ADR-063).** Any frontend consumes the
  published CLI/JSON/MCP surfaces; none reimplements the engine. This is why
  `rac-localview` and the extension are viable and why a homegrown editor is not.
- **RAC is not a content store (ADR-024).** Frontends view, navigate, ground, and
  link back to artifacts on disk; they do not become the canonical home of
  content.
- **The trust boundary is human PR review (ADR-065).** The "review the diff
  before it lands" ritual belongs to the git PR, not to an in-app editor's own
  approval flow.
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
- **Do nothing (the honest baseline).** Lore's five surfaces already cover the
  three audiences. Acceptable until the grounding-distribution story (Thread D)
  is worth scheduling — which is the signal that would open a future roadmap
  item, not this design.

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

## Related Decisions

- ADR-005
- ADR-007
- ADR-011
- ADR-024
- ADR-028
- ADR-029
- ADR-030
- ADR-045
- ADR-063
- ADR-065
- ADR-067
- ADR-068

## Related Roadmaps

- lore-supermemory-grounding
- repo-extraction-programme
