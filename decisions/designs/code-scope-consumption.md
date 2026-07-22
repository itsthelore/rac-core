---
schema_version: 1
id: RAC-KWMHNQTQ17AK
type: design
---
# Code-Scope Consumption Seam

## Status

Accepted

## Context

The `decision-to-code-proximity` roadmap authors code scope once — a decision's
`## Applies To` section (Initiative 1) — and reads it everywhere. Initiative 2
shipped the single deterministic reader, `decisions_for_path` in
`src/rac/services/scope.py`: given a repository path, it returns the live
decisions whose declared scope covers it, a pure function of the declared
references and the file tree (ADR-066).

Initiative 3 (this design) records how that one reader is consumed, so the
"authored once, read everywhere" property is a documented architectural
invariant rather than an accident. It exists now because a second and a third
consumer are arriving — the Explorer's "decisions for this area" surface (this
batch) and `freshness-and-drift-detection` phase-2 code-scope drift (a later
phase, #279) — and each must resolve the *same* declared entries with no adapter
layer and no parallel vocabulary. Without a recorded seam, a consumer could
re-derive scope matching and the vocabulary would silently fork.

## User Need

The consumers are code, not people; the "user" is a future contributor wiring a
new consumer of code scope. They need one obvious, stable entry point so they
join on the declared `## Applies To` entries directly — not a re-implementation
of glob or path-containment matching, and not a second scope section invented for
their surface. The need this records: any consumer of "which decisions govern
this path" calls `decisions_for_path` and maps its result to its own display or
finding shape, nothing more.

## Design

`decisions_for_path(directory, path, recursive=True) -> ScopeLookupResult` is the
sole seam. Every consumer calls it and adapts only *presentation*:

- **CLI** (`rac decisions-for`, Initiative 2) — renders `ScopeLookupResult` as
  human or `--json`.
- **MCP** (`find_decisions` `path` argument, Initiative 2) — serializes the same
  result within the response budget (ADR-033).
- **Explorer** (`/decisions-for <path>`, this batch) — `ExplorerAdapter.governing_decisions`
  calls the seam and maps each `GoverningDecision` to an artifact row by path,
  reusing the existing results surface. No new view, no code-path browser.
- **Freshness phase-2 code-scope drift** (later phase, #279) — the recorded
  future consumer: it extends the advisory suspect finding
  (`rac-drift-advisory-finding` REQ-007) with governed-code drift by reading the
  same seam. Nothing here builds it; this design guarantees the seam stays
  consumable for it — additively, without renaming the stable finding code.

The invariant: mapping a `ScopeLookupResult` to a consumer's own row or finding
shape is *presentation* and is allowed; re-deriving scope matching, or declaring
a second scope vocabulary, is not. The matching semantics (literal
path/directory containment, segment-aware glob, component-name exclusion,
POSIX-normalisation) live once, in the seam.

## Constraints

- One reader (ADR-031): all consumers resolve the same declared entries through
  `decisions_for_path`; no consumer re-implements matching.
- One vocabulary: `## Applies To` (Initiative 1) is the only code-scope
  declaration; no consumer introduces a parallel section.
- Deterministic and offline (ADR-002, ADR-066): the seam is a pure function of
  declared references and the file tree — no code parsing, no index, no
  embeddings — so every consumer's answer is byte-identical across runs.
- Reported facts, never verdicts (ADR-034): consumers surface which decisions
  bind and their status; none layer a compliance judgement.
- Additive (ADR-007): a new consumer is new wiring around the existing seam,
  never a change to it.

## Rationale

Recording the seam is what makes "authored once, read everywhere" enforceable.
The alternative — each surface owning its own path→decisions logic — is exactly
the vocabulary fork the roadmap's constraint pattern forbids: two consumers would
drift on glob semantics or scope precedence and the corpus would answer the same
question two ways. A single core reader keeps the CLI, MCP, Explorer, and the
future drift gate consistent by construction, and keeps the matching semantics
tested in one place (`tests/test_scope.py`).

## Alternatives

- **A shared "scope adapter" layer between the core and each consumer.** Rejected:
  it is the adapter the acceptance proof explicitly forbids ("no adapter layer") —
  an extra indirection that would itself become a place for semantics to fork.
- **Let each consumer read `## Applies To` and match paths itself.** Rejected: it
  forks the vocabulary and the glob/containment semantics, the precise failure the
  initiative exists to prevent.
- **Precompute a path→decisions index at load time.** Rejected: a persisted index
  (ADR-080) the roadmap rules out; the seam resolves at read time, fresh per call
  (ADR-032).

## Accessibility

Not a presentation surface of its own. Each consumer owns its own accessibility:
the CLI and MCP emit plain text and JSON; the Explorer renders governing
decisions through its existing results surface, inheriting its keyboard
navigation and theme. The seam imposes no new interaction affordance to make
accessible.

## Style Guidance

Consumers name the capability consistently so it reads as one feature across
surfaces: the CLI subcommand `rac decisions-for` and the Explorer command
`/decisions-for` share a name; the MCP surface exposes it as the `path` argument
on `find_decisions`. A new consumer should follow this naming rather than coin a
synonym.

## Open Questions

- Whether component-name scope entries ever gain registry resolution (a later
  decision, per `rac-decision-applies-to-scope`); if so, the seam gains the
  resolution and every consumer inherits it with no change.
- Whether the future drift consumer needs per-artifact change sets beyond what
  the recency service exposes (the Watchkeeper materialisation seam, ADR-043);
  that is `rac-drift-advisory-finding`'s question, not the seam's.

## Related Requirements

- rac-path-decisions-lookup
- rac-decision-applies-to-scope
- rac-drift-advisory-finding

## Related Decisions

- adr-031
- adr-032
- adr-034
- adr-066
- adr-080

## Related Roadmaps

- decision-to-code-proximity
- freshness-and-drift-detection
