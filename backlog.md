# Backlog — building out Lore/RAC from here

Personal implementation document. **Not a RAC artifact** — no frontmatter, no
gates, no authority; the corpus stays canonical until items here are executed
or archived. This displaces `rac/roadmaps/future/` as the working view: all 24
future items are triaged below, ranked into one efficient build-out order for
the product **as it currently stands** (no new scope invented).

- Snapshot: 2026-07-17, branch `claude/rac-engine-council-review-9qd7pd`
  (48 commits ahead of `origin/main`, which still ends at the native spike).
- Effort scale (solo maintainer + agent sessions): **S** ≤ 1 day ·
  **M** 2–5 days · **L** 1–3 weeks · **XL** month+.
- When an item graduates into real work, the corpus still gets its scoped
  roadmap/design per ADR-093/ADR-047 — this doc decides *order*, the corpus
  records *intent*.

---

## 1. Reality check — where the artifacts lag the tree

The `future/` statuses were written before the native-engine campaign ran.
Corrections, verified against the tree and CI on 2026-07-17:

| Item | Artifact says | Actually |
|---|---|---|
| `native-engine-spike` | Planned | **Done.** `rust/` + PARITY/PERF reports are on `main`. |
| `native-cli-closure` | Planned | **Done, unmerged.** 391-case closure battery green (`rust/CLOSURE-REPORT.md`), sitting in PR #347. |
| `native-derived-index` | Planned | **Done, unmerged.** ADR-099→112 ported (`rust/INDEX-REPORT.md`); the ADR-063-flip precondition is satisfied. In PR #347. |
| `native-engine-cutover` | Planned | **Code complete, unmerged.** Dispatch, packaging, HTTP MCP, guards — all on the #347 line + this branch. Remaining work is landing it, not building it. |
| `artifact-specs-extraction` | Planned | **Delivered in substance** by ADR-115 (shared artifact-spec registry both engines read) + Guard 1 (`rust/spec/sync_spec.py` vs `itsthelore/rac-spec` in CI). Residue: flip status, confirm packaging claim. |
| `conformance-fixtures` | Planned | **Core delivered** by Guard 2 (`rust/tools/conformance_certify.py` certifies both engines against rac-spec goldens). Residue: the TS-SDK-CI consumption half — folded into the TS SDK item below. |
| `explorer-followups` | informal note | **Fully absorbed.** v0.8.11 is Achieved; both deferrals shipped. Pure archive. |
| `rac-capture-skill` | Planned | **Initiative 1 shipped** (PR #193). Remaining: Initiative 2 (save/promote boundary). Hosts stay deferred. |
| `decision-grounding-paper` | Planned/blocked | Initiative 1 done, Initiative 2 **run-ready** in rac-benchmarks (only funded model runs remain). Initiative 3 blocked on GATE-1. |
| `single-node-scale-residuals` | Planned | **Mostly mooted.** The top residual (ADR-108 term-range merge) was *ported and landed* in the native index work; the rest are Python-engine hot-path concerns, and post-cutover Python is arbiter + `ingest` only. Re-measure on the native engine before scheduling anything. |

Two external in-flight dependencies, not in `future/` but binding:

- **`grounding-retrieval-surface`** (Python `retrieve` surface, oracle-next
  branch @ `0.1.dev55+gf2091befd`) — unmerged; the CI retrieve-parity job is
  `continue-on-error` until it lands, and the Rust port adopts its argparse
  delta only *after* (port follows, never leads — ADR-116).
- **GATE-1** (employer external-comms / IP review) — calendar-bound, blocks
  the paper submission and the essays. Start the clearance process now; it
  costs no build time and everything in Tier 3 queues behind it.

**Standing tax to plan around:** ADR-116's lockstep means every *additive
engine feature* is now written twice — Python reference first, Rust port with
parity cases after. While that regime holds, prefer non-engine work (docs,
actions, satellites, SDK) and batch the engine-touching items.

---

## 2. The ranked backlog

Ordering logic, in one line each:
(0) land what's built — finished-but-unmerged work decays fastest;
(1) cheap, ready, high-leverage adoption + contract freeze;
(2) the evidence engine — the thesis is unproven until published numbers exist;
(3) new operational surfaces — real value, real distribution/security tax;
(P) parked — dormant until a named trigger fires.

### Tier 0 — Land the native engine (in flight; do nothing else first)

| # | Work | Effort | Notes |
|---|---|---|---|
| 0.1 | **Merge PR #347, then this branch** (or retarget this branch as the single PR — it contains #347 plus the council fixes) | S | Everything below assumes the two-engine reality is on `main`. |
| 0.2 | **Apply council section (c)** — safety/perf/idiom cleanups from `rust/COUNCIL-REVIEW.md` (sections a, B1–B3 are done; (c) is untouched) | S–M | All byte-neutral; batch them in one pass with the full parity battery as referee. |
| 0.3 | **Merge `grounding-retrieval-surface` (Python), then adopt the `retrieve` argparse delta in Rust** | M | Unblocks folding the retrieve-parity CI job into the required tier. |
| 0.4 | **Corpus housekeeping** — flip the four native roadmaps + specs-extraction to Achieved, archive `explorer-followups`, adopt this backlog | S | Move to `rac/roadmaps/archive/` rather than delete: other artifacts hold relationship edges to these IDs; deletion breaks `rac relationships --validate`. |
| 0.5 | **Kick off GATE-1 clearance** | S (calendar) | Do it now so Tier 3 isn't gated later. |
| 0.6 | *(decision checkpoint, after a soak)* — the **ADR-063 flip** is now unblocked; taking or deferring it is a recorded decision, not code | S | Also decide the Explorer TUI's deprecation path (cutover explicitly left it out). |

### Tier 1 — Contract freeze + cheap adoption levers (~2–3 weeks total)

| # | Item (future/ source) | Effort | Why this rank |
|---|---|---|---|
| 1.1 | **corpus-setup-guidance** | S | Docs-only, no engine tax, and it answers the observed enterprise cold-start failure (the ~2,500-person org's mega-doc anti-pattern). Highest leverage-per-day in the whole list. |
| 1.2 | **rac-capture-skill — Initiative 2** (save/promote boundary) | S | The skill shipped; defining draft-commit → PR-promotion closes the capture core and is the gate for every capture host in Tier 3. |
| 1.3 | **commercial-layer-positioning** | S | Pure writing; records the substrate-not-assembler stance so README/pitch/enterprise conversations stop improvising. No build dependency, do it in the gaps. |
| 1.4 | **ts-sdk-stable-release** (+ the surviving half of conformance-fixtures: wire the suite into the SDK's CI) | M | Freezes the contract consumers copy. Standing precondition for any second SDK and the editors line; conformance-in-SDK-CI converts Guard-2 work into third-party protection. |
| 1.5 | **decisions-on-pr** | M | Top-ranked adoption lever, all dependencies shipped (`rac decisions` + `## Applies To`). Every adopting repo's PRs become passive proof. Build as an action/recipe — no engine change, no lockstep tax. |
| 1.6 | **ci-report-formats** (GitLab code-quality + JUnit) | M | Widens CI reach to GitLab/Jenkins/Bitbucket (the enterprise surfaces ADR-090 names). Engine-touching → pays the dual-engine tax: Python first, Rust port + parity cases in the same change. Batch both renderers in one pass. |

### Tier 2 — The evidence engine (thesis proof; overlaps Tier 1 where money/calendar allows)

| # | Item | Effort | Why this rank |
|---|---|---|---|
| 2.1 | **external-benchmark-evidence — GitChameleon arm first** | M–L | The only external benchmark that is executable-scored, i.e. fits ADR-066 natively. A deterministic, defensible external number beats any self-authored one. LongMemEval waits (see Tier 3). |
| 2.2 | **decision-grounding-paper — fund and run Initiative 2** | M + $ | SWE-DecisionBench is run-ready; the runs are the only blocker on the evidence pillar. Assemble the manuscript as results land; submission queues on GATE-1 (started at 0.5). |
| 2.3 | **org-site-rac-spec-surface** | S–M | rac-spec now exists (Guard 1 checks it out in CI), so the spec section is unblocked; ship it and defer the essays band + landing rebalance until GATE-1 clears and the spec content is worth headlining. |
| 2.4 | **artifact-completeness-benchmark** (dogfood N=1) | L | Second evidence pillar. Sequenced after 2.1/2.2 — it shares the rac-benchmarks harness and the funding pool, and the paper doesn't need it to submit. |

### Tier 3 — Capture hosts and the wider evidence table (new operational surfaces)

| # | Item | Effort | Why this rank |
|---|---|---|---|
| 3.1 | **lore-capture-followups — Initiative 4 only** (inbound-bot security review) | M | Pulled forward as the hard prerequisite for any hosted capture surface. The other three initiatives stay parked. |
| 3.2 | **lore-slack-bot** (MVP → governance → Grid readiness) | L | The highest-reach capture host (whole team, zero install) and the design is already complete (`lore-slack-capture-flow`). First *hosted* Lore service — hence 3.1 first. |
| 3.3 | **external-benchmark-evidence — LongMemEval adapter** (+ LoCoMo reuse, HF publication of SWE-DecisionBench) | L | The vendor-table arena. LLM-judged scoring and adapter-shape risk make it credibility-sensitive; do it only with the reproduction-command discipline the artifact demands, after the deterministic result (2.1) exists to anchor honesty. |
| 3.4 | **lore-overlay** (macOS, then Windows) | L–XL | Real signing/notarization/distribution tax for a narrower audience than Slack. Build on demand signal from 3.2 / capture-skill usage, not before. |

### Parked — dormant until the named trigger fires

| Item | Trigger to un-park | Disposition |
|---|---|---|
| **lore-supermemory-grounding** | Evidence agents miss decisions for lack of semantic recall, *after* the live `retrieval-diagnostics` roadmap and miss-payload work ship (they are the cheaper first answer to the same gap) | Keep parked; the one-way adapter is deliberately small when its day comes. |
| **skill-trust-and-surfacing** | A product decision to distribute third-party skills | Correctly speculative today; nothing to do. |
| **single-node-scale-residuals** | A post-cutover re-measurement showing a residual that still binds on the *native* engine | Expect to archive most of it: the term-range merge landed in Rust; the remaining entries describe Python hot-path costs the cutover just retired from the hot path. |
| **agentic-demand-alignment** | — | **Dissolved into this backlog.** It is an index artifact; its five initiatives are owned by: retrieval-diagnostics + miss payloads (paraphrase), the ADR-113 capture line (1.2/3.x), the spec-driven-handoff design + decisions-on-pr (1.5), freshness-and-drift-detection phase 2 (live roadmap), and corpus-setup-guidance (1.1). Archive it with the pointer here. |
| **lore-capture-followups** (Initiatives 1–3) | Capture-core usage signal (the corpus-lift measurement it itself defines) | I4 pulled into 3.1; the rest is exploration backlog, correctly unscheduled. |

---

## 3. The one efficient walk

If I simply work top-to-bottom:

1. Land #347 + this branch; apply council (c); merge the retrieval branch and
   adopt its delta; archive the finished artifacts; start GATE-1. *(Tier 0 —
   roughly a week of merging, cleanup, and paperwork.)*
2. `corpus-setup-guidance` → capture Initiative 2 → commercial positioning
   (writing, in the gaps) → TS SDK 1.0 with conformance-in-CI →
   `decisions-on-pr` → `ci-report-formats`. *(Tier 1 — the product's adoption
   surface and frozen contract, ~2–3 weeks, almost all lockstep-tax-free.)*
3. GitChameleon arm → funded SWE-DecisionBench runs → manuscript; spec surface
   on the org site as the cheap parallel task. *(Tier 2 — the proof.)*
4. Security review → Slack bot; LongMemEval + HF publication; overlay only on
   signal. *(Tier 3.)*

Rules of thumb that produced this order:

- **Merge risk compounds; parked ideas don't.** Everything 90 %-done goes
  first, everything 0 %-done-but-gated goes last, no exceptions.
- **Prefer work outside the engine** while the ADR-116 lockstep tax applies;
  when engine work is unavoidable (1.6), batch it.
- **Adoption before evidence, evidence before new surfaces**: guidance/PR
  surfacing make existing installs stickier this month; benchmarks make the
  pitch credible next quarter; hosted capture creates new users after that —
  and each tier funds conviction for the next.
- **Calendar-bound blockers start now** (GATE-1, funded runs), effort-bound
  work fills the time they take.

## 4. Displacement mechanics (when this doc takes over)

- `git mv` each absorbed/achieved `future/` artifact to
  `rac/roadmaps/archive/` (IDs and inbound relationship edges survive;
  `rac relationships rac/ --validate` stays green). Do **not** delete files —
  several live artifacts hold edges into `future/`.
- Items still pending here keep exactly one corpus home when picked up: a
  scoped roadmap graduated out of `future/` per ADR-093/ADR-094, referencing
  this doc not at all (it has no authority).
- Revisit this file after every tier lands; it is cheap to re-rank and has no
  gates to appease.
