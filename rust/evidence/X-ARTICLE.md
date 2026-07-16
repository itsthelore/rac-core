# X Article — The Oracle and the Rewrite: the cache comes home

Long-form X article (Articles format). Voice: plain, numbers carry it —
same register as `X-THREAD.md`, expanded to article length.
Cover image: `banners/x-article-banner-5x2.png` (3200×1280, 5:2 — the
log-scale perf ladder with the headline set on the banner).

---

## Headline

**Search five thousand files: 8.7 s → 43 ms. Same bytes out, every time.**

## Subtitle

Eleven days, five work threads, one frozen oracle. How a Python engine
became a byte-identical Rust engine — including the eight-ADR cache
stack it was supposed to make unnecessary.

---

## Body

Two days ago I posted a thread about rewriting an 11k-line Python engine
in Rust and fuzzing the two against each other until they agreed on
every byte. That thread ended with a boast and a fence. The boast: the
rewrite was so fast we deleted the cache and beat the cache. The fence:
one subsystem — the derived-index cache and its persistent store, eight
ADRs of architecture — was deliberately left unported.

This article is about what happened when the fence came down.

### The null result that started it

The rebuild didn't start with Rust. It started with a contract-preserving
rewrite of the Python tree itself: 1,747 tests held, twice; internal
redundant work fell by a third to a half; and the wall clock moved
0.96–1.05×. Statistically nothing.

That null result was the finding. The profile said the cost wasn't in
the code we could rearrange — it was the interpreter tax and the pinned
markdown parser. You don't refactor your way out of that. You change
runtime, and you do it in a way that can't quietly change behavior.

### The rule

One rule governed everything after: the Python tree was frozen as an
oracle, and the Rust engine had to produce **identical stdout bytes and
identical exit codes** on every command, or the port didn't count. Not
similar. Not equivalent. Identical.

A referee harness pipes the same argv, cwd, and environment into both
binaries and byte-compares the output. Two fuzz campaigns threw ~13,000
mutated inputs at the pair. Every one of the nine bugs found was in my
rewrite, and every one was fixed and pinned. Zero unexplained
divergences remain. Along the way, the fuzzer also found 30+ tiny inputs
that crash the *original* — the oracle earns its keep in both directions.

Three more threads followed the spike: a heal pass (−548 lines, zero
output bytes changed), a closure pass (the 20 remaining CLI commands,
391 new byte-parity cases), and then the last one.

### The cache comes home

Here's the uncomfortable part of the "we deleted the cache" boast: it
was true for a 400-file corpus. On a 5,000-file corpus, the cache-free
fresh walk costs 647 ms per query in Rust — and 8.7 seconds in Python.
The Python engine had grown an answer to that over eight recorded
decisions: a content-addressed cache, a memory-mapped binary index
store, incremental validation, a parallel cold build, and an
event-sourced freshness tracker for the long-lived server. All of it
unported. And the maintainer had recorded a precondition: the Rust
engine doesn't become a candidate for authoritative status until it
carries that stack.

So the last thread ported it — and raised the bar while doing it. The
roadmap allowed the on-disk format to differ, as long as the served
answers matched. Instead, the port made **the store file itself** the
parity surface: the Rust engine writes the oracle's binary store
byte-for-byte. Same magic bytes, same sorted term dictionary, same
postings, same alias maps, same header gates. `diff -r` between a
store written by Python and a store written by Rust over the same
corpus: clean. A parity case even runs both engines' CLIs cold, warm,
and mid-mutation, then compares their entire cache directories.

That's the banner chart. Four bars, log scale, one workload. Python
fresh: 8,654 ms. Python's warm cache — the best that stack ever did:
446 ms. Rust with no cache at all: 647 ms. Rust warm: **43 ms**. And
the fine print is the whole point: every bar returns the same bytes.
The cache is contractually not allowed to change an answer, only its
latency — and now both engines prove it against each other, cache on,
cache off, and while the corpus is being edited under a live server.

### What byte-for-byte finds that "works fine" never would

Holding a rewrite to byte-identity sounds obsessive until you see what
it catches.

It caught an oracle bug: the Python engine's warm search path scores a
repeated query term differently from its own cold path — its cache
violates its own byte-neutrality rule on that input class. The Rust
engine deliberately does not reproduce this; warm equals cold, and the
divergence is on the record.

It caught a myth in our own roadmap: the motivating measurement said an
uncached 5k-file search took ~21.6 seconds. Byte-level accounting
showed most of that was git — a per-match recency lookup that runs
identically warm or cold, in both engines. Outside git the fresh walk
is 0.87 s. The cache's real win is 647 → 43 ms, and the report says
so, because a number with a wrong cause attached is worse than no
number.

And it pinned an accepted imperfection instead of hiding it: an
in-place file rewrite that preserves both size and mtime is invisible
to the fast freshness check in both engines. There's a `--verify`
floor that catches it. Both behaviors are pinned by tests, confirmed
against the oracle by experiment.

### Where it stands

After five threads: 610 byte-parity CLI cases green. The MCP server's
wire frames identical with the cache off (56 + 76 cases) and on
(52 + 71), plus a mutation referee that edits, adds, and deletes files
between tool calls against both servers — every frame byte-identical.
Everything run twice from a clean build, with byte-identical
scoreboards between runs.

The remaining surface is two product fences kept Python on purpose,
and one decision: whether the Rust engine becomes the authoritative
one. The recorded precondition for taking that decision is now
satisfied. The evidence is filed. The call belongs to the maintainer —
which is exactly how an engine built on recorded decisions should
retire its predecessor.

---

## Figure map

| Position | Image |
|---|---|
| Cover / banner | `banners/x-article-banner-5x2.png` — the log-scale perf ladder |

Optional inline figures if the article gets a second image slot:
re-export `fig-cache.png` / `fig-verdict.png` from the spike thread's
set for the "rule" section.
