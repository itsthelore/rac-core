---
schema_version: 1
id: RAC-KVJY1KJEWZ87
type: decision
---
# ADR-073: Backend Connectors Are Export-Contract Consumers, Not Per-Provider Repos

## Context

> **Renamed and generalised by ADR-092.** `lore-connectors` is now
> `rac-connectors`, and ADR-092 broadens this one-repo consolidation to cover
> inbound (`rac ingest`) and outbound (`rac export`) integrations and provider
> suites alike — Atlassian is a subdir, not its own repo. The decision below —
> connectors are export-contract consumers, consolidated, never one repo per
> provider — is unchanged; it is the pattern ADR-092 generalises across the
> `rac-*` family. Execution is planned in the `repo-topology` series.

The export-to-RAG work (the umbrella roadmap `corpus-export-to-rag-backends`, the
interplay design `lore-supermemory-interplay`, and the wire-shape design
`corpus-export-shape-contract`) introduces *connectors* that push the corpus into
external memory, vector, and graph backends — Supermemory, Mem0, Pinecone, Neo4j,
Graphiti, Cognee, and so on. The early phrasing named a per-provider companion
(`lore-supermemory`), which implies **one repository per provider** — a sprawl
trap as the backend list grows.

ADR-068 settles the topology for **client integrations**: each editor/agent
integration is its own `lore-<client>` repository (`lore-vscode`, `lore-cursor`,
`lore-claude`), and a single container repo is *rejected*, justified by
"independent per-client cadence and ownership." But ADR-068 does not cover
**backend connectors**, and the cadence/ownership rationale that warrants
per-client repos does not hold for them:

- A connector is a thin consumer of the published export contract (ADR-063), not
  an independently-owned installable product.
- Most backends need **no RAC-side code at all** — RAC emits a standard ingestion
  shape (`rac export --documents` / `--graph`, per `corpus-export-shape-contract`)
  that a provider's own ingestion consumes. The contract is the product.
- ADR-064's "single `rac-actions` repo, one subdirectory per action" is the
  closer precedent for thin, related wrappers maintained together.

A connector also belongs outside `rac-core` regardless of repo count: it carries
third-party SDK and network dependencies the engine must not (ADR-002, ADR-066),
and pushing into an external store is not the engine's job (ADR-024).

## Decision

Treat memory, vector, and graph backend connectors as **export-contract
consumers**, not per-provider installable products:

- **The export contract is the product.** The long tail of backends is served by
  the documented export shape (`rac export --documents` / `--graph`) plus the
  provider's own ingestion — no RAC-side code per provider.
- **Reference connectors consolidate into one companion repository,
  `lore-connectors`**, with a module or recipe per provider — not one repo per
  provider. This deliberately differs from ADR-068's per-client rule; the
  discriminator is that connectors lack the independent cadence and ownership that
  justify a repo per client.
- **A dedicated `lore-<provider>` repo is created only if** a specific integration
  grows into an installable product with its own surface — auth, a sync daemon,
  an independent release cadence — the same test ADR-068 applies to clients. That
  is the documented escape hatch, not the default.
- **Connectors live outside `rac-core`** (ADR-002, ADR-024, ADR-063, ADR-066):
  the engine stays pure-Python, AI-optional, deterministic, and offline.

This does not reopen ADR-068; it extends the `lore-*` topology to a category
ADR-068 did not address.

## Consequences

### Positive

- No repo-per-provider sprawl; the export contract does the heavy lifting and most
  providers need zero code.
- One discoverable home for reference connectors (`lore-connectors`).
- The engine stays clean — no third-party backend SDKs or network in `rac-core`.
- The connector-vs-client distinction is now recorded, so it is not re-litigated.

### Negative / trade-offs

- `lore-connectors` mixes providers with different release needs in one repo.
  Accepted: they are reference adapters, not independently-owned products; if one
  outgrows that, it graduates to its own repo via the escape hatch.

### Risks

- The connector-vs-client line could blur over time. Mitigation: the test is
  recorded — "an installable product with independent cadence and ownership earns
  its own repo; a contract consumer does not."

## Status

Accepted

## Category

Architecture

## Alternatives Considered

### One `lore-<provider>` repo per backend

Rejected: it is the sprawl this decision exists to prevent, and it misapplies
ADR-068's per-client rule to a category whose cadence/ownership rationale does not
fit.

### Build connectors into `rac-core`

Rejected: it drags third-party SDK and network dependencies into the engine,
breaking its pure-Python, AI-optional, offline posture (ADR-002, ADR-066) and
ADR-024 (not a content store).

### Documentation recipes only, no connector repo

Viable for the simplest `--documents` cases and encouraged where it suffices, but
insufficient as the sole answer: a graph projection or a re-sync workflow wants
real code. `lore-connectors` is the home for that; recipes cover the rest.

## Related Decisions

- adr-002
- adr-024
- adr-063
- adr-064
- adr-066
- adr-068
- adr-092

## Related Designs

- lore-supermemory-interplay
- corpus-export-shape-contract

## Related Roadmaps

- corpus-export-to-rag-backends

## Review Date

Revisit if a backend connector grows into an installable product with its own
cadence (triggering the dedicated-repo escape hatch), or if the number of
consolidated connectors makes `lore-connectors` unwieldy.
