---
schema_version: 1
id: DG-ADR-0002
type: decision
tags: [corpus, methodology, supersession, pilot]
---

# ADR-0002: Real-Corpus Pilot — PEP Supersession

## Status

Accepted

## Category

Methodology

## Context

ADR-0001 built the harness and recorded an explicit limitation: the headline
crossover "remains an unvalidated hypothesis until the pinned Claude answering
model runs on **real/public-derived corpora**." Every scenario shipped so far
lives under `scenarios/` and is synthetic — useful for exercising the harness,
but disqualified from being reported as a result by CONTRIBUTING.md rule 2 (no
win-only / hand-authored corpora).

To move the thesis from "plumbing" to "evidence" we need a first corpus that:

1. is derived from a **real, public** decision set, not invented here;
2. contains a genuine, *machine-stated* `supersedes` relationship (the
   discriminating signal the benchmark is built around); and
3. is **byte-for-byte reproducible** by a skeptic, so the corpus itself cannot
   be dismissed as cherry-picked or quietly edited.

Python Enhancement Proposals (PEPs) fit. They are public, carry RFC-2822
headers that state supersession in the artifact itself (`Status: Superseded`,
`Superseded-By:`, `Replaces:`), and the `python/peps` repository can be pinned
to an immutable commit.

## Decision

Add a **real-corpus pilot**: one `superseded_decision` scenario built from the
**PEP 386 → PEP 440** version-scheme supersession, plus a deterministic ingest
tool that produces the corpus from a pinned upstream commit.

- **Pair.** PEP 386 (*Changing the version comparison module in Distutils*,
  `Status: Superseded`, `Superseded-By: 440`) is superseded by PEP 440
  (*Version Identification and Dependency Specification*, `Status: Final`,
  `Replaces: 386`). PEP 440 states verbatim: "this PEP MUST be used for all
  versions of metadata and supersedes PEP 386 … Tools SHOULD ignore any versions
  which cannot be parsed by the rules in this PEP." The supersession is stated
  by the artifacts, not asserted by us.
- **Pin.** Sources are fetched from `python/peps` at commit
  `f866e77409305866038471574f075cd8d83eee9e`. The pin is a constant in
  `ingest/peps.py`; bumping it is a deliberate, reviewable change because it
  changes the corpus.
- **Layout.** Real scenarios live under a new top-level `scenarios_real/`,
  separate from the synthetic `scenarios/`, so the default offline demo never
  silently mixes real and synthetic corpora. Each PEP becomes a `decision`
  artifact (provenance preamble + verbatim reStructuredText); `provenance.json`
  records the upstream URL, sha256, parsed headers, and the header-derived
  `supersedes` edges.
- **Verb mapping.** The scenario uses `verdict: prohibited`: the proposed action
  implements the retired PEP 386 `verlib`/`NormalizedVersion` scheme, which the
  governing decision (PEP 440) forbids. Adherence = recognise PEP 386 is
  superseded and cite PEP 440; citing only PEP 386 and proceeding is the
  `stale_decision_followed` failure. This matches the deterministic scorer's
  superseded-decision branch without a bespoke scorer.
- **Blind gold label.** The gold label was authored from the pinned PEP texts
  with no arm having been run (this environment has no API keys, so no arm
  output could exist), satisfying CONTRIBUTING.md rule 1 by construction.

## Consequences

### Positive

- The benchmark now has a real, public, reproducible corpus exercising the
  discriminating `supersedes` mechanism — the headline is testable on it.
- The ingest tool (`build`/`verify`) lets any reviewer regenerate the corpus and
  prove it matches the upstream pin, turning "trust us" into "re-run it."
- Synthetic and real corpora are physically separated, so the credibility rule
  "synthetic scenarios are never reported as results" is enforced by layout.

### Negative

- The corpus carries large verbatim documents (PEP 440 is ~67 KB). This is
  intentional — trimming would invite "you cherry-picked" — but it is heavier
  than a synthetic scenario.

### Risks

- **Single pair is not a benchmark.** One scenario is a pilot, not a result.
  Mitigation: this ADR scopes it as the first increment; more public pairs
  (e.g. the PEP 345 → 566 metadata supersession) follow before any headline
  claim.
- **Real numbers not yet produced.** Running the pilot needs the `[real]` extra,
  `ANTHROPIC_API_KEY`, and `VOYAGE_API_KEY`, which are absent in the build
  environment. Mitigation: the scenario is offline-validated (loads,
  schema-validates, scores) and the exact real-run command is documented; the
  run appends to `results/` like any other.

## Alternatives Considered

- **PEP 345 → 566 (package metadata).** Also a real, machine-stated
  supersession, but the conflict (metadata field formats) is dryer and maps less
  cleanly onto an action an agent is "on the verge of taking." Kept as the next
  pair, not the first.
- **Mix real scenarios into `scenarios/`.** Rejected: the crossover would graft
  synthetic filler onto a real scenario and the default demo would blur the
  synthetic/real line that CONTRIBUTING.md draws.
- **Hand-transcribe the relevant PEP sections.** Rejected: excerpting is exactly
  the cherry-picking the credibility rules exist to prevent. Verbatim + pinned +
  hashed is the defensible form.

## Related Decisions

- ADR-0001 — Harness Foundation (this pilot realises its "real/public-derived
  corpora" success condition).

## Success Measures

- A reviewer can run `python -m ingest.peps verify --out
  scenarios_real/peps_version_supersession` and reproduce the corpus from the
  pin.
- The scenario loads, schema-validates, and is scored by the same deterministic
  scorer as every other scenario — no bespoke scoring.
- When run with the pinned Claude model on real embeddings, the result (win,
  tie, or loss) is appended to `results/` and reported.

## Review Date

Revisit once a second real pair lands, or if the deterministic scorer's
superseded-decision branch proves too coarse for real, prose-heavy artifacts.
