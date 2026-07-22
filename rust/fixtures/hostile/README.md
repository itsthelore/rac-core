# Hostile-input regression fixtures (RAC-KXBPS7SRM6ZB REQ-004)

The differential-fuzz oracle-crash catalog (`rust/fuzz/findings2/`,
campaign reports `rust/fuzz/CAMPAIGN-1.md` / `CAMPAIGN-2.md`, curated
repros `rust/fuzz/pinned/oracle-crashes/`) distilled to one minimized
fixture per crash CLASS. Each input crashes the frozen Python oracle
with an uncaught traceback; the native engine must stay total and
report issues gracefully. Consumed ONLY by the native-only cargo test
`rac-engine/tests/hostile_inputs.rs` — never by an oracle-refereed
parity case (the oracle crashes on these anywhere in its walk, so keep
this directory out of every parity-case sandbox and fixture tree).

| fixture | class | oracle crash | native behavior |
| --- | --- | --- | --- |
| `class-a-unhashable-list-key.md` | A — unhashable YAML mapping key (list, `? []`) | `TypeError: unhashable type: 'list'` in `frontmatter._no_duplicates` | error issue `internal-oracle-divergence` with the mirrored exception line |
| `class-a-unhashable-dict-key.md` | A — unhashable YAML mapping key (flow mapping `{a1}:`) | `TypeError: unhashable type: 'dict'` | same marker issue, `'dict'` variant |
| `class-b-read-cap.md` | B — `DECIDED_MAX_FILE_BYTES` read-crash zones (any readable file) | `OverflowError: cannot fit 'int' into an index-sized integer` (cap >= 2^63-1) / `OverflowError: byte string is too large` (2^63-34 .. 2^63-2) | `FileCap::OracleCrash` marker at the read stage; incremental reads never preallocate the cap |
| `class-c-stdin-surrogate.md` | C — undecodable bytes on stdin (PEP 383 surrogateescape) | `UnicodeEncodeError` when lone-surrogate text later hits a strict `str.encode` | plane-16 sentinel decode (`pycompat::decode_stdin_surrogateescape`), total parse |
| `class-d-nonutf8-decision.md` | D — strict-UTF-8 re-read of a classified artifact (`export _body_markdown`) | `UnicodeDecodeError` before any output | lossy decode + `non-utf8-content` warning; export keeps the lossy body |

Classes and boundaries per `rust/fuzz/pinned/oracle-crashes/README.md`;
the class-B env-value grid is additionally asserted in
`rac-engine/tests/frontmatter_vectors.rs`.
