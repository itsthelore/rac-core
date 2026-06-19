---
schema_version: 1
id: EVAL-RADN71DPV8KA
type: design
tags: [navigation, mobile]
---
# Mobile Navigation Drawer

## Status

Accepted

## Context

On phones the editor canvas needs the full screen width, so a persistent
side panel is not an option. Writers still need to reach folders and documents
without leaving the document they are editing.

## User Need

A writer on a phone needs to reach folders and documents without permanently
sacrificing canvas width to a navigation surface.

## Design

Navigation lives in a drawer that slides in from the left edge over the canvas
and is summoned by a hamburger control or an edge swipe. The drawer dismisses
on selection or on tapping the dimmed canvas behind it.

## Constraints

The drawer must be reachable one-handed and must not trap focus for assistive
technology when open.

## Rationale

An overlay drawer preserves full canvas width on small screens while keeping
navigation one gesture away.
