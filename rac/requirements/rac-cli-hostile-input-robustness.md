---
schema_version: 1
id: RAC-KXBPS7SRM6ZB
type: requirement
---
# RAC CLI Robustness to Hostile Markdown in the Repository Walk

## Status

Proposed

## Problem

Every `rac` command that indexes the repository — `rac new` most
visibly, because it walks the whole repository root to mint a unique
id — parses every Markdown file it encounters. A single file with
malformed frontmatter (for example a YAML mapping whose key is itself a
list) crashes the Python engine with a raw traceback
(`TypeError: unhashable type: 'list'` in the duplicate-key check)
instead of reporting a validation issue. Observed 2026-07-12: `rac new`
was unusable in a checkout containing fuzz repro fixtures under
`rust/fuzz/`, even though the `rac/` corpus itself was healthy; the
fixtures had to be moved aside to mint an artifact.

This contradicts two recorded positions. ADR-065 makes artifact content
untrusted input — an engine that can be crashed by a Markdown file in
the tree fails that posture. And the core principle that invalid but
recognizable artifacts classify and then fail validation is violated
when parsing raises instead of returning issues. The Rust engine
already meets the bar: the native-engine spike's differential fuzzing
catalogued this exact input class as oracle-crash divergences — inputs
the Rust engine handles gracefully and the Python engine dies on.

## Requirements

- [REQ-001] Parsing a Markdown file with malformed frontmatter — including YAML constructs outside the bounded subset, unhashable mapping keys, and every input in the fuzz oracle-crash catalog — never raises an unhandled exception; it yields a parse/validation issue attributed to that file.
- [REQ-002] `rac new <type> <path>` succeeds whenever the target path is writable and the id can be minted, regardless of unparseable Markdown elsewhere in the repository; encountered unparseable files are skipped for id-collision purposes (or surfaced as warnings), never fatal.
- [REQ-003] Corpus-walking commands (`validate`, `stats`, `relationships`, `review`, `find`, `resolve`, `export`, `new`) report a malformed file as a per-file finding with a non-zero exit where the command's contract requires it, and continue processing the remaining files.
- [REQ-004] The fuzz oracle-crash catalog (`rust/fuzz/findings2/` classes, pinned in the campaign reports) is converted into pinned regression fixtures for the native engine's graceful handling, so the class stays closed as the native CLI surface grows.

## Delivery Path

Recorded maintainer direction (2026-07-12): this capability is
delivered from the **native (Rust) engine side**, not by hardening the
Python engine. The Rust engine already satisfies REQ-001 and REQ-003
by construction — differential fuzzing catalogued every crash input as
an oracle-crash divergence the Rust engine handles gracefully — and
REQ-002 lands with the native `new` command as part of closing the CLI
parity gap. The Python engine is not modified: it remains the frozen
parity oracle, and the shipped Python CLI knowingly retains the crash
until ADR-063 is flipped (itself gated on the native derived-index
roadmap item). Consequence: no oracle bytes change, so no port-contract
spec revision is required for this capability.

## Success Metrics

- `rac new` mints an artifact in a checkout containing the full fuzz
  repro catalog on disk, with no files moved aside.
- A differential fuzz round reports zero oracle-crash findings: neither
  engine crashes on any generated input; divergences, if any, are
  behavioral and enumerable.
- No `rac` command emits a Python traceback for any Markdown input.

## Risks

- Swallowing parse crashes too broadly could mask genuine engine bugs;
  the issue objects must preserve the underlying error class and file
  path so nothing is silently dropped.
- The shipped Python CLI keeps the crash until ADR-063 flips; if a
  user-facing report arrives before then, the decision to leave the
  Python engine untouched may need revisiting.
- The native `new` command mints a fresh id per invocation, so its
  output is not naturally byte-comparable; the parity harness needs an
  id-injection seam (as with `RAC_RS_VERSION`) before REQ-002 can be
  refereed.

## Assumptions

- The bounded YAML subset (schema_version and id only) remains the
  frontmatter contract; robustness here means failing gracefully, not
  widening what is accepted.
- The walk continues to parse non-corpus Markdown it encounters at the
  repository root; scoping the id-mint walk to the RAC directory is a
  possible complementary change but is not assumed by REQ-001–003.

## Related Decisions

- ADR-065

## Related Roadmaps

- native-engine-spike
