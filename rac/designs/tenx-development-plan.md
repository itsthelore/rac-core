---
schema_version: 1
id: RAC-KWJ564WGG8JZ
type: design
tags: [tenx, engine-rebuild, performance, dx, architecture, safety]
---
# Design: Ten-x Development Plan

## Context

A full-codebase review of `rac-core` — every subsystem plus four cross-cutting
lenses (architecture and layering, developer experience and product,
performance and scalability, test-quality and safety) — ran alongside a
from-scratch, contract-preserving rebuild of `src/rac` against the 1747-test
acceptance suite. The rebuild is deliberately conservative: it re-derives the
internals for clarity and layering while holding every test-visible contract
(module paths, public names, CLI bytes, JSON shapes, exit codes, determinism)
byte-identical. That conservatism is the point, and it is also the limit. The
review surfaced a large class of improvements a contract-preserving rewrite
*cannot* deliver, because they change behaviour, add capability, move the test
contract, or need a new decision.

The `Engine Rebuild` roadmap (`engine-rebuild`) fences exactly this: its third
initiative, "Ten-x development plan," calls for "a prioritised development plan
whose items can be scheduled as their own roadmap entries without re-deriving
the analysis." This design is that plan made concrete. It converts the review
corpus — the four lens analyses and the per-subsystem reviewer findings — into a
staged programme, each initiative traced to the evidence that motivates it, the
mechanism that delivers it, the decisions it touches, and a measurable signal
that tells us it landed.

The plan rests on a real, current assessment, not aspiration. The engine is
already well-built: `core` has zero upward imports, behaviour is spec-driven
(only twelve hard-coded per-type branches survive across the whole tree), one
canonical corpus walk feeds ~20 services, and the privacy/telemetry surface is
the strongest-engineered part of the codebase. The 10x opportunity is therefore
not a rescue — it is leverage on a sound base. Where the base is weak the review
was specific, and this plan inherits that specificity.

## User Need

The primary reader is the maintainer scheduling the series that follows the
engine rebuild, plus the contributors who will implement each item. They need a
plan that is decision-grade: it must say *what* to build, *why* the evidence
supports it, *how* to build it against the real code, which settled decisions it
respects or must revisit, and how to know it worked — so that the review's value
is scheduled deliberately rather than rediscovered opportunistically, and so
that each initiative can be lifted into its own roadmap entry intact.

Behind the maintainer are the two audiences the product ultimately serves, and
the plan's axes are chosen for them: the PM authoring recorded knowledge, who
needs authoring to be low-friction and "valid" to mean "actually written"; and
the coding agent grounding against that knowledge over MCP, which needs the
integration the product already advertises to be shipped, fast on the hot path,
and honest about untrusted content. Every initiative below traces back to a need
one of these audiences actually has, evidenced in the review, not to a
refactor pursued for its own sake.

## Design

### What "10x" means here

"10x" is not one number. The evidence supports four axes on which this product
can become an order of magnitude better, plus an enabling substrate that makes
work on all four safe. Each axis is grounded in a specific lens finding.

1. **Corpus and query scale.** The performance lens measured a "single walk,
   many recomputations" engine: inside one `build_gate` over 1200 artifacts,
   `validate()` runs 2x per artifact, relationship extraction 10x, and
   classification 3x; the resolution index is rebuilt three times per gate. Half
   of a profiled gate is markdown-it tokenization it mostly throws away; the
   other half is redundant re-derivation over already-parsed products. The MCP
   serving path — the product's actual hot surface — re-reads and re-derives the
   whole corpus on every tool call (search ~1017 ms, `get_summary` ~412 ms on
   1200 artifacts). 10x on this axis means the engine stays sub-100 ms at corpus
   and query volumes an order of magnitude larger than today's, because cost
   today is super-linear in *consumers and queries*, not just artifacts.

2. **Agent-native depth.** The DX lens found the flagship promise half-shipped:
   ADR-067's pre-edit enforcement is referenced throughout the code and the
   `rac validate - --corpus` seam exists, but no command emits the Claude Code
   `PreToolUse` hook that would use it. The managed agent-rules block is
   IDs-only ("a pointer, never a body"), so an agent without MCP connected sees
   decision *names* but no *content*. Authoring skills install only under
   `.claude/`. 10x means the integration the product leads with is actually
   handed to the user, in one command, for more than one client, carrying enough
   content to be useful standalone.

3. **Authored, not merely valid.** The DX lens demonstrated the credibility gap
   live: a corpus of empty `TODO` scaffolds — including an artifact literally
   titled `Title` — passes `validate`, `improve`, `review`, and `doctor` as
   "conformant, nothing needs attention," because validation is structural and
   cannot tell an authored decision from an unedited template. For a product
   whose pitch is that the agent grounds against *real* recorded decisions, this
   is the central claim reporting success on placeholder input. 10x means the
   gates distinguish authored knowledge from scaffolding.

4. **Adoption friction.** The DX lens found 32 subcommands with no functional
   grouping, no shell completion, and no did-you-mean; a typo prints the full
   32-choice argparse dump. There is no single front door — seven commands report
   overlapping health — and onboarding seeds an empty requirement, not the
   decision the pitch is about. 10x means a newcomer lands on a map, not a wall,
   and the first artifact they see demonstrates the product's actual value.

The enabling substrate is the architecture and test-quality work. The
architecture lens is explicit that the 1747 tests pin the *internal module map*
(65 files import `rac.services.*`, 38 `rac.core.*`, 12 `rac.output.*`) versus
only 10 that use the public `rac` façade — so the largest structural wins are
"blocked by tests" until that coupling is inverted. The staging below front-loads
that substrate, because without it Stage 2 and Stage 3 are unsafe.

### Stage 1 — Hardening and near-term engineering

Stage 1 is low-risk, mostly contract-preserving, and folds in the backlog the
rebuild fleet deferred. It builds the substrate the later stages stand on. None
of these items require a new decision.

**1.1 Invert the test coupling into a contract tier and an internal tier.**
*What:* re-baseline the suite so a thin **contract tier** (CLI stdout/exit via
golden files plus the public `rac.__all__` façade) is what must survive any
restructure, and an **internal tier** is free to move with the code. *Why:* the
architecture lens names this the single highest-leverage item and the
prerequisite for opportunities 1.2, 1.5, 2.1, and 3.3 — today's coupling is why
a 10x restructure "can't be done without breaking tests." *Mechanism:* route the
~65 `rac.services.*` and ~12 `rac.output.*` imports that assert contract-level
behaviour through the façade or the CLI; mark the genuinely-internal ones as
internal; leave the golden bytes untouched. *Affected ADRs:* ADR-062 (the SDK
surface is `rac.__all__`) becomes the load-bearing contract instead of the
module map; ADR-007, ADR-027, ADR-075 unchanged. *Success signal:* the count of
test files importing internal modules for contract assertions drops toward zero,
and a no-op internal module rename touches no contract-tier test.

**1.2 One shared `Finding` value type; delete the `services → output` leak.**
*What:* define a single `Finding(code, severity, path, line, message)` in
`core`, produced by validate/relationships/review/okf and consumed by the
sarif/human/json/github renderers. *Why:* `services/gate.py:193` reaches *up*
into `rac.output.sarif._relationship_result` — a private presentation symbol —
purely so the two "never drift"; this is the one genuine inversion of the
declared layer arrow (architecture Finding 1). *Mechanism:* the shared type makes
sarif/human/gate non-divergent by construction; `gate.py` stops importing the
renderer, removing the only `services → output` edge. *Affected ADRs:* ADR-060
(shared structural validation) extended to findings; ADR-023 (clean-break
internal refactor) governs the change. *Success signal:* zero `services → output`
imports in the dependency graph; the four finding shapes unify into one.

**1.3 Collapse the rebuild's deferred duplication backlog.** *What:* the
cross-module cleanups the rebuild fleet could not absorb into a
contract-preserving rewrite. *Why:* each is a named latent-bug or drift risk from
a subsystem reviewer, not a stylistic preference. *Mechanism, per item:*
(a) unify the two divergent `_first_value` implementations (`core/validation`
does not strip a leading list marker, `core/identity` does) behind one core
helper with an explicit `strip_list_marker` flag — today a `## Status` written as
`- Accepted` would validate against the raw `- Accepted` while identity
resolution strips it (core-artifacts Finding 1);
(b) make roadmap horizon validation data-driven via a new `ArtifactSpec`
"constrained free field" declaration, removing the last artifact-specific
validator branch (core-artifacts Finding 4);
(c) give `PortfolioStats.largest_feature` a single deliberate, tested tie-break
semantic, resolving the `_neg_name` tuple-vs-string divergence on prefix ties
(services-io Finding 4);
(d) replace the MCP budget `serialize()` default-JSON-separators trap with a
proper byte-budget abstraction, so the budget measures the exact serialized bytes
by construction (mcp reviewer);
(e) fold the scattered issue-code literals into one registry, unify the three
bundled-resource registries (templates/skills/hooks), and collapse the three
corpus-traversal builders onto one `_entry_for` primitive (core-parsing and
core-artifacts). *Affected ADRs:* ADR-059 (single parser instance), ADR-026
(opaque identities), ADR-033 (response budget), ADR-060, ADR-023 — all preserved.
*Success signal:* one definition each for first-line extraction, issue codes,
bundled-resource loading, and byte-budgeting; a regression test pins the
`largest_feature` tie-break and the list-marker status case that pass silently
today.

**1.4 Trust and CI hardening.** *What:* widen the proven trust guarantees to the
whole surface they claim. *Why:* the quality lens found the guarantees strong but
narrow — the no-egress control exercises ~6 functions, not the MCP tool path; the
"one file is the entire network surface" claim rests on a two-name denylist; the
SBOM attests 3 of 30+ shipped packages with unverified versions; there are no
security gates in CI; and the MCP JSON contract is asserted field-by-field, not
golden-pinned. *Mechanism:* an autouse session-scoped socket-blocking fixture
with a ping-only opt-in marker (every test becomes a no-egress assertion); a
denylist-plus-AST-call check over network-capable modules and binaries; an SBOM
generated from the locked environment and scanned (`osv-scanner`/`pip-audit`)
with `test_sbom` asserting component versions equal the installed environment;
`filterwarnings=error` and a coverage floor as merge gates; whole-envelope golden
snapshots for the five MCP tools; and SHA-pinned GitHub Actions. *Affected ADRs:*
ADR-086 (air-gap posture), ADR-041 (usage ping), ADR-046 (CLI telemetry),
ADR-084 (audit), ADR-065 (untrusted content) — all *strengthened*, none revised;
the CI scanners fetch advisory data in CI infrastructure, never in the shipped
tool, so ADR-086's air-gap posture on the installed binary is untouched. New
gates join the ADR-075 required tier. *Success signal:* a network call in any
service fails at the exact test that introduced it; the SBOM carries the full
transitive closure with resolved versions; MCP payloads diff byte-for-byte
against committed goldens.

**1.5 Output and CLI cohesion.** *What:* dissolve the two output god-modules and
the CLI monolith. *Why:* `output/human.py` is 1388 LOC importing result types
from ~20 services; `cli.py` is 2218 LOC with a 945-line `build_parser()` and 47
duplicated `args.json`/`args.sarif` dispatch sites; the ADR-007 `schema_version`
literal is hand-written in ~10 renderers (architecture Findings 3-5). *Mechanism:*
a `(kind, format) → renderer` registry so handlers collapse to
`read → service → render(result, fmt) → print`; split `output` by capability
(co-locating a capability's human+json+sarif renderers) behind re-export shims; a
command registry so `build_parser()` becomes a loop; one `envelope()` helper for
the version stamp; and an AST import-direction gate enforcing a declared
`services/foundation → services/compose` sub-layering. *Affected ADRs:* ADR-007
(JSON stability) preserved — golden bytes are identical; ADR-005 (CLI first)
preserved; ADR-023 governs the refactor. *Success signal:* "add a format" and
"add a command" each become a one-line registration; the 47 branch sites and the
~10 envelope literals collapse to one each; golden output is byte-identical.

### Stage 2 — Capability multipliers

Stage 2 scales the engine and ships the depth the product advertises. It depends
on Stage 1's substrate (the read-model and registry work, the inverted test
tiers). Most items are clean-break internal refactors with byte-identical output;
two add user-visible capability.

**2.1 One `CorpusAnalysis`, one `CorpusGraph`, built once and shared.** *What:* an
immutable per-run analysis computed by a single pass over the corpus snapshot —
canonical identifier and alias sets, the extracted relationship map, per-artifact
validation issues, the resolution index, and per-kind adjacency — that gate,
portfolio, review, repository, and `relationships --validate` all read instead of
re-deriving. *Why:* this kills the performance lens's dominant waste (F1, F8):
`validate()` 2x, extraction 10x, classification 3x, resolution index 3x per gate,
and the "portfolio resolves relationships twice" and "combined relationships
pass" items the reviewers and the deferred backlog both name. It also resolves
the architecture lens's second resolution engine: `relationships.py` (1254 LOC,
the highest-coupling node) builds its own identifier/resolution index separate
from `resolve.py`; the merge yields one `CorpusGraph.from_corpus(entries)` that
`resolve`, `find`, `relationships`, `rename`, and `watchkeeper` all query.
*Mechanism:* decompose `relationships.py` into a `graph/` subpackage
(references, index, resolve, cycles, report, validate); memoize extraction on the
entry; build the resolution index once. *Affected ADRs:* ADR-023 (clean-break),
ADR-016 (relationships as structural references), ADR-026 (one identity model),
ADR-002 (determinism) — output stays byte-identical, which the existing
`*_from_corpus` seams already prove; and the refactor must *not* absorb the two
deliberately-separate git modules (ADR-043 watchkeeper revisions, ADR-045
git-derived recency), which stay the only git-aware code. *Success signal:*
`build_gate` over 1200 artifacts drops from ~510 ms toward the ~360 ms parse
floor; `validate()` runs once per artifact, extraction once, the resolution index
built once — asserted by call-count instrumentation in a perf test.

**2.2 Attack the parse floor and the discovery walk.** *What:* remove the cost
Stage 2.1 leaves behind. *Why:* the performance lens attributes ~50% of a cold
gate to markdown-it tokenization the structural extractor throws away (F3);
search re-tokenizes the corpus ~20x per query (24001 `tokenize()` calls, F4);
`find_markdown_files` descends `.git`/`.venv`/`node_modules` then filters,
measured 14x slower with noise dirs *and* wrongly including `node_modules/**.md`
(F5); the `Repository` model linear-scans where it should index (F7).
*Mechanism:* a purpose-built single-pass structural line-scanner (heading set and
order, section bodies with accurate line numbers, requirement lines, fenced-code
awareness) that produces the exact current `Product`, kept honest by a
corpus-wide golden-equivalence test against the retained markdown-it path;
tokens computed once at index-build time and cached on the entry (in-memory,
outside the JSON contract); an `os.scandir` walk that prunes ignored trees
*before* descending; and dict-indexed `Repository` accessors. *Affected ADRs:*
this **revisits ADR-059** (reuse a single markdown parser instance) — the
scanner becomes the primary structural parse path with markdown-it retained as
the equivalence oracle, which changes ADR-059's premise; **requires a new ADR
superseding ADR-059** establishing the two-path design. ADR-002 (determinism)
preserved by the golden-equivalence gate. *Success signal:* parse from
~0.68 ms/file to ~0.1 ms/file; `find_artifacts` from ~436 ms toward ~100 ms
cold; `find_markdown_files` from 28.4 ms to 2.0 ms on a noisy tree, and
`node_modules` markdown no longer pollutes the corpus.

**2.3 Ship the agent surface end to end.** *What:* a single
`rac agent init --client claude|cursor|codex|copilot` that provisions the whole
integration: MCP wiring, the **pre-edit hook** (emit the Claude Code
`settings.json` `PreToolUse` block plus a wrapper piping proposed content into
`rac validate - --corpus rac/`), client-appropriate skill install, and a
refreshed agent-rules block that carries each live decision's one-line statement
under a character budget. *Why:* this is the DX lens's highest-leverage single
addition — it ships the feature ADR-067 already leads with but no command emits,
generalizes the Claude-only skill installer to the Cursor/Codex audience the
README claims, and closes the IDs-only agent-rules gap so an agent without MCP
still sees *what was decided*. *Mechanism:* generalize the existing `profiles`,
`agent_rules`, and `hook` services behind one client-parameterized front door
with a per-client hook template; project the `## Decision` first line
(`agent_rules._first_line` already parses it) into the managed block using the
MCP budget discipline. *Affected ADRs:* ADR-067 (agent integration is
context-supply and post-edit enforcement) realized as intended; ADR-047 (agent
guidance are prompt artifacts), ADR-088 (enterprise profile scaffold), ADR-005
(CLI first) preserved; ADR-033 (response budget) reused; ADR-034 (agent
reasoning boundary) preserved — the block *supplies* content, it does not reason.
The change from "pointer, never a body" to "budgeted body" is a code convention,
not a settled ADR, but should be recorded as a new decision so the projection
policy is auditable. *Success signal:* `rac agent init --client claude` produces
a working `PreToolUse` block a fresh Claude Code session honours; the same
command targets Cursor and Codex; the agent-rules block is useful with MCP
disconnected.

**2.4 Make `valid` mean `authored`, and give untrusted content a typed signal.**
*What:* a `placeholder-content` finding class plus a hardened content-threat
signal. *Why:* the DX lens's central credibility gap (empty scaffolds pass every
gate) and the quality lens's residual hotspot (the English-idiom injection regex
is trivially evaded and never runs on the MCP path where untrusted bytes actually
reach the agent). *Mechanism:* for each section, compare the body against the
shipped template placeholder for that type/section (`rac.templates` already loads
them), flag any still byte-equal plus a title still equal to `Title` and residual
`TODO:` markers, emitted as a gate-blocking finding with a severity-override key;
and normalize before matching (NFKC-fold, strip zero-width/bidi controls), add a
structural detector for content impersonating RAC's own contract (fake
`## Status` outside frontmatter, embedded fenced tool-output, HTML comments), and
surface the doctor verdict on the MCP path as an *additive, advisory*
`provenance.review` signal. *Affected ADRs:* ADR-021 (templates as creation
contracts) supplies the placeholder oracle; **ADR-065 (content is untrusted; the
boundary is human PR review) is strictly preserved** — the signal is advisory,
never a gate, never sanitization; **ADR-066 (deterministic eval, no embeddings,
no LLM judge)** and ADR-002 preserved — every check is deterministic and offline.
*Success signal:* a byte-for-byte template corpus stops reporting "conformant";
homoglyph/bidi-obfuscated injection no longer slips the doctor patterns; an agent
reading `get_artifact` sees the same review flag a human reviewer would.

### Stage 3 — Product bets

Stage 3 holds the bigger, riskier moves: one needs a superseding decision, one
changes the product's shape for a new adopter, one unifies three surfaces behind
a single model. Each depends on Stage 1 and Stage 2.

**3.1 A warm, content-hash-invalidated MCP serving index.** *What:* hold an
incremental index for the server's lifetime; on each tool call, `os.scandir`-walk
a `{path: (size, mtime)}` dirstate, recompute the content hash only for changed
files, reparse only on hash change, and reuse the cached `CorpusEntry` /
`CorpusAnalysis` for everything unchanged. *Why:* the performance lens calls this
the highest-leverage *user-facing* win, because the MCP path is the product's
real hot surface and ADR-032 currently mandates a full cold read per call.
*Mechanism:* output stays byte-identical to a cold read whenever the bytes are
unchanged — the cache invalidates on change and never serves stale — so warm
per-call latency drops from 400 ms-1 s to the stat-walk cost (single-digit ms for
hundreds of artifacts). *Affected ADRs:* this **requires a new ADR superseding
ADR-032 (Guide Stateless Reads)**. ADR-032's guarantee is that identical
repository bytes and identical input produce identical output — a *determinism*
contract, which this design honours — but its literal current form is "re-read
everything every call." The new decision must reframe the guarantee as "no stale
reads, invalidate on change" rather than "no cache." ADR-002 (determinism) and
ADR-033 (budget) preserved; ADR-031 (in-process consumption) unchanged.
*Success signal:* warm MCP `search_artifacts` on 1200 artifacts from ~1 s to
sub-100 ms; a determinism test proves byte-identical output between a cold read
and a warm read of unchanged bytes, and invalidation on any byte change.

**3.2 A human front door and real authoring.** *What:* the DX curation work —
wayfinding (an argparse epilog grouping commands as Author/Enforce/Explore/
Integrate, a `rac completion` command plus `argcomplete`, and a
Levenshtein did-you-mean on invalid choice), `rac status` promoted to the default
action inside a corpus, `rac schema` defaulting to `--list`, schema-guided
interactive authoring (`rac new --interactive`) driven by `spec.guidance`, and
decision-first onboarding seeded with a *filled* example in the product's own
idiom. *Why:* the DX lens found 32 commands with no map, seven overlapping health
commands with no single door, and onboarding that seeds an empty requirement
titled `Title` rather than the decision the pitch is about. *Mechanism:* reuse
the guidance strings the schema already carries; fold the signals `doctor`
already aggregates into one ranked, copy-paste-fix front door; pair interactive
authoring with the 2.4 meaningfulness lint so content authored this way passes by
construction. *Affected ADRs:* ADR-005 (CLI first) preserved and extended;
ADR-044 (onboarding scaffold writes one starter artifact) — the starter becomes a
filled decision; ADR-021 (templates as contracts) supplies the interactive
prompts. *Success signal:* a first `rac --help` reads as a grouped map; a mistyped
command suggests the intended one; a new user's first artifact is a filled
decision that demonstrates the pitch.

**3.3 One shared read-model behind CLI, MCP, and Explorer.** *What:* make
`services/repository.py`'s `Repository` read-model — which already composes
index, validation, relationships, and diagnostics on top of `collect_corpus` —
the single source all three presentation surfaces read. *Why:* the architecture
lens found artifact summary, status label, and relationship rendering derived
three independent times (output/, `mcp/server.py`, and the Explorer's 994-LOC
adapter plus 1287-LOC views), so they drift and are maintained in triplicate,
risking `rac get_related` and `rac relationships` describing the same edge
differently. *Mechanism:* MCP's `_get_artifact`/`_get_related` and the Explorer
adapter consume the read-model instead of re-deriving strings; the Explorer
memoizes the per-load review report (the reviewer's single biggest Explorer
responsiveness win) against the loaded `Repository`. *Affected ADRs:* ADR-030
(guide tools-only surface) and ADR-031 (in-process consumption) preserved — the
model is read-only and in-process; ADR-028 (explorer delivery surface) and
ADR-015 (explorer as consumer) preserved — the Explorer stays a consumer of
services. *Success signal:* one code path computes an artifact's summary, status
label, and relationship rendering; a cross-surface test asserts CLI, MCP, and
Explorer describe the same edge identically.

### Sequencing and disagreement

The stages are ordered by dependency and risk, not theme. Stage 1.1 (test-tier
inversion) gates the structural work in 1.5, 2.1, and 3.3 and is therefore first.
Where the lenses pull in different directions, the plan takes a position. The
performance lens would push the warm MCP index earliest (it is the biggest
user-facing win); the architecture lens implies it should wait until the single
`CorpusAnalysis` (2.1) exists to be cached and until ADR-032 is revisited. This
plan sides with sequencing it *after* 2.1 and behind a new ADR (3.1), accepting a
later landing for a safer one. Similarly, the DX lens treats wayfinding as cheap
and immediate; this plan defers it to Stage 3.2 not because it is hard but because
it is best delivered alongside the front-door and authoring changes it belongs
with, and because the substrate work has higher leverage first.

## Constraints

- **ADR-002 (AI optional / deterministic).** Every item — the meaningfulness
  lint, the content-threat detector, the scanner, the caches — stays
  deterministic and offline. No LLM call, no network dependency in the engine.
- **ADR-066 (deterministic grounding eval).** No embeddings and no LLM judge
  enter scoring or content analysis; the content-threat signal is rule-based.
- **ADR-065 (content is untrusted; the boundary is human PR review).** The MCP
  content-threat signal is additive and advisory only — never a gate, never
  sanitization. The trust boundary stays human PR review.
- **ADR-007 (JSON contract stability) and ADR-062 (SDK surface is
  `rac.__all__`).** The contract-preserving refactors keep golden bytes and the
  public surface identical; the MCP golden snapshots and the test-tier inversion
  make that contract, not the module map, the thing under test.
- **ADR-023 (clean-break internal refactors).** The `CorpusAnalysis`, output
  split, and graph subpackage are internal clean breaks with byte-identical
  output, exactly the pattern this ADR governs.
- **ADR-075 (required merge gate).** New gates (egress guard, coverage floor,
  security scan, MCP goldens) join the required tier rather than sitting advisory.
- **Spec-driven, not type-branched.** New behaviour comes from data on
  `ArtifactSpec` (the constrained-free-field for roadmap horizon, the placeholder
  oracle) rather than new `if artifact_type == …` branches — preserving the
  codebase's strongest architectural property.
- **Two items require a new decision before implementation:** the warm MCP index
  (superseding ADR-032) and the structural line-scanner (superseding ADR-059).
  Neither may proceed on this design alone.

## Rationale

The staging is dependency-and-risk ordered because the review's clearest single
finding is that the biggest wins are gated: the architecture lens shows the test
coupling blocks the structural work, so inverting it first converts a dozen
"blocked by tests" items into "safe." Hardening precedes capability because
shipping the agent surface (2.3) and the warm index (3.1) onto an un-hardened
trust posture would widen the very surface the quality lens found under-guarded.
Capability precedes the product bets because the warm index needs the single
`CorpusAnalysis` to cache and the shared read-model needs the inverted test tiers
to move safely.

Tracing every initiative to a measured or observed finding — rather than to a
refactor instinct — is deliberate: it lets each item become its own roadmap entry
without re-deriving the analysis, which is exactly the outcome the engine-rebuild
roadmap asks this plan to produce. The two supersession flags are called out
rather than buried because the plan must not silently contradict a settled
decision; both are genuine 10x levers whose value justifies a new ADR, and both
are held behind that ADR rather than assumed.

## Alternatives

- **One big rewrite series instead of three staged tiers.** Rejected: the review
  showed the wins have hard dependencies (test-tier inversion before structural
  work; `CorpusAnalysis` before the warm cache), so a flat rewrite would either
  serialize badly or land unsafe intermediate states.
- **Lead with the warm MCP index (biggest headline win).** Rejected as the
  opening move: it needs `CorpusAnalysis` to cache and an ADR revisiting ADR-032;
  sequencing it early trades safety for a headline. It stays the marquee Stage 3
  bet.
- **Treat performance as the whole 10x story.** Rejected: the engine is already
  ~100x under its own perf ceilings at target corpus sizes, so pure speed is not
  where a first-time adopter feels 10x. The authored-not-valid and agent-depth
  axes move the product's *credibility and reach*, which the evidence weights at
  least as heavily.
- **Ship the meaningfulness lint as a warning, not a gate-blocking finding.**
  Rejected: a warning leaves the central claim ("bad knowledge never lands")
  still reporting success on placeholder input; the severity-override key gives
  teams the escape hatch without weakening the default.
- **Keep the injection heuristic CLI-only.** Rejected: the untrusted bytes reach
  the agent on the MCP path, which never runs `doctor` today; an advisory
  `provenance.review` signal is where the residual risk actually is, and it
  stays advisory to preserve ADR-065.

## Accessibility

The plan's outputs must preserve the product's viewer-agnostic, plain-text model:
new CLI surfaces (grouped help, `rac status`, did-you-mean) stay legible without
colour dependence, and the meaningfulness and content-threat findings render as
plain words and codes in `review`/`doctor` output, not colour-only cues —
consistent with the determinism and plain-Markdown guarantees the engine already
holds. Interactive authoring must remain fully keyboard-driven and degrade to the
existing non-interactive `rac new` when no TTY is present.

## Style Guidance

Each initiative, when promoted to its own roadmap entry, keeps this artifact's
shape: what, why-with-evidence, mechanism, affected ADRs, measurable signal.
Evidence citations name the lens or reviewer finding, not a vague appeal. New
behaviour is expressed as data on `ArtifactSpec` wherever possible, matching the
spec-driven convention. Prose stays decision-grade and plain — no hype, every
claim traceable — matching the surrounding corpus.

## Open Questions

- **Warm MCP index (3.1):** what exactly does the new ADR superseding ADR-032
  guarantee — "identical output for unchanged bytes, invalidate on any change" —
  and how is staleness proven absent in the isolation battery?
- **Structural scanner (2.2):** does the new ADR retire ADR-059 or amend it,
  and is markdown-it kept permanently as the equivalence oracle or only through
  a deprecation window?
- **Body-bearing agent rules (2.3):** what is the per-decision character budget
  and the overflow rule, and should the projection policy be its own ADR given it
  reverses the "pointer, never a body" convention?
- **Meaningfulness lint (2.4):** is `placeholder-content` an error by default
  with a team-level downgrade, or a warning that CI can promote — and does it
  block `gate` in the required tier from day one?
- **Scheduling:** which of these initiatives share a release series, and which
  warrant their own roadmap codename? The two ADR-gated items (3.1, 2.2) likely
  need decision entries scheduled ahead of their implementation series.

## Related Roadmaps

- engine-rebuild

## Related Decisions

- adr-002
- adr-005
- adr-007
- adr-015
- adr-016
- adr-021
- adr-023
- adr-026
- adr-027
- adr-028
- adr-030
- adr-031
- adr-032
- adr-033
- adr-034
- adr-041
- adr-043
- adr-044
- adr-045
- adr-046
- adr-047
- adr-059
- adr-060
- adr-062
- adr-065
- adr-066
- adr-067
- adr-075
- adr-084
- adr-086
- adr-088
