# Pinned oracle-crash repros (divergence by design)

These inputs crash the Python oracle with an **uncaught traceback**. Per
PORT-CONTRACT decision 3, the Rust engine does not crash: it reports the
mirrored exception line as an `internal-oracle-divergence` issue and keeps
going. Because the oracle dies, byte parity is impossible **by design** —
these repros are therefore *excluded from the parity suite* and listed here
(and in the PARITY-REPORT gap list) instead.

Every repro below was re-verified against the campaign-2 engine build:
the oracle exits via traceback, the Rust engine exits cleanly with the
marker issue.

## Class A — unhashable / mismatched YAML constructs (campaign-1 finding 001)

Reproduce: put `repro.md` at `corpus/case.md` under an empty dir, run any
covered command that parses it (`validate`, `stats`, `relationships`,
`review`, `find`, `resolve`, `export` — file or directory arm) under the
parity env.

- `unhashable-key/` — `? []` complex mapping key: oracle
  `TypeError: unhashable type: 'list'` from `frontmatter.py _no_duplicates`.
  Campaign 2 confirmed the same class is reachable through EVERY corpus
  command (validate/stats/relationships/review/export/find/resolve; file,
  dir, trailing-slash, `./`-prefixed and `//` path arms, and dir walks with
  multi-file corpora), not just `validate` — see `rust/fuzz/findings2/`
  entries suffixed `-oracle-crash`.

## Class B — `RAC_MAX_FILE_BYTES` in the read-crash zone (campaign-2 finding 004)

No special corpus needed — ANY readable file crashes the oracle's
`parse_file` at `fh.read(cap + 1)`:

- `RAC_MAX_FILE_BYTES=99999999999999999999` (any cap >= 2^63 - 1):
  `OverflowError: cannot fit 'int' into an index-sized integer`
- `RAC_MAX_FILE_BYTES=9223372036854775806` (2^63 - 34 .. 2^63 - 2):
  `OverflowError: byte string is too large`
- caps below 2^63 - 34 but above the machine's allocatable memory
  (e.g. `1099511627776` on the campaign box): `MemoryError` —
  **environment-dependent**, deliberately NOT mirrored by the Rust engine
  (it reads incrementally and never preallocates the cap; such runs
  simply succeed on the Rust side).

The Rust engine mirrors the two deterministic OverflowError zones as
marker issues (`rust/rac-engine/src/frontmatter.rs`, `FileCap`); boundaries
were pinned empirically against CPython 3.11 and are asserted in
`rust/rac-engine/tests/frontmatter_vectors.rs`.

## Class D — export re-reads with strict UTF-8 (campaign-2)

`export DIR [--json|--documents]` re-reads each classified artifact in text
mode (`open(path, encoding="utf-8")`, `services/export.py _body_markdown`)
with the STRICT error handler — even though the classification walk decoded
the same file with `errors="replace"`. A classified artifact containing
invalid UTF-8 therefore crashes the oracle's export with an uncaught
`UnicodeDecodeError` before anything is printed. The Rust engine keeps its
lossy-decoded body and exports normally (no per-artifact issue channel
exists on this surface).

- `export-nonutf8/` — a recognizable decision whose body contains a raw
  `0xCC` byte; `rac export corpus --json` / `--documents` crash the oracle.

## Class C — surrogate text meets `str.encode` (campaign-2, stdin arm)

`validate -` with undecodable stdin bytes produces lone-surrogate text
(PEP 383). If such text later hits a strict `str.encode("utf-8")` in the
oracle (e.g. `exceeds_byte_cap`'s near-the-cap fast path), the oracle dies
with `UnicodeEncodeError`. Only reachable when stdin length lands inside
`(cap/4, cap]` with invalid bytes present; catalogued when the fuzzer
surfaces a concrete repro.
