---
schema_version: 1
id: RAC-SEEDSEEDSEED
type: decision
---
# Seed the Closure Mini Corpus

## Context

The closure parity smoke cases need a clean, minimal repository fixture:
a repository key under `.rac/` and one valid decision so corpus walks
have something deterministic to index.

## Decision

Keep exactly one hand-authored decision in the fixture, with a pinned
identifier, and never add hostile markdown to this tree.

## Consequences

Sandboxes copied from this fixture validate green and the oracle's
id-collision walk completes without crashing.

## Status

Accepted

## Category

Process

## Alternatives Considered

An empty corpus was considered, but a seed artifact also pins the
copied-fixture byte comparison and the id-collision index walk.
