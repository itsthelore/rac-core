# ADR-019: Asset References

## Status

Accepted

## Context

RAC uses Markdown as the canonical source format for product knowledge artifacts.

As artifacts expand beyond text-only requirements into:

- Designs
- Architecture decisions
- Roadmaps
- Prompts
- Explorer experiences

some artifacts require supporting visual or binary material.

Examples include:

- Design mockups
- Diagrams
- Screenshots
- Mascot artwork
- Animation references
- Research material

Embedding these directly inside Markdown would reduce portability and make artifacts harder to review, diff, and maintain.

RAC requires a consistent approach for connecting structured knowledge artifacts with supporting files.

## Decision

Supporting files shall exist as external assets referenced from Markdown artifacts.

Markdown remains the source of truth.

Assets provide supporting context.

Recommended repository structure:

```text
rac/
├── requirements/
├── decisions/
├── designs/
├── roadmaps/
└── assets/
    ├── images/
    ├── diagrams/
    └── references/
```

Artifacts reference assets using standard Markdown links.

Example:

```markdown
## Visual Reference

![Explorer Mascot](../assets/images/explorer-mascot.png)
```

RAC treats these references as relationships between artifacts and supporting material.

Assets are not first-class knowledge artifacts.

They provide evidence, examples, and context.

## Principles

### Principle 1 — Markdown Remains Canonical

The Markdown artifact describes:

- Intent
- Context
- Decisions
- Requirements
- Constraints

The asset illustrates or supports that knowledge.

The meaning of an artifact should not exist only inside an image.

---

### Principle 2 — Assets Are Referenced, Not Embedded

Avoid:

- Base64 encoded images
- Binary content inside Markdown
- Tool-specific attachments

Prefer:

```text
artifact.md
      |
      └── assets/reference.png
```

This preserves:

- Git compatibility
- Reviewability
- Tool independence

---

### Principle 3 — Assets Are Viewer Agnostic

Assets should work across:

- GitHub
- IDEs
- Markdown viewers
- RAC Explorer
- Future integrations

No RAC-specific rendering format is required.

---

## Consequences

### Positive

- Keeps artifacts lightweight
- Preserves clean Markdown diffs
- Supports visual design workflows
- Allows richer documentation
- Maintains compatibility with existing tools
- Enables future relationship discovery

Example:

```text
Design Artifact

Related Requirement:
✓ Explorer Foundation

Related Decision:
✓ ADR-015 Explorer Consumer

Related Assets:
✓ mascot.png
✓ idle-animation.gif
```

---

### Negative

- Requires repository asset organisation
- Broken asset references become possible
- Asset lifecycle management may require future validation

---

## Future Considerations

RAC may introduce asset validation capabilities.

Examples:

```bash
rac relationships --validate
```

could detect:

```text
✓ Referenced asset exists

✗ Missing asset:
  assets/images/old-design.png
```

RAC Explorer may provide asset previews while continuing to treat assets as supporting material only.

## Related Decisions

- ADR-001 Markdown First
- ADR-014 Viewer-Agnostic Knowledge Artifacts
- ADR-015 Explorer as Consumer
```