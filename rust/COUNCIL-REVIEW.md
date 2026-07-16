# COUNCIL-REVIEW — native Rust engine (`rust/`) at PR #347

Architecture and code-quality review of the byte-parity Rust port, commit
`37ac948` (head of PR #347, "native Rust engine as the default for the
covered surface"). Scope: the `rust/` workspace — `rac-engine`, `rac`,
`rac-mcp`, `parity-harness` (~24k src LOC).

This review deliberately does **not** re-verify output correctness. Byte
parity is machine-proven elsewhere (`PARITY-REPORT.md`: 610+ CLI cases, MCP
frame parity, ~13k fuzz inputs; `INDEX-REPORT.md`: store byte-identity,
cache on/off). The council's charter is everything parity cannot see:
architecture, idiom, memory/panic safety, robustness, performance, and test
strategy — with an eye on the recorded end state (Rust as the only engine,
Python retired to a CI arbiter and then removed).

## Method

Six independent reviewer "seats" (architecture, idiomatic-Rust, safety,
robustness/security, performance, test-architecture) swept the workspace
blind to each other, then every finding went to a three-lens adversarial
refute panel (contract lens, code lens, practicality lens; default-refute,
2-of-3 majority to survive). Finders looped for two rounds, then a
completeness critic dispatched a targeted deep-read of the one hot module no
seat had opened closely (`markdown.rs`).

- **58 findings filed → 52 upheld → 6 killed** by the panel.
- Severity of the survivors: **1 blocker, 11 high, 22 medium, 18 low**.
- **Only 1 of 52 is parity-sensitive** (the recency-join optimisation, and
  only its second step). Every other fix is byte-neutral to covered output —
  a strong signal the port's contract surface is well isolated from the
  quality debt.

Two operational notes, in the interest of honesty about coverage: the run
was interrupted once by an Anthropic-side API overload and re-driven to
completion, and the finder loop was capped at two rounds. Round 1 was the
exhaustive per-seat sweep; round 2 hunted new ground; the critic closed the
`markdown.rs` gap. Coverage of the serving surface, the index/store stack,
the git-recency paths, and the test topology is deep; a third finder round
would most likely have added low-severity items only.

Every finding below carries `file:line`, the panel verdict (e.g. `upheld
3-0`, or `2-1` with which lens dissented), a fix size (**S** < 1h / **M** ~1
day / **L** multi-day), and whether it is parity-sensitive. Nothing here was
pushed to `claude/rac-engine-heal`; patches are proposed inline.

---

## (a) Merge-blocker candidates for PR #347

### A1 — The hand-rolled HTTP front-end is unhardened on a shared endpoint · `rust/rac-mcp/src/http.rs` · fix **M**, parity-neutral

This is the review's headline. **Every seat that looked at `http.rs`
independently flagged it** — the sole blocker plus seven of the eleven highs
land in this one 270-line file. The frame processor it wraps is byte-parity
proven and the audit logic is sound; the risk is entirely in the
hand-written HTTP/1.1 connection handling that ADR-098 turns into a **shared,
multi-client endpoint**. Connection handling is explicitly *unpinned* by the
port contract (`PORT-CONTRACT.d/19 §0` pins only response-body bytes and the
§2 status map), so **all of these fixes are parity-safe** — no covered case
exercises them.

| # | file:line | issue | verdict | fix |
|---|-----------|-------|---------|-----|
| **BLOCKER** | `http.rs:121` | No socket read/write timeout + serial accept loop → one idle/slow client stalls the whole endpoint for every user (slowloris; also head-of-line blocking when a client reads a large `get_related` response slowly) | `upheld 3-0` | `set_read_timeout`/`set_write_timeout` on each accepted stream; drop on timeout |
| HIGH | `http.rs:85` | Strictly serial accept loop — zero request concurrency because `FreshnessTracker::read_model(&mut self)` needs exclusive access | `upheld 3-0` | tracker behind `RwLock` (or snapshot under a short lock); small worker pool |
| HIGH | `http.rs:129` | No `catch_unwind` around request handling — any engine panic (an `expect`/`unwrap` reachable from a hostile corpus edge, or a future bug) unwinds out of the accept loop and kills the shared server for all clients; the in-flight read is never audited | `upheld 3-0` | wrap handling in `catch_unwind(AssertUnwindSafe(..))`, respond 500, continue |
| HIGH | `http.rs:162` | `vec![0u8; content_length]` allocated from the raw client header **before** reading a byte or checking method/path/auth → `Content-Length: 999999999999` OOM-aborts the process | `upheld 3-0` (filed twice, arch+safety) | reject `len > MAX_BODY` (a few MiB — MCP frames are tiny) with 413 before allocating |
| HIGH | `http.rs:144` | Unbounded `read_line` on the request line and each header, no header count/size cap → a never-terminated header line or header flood exhausts memory | `upheld 3-0` | read through `by_ref().take(MAX_HEADER_BYTES)` and cap header count (mirrors the `.take()` bounding already in `frontmatter.rs:4427`) |
| MED | `http.rs:157` | `Transfer-Encoding: chunked` neither decoded nor rejected — a chunked POST is misread as empty body and wrongly answered 400 where the oracle answers 200 (`connection: close` prevents smuggling, so this is an interop break, not a hole) | `upheld 3-0` | detect the header, decode or return explicit 400/501; record in `PORT-CONTRACT.d/19 §5` |

**Sketch (the minimum viable hardening, ~15 lines):**

```rust
fn handle_connection(stream: TcpStream, ...) {
    stream.set_read_timeout(Some(Duration::from_secs(30))).ok();
    stream.set_write_timeout(Some(Duration::from_secs(30))).ok();
    let result = std::panic::catch_unwind(AssertUnwindSafe(|| {
        // read_request now: bounded header loop via .take(MAX_HEADER_BYTES),
        // and after parsing len:  if len > MAX_BODY { return respond_413(); }
        route(&mut reader, &mut stream, ...)
    }));
    if result.is_err() { let _ = respond_500(&mut stream); }
}
```

**Is it merge-blocking?** The council rated the slowloris a blocker on the
"shared endpoint" reading of ADR-098; the mitigating facts are that the
server defaults to `127.0.0.1` (exposure is a deliberate proxy act,
ADR-085) and that a hardened reverse proxy caps some of these vectors. The
honest call: **if `rac mcp --transport http` ships enabled and is relied on
in this PR, A1 should land first** — the timeout + body-cap + `catch_unwind`
subset is an afternoon's work, entirely parity-neutral, and closes a genuine
one-line DoS against a shared server plus a fleet-wide-outage-on-any-panic
class. If the HTTP transport is understood as experimental/gated behind the
stdio default, A1 downgrades to the top of section (b). This is a maintainer
judgement about the transport's shipping status, so I flag it rather than
decide it.

There are no other blocker-severity findings. The engine core, the codec,
and the stdio transport are clean (see the verdict in section (d)).

---

## (b) High-value follow-ups

### B1 — Recency join spawns one `git log` per match · `rust/rac-engine/src/commands.rs:1345` · fix **M** · ⚠ parity-sensitive (step 2 only) · `upheld 3-0`

The ADR-045 recency join loops `gitinfo::last_committed` once **per match**
(and re-canonicalises `repo_root` every call), so `rac find` and MCP
`search_artifacts` pay O(matches) subprocess spawns inside any git tree —
the exact cost `PERF-REPORT.md` identifies as dominating the roadmap's 21.6s
motivating number, which the index stack left untouched (it fixed the walk,
not the join). Broad `rac find "system" --json` on a 5k corpus ≈ 2000
`git log -1` spawns ≈ 5–15s while the warm store answers in 43ms;
`search_artifacts` pays it per `tools/call`, and it annotates *all* matches
before budget truncation drops most of them. The same O(n)-spawn shape
recurs at `review.rs:221`+`305` (two overlapping passes), `doctor.rs:288`,
and `okf.rs:76` (two spawns/artifact, one a full-history `--reverse`).

- **Step 1 — byte-neutral, do now:** hoist/canonicalise `repo_root` once,
  dedupe paths, and `par_iter` the per-path spawns (identical argv → identical
  stdout, ~4× on the 4-core box); share one `path→%cI` memo across the
  drift+cadence passes in a single `review`. This alone is a large win and
  changes no bytes.
- **Step 2 — parity-sensitive, gate on proof:** collapse to a single
  `git log --format=<sep>%cI --name-only` history pass with a per-path
  `git log -1` fallback. Merge-simplification can make batched history differ
  from per-path `-1`, so this must be proven equal on merge edges via the
  existing differential harness before swapping. ADR-045 pins *that* recency
  is git-derived, not *how*.

### B2 — CI is a finished campaign, not a durable gate · `.github/workflows/rust-spike.yml` · fix **S–M**

The strongest cluster from the test seat, and the most important for the
recorded end state — this is "what regresses **silently** once the Python
oracle retires." Four upheld findings, all `3-0`:

| # | file:line | gap | fix |
|---|-----------|-----|-----|
| B2a HIGH | `rust-spike.yml:17` | `paths:` filter is `rust/**` only, but the cargo suites read the **live** `rac/` and `tests/` trees (`resolve_vectors.rs` builds the index over `rac/` and asserts a pinned `entry_count`). A routine ADR-adding PR skips rust-spike, merges, and leaves `cargo test -p rac-engine` broken on `main` — the next unrelated rust PR eats a 56k-line vector mismatch it didn't cause. The `push:` trigger also targets the defunct `claude/rac-mcp-http-spike` branch, so post-merge `main` is never re-verified. | add `rac/**`, `tests/**`, `src/**` to both filters; point `push:` at `main` (**S**) |
| B2b HIGH | `rust-spike.yml:69` | CI runs only `parity-cases.json` (130 cases). `parity-cases-closure.json` (391 cases: 21 commands incl. all 113 written-tree capture cases) and `parity-cases-index.json` (45 cases — the **only** end-to-end referee of cache-ON behaviour, the ADR-112 default) were one-shot runs, gated nowhere. Two-thirds of the proven surface never consults the arbiter. | add harness steps for the closure + index case lists (+ `mcp_parity.py --cache-on`, `mcp_mutation_referee.py`); the index file (45 cases) must be unconditional (**S**) |
| B2c HIGH | `rac-mcp/src/main.rs:1` | `rac-mcp` (~2.2k LOC: JSON-RPC framing, six-tool dispatch, the ADR-084 audit recorder, the HTTP transport) has **zero** native tests, and CI runs `cargo test -p rac-engine` only — so even tests added later wouldn't run. Every behavioural claim about this binary lives in Python referee scripts that retire with the oracle. | `cargo test --workspace`; add frame-processor replay tests, an audit-row/refusal unit test, and an HTTP status-matrix test on an ephemeral port (**M**) |
| B2d MED | `rust-spike.yml:58` | `cargo test -p rac-engine` is single-package; `rac-mcp`, `parity-harness`, `rac` tests never run in CI — the exact crates that must be self-verifying once Python is gone. | `cargo test --workspace --release` (**S**) |

### B3 — Vector fixtures are pinned to the live corpus · `rust/spec/gen_vectors_resolve.py` → `tests/*_vectors.rs` · fix **M** · `upheld 2-1` (practicality dissent)

Five committed vector files (~9.8 MB) are pinned byte-exactly against the
**live** `rac/` (431 `.md`) and `tests/` trees; `resolve.json` (3.28 MB, 60
queries) breaks on *any* corpus change via its `entry_count`/df/score
asserts. Already incurred once — commit `cb55284` regenerated 56,129 lines
because a session added three artifacts — and it recurs on every ordinary
corpus PR, poisoning diffs and conflicting across parallel branches. Worse
for the end state: `gen_vectors_*.py` import `rac.core`, so after Python
retires the first `rac/` edit permanently breaks `cargo test` with no
regeneration path. **Fix:** snapshot a frozen fixture corpus into
`rust/fixtures/corpus/`, regenerate the five files against it **once** while
`.venv-oracle` still exists, and point the suites there —
`gen_vectors_index.py:22` already records exactly this rationale for *not*
pinning the live corpus. Live-corpus coverage stays in the parity/golden
tier where both engines move together. (The practicality dissenter agreed
the fragility is real but questioned the effort ranking; the fix is still
the clean one.)

Two smaller CI-hermeticity items ride along: the retrieve arbiter is fetched
from a **floating branch** (`rust-spike.yml:163`, `continue-on-error:true`
hides the rot) — pin the SHA (**S**, `3-0`); and `tests/gitinfo.rs:21` shells
out with the developer's real git config, so `commit.gpgsign=true` or a user
`core.hooksPath` makes the suite machine-dependent — isolate `HOME` +
`GIT_CONFIG_NOSYSTEM` like the harness already does (**S**, `3-0`).

---

## (c) Hardening and idiom cleanups

### Safety hardening (all byte-neutral)

The codec is the strongest part of the tree — `index_format.rs` bounds-checks
every decoded offset/length, caps every attacker-sized allocation, and
validates magic/version before trusting layout, with `hostile_inputs.rs` +
`index_store_vectors.rs` pinning the corruption classes. The gaps are at the
edges:

| file:line | issue | sev | verdict | fix |
|-----------|-------|-----|---------|-----|
| `relationships.rs:518` | Recursive Tarjan `strongconnect` with no depth guard → a long resolvable reference chain overflows the native stack and aborts `rac relationships --validate` (safe abort, not UB; oracle also dies, at ~1000, so it's a failure-*mode* divergence) | MED | `3-0` | iterative explicit-stack Tarjan (or depth cap) — identical SCC output |
| `mdhtml.rs:41` | `export` body renderer walks the markdown-it AST with two **unguarded** native recursions; a ~500k-deep nested-blockquote body (under the 1 MiB cap; `body_markdown` re-reads with no cap) overflows the stack and SIGSEGVs — uncatchable, so one poisoned artifact denies `export` of the whole corpus, incl. CI export on an unreviewed branch (ADR-065). The block tokenizer in `markdown.rs` is safe — it has a `MAX_NESTING=20` guard; this AST walk does not. | MED | `2-1` (practicality) | `stacker::maybe_grow` in both recursive bodies (markdown-it already vendors stacker) or an explicit worklist |
| `revisions.rs:286` | `extract_tar` creates symlinks from the raw tar linkname with **no target-escape check**, under-implementing the oracle's `tarfile(filter="data")`. A revision containing a name-safe symlink `notes/leak.md → /etc/passwd` is materialised, then `walk.rs` yields it as a corpus file and folds external file bytes into watchkeeper drift output at exit 0 — a read-outside-corpus disclosure and a byte/exit divergence (filed by two seats) | MED | `3-0` | validate the link target (reject absolute / `..`-escaping) before `symlink()`, mirroring the existing name check |
| `index_store.rs:421` | The workspace's **only** `unsafe` (`Mmap::map`) has no `// SAFETY:` comment; its soundness rests on an unwritten, Unix-specific invariant (segments immutable; writes go temp-dir→rename to a fresh inode; removal unlinks). A future in-place self-heal or a Windows port silently reintroduces SIGBUS/torn-read UB | MED | `2-1` (code) | add the `// SAFETY:` note stating the invariant + Windows caveat; gate any future in-place rewrite behind a lock/generation counter |
| `audit.rs:183` | The content-bearing audit log (principals, query text, returned IDs — ADR-084 designates it sensitive) is created 0644; a shared-host operator pointing `audit.path` at a central file exposes it to every local user | MED | `3-0` | `.mode(0o600)` on both opens (`audit.rs:183`, `http.rs:45`) — not a wire surface |

### Performance (all byte-neutral; respect ADR-105/112 freshness)

The hot-path architecture is sound (rayon-parallel deterministic walk, O(1)
mmap point access, single-buffer rendering). These are redundant-work and
allocation-churn cleanups, none parity-sensitive:

| file:line | issue | sev | fix |
|-----------|-------|-----|-----|
| `commands.rs:248` | Incremental-validate recompute is **sequential** — cold/verify run ~5.3× slower than the `--no-cache` rayon path (800ms vs 150ms @5k); the cache's first run costs more than never caching, on the default-on path | MED | indexed `par_iter().collect()` preserves manifest order → byte-identical |
| `gate.rs:359` / `doctor.rs:94` | `rac gate`/`rac doctor` walk+parse+classify the **whole corpus 3×** per invocation — and gate is the ADR-067 post-edit hot path (once per edit) | MED | walk once, thread `&items` through the three passes |
| `freshness.rs:182` | `ordered_items` deep-clones **every** parsed `Artifact` on every model rebuild just to hand an owned Vec to a function that only borrows — tens of MB of transient alloc per changed `tools/call` in a long MCP session | MED | return `Vec<&CorpusItem>`; generalise the derive over `&[&CorpusItem]` |
| `portfolio.rs:210` | Relationship graph resolved **2–3× per call** (`summary_from_rows` + `validation_from_rows` + `relationships_from_corpus` each rebuild the full resolution index) | MED | build `resolution_index_from_rows` once, thread it in |
| `eval.rs:331` | `related_returned` re-walks + re-parses + re-derives the entire corpus **per get_related case**, discarding the index `run_eval` already built — O(G×M) where O(M+G) suffices | MED | compute corpus items + relationships once, pass in |
| `resolve.rs:789` | Final sort calls `py_round(fused,12)` **twice per comparison** — each an exact-decimal bignum expansion + `format!` + f64 re-parse — turning O(m) key work into O(m log m) allocating bignum work on every find | MED | precompute the rounded key once per element, sort that |
| `read_model.rs:46` | `store_search` materialises each term's postings **twice** and unions per-term docid sets as candidates, even though `match_entry` is AND — so it `full_entry`s + re-tokenises docs that can never match | MED | one `HashMap<&str,BTreeSet>`, intersect for candidates; df from the same map |
| `main.rs:132` (mcp) | `check_corpus` runs the full `build_index` (walk+parse+classify+whole-graph resolve) on **every startup** for one boolean stderr warning, then discards it — and the tracker re-parses on the first call | MED | short-circuit the empty check, or defer the warning to the tracker's first `read_model` |

Plus eight **low** perf items — the same theme at smaller scale: `store_search`
reconstructs section strings before the type/tag filter (`read_model.rs:54`);
mmap bisect allocates a throwaway `String` per compare (`index_store.rs:599`);
`tokenize_entry` allocates every token twice (`resolve.rs:365`); `corpus_stats`
df does a full token count where existence suffices (`resolve.rs:554`);
`get_related` clones the whole read-model per call (`tools.rs:230`); `audit::observe`
parses its payload twice (`audit.rs:226`); the cold-hash pass and corpus
double-walk in `derived_cache.rs:85`/`228`; and the `parallel_build.rs:32`
threshold (5000) is the Python pickling crossover carried into rayon, leaving
mid-size corpora on the serial floor. All `3-0`, all byte-neutral, each **S**
(one **M**).

### Idiom / maintainability

| file:line | issue | sev | verdict | fix |
|-----------|-------|-----|---------|-----|
| `commands.rs:341` | Severity is a closed 3-value domain threaded as raw `&str`/`String` across ~13 structs in 6+ modules, with lossy `_ =>` fallbacks — a new/renamed severity read from an older `.vseg` cache silently collapses to `info` and renders wrong, no compiler help | MED | `enum Severity` with pinned `as_str()` + `from_str→Result`; serialisation stays byte-identical, `match` becomes exhaustive | **L** |
| `commands.rs:1369` / `tools.rs:135` | The warm-store-vs-cold dispatch is hand-duplicated across `find_from_store` (`ReadModel`) and `search_artifacts` (`TrackerModel`) — two isomorphic enums, no shared choke point, even though ADR-110/112 require `rac find` ≡ MCP `search_artifacts` byte-for-byte | LOW | `2-1` (code) | collapse to one enum + one `serve_search` helper | **M** |
| `audit.rs:102` | `rac-mcp` re-implements `.rac/config.yaml` ancestor-walk discovery over raw frontmatter primitives instead of the engine's config layer — and the two already diverge in their canonicalize-failure fallback, so audit could read a *different* config than validation | MED | `2-1` (contract) | expose a config API on the engine; align the fallback | **M** |
| `tools.rs:341` | MCP `get_summary` fresh-walk fallback hand-rebuilds the entire portfolio-summary payload inline instead of calling the canonical `output::portfolio_summary_value` (the one builder "so the two cannot drift") — a third copy that silently staleness-breaks `--no-cache` vs cache-on | MED | `3-0` | call the canonical builder | **S** |
| `audit.rs:347` / `consent.rs:338` | The tricky Hinnant `civil_from_days` calendar math is copy-pasted byte-for-byte across two crates | LOW | `3-0` | hoist to one shared `rac-engine` helper | **S** |
| `main.rs:386` (mcp) | Tool dispatch reads coerced args by hard-coded positional index with each Python default restated at the call site (e.g. `top_k` default `5` appears in both `a_int(&a,2,5)` and the `if top_k != 5` audit gate) — reorder a param and an accessor silently reads the wrong argument | LOW | `3-0` | named fields from `args::validate`, or shared default constants | **M** |
| `cli.rs:76` | `cli::run` signals "parse-level exit, skip usage recording" through a process-global `AtomicBool` that ~20 sites set and nothing resets → `run()` is non-reentrant, so the ADR-063 in-process embedder end state (and in-process tests) silently drop usage events after any `--version`/`--help`/bad-flag call | LOW | `2-1` (practicality) | thread the signal through the return value | **S** |

Two low test-scaffolding items: `markdown_fuzz.rs:64` replays an
uncommitted vector file and so has **passed vacuously** since the campaign
closed (its generator needs the oracle, so it can never be armed post-retirement)
— commit a frozen minimized vector now or delete it with `frontmatter_differential.rs`;
and `Cargo.toml:11` + release-only CI means the engine's `debug_assert!`
invariants and overflow traps never fire in any test — add a debug-profile
`cargo test` step (do **not** flip `overflow-checks` on `[profile.release]`
alone — the shipped binary's arithmetic may be parity-load-bearing). Both `3-0`.
`markdown.rs:2202`'s 50k-line body-truncation cap likewise has zero coverage
(the largest vector reaches 39k and trips the char cap first) — add one
oracle-generated case (`3-0`).

---

## (d) Architecture verdict

**This is a sound foundation for the recorded end state — Rust as the only
engine, Python retired to a CI arbiter.** All six seats reached that
conclusion independently. The reasons, synthesised:

- **Clean seams.** The binary/engine/transport split holds: `parity-harness`
  is a black-box referee that shells out to both executables (no engine
  linkage); `rac-mcp` is a thin transport whose stdio and HTTP paths share
  exactly one `process_request` seam, as contract 19 requires; and the index
  subsystem's recorded seams (read-model consumes store, freshness decides
  reuse — ADR-104/105) are the code's real seams.
- **Disciplined dependencies.** Five direct deps. The hand-rolls are each
  justified by pinned-oracle semantics (the PyYAML-1.1 subset, argv, pyjson,
  tar-over-`git archive`) rather than NIH — and the panel *confirmed* the two
  that looked riskiest are fine: `sha256.rs` **does** carry FIPS known-answer
  tests (a "no KAT" finding was killed `3-0` as factually false), and the
  memmap `unsafe` is sound under the current write discipline (it just wants
  a `// SAFETY:` note).
- **Careful core.** `Result<_,String>` density is low (~21 sites), there is
  exactly one `unsafe` block, the codec bounds-checks and caps every
  attacker-controlled quantity, and Python-shaping appears only where parity
  demands it. The idiom seat found the engine "genuinely idiomatic where the
  contract allows."

**The debt is concentrated and shallow, not structural.** It clusters in two
places: the hand-rolled HTTP front-end (section a — an afternoon of
parity-neutral hardening) and the **test topology** (section b — the suite is
a finished *campaign*, not yet a durable *gate*: only 130 of 610 CLI cases
and none of the cache-on cases run on PR, `rac-mcp` has no native tests, and
key vectors are pinned to the live corpus so they can't survive the oracle's
departure). Neither is a design flaw; both are the predictable seams of a
port that prioritised proving parity first.

**The one thing to watch for the end state** is exactly the test seat's
concern: today the Python oracle is load-bearing for most end-to-end byte
assertions. The path to retiring it safely is explicit and cheap — snapshot a
fixture corpus, generate native goldens once while `.venv-oracle` still
exists, gate the closure + index case lists and the workspace tests in CI —
and none of it requires touching the engine. (Note the panel *killed*,
`3-0`, the stronger claim that "retirement removes all regression coverage":
ADR-116 keeps the oracle as arbiter and the goldens as the bridge, so the
gap is real but bounded to the items in section b, not existential.)

Recommendation: **land PR #347**, resolving A1 first if the HTTP transport
ships enabled (otherwise take it as the top follow-up), then work section (b)
as the near-term backlog toward Python retirement. Sections (c) is steady
hardening that can flow as capacity allows — every item is byte-neutral
except B1-step-2.

### What the panel rejected (6 killed — recorded so they aren't re-litigated)

- `engine-no-embedder-facade` (`lib.rs:40`, refuted `3-0`): ADR-063/116 make
  the JSON/CLI/MCP contract — not the `rac-engine` crate — the embedder
  surface, so "all modules pub" is not the boundary violation it looks like.
  (The narrower, real consequence survives as the `pub(crate)`/dead-method
  item at `index_store.rs:544`.)
- `oracle-retirement-no-native-goldens` (refuted `3-0`): overstated —
  contradicts ADR-116, which keeps the oracle as arbiter and goldens as the
  bridge. The bounded, true version is section (b).
- `sha256-handroll-no-kat` (refuted `3-0`): factually wrong — `sha256.rs:145`
  has a `tests` module with FIPS vectors incl. the 448-bit boundary message.
- `stdio-nonutf8-line-kills-server` (refuted `3-0`): misreads
  `PORT-CONTRACT.d/10 §1`, which disclaims non-UTF-8 garbage input; the
  UTF-8-valid-but-JSON-invalid path *is* handled.
- `audit-no-fsync-durability` (refuted `2-1`): misreads ADR-084's audit-gap
  clause, which addresses detected write failures, not crash-durability.
- `evidence-dir-social-media-residue` (refuted `2-1`): the load-bearing
  premise (that an engineering report cites `metrics.json`) is false.

---

*Review conducted read-only against `37ac948`; no commits were pushed to
`claude/rac-engine-heal`. Findings are the product of six independent
reviewer seats and a three-lens adversarial refute panel (2-of-3 majority to
survive); `file:line` and panel verdicts are carried on every item above.*
