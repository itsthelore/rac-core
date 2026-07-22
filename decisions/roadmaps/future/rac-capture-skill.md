---
schema_version: 1
id: RAC-KVSPDB82WFK0
type: roadmap
---
# RAC Capture Skill (Future)

## Status

Planned

Unscheduled — captured as future intent, not yet on a release. This is the first
concrete build proposed by the `lore-capture-surfaces` design (Host A); it is a
near-zero-build item gated only on the decision to start, and it must not
displace nearer-term committed work.

**Update — Initiative 1 (the `rac-capture` skill) shipped** (merged in PR #193).
The roadmap stays `Planned` rather than `Achieved` because Initiatives 2–3 (the
host surfaces) remain deferred; this records that the shared capture core now
exists.

## Context

`lore-frontend-optionality` established that Lore's binding constraint is
**authoring**: the corpus has to be written before grounding it has any value,
and the people who own the source knowledge — product managers — cannot get a
decision or requirement into the corpus without git, Markdown, and an IDE.
`lore-capture-surfaces` answered the *how* with one organizing idea — **the
skill is the brain, the host is the interface** — and named the cheapest first
move: an agent-interview capture skill that runs in the harnesses people already
have.

That skill is `rac-capture`. It is the interview twin of the existing
`rac-import` skill (`src/rac/skills/rac-import/SKILL.md`): same deterministic
spine, but the *source* is a short interview with the author instead of a
supplied document. It interviews the author in plain language, drafts an artifact
against the **real schema** (`rac schema <type>`, never invented fields), has the
human ratify type, title, and each relationship, scaffolds the file with
`rac new` (which mints the opaque id), and closes on `rac validate`. The model
that runs the interview lives in the harness, never in `rac-core` (there is no
LLM client in the engine), so the skill adds no AI to the core (ADR-002,
ADR-067).

This roadmap records the *what and why* and the acceptance bar for that build,
kept as recorded intent rather than a scheduled release. The host surfaces the
design also describes (desktop overlay, Slack bot, web modal) are explicitly out
of scope here — they wrap this same skill later.

## Outcomes

- A non-technical author can record a decision or a long-lived requirement
  (ADR-020) through a guided interview in a harness they already run (Claude
  Desktop / Code / Cursor), **without** writing Markdown, choosing an id, or
  knowing the schema — and nothing lands in the reviewed corpus except through a
  human-reviewed pull request (ADR-065).
- The corpus starts getting authored by the people who own the knowledge, not
  only by a handful of technical maintainers — lifting the ceiling on everything
  downstream, grounding included.
- The shared **capture core** exists and is proven, so the later host surfaces
  (overlay / Slack / web) are thin adapters over it rather than re-implementations.

## Initiatives

### Initiative 1 — The `rac-capture` skill *(delivered, PR #193)*

Author `src/rac/skills/rac-capture/SKILL.md` as the interview variant of
`rac-import`, reusing the same CLI seams (`rac schema`, `rac inspect`, `rac new`,
`rac validate`, `rac resolve` / `rac find` for relationship targets). The loop:

1. **Capture raw intent first.** Let the author brain-dump the decision in plain
   language before any structuring question — never gate capture behind the
   interview.
2. **Interview to fill the template, pre-filling from the dump.** Ask only the
   two-to-four essential things that cannot be inferred or safely defaulted, as
   confirmations rather than blank prompts; allow skip / Enter-through.
3. **Ratify, then write.** Present the draft with its proposed type, title, and
   any relationships the author named (never repo-scanned), require explicit
   confirmation, then `rac new` to scaffold and mint the id.
4. **Close on validation.** Run `rac validate`; treat errors as blocking; finish
   with `rac relationships --validate` if the artifact links to others.

### Initiative 2 — The save/promote boundary

Define how the skill lands its output so it respects ADR-065: a draft is a
**commit** (an unreviewed branch or `drafts/` area — a legitimate *untrusted*
state in ADR-065's own words), and a **pull request** is what promotes it into
the reviewed corpus an agent grounds against. The skill never writes straight to
the trusted corpus.

### Initiative 3 — Deferred: the host surfaces

Recorded as the sequel, **not** in scope here. The desktop overlay (Host B),
Slack bot (Host C), and web modal (Host D) from `lore-capture-surfaces` each wrap
this skill once it is proven; they carry their own build, distribution, and
bring-your-own-gateway concerns and should be scheduled separately.

## Constraints

- **No AI in the engine (ADR-002, ADR-067).** The interview model runs in the
  harness; `rac-core` stays deterministic and AI-optional. The skill, like
  `rac-import`, explicitly adds no model call to core.
- **The schema is not the skill's to invent (ADR-021).** Sections, types, and
  relationship kinds come from `rac schema` at runtime; ingestion-over-rewrite
  (ADR-006) applies when the source includes a document.
- **Knowledge, not work (ADR-017).** The skill captures decisions and long-lived
  requirements; it must not record owners, sprints, or workflow state.
- **Human ratification is mandatory before any write, and no auto-commit without
  it.** Relationships are suggestions to confirm, never silently asserted; the id
  is system-minted, never hand-chosen.
- **Not a content store (ADR-024).** The skill emits Markdown to git and stores
  nothing of its own.

## Non-Goals

- Building any host surface (overlay, Slack bot, web modal) — those are deferred
  to the design's later phases.
- Bulk or multi-document conversion — that remains `rac-ingest`'s job; this is a
  single interview → single artifact.
- Inferring relationships by scanning the repository — only links the author
  names, each confirmed.
- Inventing context, rationale, or requirements the author did not provide — gaps
  in required sections are surfaced as questions, never filled with plausible text.
- Any engine, MCP-surface, or contract change — the skill rides the existing CLI.

## Success Measures

- A non-technical author, starting from a plain-language description, produces a
  schema-valid artifact (`rac validate` exits 0) through the interview, having
  chosen no id and written no Markdown by hand.
- The artifact lands as a draft commit and is promoted only via a human-reviewed
  PR — never written straight into the trusted corpus.
- The skill reuses the `rac-import` patterns and adds **no** code to `rac-core`
  (no engine, MCP, or contract change).
- Evidence (usage or user research) that authors who would not touch an IDE will
  use the interview — the signal that would schedule a host surface out of
  `future/`.

## Assumptions

- The `rac` CLI surfaces the skill depends on — `rac schema`, `rac inspect`,
  `rac new`, `rac validate`, `rac resolve` / `rac find` — stay stable and
  additive (ADR-007, ADR-063).
- The author is working in a harness that can run a skill and reach a model;
  bring-your-own-key is the harness's concern at this stage (Host A), not the
  skill's.
- The friction the skill removes (git / Markdown / schema knowledge) is the real
  barrier for non-technical authors — to be confirmed by use.

## Risks

- **The interview re-introduces up-front friction.** If it asks blank,
  schema-shaped questions it just relocates the burden it was meant to remove;
  mitigated by capturing raw text first, pre-filling answers, and keeping the
  question count low and skippable.
- **Quality of freeform → typed structuring.** A loose description may map poorly
  onto a type's sections; mitigated by the mandatory human-ratify gate and by
  surfacing gaps as questions rather than inventing content.
- **Scope creep into a host build.** The temptation to jump to the overlay or
  Slack bot before the core skill is proven; mitigated by holding Initiative 3 as
  deferred and shipping the harness skill first.
- **Misclassification as work.** Interviews about "what we decided" can drift
  toward tickets/owners; mitigated by the ADR-017 boundary baked into the skill's
  constraints.

## Related Decisions

- ADR-002
- ADR-006
- ADR-017
- ADR-020
- ADR-021
- ADR-024
- ADR-065
- ADR-067

## Related Designs

- lore-capture-surfaces

## Related Roadmaps

- lore-supermemory-grounding
