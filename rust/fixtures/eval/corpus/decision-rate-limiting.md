---
schema_version: 1
id: EVAL-1DJ9CM8QEXJX
type: decision
tags: [gateway, abuse]
---
# Token-Bucket Rate Limiting

## Status

Accepted

## Context

The Aurora API gateway needs to throttle abusive clients while letting normal
editing traffic burst briefly. A naive fixed counter per window punished honest
bursts at window boundaries.

## Decision

The gateway enforces request limits with a token-bucket algorithm per client.
Each bucket refills at a steady rate and a request spends one token; an empty
bucket rejects the request. The bucket here is a rate-limit accounting unit and
has nothing to do with authentication tokens.

## Consequences

Honest clients can burst up to the bucket size and then settle to the refill
rate, while sustained abuse is rejected. The gateway tracks one small bucket
per client key.

## Category

Technical
