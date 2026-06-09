---
schema_version: 1
id: RAC-KTQ63DSW7R7B
type: design
---
# RAC Explorer Mascot Animations

## Context

The RAC Explorer mascot provides lightweight visual feedback during repository interaction.

Animations should make RAC feel responsive while preserving the expectations of terminal-native developer tooling.

Animations communicate state.

They are not decoration.

---

## User Need

Users need clear feedback when RAC is:

- Waiting
- Searching
- Processing
- Discovering knowledge
- Completing actions

The mascot provides a consistent interaction language.

---

## Design

Animations are implemented as explicit states.

---

## Idle

Default state.

Used when Explorer is open.

Behaviour:

- Lantern gently pulses
- Occasional eye blink

Example:

```text
Frame 1

(••)  ◇


Frame 2

(••)  ◆
```

Purpose:

Communicate that Explorer is active.

---

## Searching

Triggered by repository operations:

Examples:

```text
rac inspect

rac relationships

rac portfolio
```

Behaviour:

The explorer searches with the lantern.

```text
(••)  ◇ →

Scanning repository...
```

---

## Discovery

Triggered when RAC identifies knowledge.

Examples:

- Artifact found
- Relationship discovered
- Validation completed

Animation:

```text
       ✦

(••)   ◆
```

---

## Success

Triggered after successful operations.

Behaviour:

Explorer raises lantern.

```text
    ✦

 \(••)/
  /█\
```

---

## Empty State

Triggered when expected information does not exist.

Example:

```text
(••?)

No requirements found.

Create your first artifact?
```

---

## Error State

Errors should remain calm.

Behaviour:

- Lantern dims
- Explorer pauses

Avoid:

- Panic animations
- Failure mascots
- Excessive emotion

---

## Constraints

### Minimal Motion

Animations should feel like:

- Cursor blinking
- Terminal activity indicators
- Classic software feedback

Avoid:

- Continuous movement
- Game-like behaviour
- Attention grabbing effects

---

### State Driven

Every animation must map to:

- System state
- User action
- Repository event

---

## Accessibility

Explorer must support:

```text
animations = false
```

Reduced-motion users receive equivalent text feedback.

---

## Related Roadmaps

- v0.9.0-explorer-foundation
- v0.9.1-explorer-experience

---

## Related Decisions

- ADR-015
- ADR-019
