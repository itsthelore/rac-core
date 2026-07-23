# Team-Scale Knowledge Tooling — Competitive Landscape & Lessons for AsDecided

> **Status: research document, not a RAC artifact.** Per ADR-010 ("Documents Are
> Not Artifacts") and ADR-024 ("RAC Is Not a Content Store"), this is reference /
> working material, not part of the validated `decisions/` corpus. Its *actionable*
> conclusions are captured as corpus artifacts — see "What this produced" below.
>
> **Scope:** how software teams of 20+ engineers (not indie hackers) adopt, govern,
> and sustain knowledge tools, and what AsDecided (RAC) should learn.
> **Method:** multi-angle web research across four adjacent product categories plus
> a cross-cutting failure-mode pass, with adversarial verification and
> evidence-vs-marketing tagging. Confidence and primary sources cited inline.
> **Date:** 2026-06.

---

## Executive summary

Across every category the finding is the same: **capture is solved and identical
everywhere (Markdown-in-git, immutable records, status + supersession). What decides
survival at 20+ is (a) fighting staleness/trust-collapse, (b) discovery, and (c)
riding the existing workflow.** AsDecided's no-database / files-in-git / PR-review / MCP
design is *structurally aligned with nearly every sustaining mechanism the evidence
supports* — its single biggest exposure is the **freshness-signal gap**, which is
both the best-documented cause of abandonment *and* the gap no agent-context
competitor has solved.

One-sentence positioning that the research supports:

> **AsDecided is the shared, git-native, deterministic source of truth for product
> *decisions* — the knowledge class no agent-context tool governs and no team can
> afford from enterprise requirements management — winning on the freshness/drift
> problem (now empirically the #1 adoption determinant) and the no-embeddings bet
> that a major incumbent (Sourcegraph) publicly reversed into.**

---

## Category findings

### 1. AI agent context / memory for teams

*Cursor, Continue, Sourcegraph Cody & Amp, Augment, Glean, Dust, Onyx.*

- **Files-in-git + PR review is now an industry pattern, not a compromise.** Cursor
  (`.cursor/rules/*.mdc`) and Amp (`AGENTS.md`) are git-committed Markdown reviewed
  through the normal PR flow — AsDecided's exact substrate. [high]
  ([Cursor rules](https://cursor.com/docs/context/rules), [Amp](https://ampcode.com/news/AGENT.md))
- **Sourcegraph publicly abandoned embeddings** for enterprise context (third-party
  code transmission, vector-DB maintenance, poor scaling) and replaced them with
  deterministic search — strong external validation of AsDecided's no-embeddings stance
  (ADR-066). [high] ([Sourcegraph](https://sourcegraph.com/blog/how-cody-understands-your-codebase))
- **"Shared team memory" is oversold.** Cursor Memories and Augment's base index are
  **per-user**; real org memory (Augment Cosmos) is preview-only — a genuinely
  shared, governed team source is unmet demand. [high]
- **Hosted RAG has under-disclosed staleness windows everywhere** (Glean up to a
  ~30-day full-crawl gap; Dust 1–2 days; Onyx 30-min default). "Real-time" is
  marketing; ACLs gate *retrieval*, not LLM-synthesis oversharing. [high/medium]
- **The dominant adoption-killer is context being silently ignored** by the model —
  "Cursor is a predictive engine, not a policy enforcer." Shared context buys
  consistency-by-default, never compliance-by-guarantee — exactly the boundary
  ADR-067 already encodes (context-supply + post-edit enforcement). [high]
- **None of them ship freshness, expiry, or ownership metadata on the rules
  themselves** — the gap AsDecided can own. [high]

### 2. Decision & spec tooling

*ADR tools (adr-tools, MADR, Log4brains, Backstage ADR plugin); spec-driven dev
(GitHub Spec Kit, AWS Kiro, Tessl); enterprise RM (Jama, IBM DOORS, Siemens
Polarion).*

**ADRs.** Convergent design since Nygard (2011): Markdown-in-repo, immutable,
status + supersession. Tools differ on **discovery**, not capture (Log4brains adds a
static searchable site; Backstage couples ADRs to the catalog entity via
`backstage.io/adr-location`). The documented death pattern is the **"abandonment
curve"** (5 ADRs in month one, then nothing) and **stale "Accepted" records eroding
trust**; the antidote is an *operating model* (ownership + cadence + a "Gardener"
role + bounded review windows + CODEOWNERS), not tooling. ThoughtWorks put
lightweight ADRs in **Adopt** and the rule is "store in source control… in sync with
the code." [high on mechanics, medium on failure-mode blogs]
([Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions),
[MADR](https://adr.github.io/madr/),
[Log4brains](https://github.com/thomvaill/log4brains),
[Backstage](https://backstage.io/docs/architecture-decisions/),
[ThoughtWorks](https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records))

> Note for AsDecided: Log4brains deliberately avoids fixed numbered filenames to prevent
> multi-dev merge collisions — AsDecided's minted opaque IDs (`RAC-…`) already solve this.
> And `decided review`/`doctor`/`coverage` *automate the "Gardener" role* that the
> evidence says is the manual antidote to the abandonment curve.

**Spec-driven dev.** Spec Kit / Kiro / Tessl invert the source of truth ("intent is
the source of truth, code is generated") via a Markdown phase pipeline. Enforcement
is **AI-mediated and human-gated, not deterministic** (Spec Kit has no blocking
gates; Kiro's "neuro-symbolic" analysis uses LLM + SMT). **Their central, openly
unsolved problem is spec↔code drift** — there is an "Ask HN: specs go stale" thread
and no vendor documents a deterministic anti-drift mechanism; the recurring critique
is "SDD is waterfall." Kiro independently uses **EARS** (which AsDecided validates
deterministically). [high]
([Spec Kit](https://github.com/github/spec-kit),
[Kiro](https://kiro.dev/docs/specs/), [Kiro deep analysis](https://kiro.dev/blog/deep-spec-analysis/),
[Tessl](https://tessl.io/blog/tessl-launches-spec-driven-framework-and-registry/),
["waterfall" critique](https://news.ycombinator.com/item?id=45935763))

> Note for AsDecided: **AsDecided sidesteps SDD's core unsolved problem** — it doesn't generate
> code from artifacts, it records *decisions an agent consults*, so there's no
> spec→code sync to rot. And it does deterministically the structural slice Kiro
> needs an LLM+SMT solver for.

**Enterprise RM (Jama / DOORS / Polarion).** Full formal governance — e-signatures,
FDA 21 CFR Part 11, baselines, workflow states, and **"suspect links"** (downstream
items flagged the moment an upstream item changes; DOORS: valid/invalid/suspect).
The gap is **not capability — it's friction**: opaque seat pricing
(~$400–600/user/yr DOORS; ~$1,788/user/yr Polarion; Jama quote-only), steep admin,
performance that degrades at scale (DOORS Next is *vendor-acknowledged* poor;
Polarion is bottlenecked by SVN single-writer commits), brutal export/migration
lock-in, and — most telling — **license cost literally throttles collaboration**
("only a limited number of people" get authoring licenses). [high on friction,
medium on third-party pricing]
([Jama](https://www.jamasoftware.com/platform/jama-connect/features/),
[DOORS link validity](https://jazz.net/help-dev/clm/topic/com.ibm.jazz.vvc.doc/topics/c_linkval.html),
[DOORS Next perf](https://www.ibm.com/support/pages/ibm-doors-next-7x-performance-considerations),
[Polarion](https://www.siemens.com/en-us/products/polarion/requirements/))

> Note for AsDecided: **"suspect links" is the proven enterprise drift mechanism** — AsDecided
> can deliver a deterministic, git-native version (commit diffs + the validated
> graph) without the per-seat tax, SVN bottleneck, or lock-in. Their fatal flaw
> (friction/cost/lock-in, not capability) is AsDecided's wedge.

### 3. Internal developer portals

*Backstage, Port, Cortex, OpsLevel.*

- **Ownership is a committed field for routing, not enforcement** (`catalog-info.yaml`
  `spec.owner`); Backstage's own docs say it is explicitly *not* for runtime auth.
  [high] ([Backstage descriptor](https://backstage.io/docs/features/software-catalog/descriptor-format/))
- **Scorecards = deterministic checks** grouped into maturity levels (OpsLevel
  bronze/silver/gold; a baseline check flags orphaned/ownerless services) — AsDecided's
  `decided validate`/`review` analog. [high] ([OpsLevel](https://docs.opslevel.com/docs/scorecards))
- **Drift is the real enemy**; portals fight it with auto-discovery + orphan/drift
  detection (Backstage `backstage.io/orphan` + `orphanStrategy`). AsDecided can't
  auto-discover (no crawler/DB) but counters with **git-derived staleness** (ADR-045).
  [high] ([Backstage life-of-an-entity](https://backstage.io/docs/features/software-catalog/life-of-an-entity/))
- **TechDocs = Markdown in the same repo as code, updated in the same PR** — AsDecided's
  exact model, proven at Spotify scale (280+ teams, 2,000+ services). [high]
- Adoption: **"usage can be mandated, but adoption must be earned"** — top-down
  mandates correlate with *lower* developer satisfaction; portals become shelfware
  when devs revert to Slack. [medium, analyst/vendor]

### 4. Team knowledge bases / wikis

*Notion, Confluence, Stack Overflow for Teams, Slab, Slite.*

- **The decay problem is real and vendor-acknowledged.** Failure modes: content
  decay ("the gap between documented truth and operational reality widens silently"),
  ownership vacuum ("everyone is responsible = nobody"), and misaligned incentives
  ("nobody gets recognized for updating a Confluence page"). [high on mechanisms]
- **Every tool ships the same anti-staleness primitive: owner + expiry clock +
  freshness signal that biases retrieval** (Notion page verification, Slab/Confluence
  verified status with auto-un-verify, SO for Teams Content Health, Slite
  verification). But it's a **self-clicked "verify" button** — human attestation, not
  proof. [high] ([Notion](https://www.notion.com/help/guides/verify-knowledge-your-teammates-can-trust-with-page-verification),
  [SO for Teams](https://stackoverflow.co/internal/features/))
- **Findability decays independently** (recycled but directional stats: ~1.8 hrs/day
  searching; ~½ of searches end in "not found"); knowledge fragments across
  Slack/docs and the single source of truth splinters. [medium]
- All five are bolting LLM Q&A over the corpus; Slite explicitly positions verified
  docs as "the source of truth for Claude, ChatGPT, Cursor." AI *surfaces* gaps but
  doesn't fix decay. [high]

> Note for AsDecided: its freshness primitive is *structurally stronger* — **git history
> is deterministic recency (ADR-045) and PR review is enforced attestation —
> "verification you can't fake"** — plus `decided validate`/`relationships` as
> machine-checkable rot detection no wiki has. The inherited risk: **PR review raises
> contribution cost — the exact friction that kills wikis at 20+** (mitigate with
> agent-assisted authoring + fast gates).

---

## Cross-cutting evidence (the empirical backbone)

- **Docs measurably drift.** A study of 27,772 PRs across 714 repos: only ~0.8% of
  PRs update the README; ~21.5% of changes that should have updated it didn't; doc
  updates are ~1% of PR activity and routinely overlooked. [high]
  ([arXiv 2603.00489](https://arxiv.org/abs/2603.00489))
- **Documentation quality has a measured payoff.** DORA: high-quality docs make teams
  "more than twice as likely" to hit performance targets, and amplify every technical
  practice. **DORA 2025 explicitly endorses "connecting AI tools to internal
  documentation, codebases, and *decision logs*"** — AsDecided's exact use case, named.
  AI is an "amplifier" that magnifies good docs and exposes bad. [high / medium-high]
  ([DORA docs](https://dora.dev/capabilities/documentation-quality/),
  [DORA 2025](https://dora.dev/dora-report-2025/))
- **The load-bearing adversarial finding: git + PR review alone does *not* keep docs
  fresh.** The docs-as-code literature itself concedes "no empirical data validates
  whether drift actually decreases at scale," and the 0.8% data shows reviewers
  routinely miss doc drift. Co-locating in git is **necessary but proven-insufficient**
  — which is why the deterministic freshness/drift signal matters. [high]
- **Context rot is established.** Chroma Research tested 18 frontier models; every one
  degrades as input length grows, well before window overflow — favoring *curated,
  minimal, on-demand* context over corpus dumps. [high]
  ([Chroma](https://research.trychroma.com/context-rot))
- **The MCP "context tax."** Simon Willison stopped using MCP for coding agents
  because tool descriptions eat context (GitHub's MCP ≈23k tokens) and CLIs are
  lower-tax — but he endorses the underlying "context engineering" discipline. A
  knowledge server justifies itself only if it stays lean. [high]
  ([Willison](https://simonwillison.net/tags/model-context-protocol/))
- **Honest gap:** there is **no published proof that curated decision context lifts
  coding-agent task success.** The strongest defensible claim is that context-rot +
  context-engineering evidence supports *selective* delivery. AsDecided's grounding-eval
  (ADR-066) is the way to *be* the one who proves it. [high confidence in the gap]

---

## What determines whether a 20-person team adopts vs abandons AsDecided (impact-ordered)

| # | Lesson | Tag | Action |
|---|---|---|---|
| 1 | Lives in the PR/git workflow, not a separate destination | **FITS** (strongest) | This *is* docs-as-code — the #1 sustaining mechanism. Lead with it. |
| 2 | Staleness → trust collapse is the top killer; git+PR review is proven-insufficient | **RISK** (no DB; recency from git, ADR-045) | Surface git-derived staleness loudly + a deterministic "suspect" drift gate. Highest-leverage build. → `future/freshness-and-drift-detection` |
| 3 | Automate the "Gardener" (the manual health-review that's the documented ADR antidote) | **POSITIONING** | `decided review`/`doctor`/`coverage` = machine-checkable health no wiki/portal has. Make it a scheduled CI report. |
| 4 | "Verification you can't fake" | **POSITIONING** | Enforced PR review + immutable git history vs competitors' self-clicked verify buttons. |
| 5 | Effortless consumption — context comes to the agent | **FITS** | The read-only MCP server pushes context in-flow; counters the "go to the wiki" abandonment driver. |
| 6 | …but keep the surface LEAN (context tax + context rot) | **POSITIONING / RISK** | Few tools, small descriptions, retrieve-on-demand (ADR-033). CLI-first (ADR-005) may out-adopt MCP. → `future/lean-context-delivery` |
| 7 | Discovery/proximity is the survival differentiator, not capture | **FITS** | Attach decisions to the code/services they affect + the typed graph (ADR-074). → `future/decision-to-code-proximity` |
| 8 | Contribution friction from the PR gate (the friction that kills wikis) | **CONFLICT** (ADR-065) | Mitigate with agent-assisted authoring (`rac-artifacts` skill) + fast gates. |
| 9 | AI changes the ROI of curation | **POSITIONING** | The timing tailwind. Lead GTM with "your agents improve on day one from artifacts you already have." |
| 10 | Only wins if it REPLACES a silo, not adds one | **POSITIONING** | Position as *the* source of truth, not "another store" beside Confluence/Slack. |
| 11 | Low ceremony | **FITS** | ADR evidence: heavy templates get abandoned. Guard against template bloat. |
| 12 | Prove it | **HONEST** | Grounding-eval (ADR-066) — no public proof curated context lifts task success yet; be the one with the number. |

---

## Competitive landscape & positioning

- **Closest single competitor concept:** `mcp-adr-analysis-server` — an MCP server that
  serves/analyzes ADRs to agents. AsDecided differentiates by being full artifact families
  + deterministic validation + a validated graph, not ADR analysis alone.
  ([repo](https://github.com/tosin2013/mcp-adr-analysis-server))
- **Patterns to borrow:** Spec Kit's `constitution` (governed project principles),
  Backstage's catalog-coupled ADR discovery (`adr-location`).
- **The whitespace:** every agent-context tool stores **coding rules** or **indexed
  code**; none governs **product decisions / requirements / roadmaps**. That is AsDecided's
  uncontested niche.
- **The wedge against enterprise RM:** the traceability + governance value of
  DOORS/Jama/Polarion (suspect links, baselines, review), git-native — no per-seat
  collaboration tax, zero lock-in (it's just Markdown), no SVN bottleneck,
  deterministic — for teams priced out of or crushed by enterprise RM.
- **AsDecided's defensible middle** sits between lightweight MCP file/notes servers
  (deterministic but unstructured) and enterprise RAG-over-docs (embeddings,
  precision-poor for decisions): deterministic + *structured artifacts* + a *validated
  graph*.

---

## Honest caveats & open questions

1. **No published proof curated decision context lifts agent task success.** Evidence
   supports *selective* delivery (context rot), not "decisions demonstrably make
   agents better." Grounding-eval (ADR-066) is the answer and a moat.
2. **The freshness gap is real and is AsDecided's softest spot** — but also the gap nobody
   else has solved, so it is a differentiator to win, not just a risk to cover.
3. **Decision rationale cannot be auto-generated**, so AsDecided can *detect and surface*
   staleness, not make it "structurally impossible" the way generated API docs can.
4. **MCP resources are under-adopted** (clients favor tools); agent-context conventions
   (AGENTS.md / CLAUDE.md / Cursor rules) are unsettled — don't over-commit to one
   surface.
5. **Contribution friction** at 20+ is inherited from the PR gate.
6. **Sourcing limits:** many adoption/ROI and pricing figures are vendor or
   third-party estimates (medium confidence); the durable facts are the mechanism
   docs, the arXiv drift study, DORA, the Sourcegraph embeddings reversal, and the
   enterprise "suspect link" semantics.

---

## What this produced (captured as corpus)

The *actionable* findings were distilled into unscheduled `future/` roadmap items
(this document is the reference behind them):

- `decisions/roadmaps/future/freshness-and-drift-detection.md` — loud git-derived staleness
  + a deterministic git-native "suspect links" drift gate (lesson #2/#3/#4).
- `decisions/roadmaps/future/decision-to-code-proximity.md` — declared code-scope references
  so the governing decision surfaces at the point of work (lesson #7).
- `decisions/roadmaps/future/lean-context-delivery.md` — measure/bound the agent-facing
  footprint and keep a first-class CLI path (lesson #6).

The competitive *positioning* conclusions belong with the `rac-growth-positioning`
requirement or a dedicated `design` (not yet captured at the time of writing).
