# TUI Navigation Design

## Context

RAC Explorer needs a consistent navigation model for browsing product knowledge.

## User Need

Product managers need to move between artifacts without memorizing file paths.

## Design

Use a keyboard-first navigation model with a searchable artifact list and detail pane.

## Constraints

The interface must remain readable in a terminal and avoid viewer-specific state.

## Rationale

A list-and-detail flow keeps artifact browsing predictable for repeated use.

## Alternatives

A command-only flow was considered but would make discovery harder for new users.

## Accessibility

Navigation must support keyboard-only use and clear focus indicators.

## Style Guidance

Use restrained visual hierarchy and concise labels suitable for terminal layouts.

## Open Questions

Should search results preserve the previous selection after filtering changes?
