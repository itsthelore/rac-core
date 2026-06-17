---
schema_version: 1
id: RAC-KV8WY8XAJ55S
type: decision
---
# ADR-068: Prompt-Complexity Routing Boundary

## Status

Proposed

The product home for this capability is now Wayfinder, a separate product
(ADR-069), and the in-RAC `rac route` prototype this boundary governed has since
been **removed** from RAC. The boundary carries into Wayfinder unchanged (its
WF-ADR-0001/0004); this ADR is retained as the historical record of why the line
was drawn.

## Category

Architecture

## Context

A recurring request asks RAC to route prompts to a local or cloud model by
complexity — cheap local inference for easy prompts, the cloud model only when a
prompt warrants it. The deterministic half of that is squarely in RAC's wheel:
`core/classification.py` already scores documents structurally without a model,
and `core/markdown.py` parses prompt bytes offline. A prompt-complexity scorer
is the same pattern on a new axis.

The danger is the other half. The obvious "complete" router calls a model to
judge complexity, or runs the chosen model itself once it has decided. Either
move would put a model call inside RAC — breaking the AI-optional, offline Core
(ADR-002), embedding the judgment ADR-034 reserves for the caller, and taking on
the provider selection, credentials, and inference that ADR-035 places with the
user. RAC's trustworthiness rests on its output being a reproducible function of
repository state; a model call inside that surface forfeits it. This decision
draws the line before any routing capability is built, so the surface cannot
quietly grow a model call later. It is recorded as Proposed: an exploration
boundary, pinned now to keep the future work honest.

## Decision

RAC may compute and expose a **deterministic, structural** prompt-complexity
score and a threshold-based `local`/`cloud` routing recommendation. RAC must not
cross into inference.

- RAC computes the score from structural features only (length proxy from
  word/character counts, section and instruction-step counts, cross-references,
  heading depth, code/table counts) — a pure, byte-stable function of the prompt
  bytes and a user-configured threshold.
- The score is a *fact*, like classification confidence — not a semantic verdict
  about how hard the prompt is, and not a guarantee that the recommendation
  matches any model's real capability.
- RAC must not invoke a model, select a provider or model, read a credential, or
  tokenize per a vendor model. The caller maps the recommendation onto its own
  configured local/cloud endpoints and performs inference.
- This boundary is permanent for Core. A capability that crosses it (an
  in-engine model call, a vendor tokenizer, credential handling) arrives only by
  an explicit superseding decision, never by drift.

The honest claim, echoing ADR-034: RAC asserts *structural* complexity
deterministically; whether that structural score correlates with "this prompt
needs the cloud model" is the caller's empirical calibration, not a RAC promise.

## Consequences

### Positive

- The routing decision is reproducible, testable, and free — no model call to
  decide whether to make a model call.
- Core stays AI-optional and offline; the score works with no key or network.
- The product claim stays honest: RAC supplies the structural fact, the caller
  supplies the judgment and the inference — the same division ADR-034 already
  draws for grounding.
- The scorer reuses the `classification.py` shape, so it is bounded,
  explainable, and golden-testable rather than a parallel mechanism.

### Negative

- RAC's router is "incomplete" by design — it recommends but never routes-and-
  runs; integrators must wire the model call themselves.
- A structural score can mis-rank a prompt whose difficulty is semantic, not
  structural; callers must calibrate the threshold and may override.

### Risks

- The recommendation is read as a capability verdict ("cloud = too hard for
  local"). Mitigation: this ADR names it a structural proxy, and the surface
  reports the contributing features so the recommendation is inspectable.
- Pressure to "just run the prompt" once `rac route` exists. Mitigation: this
  decision makes invocation an explicit boundary; crossing it requires
  superseding this ADR.

## Alternatives Considered

### LLM-as-judge router inside Core

Call a model to assess complexity (and possibly run the chosen model).

#### Advantages

- A single tool gives a "complete" router and a semantically informed verdict.

#### Disadvantages

- Requires a model, key, and network inside an AI-optional Core (ADR-002).
- Non-deterministic output inside the deterministic contract surface.
- Embeds the judgment and inference ADR-034 and ADR-035 place with the caller.

### Per-model tokenizer for the length feature

Use a vendor tokenizer so the length signal matches a specific model's tokens.

#### Advantages

- The length feature aligns with a target model's real token budget.

#### Disadvantages

- Pulls a vendor dependency into an offline Core and ties the score to one model
  family (ADR-035). A word/character proxy stays deterministic and
  provider-neutral.

### Ship nothing; leave routing entirely to callers

Provide no scorer and let each integrator build its own.

#### Advantages

- Zero new surface to maintain.

#### Disadvantages

- Every caller re-implements an ad hoc, untested heuristic. The deterministic
  score is the reusable, testable piece RAC is uniquely placed to own.

Exposing a deterministic structural score and recommendation, while leaving
inference to the caller, is selected.

## Success Measures

- The same prompt scores byte-identically across runs and across the CLI and
  MCP surfaces, with no model, key, or network involved.
- No RAC code path invokes a model, reads a credential, or imports a vendor
  tokenizer to compute the score.
- Requests for an in-engine "LLM router" are answered by this ADR rather than by
  scope drift.

## Related Decisions

- adr-069
- adr-002
- adr-034
- adr-035

## Related Roadmaps

- complexity-based-model-routing

## Related Designs

- prompt-complexity-routing
