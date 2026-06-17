---
schema_version: 1
id: RAC-KV8YZQC7G7NW
type: decision
---
# ADR-069: Wayfinder — Prompt-Complexity Routing as a Separate Product

## Status

Proposed

## Category

Product

## Context

`rac route` (ADR-068) was built as an exploration: a deterministic, structural
prompt-complexity scorer that recommends a local or cloud model. It works, but it
sits *outside* the product line every other decision has drawn. Lore is recorded
team knowledge served to agents — "no AI in the core, no inference, no guessing"
(ADR-036 product identity, ADR-002 AI-optional, ADR-035 RAC owns context not
inference, ADR-017 knowledge-not-work, ADR-049 enforcement-is-the-product). A
prompt router is the opposite pole: a runtime *inference* concern that scores
arbitrary prompt text to choose a model to run. It manages no knowledge, validates
no corpus, and has nothing to do with requirements-as-code.

Keeping it inside RAC would blur the one thing the product is clearest about.
Leaving it as an optional extra (the `explorer` / `ingest` pattern) is the wrong
shape too — extras exist for capabilities *within* RAC's domain, and this is not
one. The cleaner move is the topology RAC already chose: a small multi-repo family
under the `itsthelore` org (ADR-064), into which genuinely standalone components
are extracted. Routing is a textbook candidate — it is a leaf feature nothing in
RAC depends on, and its only tie to RAC is heritage.

## Decision

Prompt-complexity routing becomes its own product, **Wayfinder**, in its own
`itsthelore/wayfinder` repository — **fully independent of RAC, with zero runtime
dependency on it.**

- Wayfinder does not import `rac`, depend on the `requirements-as-code` package,
  or read RAC's `.rac/` config namespace. A prompt router must not require
  installing a requirements-as-code knowledge engine — that independence is the
  reason to split, not an incidental detail.
- The two small things it currently borrows are generic, not RAC internals, and
  Wayfinder reimplements them under its own namespace: stripping a leading `---`
  block (the ~17-line, import-free `split_frontmatter`) and a config-file walk-up
  (~10 lines, pointed at Wayfinder's own `wayfinder.toml` / env / flags, never
  `.rac/`).
- ADR-068's boundary carries into Wayfinder unchanged: it scores deterministically
  and recommends; it never invokes a model, selects a provider, reads a
  credential, or tokenizes per a vendor model. The caller runs inference.
- The in-RAC `rac route` stays for now and is **earmarked for removal** once
  Wayfinder ships, following ADR-064's history-preserving safety contract (never
  delete until the capability lives elsewhere). The extraction is sequenced in the
  `wayfinder-extraction` roadmap. *(Update: now done — with Wayfinder at parity in
  the `wayfinder/` subproject, the `rac route` prototype has been removed from RAC;
  this ADR and its siblings are kept as the record. See `wayfinder-extraction`
  Initiative 3.)*
- The relationship to RAC is heritage only: Wayfinder was prototyped here, and its
  scoring shape was inspired by `classification.py`'s `points / ceiling`
  normalization. No shipped runtime dependency remains.

## Consequences

### Positive

- Lore's story stays clean: recorded knowledge, deterministic, no inference. The
  inference-adjacent concern lives in a sibling product, reinforcing ADR-035's
  "RAC owns context, not inference" rather than eroding it.
- Wayfinder can serve anyone running local + cloud models, with no knowledge
  corpus and no Lore adoption required — a far larger audience than RAC's.
- RAC's surface does not grow an out-of-domain command long-term; `rac route`
  becomes a temporary prototype with a named removal owner.

### Negative

- A third name in the org to position and explain: RAC (engine), Lore (knowledge
  product), Wayfinder (routing product).
- ~30 lines of generic utility are reimplemented in Wayfinder rather than shared.
  Accepted deliberately: sharing them would re-couple the audiences the split
  exists to separate, for trivially small, stable code.

### Risks

- The prototype lingers in RAC and the removal never happens. Mitigation: the
  removal is an initiative in the `wayfinder-extraction` roadmap, gated on
  Wayfinder shipping, per ADR-064's cutover discipline.
- The `Wayfinder` name is taken (PyPI / trademark). Mitigation: an availability
  check is the first initiative before the name is committed anywhere public.

## Alternatives Considered

### Keep routing in RAC core

Ship `rac route` as a permanent RAC capability.

#### Disadvantages

- Bloats a knowledge product with a runtime-inference concern, muddying
  ADR-036/002/017 — the clearest claims the product makes.

### Ship routing as a RAC optional extra

Distribute it like the `explorer` / `ingest` extras.

#### Disadvantages

- Extras are for capabilities within RAC's domain; routing is not one. It would
  still travel inside the `requirements-as-code` package and identity.

### Wayfinder depends on the published `requirements-as-code`

Reuse RAC's helpers via the published package (ADR-064's "depend on the package,
never internals" rule).

#### Disadvantages

- Re-couples the audiences the split exists to separate, forcing prompt-routing
  users to install a knowledge engine — for ~30 trivial, stable lines.

Full independence is selected.

## Success Measures

- Wayfinder installs and runs with no `requirements-as-code` present and no `.rac/`
  directory anywhere on the path.
- Wayfinder reaches behavior parity with `rac route`, after which `rac route` is
  removed from RAC with history preserved (ADR-064).
- Requests to "add the router to Lore" are answered by this ADR rather than by
  scope drift.

## Related Decisions

- adr-068
- adr-064
- adr-036
- adr-035
- adr-017
- adr-002
- adr-049

## Related Roadmaps

- wayfinder-extraction

## Related Designs

- prompt-complexity-routing
