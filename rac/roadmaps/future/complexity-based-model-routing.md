---
schema_version: 1
id: RAC-KV8WY6Q9DFXZ
type: roadmap
---
# RAC — Complexity-Based Model Routing (Future)

## Status

Achieved

Achieved by spinning the capability out as the separate **Wayfinder** product
(ADR-069), rather than shipping it inside RAC. The in-RAC `rac route` prototype
that explored this has since been removed (its code, tests, CI battery, and
`docs/cli.md` section); this item is retained as the historical record of the
exploration. The boundary it established lives on in Wayfinder.

## Context

A recurring external question: "how do I deterministically route a prompt to a
local model or a cloud model based on how complex it is?" The instinct is
sound — cheap local inference for the easy prompts, the expensive cloud model
only when the prompt warrants it — but the usual answer reaches for an
LLM-as-judge router, which is non-deterministic, costs a model call to decide
whether to make a model call, and cannot be reproduced or tested.

RAC is unusually well placed to own the deterministic *half* of this. RAC
already scores artifacts structurally without any model: `classification.py`
computes a reproducible fit from which sections a document has
(`points / ceiling`), and the same parsing machinery (`core/markdown.py`) is
content-free and offline. "Score a prompt's complexity" is that same pattern
applied to a new dimension. What RAC must *not* do is cross the line the corpus
already drew: it serves deterministic facts and leaves judgment and inference to
the caller (ADR-034), stays AI-optional and offline (ADR-002), and never owns
provider selection, credentials, or model invocation (ADR-035).

So the honest split this item explores: RAC computes a reproducible complexity
score over a prompt's structure and maps it to a `local`/`cloud` recommendation
against a configurable threshold; the consuming agent or skill takes that
recommendation and invokes its own configured model. RAC stops at the
recommendation. The boundary is drawn in ADR-070; this item records the product
intent. It is considered, not scheduled — when scheduled it graduates out of
`future/` into a versioned series and grows an implementation contract.

## Outcomes

- A prompt — a stored `rac/prompts/` artifact or arbitrary text on stdin —
  yields a single, reproducible structural complexity score, identical bytes
  for identical input.
- That score maps to a deterministic `local`/`cloud` recommendation against a
  threshold the user configures, with the contributing features and the
  threshold reported alongside, so the recommendation is explainable.
- Both input scopes share one scorer: stored Prompt artifacts and raw stdin
  text route through the same deterministic path, so a caller gets the same
  answer whether the prompt lives in the corpus or is passed in live.
- The boundary holds end to end: RAC never tokenizes per a vendor model, never
  reads a credential, never calls a model — the caller maps the recommendation
  onto its own local/cloud endpoints and runs inference.

## Initiatives

### Initiative 1 — Deterministic prompt-complexity scorer (Core)

A pure scoring function over a parsed prompt, reusing `core/markdown.py` and the
structural-feature instinct behind `classification.py`. It derives only
structural, offline, reproducible features (length proxy from word/character
counts — not model tokenization; section and instruction-step counts;
cross-reference count; heading depth; code-fence and table counts; presence of
Constraints/Examples) and combines them into a normalized 0..1 score the same
deterministic way `classification.py` normalizes fit. No new recorded artifact
field; the score is computed, not stored. The *how* is in the
`prompt-complexity-routing` design.

### Initiative 2 — `rac route` CLI surface

Expose the score and recommendation through a new additive verb: `rac route
<file>` and `rac route -` (stdin), with human output, `--json`, and a documented
exit-code contract — the CLI-contract principle. Output reports the score, the
contributing features, the threshold used, and the `local`/`cloud`
recommendation. Read-only; emits no content and calls no model.

### Initiative 3 — `lore`/MCP fact tool

An additive read-only tool returning the same deterministic object (score +
features + recommendation) so an in-loop agent can consult it the way it
consults the existing Guide tools — a fact, in ADR-030's additive-tool style,
never a verdict the server acts on.

### Initiative 4 — Configurable threshold and weights

The decision boundary is the user's, not a hard-coded constant. The threshold
(and, if the design keeps weights tunable, the feature weights) live in
`.rac/config.yaml` so a team calibrates the cut to its own local/cloud
capability without a RAC release.

## Constraints

- AI-optional, offline (ADR-002): scoring requires no model, key, or network;
  it is a pure function of the prompt bytes and the configured threshold.
- Facts, not verdicts (ADR-034): RAC emits a structural score and a
  recommendation; the caller decides and invokes. No model call inside Core.
- User owns inference (ADR-035): RAC never selects a provider, reads a
  credential, or tokenizes per a vendor model.
- Determinism: identical input plus identical configured threshold yields
  byte-identical output, proven by golden tests.

## Non-Goals

- Calling, hosting, or selecting any model — local or cloud.
- Provider or credential selection of any kind.
- Per-vendor tokenization or a model-specific token count.
- A semantic verdict on prompt difficulty, or any promise that the structural
  score predicts which model can actually handle the prompt — that correlation
  is the caller's empirical calibration (see ADR-070).

## Success Measures

- The same prompt scores byte-identically across repeated runs and across the
  CLI and MCP surfaces.
- A stored Prompt artifact and the same text on stdin produce the same score.
- Moving the configured threshold moves the `local`/`cloud` recommendation
  predictably, with no other behavior change.
- Feature requests for an "LLM router" inside RAC are answered by ADR-070 rather
  than by scope drift.

## Assumptions

- Structural complexity is a useful *proxy* worth exposing deterministically,
  even though it is not a guarantee of model capability; callers calibrate.
- One scalar score with reported contributing features is enough to start; a
  richer vector can come later if calibration demands it (an open question in
  the design).
- Demand is real but unproven; this stays considered until a concrete consumer
  (a skill or extension) needs it.

## Risks

- The score is mistaken for a capability verdict ("cloud means the prompt is too
  hard for local"). Mitigation: ADR-070 names it a structural proxy; output
  reports the contributing features so the recommendation is inspectable.
- Pressure to "just add the model call" so `rac route` also runs the prompt.
  Mitigation: ADR-070 makes invocation an explicit boundary RAC does not cross;
  crossing it requires superseding the ADR, not drifting.

## Related Decisions

- adr-069
- adr-070
- adr-002
- adr-034
- adr-035

## Related Designs

- prompt-complexity-routing

## Related Roadmaps

- wayfinder-extraction
