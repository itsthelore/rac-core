---
schema_version: 1
id: RAC-KTXTAF6ZKDK8
type: decision
---
# ADR-037: Token-Boundary Search Matching

## Status

Proposed

## Category

Technical

## Context

Artifact search — `rac find` on the CLI and `search_artifacts` on the
Guide tool surface — matches by case-insensitive substring over
identifiers, titles, and paths. Substring matching produces false
positives at word boundaries: a query for `lore` matches every Explorer
artifact, because "lore" is a substring of "Explorer". The collision now
involves the product name itself.

Search quality became a product surface when Guide shipped: an agent
that receives noisy matches burns context triaging them, and an agent
that learns the tool is noisy stops calling it. The grounding
measurement (eight-of-ten decision-ID citations) depends directly on
retrieval precision.

The `guide-tool-surface` design pinned v1 search as exactly
`find_artifacts` semantics. Changing how matching works is therefore a
deliberate contract change, not a bug fix, and is recorded as one.

## Decision

Search matching moves from raw substring to token-boundary matching.

- Identifiers, titles, and paths are tokenized on non-alphanumeric
  boundaries and lowercase-to-uppercase transitions (camelCase splits).
- A query term matches a token case-insensitively when it equals the
  token or is a prefix of it: `relation` matches `relationships`;
  `lore` matches `Lore` but not `Explorer`.
- Multi-term queries require every term to match (AND semantics).
- The ranking ladder is unchanged: identifier matches rank above title
  matches above path matches, with sorted path as the tiebreak.
- One Core implementation serves both `rac find` and
  `search_artifacts`; their results never diverge.
- Golden and contract tests are re-pinned to the new semantics, the
  change is announced as a behavior change in the release notes, and
  the grounding measurement is re-run after it lands.

## Consequences

### Positive

- Word-boundary false positives disappear; precision improves for every
  query without any new dependency.
- Prefix matching preserves the partial-word ergonomics users already
  rely on.
- Matching stays deterministic and explainable in one sentence.

### Negative

- Existing queries can return fewer results than before; any workflow
  that depended on mid-word substring hits breaks.
- Golden tests and the pinned search contract must be re-pinned in the
  same change.

### Risks

- Tokenization rules accrete special cases over time. Mitigated by
  keeping the rule set small, documented in one place, and pinned by
  boundary tests — including `lore` versus `Explorer` as a named
  regression case.

## Alternatives Considered

### Keep substring matching

Rejected: the false-positive class now collides with the product name,
and precision failures directly suppress agent tool use.

### Fuzzy or edit-distance matching

Rejected: deterministic in the technical sense but unexplainable in
practice; ranking ceases to be a one-sentence contract and golden tests
become brittle.

## Related Decisions

- ADR-007
- ADR-038

## Related Designs

- guide-tool-surface
