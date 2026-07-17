---
schema_version: 1
id: RAC-KV6KFEA3F53R
type: prompt
tags: [release, hardening, brief, agent]
---
# v0.23.0 Hardening Release Brief

## Objective

Direct a coding agent to ship the v0.23.0 hardening release: harden Lore into a
provably correct, transparent, robust deterministic grounding layer for coding
agents. This prompt is the source brief for the release; it lives in the graph
so the plan and its origin are both recorded (dogfooding). The authoritative
expansion is the roadmap `v0.23.0-hardening` and its per-workstream requirements.

The release succeeds only if a real or partner-representative agent
demonstrably stops relitigating at least one real decision (the obey-demo,
T3-A). Green CI and the eval gate are necessary but not sufficient.

## Input

- The RAC repository and its corpus under `rac/`: requirements, decisions
  (ADRs), roadmaps, prompts, designs.
- The four read-only MCP tools (`get_artifact`, `search_artifacts`,
  `get_related`, `get_summary`) and the code-defined schema envelope.
- The recorded decisions this release rests on: ADR-030, ADR-032, ADR-033,
  ADR-002, ADR-034, ADR-052, ADR-049, plus the two it adds (ADR-065, ADR-066).

## Instructions

Build strictly in tier order; finish Tier 1 before Tier 2; touch Tier 3 only for
its two carve-outs. Prefer the smallest change that satisfies each acceptance
criterion. If a guardrail appears to block a requirement, pause and ask — do not
work around it.

- Tier 1 (this is the release): WS1 grounding eval + CI gate; WS2 explainable
  retrieval; WS3 `rac doctor`; WS4 parser + bounded-traversal robustness;
  WS11 trust model + injection flag + review signal.
- Tier 2 (scope down, cut from the bottom if short): WS6 single-schema agreement
  test (no Pydantic); WS5 minimal provenance; WS8 content-hash short-circuit
  (core only); WS10 honest changelog + tiered tests.
- Tier 3 (carve-outs only): T3-A manual obey-demo; T3-B `schema_version` already
  present (no work); T3-C resumability not built.

Each workstream is one requirement artifact carrying its normative statements and
acceptance criteria; load-bearing decisions are recorded as ADRs (citing existing
ones rather than duplicating them). Run `lore doctor` over the emitted artifacts;
they must be schema-valid and pass the same checks the product enforces.

## Output

A correctly scoped, approved set of changes: the artifact graph (this brief, the
roadmap, one requirement per workstream, ADR-065 and ADR-066, the eval-scorecard
design); the `rac eval` and `rac doctor` subcommands with CI gates; additive
`evidence`, provenance, and review-status fields on the four tools;
`SECURITY.md`; an honest CHANGELOG entry; and a recorded obey-demo. The MCP
surface stays exactly four read-only tools, with additive output only.

## Constraints

- Determinism is load-bearing: no AI/LLM, RAG, embeddings, or vector search in
  any serving, validation, eval-scoring, doctor, or indexing path; runs offline.
- The MCP tool surface is locked at four tools and stays read-only.
- Humans author and review; nothing auto-edits artifact content. Artifact
  content is untrusted; the trust boundary is human PR review.
- The schema is defined once in code; all MCP output changes are additive and
  backward-compatible.
- Markdown + git + the existing stack only; no database, queue, daemon, HTTP+
  OAuth server, or plugin system; no heavyweight dependencies.

## Examples

A search result enriched per WS2 carries deterministic evidence, for example:
"matched field: title; term: 'eval'; via search_artifacts tier 1" — accurate,
non-empty, reproducible.

A `rac doctor` finding names the file, the problem, and a paste-ready fix, for
example: "rac/decisions/adr-099.md: references missing adr-100 — run
`rac find adr-100` or correct the reference in `## Related Decisions`."

## Evaluation

- The obey-demo shows the agent declining a forbidden change after consulting
  Lore (the definition of done).
- Tier 1 complete with all acceptance criteria; the full suite plus the eval
  gate and `doctor` pass in CI.
- Tier 2 complete or consciously descoped per each item's defer rules.
- Tier 3 not built beyond the `schema_version` field and the manual obey-demo.
- The MCP tools still number exactly four and remain read-only; no AI in core.

## Related Decisions

- adr-065
- adr-066
- adr-030
- adr-034

## Related Roadmaps

- v0.23.0-hardening
