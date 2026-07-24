---
schema_version: 1
id: EVAL-1483XGG8THGE
type: decision
tags: [storage, infrastructure]
---
# Postgres as the Primary Datastore

## Status

Accepted

## Context

Aurora needs a primary datastore for documents, accounts, and sharing metadata.
The team weighed a managed relational database against a document store.

## Decision

PostgreSQL is the primary datastore. Relational integrity, transactional
guarantees, and mature operational tooling outweigh the schema flexibility a
document store would offer at our scale.

## Consequences

The team commits to relational modelling and migrations. Document bodies are
stored as structured columns rather than opaque blobs, which keeps querying and
backup straightforward.

## Category

Architecture
