---
schema_version: 1
id: RAC-KVSM9E6BNWNH
type: design
---
# Lore Capture Surfaces

## Status

Proposed

Exploratory — this records the reasoning from a capture-interface exploration so
it lives in the corpus, not a tool's scratch space (ADR-047). It is not an
accepted build. It develops Thread E (authoring / capture) of
`lore-frontend-optionality` into its own design: how a non-technical author gets
recorded knowledge *into* the corpus, and which host surfaces are worth building.

## Context

`lore-frontend-optionality` established that Lore's biggest gap is **authoring**:
grounding (serving recorded knowledge to agents) is leverage on an asset that has
to be authored first, and the people who own the source knowledge — product
managers — live in Word, Docs, Confluence, and Jira, not in an IDE or an agent
harness. That design reframed the barrier as **capture-and-structure**, not
*editing*, and sketched four capture options. This design takes the first of
them — an agent-interview capture flow — and works out the interface.

The organizing insight comes from grounding the question against the code rather
than the tool landscape: **the skill is the brain; the host is the interface.**
A capture skill modelled on `rac-import` (`src/rac/skills/rac-import/SKILL.md`)
is host-agnostic. Its loop is already most of what is needed:

> interview the author → draft against the real schema (`rac schema <type>`) →
> the human ratifies type, title, and each relationship → `rac new` mints the
> opaque id and scaffolds the file → `rac validate` is the deterministic close.

`rac-import` does exactly this for an existing *document*; capture does it for a
*conversation*. Crucially, the MCP server exposes five read-only tools and the
engine contains **no LLM client at all** (there is no model call anywhere under
`src/rac/`). So the language model that runs the interview never lives in the
engine — it lives in whatever **host** runs the agent. "What interface should
capture take?" therefore resolves to: **what hosts run the capture agent for
people who do not live in a coding harness?** Each host is a thin client
(ADR-063) over one shared capture core, and each emits to git; none stores
content (ADR-024) and none is an editor.

This design was prompted by a survey of how always-available capture tools work —
the macOS menu-bar "click the icon → modal" pattern (ChatGPT desktop, Raycast),
Slack's assistant and modal surfaces, the bring-your-own-LLM gateway model
(LiteLLM, OpenRouter), and quick-capture UX (Drafts, Linear, Todoist, Obsidian
QuickAdd). A seven-angle research pass (primary sources, contested claims flagged
inline) backs the trade-offs below.

## User Need

The author this design serves is the one Lore currently locks out: a **product
manager or domain owner who has a decision or requirement in their head** (or in
a Word doc, or a Slack thread) and **no way to get it into the corpus without
learning git, Markdown, or an IDE.** They need to:

- record the durable knowledge — a decision and its rationale, a long-lived
  requirement (ADR-020) — not a work item (ADR-017);
- do it in a surface they already have open, with the fewest possible steps;
- trust that nothing lands in the team's record without review.

A second audience is the **larger engineering team** that will host any such
surface: they need it to route through their own model gateway for cost, audit,
and data-residency control, and to respect the existing git/PR trust boundary.

## Design

### The capture core (the `rac-capture` skill)

A new skill — `rac-capture` — is the interview variant of `rac-import`: same
hard constraints (the schema is not the agent's to invent; human review of type,
title, and relationships is mandatory before any write; close on `rac validate`;
no invention), with the *source* being a short interview instead of a supplied
document. The research on quick-capture converges on a clear shape the interview
should follow:

- **Capture the raw intent first, ask questions second.** Every leading tool
  lets the user dump unstructured text instantly (Drafts' "where text starts";
  Linear/Todoist/Things default to an inbox) before any structuring. The
  interview must never gate capture behind its questions.
- **Pre-fill answers from the dump; ask only what cannot be inferred or safely
  defaulted.** Linear requires only a title and status and defaults everything
  else; the interview's two-to-four questions should be confirmations, not blank
  prompts. *(The specific "2–4" count and the circulated conversational-form
  completion-lift figures are weakly-sourced heuristics, not research constants —
  treat the direction as sound and the numbers as advisory.)*
- **Defer structure, then draft it.** Capture now, ask a few questions, produce
  the structured artifact, leave it editable — mirroring progressive disclosure
  and Linear's grace window.

The single biggest failure mode is the interview re-introducing the up-front
decisions that capture is supposed to defer; the mitigation is to capture free
text first, pre-fill proposed answers, and allow skip/Enter-through.

### Save is a commit; promotion is a PR

Following `lore-frontend-optionality`'s refinement of ADR-065: a capture surface
**commits a draft freely** (an unreviewed branch or a `drafts/` area is, in
ADR-065's own words, a legitimate *untrusted* state), and the **pull request is
reserved for promoting** that draft into the reviewed corpus an agent grounds
against. Capture stays low-friction without weakening the trust boundary.

### The two-gate write model (every host)

"Approval" in a capture flow is **two distinct gates, on two different actors** —
a distinction that holds for *every* writing host, not just Slack. **Gate 1** is
the author confirming, in the host, *"you captured what I meant"* — a
**data-quality / fidelity** check that is **not a trust boundary** (it is
self-approval, which separation-of-duties and four-eyes guidance — NIST AC-5,
OWASP, SLSA two-party review — classify as the absence of a control). **Gate 2**
is an **independent** maintainer reviewing and merging the pull request — the
actual trust boundary (ADR-065), enforced by required reviews + a "someone other
than the author" rule. The corollary binds every host: a writer host or bot only
ever **proposes** (opens the draft PR) and **never holds approval or merge power**
— otherwise the second gate collapses back into self-approval. The Slack host
works this out end to end in `lore-slack-capture-flow`.

### Four hosts over the one core

Each host is a thin adapter that runs the capture agent and drives the `rac` CLI;
they differ only in reach, friction, build cost, and where the model call lives.

**Host A — existing agent harnesses (Claude Desktop / Claude Code / Cursor).**
Near-zero build: the skill plus the existing MCP server already work here. It
reaches engineers, *not* PMs, and the harness owns the model (bring-your-own-key
is the harness's concern). This is the cheapest test of the whole loop and is the
shared core every other host wraps, so it ships first.

**Host B — a cross-platform desktop overlay** (the "little app alongside any
screen"). A global hotkey summons a small modal that runs the interview and then
commits a file / opens a PR. The decisive scoping insight: **capture needs
*summon-a-modal*, not *watch-the-screen*.** A plain global-hotkey-plus-modal
avoids the entire macOS permission gauntlet the research surfaced — Accessibility
reads (which can capture passwords with *no* on-screen recording indicator) and
Screen Recording (which on macOS Sequoia re-prompts roughly monthly). Reading
on-screen context, à la ChatGPT "Work with Apps" or Cluely, is a *later,
permission-gated* enhancement, never the MVP.

Stack: **Tauri v2**, not native Swift/AppKit. The MVP can ship **macOS-first**
(`NSStatusItem` menu-bar item, `NSPanel` non-activating floating panel,
`collectionBehavior` to cross Spaces), but Tauri keeps **Windows** a cheap
fast-follow (tray via `Shell_NotifyIcon`, global hotkey via `RegisterHotKey`,
always-on-top via `WS_EX_TOPMOST`) on one codebase, where native AppKit would
lock the surface to macOS forever. Because Tauri renders in the OS webview
(`WKWebView` on macOS, **WebView2 / Edge Chromium on Windows**), a Windows build
carries a **WebView2 runtime dependency** — evergreen on current Windows 11, but
the installer should bootstrap it for older targets. **Linux is deferred**: on
Wayland, global hotkeys, always-on-top, and tray icons are all portal-mediated
with uneven compositor support (KDE better, GNOME gaps), so "always-available"
there is a per-compositor gamble rather than a guarantee. The distribution tax is
real on both shipping platforms — Developer ID signing + notarization on macOS,
and **Authenticode** signing on Windows, where unsigned or low-reputation
binaries trip **SmartScreen** warnings; the current low-friction path is a cloud
signing service such as **Azure Trusted Signing**, the modern alternative to
buying a traditional EV certificate. The overlay is **where bring-your-own-gateway
config lives**, because the app itself makes the model call.

**Host C — a Slack bot.** Reaches the **whole team, including PMs, with no
per-user install**, and captures decisions *where they are actually made* — the
direct answer to "decisions happen in Slack and never get recorded." A message
shortcut ("Save as decision") or slash command starts the flow. Two Slack
constraints shape it: Block Kit **modals cap at 100 blocks and a three-view
stack**, so a genuine multi-turn interview belongs in the **assistant-thread
surface** (`assistant.threads.*`, with native streaming), not a modal; and the
**three-second acknowledgement rule** forces a quick-ack-then-async-follow-up
architecture for any model call. It commits through a **GitHub App → PR**, which
suits the async, review-first flow. The costs are a hosted, multi-tenant network
service (a public endpoint or Socket Mode, per-workspace OAuth token storage,
request-signature verification) and a **governance boundary crossing**: piping
Slack thread content to an external model triggers app-approval, data-residency,
and (on Enterprise Grid) admin-policy review. That crossing is precisely why
bring-your-own-gateway is *mandatory* here, not optional. *(Slack's AI/assistant
APIs are fast-moving — the assistant surface, native streaming, and a scope
change for `assistant.threads.setStatus` all shipped or shifted across 2025–2026
— so this host carries the most version risk.)*

**Host D — a web modal** (extending `rac-localview`). Reuses the existing React
app: pick a type, fill a template-driven form *or* paste prose for an
AI-assisted draft, preview, and open a PR via the GitHub API — the GitBook middle
path, git staying the source of truth. It reaches anyone with a link and no
install (good for PMs), but it is "another tab": it lacks the overlay's
always-available friction win and Slack's team-native reach.

### The bring-your-own-gateway seam (the LiteLLM answer)

For every host that itself calls the model (B, C, D), "support the team's LiteLLM
key" costs almost nothing: expose a configurable **OpenAI-compatible `base_url` +
API key + model name (+ optional headers)**, source the key from an environment
variable or OS secret store, and emit **no prompt-content telemetry**. That one
seam is the de-facto industry convention — LiteLLM, OpenRouter, Azure OpenAI,
Vertex, Ollama, and vLLM all expose it, and Cursor, Continue, Aider, Cline, and
Zed all consume it. For an engineering team it unlocks data-residency, cost
control, and audit; for the Slack host it is what makes the model boundary
crossing acceptable to admins. In Host A it is free (the harness owns the model).
This is baked in from the first version of any host, not retrofitted.

### Recommended sequencing

1. **Host A — the `rac-capture` skill — now.** Near-zero build, validates the
   loop in today's harnesses, seeds the corpus, and is the shared core B/C/D
   wrap.
2. **The favoured pair, B + C, which are complementary across platforms.** The
   macOS-first overlay serves desktop users where they work; the Slack bot serves
   everyone else — including Windows users — with no install. They are not
   either/or so much as two reach surfaces over the same core.
3. **Host D (web modal)** as the broad-but-shallow fallback, reusing
   `rac-localview`, if a no-install browser surface is wanted.

All three reach surfaces are recorded as open options; B + C are the favoured
direction, not a closed decision.

## Constraints

- **AI lives in the host, never the engine (ADR-002, ADR-067).** The interview
  model, like every other model in Lore's orbit, runs in the harness, the
  overlay, or the bot — never in `rac-core`. The engine stays deterministic and
  AI-optional.
- **Thin clients over the contract (ADR-063).** Every host drives the published
  `rac` CLI and consumes the stable contract; none reimplements classification or
  validation.
- **Capture knowledge, not work (ADR-017).** A capture flow records decisions and
  long-lived requirements (ADR-020); it must not mirror tickets, owners, sprints,
  or workflow state, even when the source is a Jira-shaped conversation.
- **Templates are the creation contract (ADR-021).** Drafts are shaped by the
  real schema read at runtime (`rac schema`), never by fields the host invents;
  ingestion-over-rewrite (ADR-006) still applies when the source is a document.
- **Save is a commit; promotion into the trusted corpus is a PR (ADR-065).** A
  host commits drafts freely but never lets unreviewed content enter the
  agent-grounding corpus except through human PR review.
- **Two gates, and the writer only proposes.** The author's in-host confirmation
  is a fidelity gate, not a trust boundary; an *independent* maintainer's PR merge
  is the trust boundary (ADR-065). A writer host or bot opens the draft PR and
  must never hold approval or merge power.
- **Not a content store (ADR-024).** A host emits artifacts to git and stores no
  canonical content of its own.
- **Installed surfaces are `lore-*` products (ADR-068).** The overlay, the bot,
  and the web capture surface are `lore-*` brand, not `rac-*` engine code.
- **Bring-your-own-gateway carries no prompt telemetry.** Any host making a model
  call exposes a configurable OpenAI-compatible endpoint and must not exfiltrate
  prompt content, consistent with the local/opt-in telemetry posture (ADR-040,
  ADR-041).

## Rationale

The skill-is-brain / host-is-interface split is what makes the whole space
tractable: it concentrates all the durable value (classification against the real
schema, validation, the human-ratify gate, the commit/PR discipline) in one
host-agnostic core, and reduces each surface to a thin adapter. That is why
building three reach surfaces is not three times the work — they share the core
and differ only in how they collect the interview and where they post the result.

The summon-a-modal-not-watch-the-screen decision is the highest-leverage scoping
call. The instinct to build a Cluely-style always-watching overlay would saddle
the product with the macOS TCC permission gauntlet, a standing privacy liability
(Accessibility reads have no recording indicator and can capture secrets visible
on screen), and a recurring-reprompt UX tax — all for context a knowledge-capture
tool does not need. A global hotkey and a focused modal deliver the "alongside
any screen" feel with none of that.

Choosing Tauri v2 over native AppKit trades a small amount of per-platform polish
for keeping Windows a cheap fast-follow on one codebase. Since the favoured B + C
pair already covers Windows users through Slack, the overlay can ship macOS-first
without stranding anyone — but the stack choice keeps the door open rather than
nailing it shut.

The bring-your-own-gateway seam is near-free and does double duty: it is the
engineering-team governance story *and* the mitigation for Slack's model boundary
crossing. Exposing one configurable endpoint is cheaper than any bespoke
integration and is what every comparable dev tool already does.

The trade-off accepted: capture surfaces are real `lore-*` products with real
build and (for the bot) operational cost, which Lore takes on because the
alternative — leaving authoring to a handful of technical maintainers — caps the
corpus and, with it, the value of everything downstream (grounding included).

## Alternatives

- **Build an editor instead of a capture flow — rejected.** This repeats the
  framing `lore-frontend-optionality` already rejected: the barrier is
  capture-and-structure, not text entry, and a homegrown editor is a perpetual
  maintenance sink that fights "file over app" portability. A capture surface
  produces a draft and a PR; it never becomes the editor the author lives in.
- **An always-watching, screen-reading overlay (Cluely-shaped) — rejected for
  the MVP.** It buys context the capture use case does not need at the price of
  the full TCC permission surface and a standing privacy liability. On-screen
  context is a later, explicitly permission-gated option, not the core.
- **Native Swift/AppKit overlay — rejected.** It locks the surface to macOS,
  whereas Tauri keeps Windows a cheap fast-follow on a single codebase for a
  modest polish cost.
- **MCP write tools for direct authoring — rejected.** The read-only, tools-only
  surface (ADR-030) and the no-pre-edit-interception stance (ADR-067) keep
  authoring on the file/PR path; a write tool in the MCP would cross the trust
  boundary in the wrong place.
- **Do nothing — the honest baseline.** Engineers can already author through Host
  A today. Acceptable only if the corpus is being authored; the whole point of
  Thread E is that the non-technical author is locked out, so "do nothing"
  silently bets the record stays the domain of a few maintainers.

## Accessibility

- **Keyboard-first capture.** The capture modal should take keyboard focus on
  open and be fully operable and dismissible from the keyboard, matching the
  Explorer's keyboard-first conventions (ADR-028) and the universal quick-capture
  pattern (a global hotkey into a focused modal).
- **Provenance legibility.** As elsewhere in Lore, a draft produced by an
  AI-assisted interview must be clearly marked as a *proposed* artifact awaiting
  human ratification, never presented as already-authoritative recorded
  knowledge.
- **Plain-language first.** The interview asks essential questions in plain
  language and pre-fills proposed answers, so a non-technical author is never
  confronted with schema jargon or empty required fields.

## Style Guidance

- Name the capture surfaces under the `lore-*` brand (ADR-068); the skill is
  `rac-capture` (an engine-adjacent skill, like `rac-import`), while the overlay,
  bot, and web surface are Lore-brand products.
- Keep the vocabulary honest: a host *captures* and *proposes*; the human
  *ratifies*; git/PR *records*. A draft is never described as a decision until it
  is merged.
- Where a claim is load-bearing, cite the source in prose and carry its caveat;
  flag the fast-moving areas (Slack AI surfaces, Windows cloud-signing, macOS
  permission cadence) rather than asserting a frozen certainty.

## Open Questions

- Where do drafts live before promotion — a `drafts/` path, an `/intake` branch,
  or a fork — and what is the lightest review that still satisfies ADR-065 for a
  solo maintainer versus a team?
- How good must the freeform→typed classification be before a non-technical
  author can self-serve, and how are its mistakes surfaced for human review
  rather than hidden?
- For Host C, does the interview live in the assistant-thread surface (richer,
  more version-risk) or a capped modal (simpler, shallower), and which model
  boundary-crossing posture clears a typical Enterprise-Grid admin review?
- Should the first build (Host A `rac-capture`) be scheduled as a non-versioned
  `rac/roadmaps/future/` item now, or after the skill is prototyped?
- Does the overlay (Host B) earn its build cost once the Slack bot (Host C)
  already covers the same authors on every platform?

## Related Decisions

- ADR-002
- ADR-006
- ADR-017
- ADR-020
- ADR-021
- ADR-024
- ADR-028
- ADR-030
- ADR-040
- ADR-041
- ADR-063
- ADR-065
- ADR-067
- ADR-068

## Related Roadmaps

- lore-supermemory-grounding
