# ADR-XXX Hybrid Artifact Metadata

## Status

Proposed

## Context

RAC artifacts are currently represented as Markdown documents whose structure and
metadata are inferred from headings, sections, filenames, and artifact-specific
conventions.

This approach keeps artifacts readable and tool-independent, but repository-level
capabilities increasingly require explicit machine-readable metadata.

Examples include:

- Stable artifact identity
- Artifact type
- Relationships
- Schema version
- Creation metadata
- Ownership metadata
- Future repository intelligence fields

Representing all such information through Markdown sections would require RAC to treat
human-readable prose as an informal serialization format.

For example:

```markdown
## Metadata

ID: RAC-01JY4M8X
Type: decision
Created: 2026-06-08
```

This is readable, but it is harder for generic tools to parse, validate, and consume
without understanding RAC's Markdown section model.

Moving all artifact information into frontmatter would create the opposite problem:
RAC artifacts could gradually become YAML records with Markdown attached, weakening
the principle that the document body contains the product knowledge itself.

RAC therefore requires a clear boundary between:

- Machine-operational artifact metadata
- Human-readable product meaning and reasoning

## Decision

RAC shall adopt a hybrid artifact metadata model.

Machine-operational metadata shall be represented in YAML frontmatter.

Human reasoning, product meaning, lifecycle explanation, and artifact content shall
remain in Markdown sections.

The guiding rule is:

> Machine-operational structure belongs in frontmatter. Human product knowledge belongs
> in the Markdown body.

An artifact may therefore take the following form:

```yaml
---
schema_version: 1
id: RAC-01JY4M8X
type: decision
relationships:
  informs:
    - RAC-01JY4N2Q
---
```

```markdown
# Markdown Is the Canonical Source Format

## Status

Accepted

## Context

RAC requires a canonical source format for product knowledge.

## Decision

Markdown is the canonical source format.
```

## Metadata Ownership

Every supported field shall have exactly one canonical location.

Initial ownership shall be:

| Field | Canonical location |
| --- | --- |
| `schema_version` | Frontmatter |
| `id` | Frontmatter |
| `type` | Frontmatter |
| `relationships` | Frontmatter |
| `created` | Frontmatter, if later supported |
| `updated` | Frontmatter, if later supported |
| `owners` | Frontmatter, if later supported |
| `tags` | Frontmatter, if later supported |
| Status | Markdown section |
| Context | Markdown section |
| Requirement | Markdown section |
| Decision | Markdown section |
| Rationale | Markdown section |
| Consequences | Markdown section |
| Goals | Markdown section |
| Non-Goals | Markdown section |
| Acceptance Criteria | Markdown section |

Fields shall not be valid in both frontmatter and Markdown sections.

Where the same canonical field is defined in multiple locations, RAC shall report a
conflict rather than silently selecting one value.

## Frontmatter Scope

Frontmatter shall remain deliberately narrow.

It may contain:

- Artifact identity
- Artifact classification
- Structural relationships
- Schema information
- Other explicitly defined machine-operational fields

It shall not contain product reasoning such as:

- Context
- Requirements
- Decisions
- Rationale
- Consequences
- Acceptance criteria
- Narrative status explanations

Frontmatter shall act as an artifact envelope.

The Markdown body shall remain the artifact itself.

## Backwards Compatibility

Artifacts without frontmatter shall remain supported during a defined migration period.

RAC may continue deriving information from existing sources such as:

- Explicit ID sections
- Artifact-specific identifier sections
- Filenames
- Recognized document structure

When frontmatter is present, supported frontmatter fields shall be treated as the
canonical source for those fields.

RAC shall not silently ignore conflicts between frontmatter and legacy locations.

Migration shall be staged:

1. Frontmatter parsing is introduced.
2. Frontmatter is recommended for newly generated artifacts.
3. Migration tooling becomes available.
4. Mandatory metadata requirements, if any, are introduced only through an explicitly
   documented breaking change.

## Parsing Requirements

The frontmatter parser shall:

- Parse only a leading YAML frontmatter block.
- Reject malformed frontmatter with an actionable error.
- Reject duplicate keys.
- Validate supported fields against an explicit schema.
- Preserve artifacts without frontmatter.
- Avoid unsafe YAML object construction.
- Normalize values deterministically.
- Avoid relying on frontmatter key order.

RAC-generated frontmatter shall use a stable key order.

## Dates

This decision establishes where explicit date metadata would live, but does not require
`created` or `updated` fields.

RAC shall not derive artifact dates from:

- Filesystem timestamps
- Git timestamps
- Clone time
- Export time

Those values describe the environment or repository history, not necessarily the
artifact itself.

Any future date field must have a defined ownership and maintenance contract.

## Consequences

### Positive

- Clear separation between machine structure and human knowledge.
- Better interoperability with Markdown and documentation tooling.
- Stronger schema validation.
- Explicit and stable artifact identity.
- More reliable relationship parsing.
- A future path for metadata-only repository scanning.
- Human-readable Markdown artifacts remain canonical.
- Existing repositories can migrate incrementally.

### Negative

- RAC must parse both YAML frontmatter and Markdown.
- Migration introduces temporary support for multiple artifact forms.
- YAML syntax creates additional user-facing failure modes.
- Conflict detection and metadata validation add parser complexity.
- Contributors must understand which fields belong in which location.

### Risks

- Too much product meaning may migrate into frontmatter.
- Fields may accidentally gain two canonical representations.
- YAML type coercion may produce surprising values.
- External tools may rewrite or reorder frontmatter.
- Frontmatter may become mandatory before migration tooling is mature.

These risks shall be mitigated through:

- A strict metadata schema
- One canonical location per field
- Actionable validation errors
- Stable RAC-generated formatting
- A staged migration policy

## Alternatives Considered

### Markdown Sections Only

Represent all metadata using Markdown sections.

#### Advantages

- Pure Markdown
- Compatible with the current parser model
- Highly visible to readers

#### Disadvantages

- Uses prose structure as an informal serialization format
- Harder for generic tools to consume
- More difficult to represent typed and nested values
- Encourages metadata-only sections throughout artifacts

### Frontmatter Only

Move both metadata and product fields into frontmatter.

#### Advantages

- Strong machine structure
- Straightforward schema validation

#### Disadvantages

- Weakens Markdown-first product knowledge
- Encourages YAML-heavy artifacts
- Makes product meaning less visible to readers

### Hybrid Metadata Model

Use frontmatter for machine-operational structure and Markdown for human knowledge.

#### Advantages

- Preserves human readability
- Introduces explicit machine-readable structure
- Supports gradual migration
- Establishes a clean ownership boundary

#### Disadvantages

- Requires two parsing layers
- Requires strict conflict and ownership rules

This alternative is selected.

## Relationship to Other Decisions

This decision extends the Markdown-first architecture rather than replacing it.

Markdown remains the canonical format for artifact meaning.

Frontmatter becomes the canonical envelope for defined machine-operational metadata.

This decision also provides the metadata foundation required by:

- Repository Index
- Relationship validation
- Explorer
- Watchkeeper
- IDE integrations
- Artifact lookup and resolution

## Success Measures

Evidence that this decision is succeeding may include:

- Every supported field has one documented canonical location.
- RAC detects conflicting metadata definitions.
- Existing section-based artifacts continue to work during migration.
- Newly generated artifacts use valid canonical frontmatter.
- External consumers can read identity and type without interpreting artifact prose.
- Markdown bodies remain readable and meaningful without RAC-specific tooling.

## Review Date

Review before frontmatter becomes mandatory or before any metadata field is moved
between frontmatter and Markdown.