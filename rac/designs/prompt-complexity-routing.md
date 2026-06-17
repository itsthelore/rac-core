---
schema_version: 1
id: RAC-KV8WY7T7S4JZ
type: design
---
# Prompt-Complexity Routing

## Context

> **Historical note.** This design described the in-RAC `rac route` prototype,
> which has since been **removed** from RAC: the capability now lives in the
> separate Wayfinder product (ADR-069), where this design was carried forward and
> extended. This document is retained as the record of the original approach.

This design is the *how* for the `complexity-based-model-routing` future
roadmap item: a deterministic way to score a prompt's complexity and recommend
a `local` or `cloud` model, without RAC ever calling a model. The boundary it
implements is ADR-070; the determinism and AI-optional posture it inherits are
ADR-002 and ADR-034; the rule that RAC never owns inference is ADR-035.

The mechanism already exists in spirit. `core/classification.py` scores a
document deterministically by structural fit — `points / ceiling` over which
sections are present — and `core/markdown.py` parses prompt bytes into a
content-free AST offline. This design reuses that machinery for a new axis:
instead of "which artifact type does this look like," it asks "how structurally
heavy is this prompt," and turns the answer into a routing recommendation.

## User Need

A caller — an agent loop, a skill, an editor extension — wants cheap local
inference for simple prompts and the cloud model only when a prompt warrants it,
and wants that decision to be reproducible, testable, and free (no model call to
decide whether to make a model call). They need a function they can hand a
prompt and get back: a stable score, the features behind it, and a `local`/
`cloud` recommendation against a threshold they control. They then invoke their
own model — RAC must not do that for them. The prompt may be a stored
`rac/prompts/` artifact or arbitrary text passed on stdin; both must score the
same way.

## Design

### Deterministic feature set

All features are structural, offline, and reproducible — no model, no network,
no per-vendor tokenizer. They are scanned line-by-line from the prompt *body*
(a leading YAML frontmatter block is stripped first, so a stored Prompt artifact
and the same prompt on stdin score identically), with lines inside fenced code
blocks excluded from structural matching so a code sample's contents do not
masquerade as headings or lists:

- **Length proxy** — a deterministic word count. Explicitly *not* model
  tokenization; v0.6.2 already deferred token counting and a per-model token
  count would pull a vendor dependency into an offline Core (ADR-035).
- **Heading count and depth** — number of headings and the maximum nesting
  depth.
- **Instruction-step count** — list items (bulleted or numbered), a proxy for
  how much the prompt asks the model to do.
- **Cross-reference count** — Markdown links in the body.
- **Code-block and table counts** — structured payloads the model must track.

### Scoring

The features combine into a single normalized 0..1 score using the same
`points / ceiling` normalization shape as `classification.py`: each feature
contributes a weighted, capped amount toward a fixed ceiling, so the result is
bounded, pure, and byte-stable for identical input. The scorer is a pure
function — same bytes plus same configured weights yield the same score — and is
the single path both the stored-artifact and stdin inputs flow through.

### Recommendation

The score is compared to a configured threshold: below it the recommendation is
`local`, at or above it `cloud`. This is a *structural threshold result*, not a
semantic judgment of difficulty. The reported object carries the score, the
contributing feature values, the threshold used, and the recommendation, so the
caller can see *why* — and recalibrate — rather than trust an opaque verdict.

### Surfaces

- **CLI** — `rac route <file>` and `rac route -` (stdin). Human-readable output
  by default, `--json` for machines, and a documented exit-code contract (the
  CLI-contract principle). Read-only; emits no content and calls no model.
- **`lore`/MCP fact tool** — an additive read-only tool returning the identical
  deterministic object, in ADR-030's additive-tool style, so an in-loop agent
  consults it like the existing Guide tools. A fact, never a verdict the server
  acts on.
- **Configuration** — the threshold (and, if kept tunable, the feature weights)
  live in `.rac/config.yaml`, so a team calibrates the cut to its own local/
  cloud capability without a RAC release. Sensible defaults ship so the surface
  works with zero configuration.

### What RAC does not do

RAC stops at the recommendation. It does not invoke a model, select a provider
or model, read a credential, or tokenize per a vendor model. The caller maps
`local`/`cloud` onto its own configured endpoints and runs inference. This is
the ADR-070 line, drawn here so the surface cannot quietly grow a model call.

## Constraints

- Offline, AI-optional (ADR-002): pure function of prompt bytes plus configured
  threshold; no model, key, or network.
- Facts, not verdicts (ADR-034): a structural score and recommendation, never a
  semantic verdict the engine acts on.
- RAC owns context, not inference (ADR-035): no provider, credential, or vendor
  tokenizer.
- Deterministic and additive: byte-stable output proven by golden tests; new
  verb and tool add surface without changing existing behavior.

## Rationale

A deterministic structural router is the piece worth owning because it is the
piece an LLM-judge router does *badly*: it is reproducible, testable, costs
nothing, and needs no key. Keeping the model invocation in the caller keeps RAC
honest under ADR-034 and offline under ADR-002, and respects ADR-035's rule that
inference and credentials are the user's. Reusing the `classification.py`
scoring shape means the new axis behaves like the existing one — bounded,
explainable, golden-tested — rather than inventing a parallel mechanism.

## Alternatives

- **LLM-as-judge router inside Core** — rejected: non-deterministic, requires a
  model and key in an AI-optional Core (ADR-002), and embeds the judgment
  ADR-034 reserves for the caller.
- **Per-model tokenizer for the length feature** — rejected: pulls a vendor
  dependency into an offline Core and ties the score to one model family
  (ADR-035); a word/character proxy stays deterministic and provider-neutral.
- **Ship nothing; leave routing entirely to callers** — rejected: every caller
  would re-implement an ad hoc, untested heuristic; the deterministic score is
  the reusable, testable piece RAC is uniquely placed to provide.

## Accessibility

Both surfaces are plain text: the CLI output is readable and diffable, the JSON
is machine-consumable, and the recommendation is stated in words
(`local`/`cloud`) with its supporting numbers — no reliance on colour or a
graphical display.

## Style Guidance

Output leads with the recommendation and the score, then lists the contributing
features compactly — scannable, like `rac inspect`. Copy frames the result as a
structural proxy and a recommendation, never as a verdict on whether a model can
handle the prompt.

## Open Questions

- Default weights and the default threshold, and how they are documented.
- Whether complexity is best expressed as one scalar or a small feature vector
  the caller thresholds itself.
- How a caller calibrates the threshold against real local/cloud capability, and
  whether RAC should ship any guidance for that calibration.

## Related Decisions

- adr-069
- adr-070
- adr-002
- adr-034
- adr-035

## Related Roadmaps

- complexity-based-model-routing
- wayfinder-extraction
