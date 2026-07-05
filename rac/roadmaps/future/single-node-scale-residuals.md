---
schema_version: 1
id: RAC-KWSTS2DCPVNH
type: roadmap
---
# Single-Node Scale Residuals

## Status

Planned

Unscheduled — the measured walls left standing after the single-node-scale
rebuild, each with a designed fix. The rebuild proved scale-invariance for
id-shaped reads (get-artifact and get-related hold three to six
milliseconds from one thousand to one million artifacts on the reference
node, resident set 6.2 of 15 gigabytes) and these items carry what the
measurements showed is not yet invariant.

## Outcomes

- Search tail latency is candidate-bound and flat: p99 under the budget at
  every corpus size, not only the median.
- A changeset splice costs time proportional to the changeset, not the
  corpus: editing a thousand files updates the index in seconds at any
  size.
- Incremental validation is index-backed: re-validating a changeset does
  not re-parse the corpus.
- The server's resident set stays bounded past three million artifacts.
- The scale harness's synthetic corpora keep query selectivity
  size-independent, as real corpora do.

## Initiatives

- Per-field token storage in the document store, so candidate scoring
  reads stored tokens instead of re-tokenising each candidate (measured:
  per-candidate rescoring of one to three milliseconds drives search p99
  to 526 ms at one hundred thousand and seconds at one million; the trade
  is roughly double index size).
- A segmented index format whose refresh splices only affected segments
  (measured: the atomic whole-directory rewrite costs 8.8 minutes for a
  thousand-file changeset at one hundred thousand artifacts even though
  detection is changeset-bound).
- Index-backed incremental validation: persist per-file validation
  results keyed by content hash so a changeset re-validates only changed
  files (measured: the CLI validate path stays corpus-bound — 8 seconds
  at ten thousand, minutes at a million).
- A lazily materialised document store: serve entries from the mapped
  blobs on demand instead of materialising every entry in memory
  (measured: 6.2 gigabytes resident at one million extrapolates past the
  node at roughly three million).
- Harness realism: scale the generator vocabulary with corpus size so
  synthetic query selectivity stays size-independent, and measure the
  three-million and ten-million points on a node with the cores and disk
  to hold them (measured top point here: one million on four cores,
  thirty gigabytes).
- Restate the cold-build budget per core (measured: 432 seconds per
  million artifacts across four cores, linear and parallel; the recorded
  two-minute budget assumed a several-fold larger node).

## Success Measures

- The scale gate passes every budget row at the largest measured size,
  with flatness held from the smallest.
- Each landed initiative cites a before-and-after measurement from the
  same harness.

## Assumptions

- ADR-100 and ADR-101 remain the recorded architecture; these items
  extend the index, they do not replace it.
- The examiner and the byte-parity gate remain frozen; every initiative
  lands behavior-frozen or extends tests deliberately.

## Risks

- Storing field tokens roughly doubles index size; if disk becomes the
  binding constraint the trade needs its own decision record.
- A segmented format adds merge-on-read complexity; byte-parity across
  segment boundaries is the regression surface and must be pinned before
  the format lands.

## Related Decisions

- RAC-KWS8TRXGQWHC
- RAC-KWS8TTSKMGQA

## Related Roadmaps

- single-node-scale
