# X Thread — The Oracle and the Rewrite

12 posts. Each ≤270 chars. Attach images per the figure map; the thread reads
top-to-bottom without them. Voice: plain, numbers carry it.

---

**Post 1** — attach `banners/banner-5x2.png`

I rewrote a 11k-line Python engine in Rust and fuzzed the two against each
other for 13,000 inputs. Every bug the fuzzer found was in MY rewrite — all 9
of them. And 30+ tiny inputs crash the ORIGINAL. Both things are the point. 🧵

**Post 2**

The setup: rac-core, a requirements-as-code CLI. The engine parses Markdown +
YAML frontmatter, classifies, validates, searches. The experiment: port it to
Rust with one rule — identical stdout bytes and exit codes to the Python
original, on every command, or it doesn't count.

**Post 3**

The rigor came from one decision: the Python tree was FROZEN as an oracle.
Zero edits to src/ or tests/ all spike (diff-verified). A 174-case harness (two oracles)
pipes identical argv/cwd/env into both binaries and compares raw bytes. The
harness itself was tested first: it must go red on 1 corrupted byte.

**Post 4** — attach `figures/fig-gate.png`

Finding 1: the interpreter tax was the whole product problem.
Startup: 202 ms → 2.1 ms (96x).
Validate one file: 206 ms → 3.7 ms (56x).
An agent gate-checking every edit used to pay ~200 ms of Python import tax
per call. That line item is now zero.

**Post 5** — attach `figures/fig-cache.png`

Finding 2: we deleted the cache and got faster than the cache.
Python fresh walk: 1672 ms. Python's warm cache (a mmap store + freshness
events, 8 ADRs of machinery): 223 ms. Rust with NO cache at all: 30 ms.
7x faster than the thing the cache existed to achieve.

**Post 6** — attach `figures/fig-scale.png`

Finding 3: two flat lines, 45x apart.
Throughput is scale-invariant from 1k to 20k files for both engines —
Python at ~700 files/s, Rust at ~35,000 files/s (4 cores). Neither line
bends. They're just on different planets.

**Post 7** — attach `figures/fig-million.png`

Finding 4: the budget line. The project's own perf ADR set a target: index
1M files in 432 s. Python's recorded best: 18.8 minutes. The rewrite's
measured projection: 29 seconds. Same box, 4 vCPUs, no cache.

**Post 8** — attach `figures/fig-fuzz.png`

Finding 5: byte-parity is a fuzzing claim, not a test-suite claim.
~13,000 mutated artifacts, ~120,000 engine-pair runs, 32 mutation operators.
Every divergence root-caused. Campaign closes only after two consecutive
800-input rounds find nothing new.

**Post 9**

My favorite bug: Python's str.strip() counts U+001C-001F as whitespace, so
markdown-it silently swallows a control char in list items. My port kept it.
One invisible byte, one red scoreboard line, one 591-case oracle-generated
regression grid later: closed.

**Post 10**

The honest wall: this is the engine core, not the product. 21 CLI commands
aren't ported. Ingestion stays Python on purpose. And the Rust is BIGGER —
17.2k lines vs 11.1k — because Python gets YAML free from PyYAML and I had
to port those exact semantics by hand (~4k lines).

**Post 11**

Also honest: the original engine crashes — uncaught traceback, empty stdout —
on 30+ minimized fuzz inputs, some 12 bytes long. The rewrite reports a normal
finding instead. A rewrite gated on "match the oracle" forces you to decide:
mirror the crash, or document the divergence. We documented.

**Post 12** — attach `figures/fig-verdict.png`

Verdict: 174/174 byte-identical across two oracles (mainline + the new retrieve surface). 0 unexplained divergences. 56x gate speed.
29 s per million files against a 432 s budget.
Full interactive report (method, figures, every rerunnable command):
https://claude.ai/code/artifact/e7ab3783-f1e6-4c4b-bbdc-f17d3680cb0b

---

## Figure map

| Post | Image |
|---|---|
| 1 | banners/banner-5x2.png |
| 4 | figures/fig-gate.png |
| 5 | figures/fig-cache.png |
| 6 | figures/fig-scale.png |
| 7 | figures/fig-million.png |
| 8 | figures/fig-fuzz.png |
| 12 | figures/fig-verdict.png |

## Alt-text

- **banner-5x2.png**: Newsprint-style banner reading "The oracle and the
  rewrite. 174 cases. Zero unexplained bytes." with paired bars comparing
  1672 ms (Python) to 30 ms (Rust) and a pass checklist: parity, fuzz dry,
  perf budget, examiner frozen.
- **fig-gate.png**: Bar chart of median wall-clock. Startup: Python 202.4 ms
  vs Rust 2.1 ms (96x). Validate one file: Python 206.4 ms vs Rust 3.7 ms
  (56x). The Rust bars are a few pixels wide at scale.
- **fig-cache.png**: Three bars for validating the live 423-artifact corpus:
  Python fresh 1672 ms, Python warm cache 223 ms, Rust with no cache 30 ms,
  annotated "the whole cache stack buys this" on the 223 ms bar.
- **fig-scale.png**: Two aligned panels of throughput vs corpus size (1k, 5k,
  20k files). Rust holds flat around 35,000 files/s; Python holds flat around
  700 files/s. Both lines are flat; the gap is 45-52x.
- **fig-million.png**: Horizontal bars projecting a 1-million-file index:
  budget line 432 s, Python recorded 1128 s, Rust projected 29 s.
- **fig-fuzz.png**: Stat-tile card: 13,000 fuzz inputs, 120,000 engine-pair
  runs, 9 bugs found and fixed in the rewrite, 30+ inputs that crash the
  original, 0 unexplained divergences, closed on 2 consecutive dry rounds.
- **fig-verdict.png**: Four verdict tiles: byte-identical parity cases; 56x
  single-file gate; 29 s per million files (budget 432 s); 0 unexplained
  divergences.
