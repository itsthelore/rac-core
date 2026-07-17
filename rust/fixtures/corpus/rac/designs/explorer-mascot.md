---
schema_version: 1
id: RAC-KTQ63DT15G7R
type: design
---
# RAC Explorer Mascot

## Context

RAC Explorer provides a terminal-native workspace for navigating product knowledge repositories.

As RAC evolves from individual CLI commands into an interactive environment, it requires a recognizable product identity that reflects its purpose.

RAC helps users navigate:

- Requirements
- Decisions
- Designs
- Roadmaps
- Relationships
- Historical context

The mascot exists as a representation of RAC's role:

> A guide that illuminates hidden product knowledge.

The mascot should reinforce RAC Explorer as a companion for navigating complex repositories without suggesting that RAC owns or creates the knowledge itself.

---

## User Need

Users need RAC Explorer to feel:

- Approachable
- Memorable
- Discoverable
- Distinct from generic developer tooling

while maintaining trust as a serious engineering and product workflow tool.

The mascot should provide identity and orientation without becoming distracting.

---

## Design

### Concept

The mascot is a small explorer carrying a lantern.

The explorer represents navigation.

The lantern represents illumination.

Together they communicate:

```text
Unknown repository
        ↓
RAC exploration
        ↓
Visible product knowledge
```

---

## Visual Reference

```markdown
![RAC Explorer Mascot](../assets/explorer/mascot.png)
```

---

## Characteristics

The mascot should have:

- Simple hooded silhouette
- Dark face area
- Two illuminated eyes
- No mouth
- Small explorer proportions
- Lantern as primary visual element

Example:

```text
       ___
     /     \
    |  • •  |
     \_____/

       |
      /█\

          ◇
```

---

## Personality

The mascot should feel:

- Curious
- Quiet
- Helpful
- Persistent

Avoid:

- Cartoon assistant
- Chatbot personality
- Overly expressive character
- Fantasy wizard styling

RAC is a guide, not a character-driven product.

---

## Constraints

### Terminal Native

The mascot must work in:

- Pixel artwork
- ASCII representation
- Monochrome rendering
- Small icon sizes

Required contexts:

- README
- Explorer welcome screen
- Empty states
- Terminal loading views
- Project branding

---

### Functional Identity

The mascot should reinforce RAC concepts.

Examples:

Preferred:

```text
The explorer discovers existing knowledge.
```

Avoid:

```text
The explorer creates answers.
```

---

## Accessibility

Mascot presence must never replace textual information.

Users must understand RAC state without seeing the mascot.

---

## Related Roadmaps

- v0.8.6-explorer-maturity

---

## Related Decisions

- ADR-015
- ADR-019
