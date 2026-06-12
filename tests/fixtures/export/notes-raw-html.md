# ADR-002: Inline HTML Handling

## Status

proposed

## Context

Bodies may carry raw HTML such as <script>alert("portal")</script> alongside
Markdown formatting like **bold text** and `inline code`:

- item one
- item two

## Decision

Raw HTML is escaped at export time, never executed.

## Consequences

<img src="https://example.com/x.png"> arrives as text, so the Portal makes
no network requests of its own.
