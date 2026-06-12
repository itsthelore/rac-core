# RAC growth programme — shared brief

Read `.agent-context/SCHEMA.md` first. Every deliverable lands as RAC
artifacts in this repository (requirements first, supporting artifacts
second, linked via `## Related …` sections where the schema allows).
A deliverable that exists only as a loose Markdown note has failed.

## Repo reality (overrides anything you assume)

- Version v0.10.3. Product identity is recorded in **ADR-036
  (`rac/decisions/adr-036-lore-product-identity.md`): Lore is the product
  ("agents that know why", MCP grounding); RAC is the engine.** The README
  first screen leads with Lore and MUST NOT be repositioned. This was
  confirmed by the maintainer on 2026-06-12.
- The corpus is already fully dogfooded (38 ADRs, requirements, designs,
  roadmaps, prompts under `rac/`, validated in CI).
- Relationships/traceability shipped in v0.7.x (ADR-016). Gap records now
  motivate FUTURE roadmap work, not "v0.8.0".
- Read `rac/decisions/` before designing; recorded decisions take
  precedence. If your task conflicts with one, stop and report the
  conflict — do not override it.

## Positioning thesis (adapted; use verbatim where comparison framing is needed)

Primary positioning is ADR-036's: Lore gives coding agents the decisions a
team already made, served deterministically over MCP from a typed Markdown
corpus in Git.

Secondary positioning, for comparison content only (below the README fold
or in `docs/`): spec-driven tools (GitHub Spec Kit, OpenSpec, Kiro) manage
the *change* — proposal, design, tasks — and treat requirements as
ephemeral inputs that are consumed and archived. RAC manages the
*requirements* as a durable, versioned, governed corpus that persists
across changes. RAC is the layer above SDD tools, not a competitor to
them. Comparison framing is "complements, owns a different layer", never
"better than".

## Global constraints (verbatim, apply to all agents)

1. **Schema fidelity.** Do not invent a requirement format. SCHEMA.md is
   extracted from the codebase; use exactly that. If the schema lacks a
   field you want, note it as a gap, do not add it ad hoc.
2. **Voice.** Conservative, execution-focused language. No promotional
   framing, no superlatives, no "blazingly", no emoji. UK spelling
   throughout. Observation before conclusion. If a claim about a
   competitor cannot be verified from their repo or docs, it is not made.
3. **Restraint.** Prefer the smallest artifact that does the job. A
   three-requirement change beats a twelve-requirement change covering
   the same ground.
4. **Human gates.** Two decisions are reserved for Tom and must be
   flagged, never resolved by an agent:
   - GATE-1: nothing intended for public posting (X/LinkedIn/HN) ships
     until employer external-communications and personal-project IP
     policies have been reviewed. Agents may draft; drafts are marked.
   - GATE-2: the contribution policy and any "PRs welcome" language does
     not go live until a CLA is in place. Same marking convention.
   Gate marking convention (the real schema has no status field for
   this — that is itself a recorded gap): keep `## Status` as `Proposed`
   and add a body line directly under it:
   `Blocked: GATE-1 (employer external-communications / IP review)` or
   `Blocked: GATE-2 (CLA not yet in place)`.
5. **No fabrication.** Where you need a fact about spec-kit, OpenSpec,
   Kiro, or any tool, read the actual repo/README/docs (web fetch).
   Uncited competitor claims are deleted at integration review.
6. **Verification.** Finish by running the validation commands in
   SCHEMA.md against your outputs and fixing failures before reporting
   done.

## Gap recording (first-class output)

When you need something RAC cannot express, do NOT work around it
silently. Append a record to `.agent-context/gaps/<your-agent-name>.md`:

```
## Gap: <relationship or capability needed>
- Instance: <concrete case from this programme or the existing corpus>
- Instance: ...
- Minimal schema addition that would have sufficed: <one sentence>
```

## Working rules

- Write files only; do NOT run `git commit` or `git push` — the
  orchestrator commits.
- Stay inside your assigned paths.
- New requirement files: `rac/requirements/rac-growth-<slug>.md`, created
  with `/tmp/racenv/bin/rac new requirement <path>`.
- UK spelling in all artifact prose.
