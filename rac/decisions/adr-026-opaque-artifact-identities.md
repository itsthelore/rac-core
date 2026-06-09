# ADR-026: Opaque System-Assigned Artifact Identity

## Status

Proposed

## Context

RAC artifacts require stable identities for:

- Relationships
- Repository indexing
- File moves and renames
- Explorer navigation
- Watchkeeper change reporting
- CLI and API integrations
- Long-term repository history

Current and proposed human-readable identifiers often encode artifact meaning or type:

```text
ADR-015
REQ-Documentation-Structure
v0.7.5
```

These references are useful to people, but they couple identity to information that may
change.

For example:

- An artifact may be reclassified.
- A file may be renamed.
- A directory may be reorganized.
- A title may change.
- A semantic numbering scheme may be inconsistent across repositories.

RAC requires an identifier that describes only identity.

The identifier should not depend on:

- Artifact type
- Filename
- Directory
- Title
- Lifecycle status
- Human numbering conventions

Sequential identifiers such as:

```text
RAC-1
RAC-2
RAC-3
```

are easy to read, but reliable allocation is difficult in a Git-native, offline-first
environment.

Two branches may independently allocate the same next number.

A central allocation service would solve this, but would conflict with RAC's local,
repository-native architecture.

## Decision

RAC shall use opaque, system-assigned artifact identifiers.

Identifiers shall be:

- Unique within a RAC repository namespace
- Stable for the lifetime of the artifact
- Independent of artifact type and file location
- Safe to generate offline
- Safe to generate concurrently across Git branches
- Permanent once assigned

A representative identifier may look like:

```text
RAC-01JY4M8X
```

The exact generation algorithm shall be defined by the implementation contract, but it
must provide sufficient collision resistance for offline and concurrent creation.

A newly created artifact may therefore contain:

```yaml
---
schema_version: 1
id: RAC-01JY4M8X
type: decision
---
```

The `id` identifies the artifact.

The `type` classifies it.

The title describes it to humans.

These concerns shall remain separate.

## Repository Namespace

`rac init` shall establish a repository namespace or repository key.

For example:

```yaml
repository_key: RAC
```

The repository key may form the human-recognizable prefix of generated IDs:

```text
RAC-01JY4M8X
```

The repository key does not determine folder structure.

Users remain free to organize artifacts using any supported repository layout.

The same opaque suffix may not be assigned twice within one repository namespace.

Identifiers may be duplicated across unrelated repositories unless RAC later introduces
cross-repository identity.

## Permanence

Once assigned, an ID shall never be reassigned to a different artifact within the same
repository namespace.

This rule continues to apply when an artifact is:

- Renamed
- Moved
- Reclassified
- Superseded
- Archived
- Deleted

Deletion shall not automatically release an identifier for reuse.

The conceptual rule is:

```text
active IDs + retired IDs = reserved IDs
```

A future registry or tombstone mechanism may preserve retired identities where required.

## Human-Friendly Resolution

Opaque IDs are canonical machine references, but users shall not be expected to
memorize or interpret them without assistance.

RAC Core shall own:

- ID allocation
- ID uniqueness validation
- ID lookup
- ID resolution
- Ambiguity handling
- Machine-readable lookup output

Explorer shall consume these capabilities and provide richer navigation and display.

Explorer shall not be the only way to resolve an artifact ID.

A relationship may store:

```yaml
relationships:
  implements:
    - RAC-01JY4M8X
```

RAC may display it as:

```text
Markdown Is the Canonical Source Format
Decision · RAC-01JY4M8X
```

The canonical reference remains the opaque ID.

The title and type are presentation information resolved from the repository.

## CLI Requirements

RAC shall provide core CLI capabilities for resolving opaque identifiers.

Representative commands may include:

```bash
rac resolve RAC-01JY4M8X
rac find "Markdown canonical"
rac show RAC-01JY4M8X
```

The exact command surface shall be defined by the associated roadmap and implementation
contract.

At minimum, a user must be able to supply an ID and obtain:

- ID
- Artifact type
- Title
- Path

Machine-readable output shall also be available.

Example:

```json
{
  "id": "RAC-01JY4M8X",
  "type": "decision",
  "title": "Markdown Is the Canonical Source Format",
  "path": "rac/decisions/markdown-first.md"
}
```

## Relationship References

Canonical relationships shall store opaque artifact IDs.

They shall not depend on:

- Filenames
- Relative paths
- Titles
- Semantic aliases

This ensures references survive moves, renames, and title changes.

Human-facing tools may resolve and display additional context without changing the
stored reference.

## Consequences

### Positive

- Identity remains stable across file moves and renames.
- Artifact type can change without changing identity.
- Relationship references become durable.
- IDs can be generated offline.
- Concurrent Git branches do not require a central numeric allocator.
- Repository folder structure remains user-defined.
- Machine identity is separated from human presentation.
- Explorer, Watchkeeper, and integrations share the same resolution model.

### Negative

- IDs are less meaningful when read without lookup context.
- Users require CLI or Explorer support to resolve unfamiliar IDs.
- RAC must maintain an ID generation and uniqueness contract.
- Existing human-readable identifiers require migration or alias handling.
- Commit messages and discussions may be less immediately descriptive if they contain
  only opaque IDs.

### Risks

- Opaque IDs could make artifacts feel like tickets if presented without titles.
- Users may copy incorrect IDs when tooling does not provide completion.
- Identifier formats may become difficult to change after adoption.
- Repository-key changes could create ambiguity if IDs are rewritten.

These risks shall be mitigated by:

- Always displaying titles alongside IDs where practical
- Providing CLI lookup and search
- Keeping identifiers immutable
- Treating the repository key as configuration, not mutable artifact meaning
- Making RAC Core, rather than Explorer alone, responsible for resolution

## Alternatives Considered

### Type-Specific Human IDs

Examples:

```text
ADR-015
REQ-042
DESIGN-007
```

#### Advantages

- Human-readable
- Communicates artifact type
- Familiar in discussions

#### Disadvantages

- Embeds mutable classification into identity
- Requires separate sequences
- Creates migration problems when type changes
- Can collide across directories or conventions

### Repository-Scoped Sequential IDs

Examples:

```text
RAC-1
RAC-2
RAC-3
```

#### Advantages

- Compact
- Easy to communicate
- Familiar from ticketing systems

#### Disadvantages

- Unsafe to allocate independently across Git branches
- Requires collision handling
- A central allocator would weaken offline-first operation
- Allocation state becomes shared mutable repository state

### Filename- or Path-Based Identity

#### Advantages

- No separate identifier required
- Immediately locatable

#### Disadvantages

- Breaks when files move or are renamed
- Couples identity to repository organization
- Produces fragile relationships

### Opaque System-Assigned Identity

#### Advantages

- Stable
- Branch-safe
- Type-independent
- Path-independent
- Suitable for machine references

#### Disadvantages

- Requires resolution tooling
- Less immediately meaningful to people

This alternative is selected.

## Relationship to Other Decisions

This decision depends on the hybrid artifact metadata decision because the canonical ID
shall live in frontmatter.

It also reinforces the principle that Explorer is a consumer of RAC Core.

ID resolution must be available through:

- Core service APIs
- CLI commands
- Structured JSON output

Explorer may improve presentation, but it shall not own identity or lookup behavior.

## Success Measures

Evidence that this decision is succeeding may include:

- New artifacts receive IDs without user intervention.
- Two concurrently created artifacts do not receive the same ID.
- IDs remain unchanged after moves, renames, and type changes.
- Duplicate IDs are detected deterministically.
- Relationships continue resolving after files are reorganized.
- Users can resolve any ID through the CLI.
- Explorer can display titles and paths without implementing separate lookup logic.

## Review Date

Review before IDs become mandatory for all artifacts or before RAC introduces
cross-repository relationships.