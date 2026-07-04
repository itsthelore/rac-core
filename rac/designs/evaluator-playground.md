---
schema_version: 1
id: RAC-KWQAZZPA101N
type: design
---
# Zero-Install Evaluator Playground

## Status

Proposed

Exploratory — Opportunity 4 of `adoption-opportunity-survey`. The highest-ceiling
activation lever, and a real build gated on a hosting decision, so it ranks
below the cheap distribution wins. Not an accepted build.

## Context

`rac-growth-adoption` optimises the *install path* — a sub-five-minute,
zero-config cold start — but it never removes the install itself, and every
minute before first value loses evaluators. An evaluator who has not yet decided
to install anything has no way to see Lore work. Competing developer tools that
win on adoption ship a zero-install "try it in the browser" surface;
`rac-localview` is a *local* viewer and the capture form
(`lore-frontend-optionality` Thread E) is for *authors*, so a public *evaluator*
surface is not covered.

## User Need

- An **evaluator** wants to write or paste a decision and instantly see it
  validated and classified — the "what does this tool actually do" moment —
  without installing, configuring, or signing up.
- A **sharer** wants a permalink to the result to send to a colleague — the
  distribution loop that absorbs the survey's Opportunity 5.

## Design

A minimal public page: paste or type an artifact, and it runs the real engine
surfaces — `rac validate`, `rac inspect` (classification), and a small
relationship view — showing the exact output the CLI produces, with a shareable
permalink to the input+result. Two engine-delivery options, both keeping the
engine as the single source of truth:

1. **Hosted `rac` endpoint** — a thin `lore-*` service that runs `rac validate
   -` / `rac inspect` on submitted text and returns the JSON the page renders.
   The pasted text is ephemeral; nothing is stored beyond an optional
   short-lived permalink (ADR-024 — not a content store).
2. **Pyodide / WASM** — the engine (or the thin TS client over the contract,
   ADR-063) runs in the browser, no server round-trip.

Either way the page is a thin client over the published contract; it
reimplements no engine logic (ADR-063) and renders the same bytes the CLI does.

## Constraints

- **Thin client over the contract (ADR-063).** The playground calls `rac`
  surfaces; it never re-derives validation or classification.
- **Not a content store (ADR-024).** Pasted text is ephemeral; a permalink, if
  offered, stores the minimal input+result for sharing, not a corpus.
- **Facts, not verdicts (ADR-034).** It shows validation output and
  classification, never a quality score of the user's decision.
- **Brand/topology (ADR-068).** A hosted playground is a `lore-*` product; any
  engine change to support a browser build is `rac-*` and additive (ADR-007).

## Rationale

It attacks the one activation cost the recorded work leaves standing — the
install itself — and adds a distribution loop via shareable permalinks. It ranks
below the badge and PR-comment because it is a genuine build with an unsettled
hosting model, not a projection of existing output; but its ceiling (converting
evaluators who would never install a CLI) is the highest of the set.

## Alternatives

- **A recorded demo GIF only.** Already planned (`growth-demo-gif`); it shows the
  loop but the evaluator cannot *try* it — passive, not hands-on.
- **Ship the desktop/live viewer instead.** Different audience (a viewer for an
  existing corpus vs. a try-it surface for a newcomer); complementary, not a
  substitute.
- **Do nothing.** Acceptable only if the install path is judged low enough
  friction; the survey's bet is that removing the install entirely is a distinct,
  higher-ceiling lever.

## Accessibility

Keyboard-first and screen-reader legible: the paste area, the run action, and the
result must be reachable and announced without a pointer, matching the
Explorer's keyboard-first conventions (ADR-028). Output preserves provenance —
verbatim engine output distinct from any explanatory chrome.

## Style Guidance

Minimal and honest — the page shows the real CLI output, not a prettified
reinterpretation. No marketing chrome around the result; the determinism *is*
the pitch. Name the surface under the `lore` brand (ADR-036).

## Open Questions

- Hosted `rac` endpoint or Pyodide/WASM — which delivery model, given the engine
  is Python and the TS client is a thin contract consumer (ADR-063)?
- Does a shareable permalink require any persistence, and if so what is the
  minimal, non-content-store shape (ADR-024) and its retention?
- Where does it live under the `lore-*` brand (ADR-068), and does it reuse
  `rac-localview` rendering or stand alone?

## Related Decisions

- adr-007
- adr-024
- adr-028
- adr-034
- adr-036
- adr-063
- adr-068

## Related Roadmaps

- growth-programme

## Related Requirements

- rac-growth-adoption
