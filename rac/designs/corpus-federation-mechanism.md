---
schema_version: 1
id: RAC-KWJ8RWSW356V
type: design
---
# Design: Corpus Federation Mechanism

## Status

Proposed

The concrete mechanism proposal ADR-089 anticipates — input to the
implementing ADR authored with the design partner, not a substitute for
it. The Open Questions below are the design-partner agenda.

## Context

ADR-089 accepted corpus federation in principle and recorded five
non-negotiable constraints any design must clear: never enterprise-gated;
deterministic and offline over materialised bytes; single canonical state
per repo with a read-only parent and explicit overrides; git-native,
human-readable declaration (`## inherits` plus a pinned source reference);
and provenance preserved end to end.

The engine's seams are already in place. Every consumer reads the corpus
through one walk (`walk_corpus`, `src/rac/core/corpus.py`), with a
per-file `content_hash` primitive alongside it. Resolution flows through
`_entry_items` into `_build_resolution_index` and
`_build_identifier_index` (`src/rac/services/relationships.py`) — the
latter is where duplicate identities are already detected — and onward to
`relationships_from_corpus`. Search and lookup flow through
`index_from_corpus` (`src/rac/services/index.py`) and `resolve_in_index`
(`src/rac/services/resolve.py`), and the MCP server builds its identity
map from the same entries. No `federation:` configuration stanza exists
today, and the profile scaffold carries no parent placeholder — the
hollow-on-parent state ADR-088 records.

## User Need

An organisation holds firm-wide standards — shared ADRs, requirements,
prompts — in one standards corpus, and needs every repository's corpus to
resolve against it: offline, deterministically, and attributably, so a
child repository can cite a firm decision the way it cites its own. A solo
developer gets the identical capability, because federation is never
gated (ADR-085, ADR-089).

## Design

### Declaration

Inheritance is declared in one fixed-path, corpus-scoped Markdown manifest
carrying a `## inherits` section — not per-artifact frontmatter, not
configuration. Each entry names a source and a pinned reference:

```markdown
## inherits

- standards: submodule:vendor/standards @ 4f2c1a9e…
- platform: bundle:.rac/parents/platform @ sha256:…
- local-dev: path:../standards-checkout @ 7b03d4c2…
```

Three reference kinds, one pin discipline:

- `submodule:` — a git submodule path; the pin is the gitlink commit.
- `bundle:` — a vendored directory of parent artifacts; the pin is a
  recorded content hash over its bytes.
- `path:` — a local checkout; the pin is a commit SHA or content hash.

The pin is always written in the Markdown. Truth stays reviewable in a
diff, git-native, and human-readable (ADR-089 constraint four); no hidden
index holds it.

### Materialisation and verification

Resolution reads the declaration, locates the referenced bytes already on
disk, and verifies the pin against the materialised bytes before any
overlay happens. No step touches the network: refreshing a parent is the
user's git operation (submodule update, re-vendor, pull), outside the
engine (ADR-002, ADR-089 constraint two). A declared parent that is
absent, or whose bytes disagree with the pin, is a deterministic finding —
fail loud, never resolve silently against unverified state.

### Overlay through the existing seams

Parent entries come from the same corpus walk, run read-only over the
materialised root, tagged with their source name, and merged into the
entry stream ahead of `_build_resolution_index` — one resolver, no
parallel machinery. The identifier index, the repository index, the MCP
identity map, and the relationship graph all see parent entries as
read-only participants carrying their source.

### Collisions and explicit overrides

A parent/child identifier collision surfaces as an explicit deterministic
finding at the existing duplicate-identity detection point — never
precedence in either direction (ADR-089 constraint three). A child masks
a parent artifact only by declaring it: an `## overrides` section naming
the parent `(source, id)`, which converts the finding into recorded
intent, with the override itself carried as provenance on the resolved
artifact.

### Provenance

Every inherited artifact is attributable to its source corpus wherever it
appears: resolution results, MCP tool responses, validation findings, and
exports. Export stamping reuses the `rac-export-source-identity`
derivation — the parent's records carry the parent's own source, so
`(source, id)` aggregation deduplicates a shared parent across N children
with no federation-specific export machinery.

### Validation semantics

- Declared parent absent → error-severity finding naming the source.
- Pin and materialised bytes disagree → a distinct stale-pin finding.
- Child validation never demands edits to parent bytes: no finding's
  remediation can require writing to the read-only layer.
- Engines predating the mechanism treat `## inherits` as an unrecognised
  section with no hard failure, per ADR-089's compatibility clause.

## Constraints

- The five ADR-089 non-negotiables, in full.
- Offline and deterministic throughout (ADR-002); identical child plus
  parent materialised bytes produce byte-identical output across runs,
  machines, and clones.
- No database, no hidden index as truth (ADR-080); the child's `main`
  remains the sole canonical state for child artifacts (ADR-018).
- All layers read-only; writes land only by PR (ADR-065).
- Artifact identity and per-repository key prefixes stay as ADR-026
  defines them.

## Rationale

- A fixed-path manifest keeps discovery deterministic and the declaration
  reviewable in one place; per-artifact declarations would scatter truth
  and invite drift.
- Pin-in-Markdown keeps the trust decision in the diff a human reviews —
  the same trust boundary the corpus already relies on (ADR-065).
- Finding-not-precedence keeps single-canonical-state honest: nothing is
  ever silently shadowed, and every mask is a recorded, reviewable act.
- Reusing the corpus-sync source-identity derivation avoids a second
  identity mechanism and makes federation and multi-corpus aggregation
  one story rather than two.

## Alternatives

- **Configuration-stanza-only declaration.** Rejected: ADR-089 constraint
  four requires the declaration in Markdown; config may hold
  materialisation defaults at most, never the truth.
- **Implicit child-wins (or parent-wins) precedence.** Rejected: violates
  constraint three; collisions must be findings and masks explicit.
- **Live fetch with a local cache.** Rejected: violates constraint two;
  the validate path must read only materialised bytes.
- **Copying parent artifacts into the child tree at resolve time.**
  Rejected: destroys provenance (constraint five) and turns inheritance
  into silent absorption.
- **Enterprise-gated federation.** Rejected: constraint one; the
  forbidden mode (ADR-085).

## Accessibility

Provenance legibility is the accessibility bar: a human reading an
artifact, a finding, or an export record can trace any inherited answer
to its source corpus and pin from the text alone — no tooling required
beyond a text editor.

## Style Guidance

- Section names exact: `## inherits`, `## overrides`.
- Lowercase list keys; deterministic entry ordering; stable finding codes.
- Pins rendered in full in the Markdown; no abbreviation that breaks
  copy-paste verification.

## Open Questions

- Which artifact type and fixed path carry the manifest — a new
  corpus-manifest artifact, or an existing family?
- Multiple parents: unordered set with collision findings, or disallowed
  in the first cut?
- Transitive inheritance (parent-of-parent): recognised, flattened, or
  rejected?
- Severity of parent-internal findings when validating a child: surfaced,
  downgraded, or suppressed?
- Should exports offer an opt-out of the inherited layer (for example
  `--no-inherited`)?
- Interaction with ADR-026 key prefixes when parent and child share a
  repository key.
- MCP response-budget behaviour (ADR-033) when the inherited layer is
  large.

## Related Requirements

- rac-parent-corpus-inheritance
- rac-federated-resolution-provenance

## Related Decisions

- adr-002
- adr-016
- adr-018
- adr-026
- adr-055
- adr-065
- adr-080
- adr-085
- adr-088
- adr-089

## Related Roadmaps

- corpus-federation
- corpus-sync
