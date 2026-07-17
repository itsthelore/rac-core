---
schema_version: 1
id: RAC-KVSNP20PPZ15
type: design
---
# Mentioned-but-Unlinked Reference Detection

## Context

This design is the *how* for the `rac-unlinked-reference-detection` requirement
and the boundary ADR-082 draws: surface body references to other artifacts that
are not declared as `## Related` edges, as advisory suggestions, deterministically,
without ever auto-applying an edge.

The machinery already exists in spirit. `services/relationships.py` builds the
declared graph — it parses each `## Related <Type>` section into resolved
`Relationship` edges and already powers orphan detection in `rac doctor`. The
reference resolver (`rac resolve`) and token-boundary matching (ADR-037) already
turn a token like `adr-074` into a known artifact without substring false
positives. This design reuses both for a new axis: instead of "which declared
edges exist," it asks "which artifacts does the *body* name that the declared
edges miss."

**Prior art.** Zero-LLM, deterministic edge extraction from Markdown text is the
mechanism behind general agent-memory tools such as GBrain. RAC adopts the
*detection* (pure string/id matching, no model) but not the *auto-wiring*: the
output is a suggestion a human promotes, never an edge the tool writes (ADR-082).

## User Need

A corpus maintainer wants the declared graph to be as complete as the prose
already implies — without hand-scanning every artifact for links they forgot to
promote. They need a check that says, in plain terms, "this artifact's body
mentions ADR-074 but has no `## Related Decisions` link to it — add one?" and
gives them a paste-ready line to do it. The agents and backends that consume the
graph need the same thing indirectly: a denser, still-validated graph.

The check must never act on its own (the maintainer decides), never block CI,
and never depend on a model or network — it has to run in the same offline,
deterministic pass as the rest of `rac doctor`.

## Design

### What counts as a mention

For a source artifact `A`, a *mention* is a token in `A`'s body that resolves —
via the same resolver `rac relationships --validate` uses — to a corpus artifact
`B`, where `B != A` and `B` is not already a declared `## Related` target of `A`.

Matched reference forms (high precision, deterministic):

- **Canonical ids** — `RAC-XXXXXXXX`.
- **Filename-style references** — `<letters>-<digits>` prefixes such as
  `adr-074`, and artifact filename stems used as refs.
- **Declared aliases** — any alias an artifact registers for resolution.

Title text is **not** matched in this design (titles are prose-like and noisy);
that is an Open Question, not part of the shipped matcher.

### What is scanned, and what is excluded

The body is taken from the parsed Markdown AST (`core/markdown.py`), reusing the
single shared parser. Excluded from matching, so they cannot produce a finding:

- the YAML frontmatter block (identity, not prose);
- the `## Related <Type>` sections themselves (their references are the declared
  edges, not mentions);
- fenced code blocks (a code sample's contents must not masquerade as a
  reference — the same exclusion the parser already applies for structural
  scanning);
- the artifact's own id/aliases (no self-references).

### The finding

One finding per `(A, B)` pair, regardless of how many times `A`'s body names
`B`. Each finding carries:

- the source artifact (`A`),
- the matched target (`B`) and the token that matched,
- the `## Related <Type>` section that would capture the edge, derived from
  `B`'s type via the relationship-type registry (ADR-055) — a decision target
  maps to `## Related Decisions`, a requirement to `## Related Requirements`,
  and so on,
- a paste-ready suggested line (for example `- adr-074` under
  `## Related Decisions`).

Findings are **advisory**: a new `rac doctor` finding code
(`unlinked-reference`) alongside the existing `orphaned-artifact` /
`high-fan-out-hub` warnings, all of which exit zero. The detection logic lives in
a service function that returns the finding set; `rac doctor` is the first
surface. `rac coverage` is a candidate second surface (a mentioned-but-unlinked
reference is also a graph-completeness gap) and is left as an Open Question so
the first release ships one clear home.

### Determinism

The function is pure over corpus bytes: same corpus, byte-identical findings,
proven by golden tests. Output is sorted (by source path, then target id) so
diffs are stable. No model, embedding, or network call is on the path
(ADR-002, ADR-066).

## Constraints

- Offline, AI-optional (ADR-002) and deterministic with no embeddings or LLM
  judge (ADR-066): pure function of corpus bytes.
- Suggest, never apply (ADR-082): the detector emits findings only; it never
  writes an edge. The declared `## Related` sections stay the source of truth
  (ADR-074), and promotion stays a human review act (ADR-065).
- Advisory severity (ADR-075 gate discipline): findings exit zero and never
  change the `rac validate` / `rac relationships --validate` contract.
- Reuse, don't reinvent: the resolver, token-boundary matcher, relationship
  index, and Markdown parser are shared with the existing relationship and
  doctor code, not duplicated.

## Rationale

Matching on ids, aliases, and filename refs — not titles or free text — is what
keeps the detector trustworthy without a model: these forms resolve
unambiguously through the same machinery validation already trusts, so a match
is a real reference, not a guess. Routing the output through `rac doctor` as an
advisory reuses the paste-ready-fix UX users already know and keeps the feature
on the correct side of every recorded boundary: it makes the *validated* graph
more complete instead of replacing it with an inferred one.

## Alternatives

- **Auto-promote matches to declared edges.** Rejected by ADR-082: an
  unreviewed edge is not a validated edge (ADR-074, ADR-065).
- **Embed artifacts and suggest by similarity.** Rejected: non-deterministic and
  contrary to ADR-002/ADR-066; also lower precision than exact id/ref matching
  for this specific job.
- **Match titles and arbitrary noun phrases too.** Deferred, not adopted: title
  matching trades precision for recall and risks a noisy channel maintainers
  learn to ignore (see Open Questions).
- **Make it a hard validation error.** Rejected by ADR-082: it would force every
  prose mention into a declared edge and turn a nudge into a merge blocker.

## Accessibility

Output is plain text, readable and diffable, in the same shape as existing
`rac doctor` findings: the suggestion is stated in words with the paste-ready
line, no reliance on colour or a graphical display. `--json` carries the same
fields for automation.

## Style Guidance

Each finding leads with the relationship it suggests ("body references B; no
Related <Type> link"), then the paste-ready fix — scannable, matching the tone of
the existing orphan and hub findings. Copy frames the result as a *suggestion to
review*, never as an assertion that an edge exists.

## Open Questions

- **Title matching.** Whether to add exact, whole-token title matching as an
  opt-in second tier, and how to bound its false-positive rate before it ships.
- **Second surface.** Whether `rac coverage` should also report
  mentioned-but-unlinked references as a completeness gap, or whether keeping it
  to `rac doctor` is clearer.
- **Directionality.** Whether a suggestion should also be offered on the *target*
  side (B could declare the inverse edge), or only on the mentioning side.

## Related Decisions

- adr-082
- adr-074
- adr-065
- adr-066
- adr-002
- adr-037

## Related Requirements

- rac-unlinked-reference-detection

## Related Roadmaps

- link-suggestions
