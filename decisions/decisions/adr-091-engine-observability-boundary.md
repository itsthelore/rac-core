---
schema_version: 1
id: RAC-KW47GPJVWDZ1
type: decision
---
# ADR-091: Engine Observability Boundary

## Status

Proposed

## Category

Technical

## Context

"Metrics on every route" is an operations default, and a tool with no Prometheus
endpoint can read as "did not think about ops." But the MCP server is stdio-only,
stateless, and runs as one process per developer (ADR-031, ADR-032), and a hosted
or shared server is a non-goal. A Prometheus `/metrics` endpoint presumes a
long-running server to scrape — exactly what the local-per-developer model does
not provide and the no-hosted-service stance rejects. The need is real
(operators want signal); the question is the shape of observability that fits a
local, stateless, offline process.

## Decision

The engine's observability is bounded to what fits a local, stateless, offline
process, all off by default with one flag to enable.

- **Opt-in structured JSON logs** to stderr (off by default; one flag turns them
  on), carrying operational events — startup, and per-call tool, outcome, and
  duration — with no artifact content beyond what the audit recorder (ADR-084)
  separately governs.
- **Sentry-compatible error-reporting hooks**: an optional DSN the operator
  supplies (bring-your-own, ADR-035); off by default; no RAC-hosted sink. It
  honours the air-gap lock (ADR-086) — disabled while telemetry is
  enterprise-locked unless the operator has explicitly set their own DSN.
- **No Prometheus `/metrics` HTTP endpoint in the engine.** There is no shared,
  long-running server to scrape in the local-per-developer model, and adding an
  HTTP surface to a stdio process is out of scope. A scrape endpoint, if ever
  justified, belongs to a shared-deployment satellite (for example the
  Helm-packaged watchkeeper, ADR-090) and is decided there.

## Consequences

### Positive

- Operators get real signal (structured logs, error reporting) without the engine
  growing a hosted or scraped surface.
- The `/metrics` gap is deliberate and documented, not an oversight; the decision
  explains where a scrape endpoint would live if a shared deployment ever needs
  one.

### Negative

- A checkbox-driven review that expects a `/metrics` endpoint will not find one;
  the rationale must be pointed to.
- Error reporting requires the operator to supply and manage a DSN; there is no
  turnkey sink.

### Risks

- A `/metrics` endpoint is added under ops pressure, dragging an HTTP server into
  a stdio process. Mitigation: this ADR scopes it out and routes it to a
  shared-deployment satellite.
- Error reporting leaks content. Mitigation: the structured-log and error payload
  carry no artifact content beyond ADR-084's governed fields.

## Alternatives Considered

### Ship a Prometheus `/metrics` endpoint now

Add an HTTP metrics surface to the MCP server.

#### Disadvantages

- Presumes a long-running, scrapable server that the local-per-developer model
  does not provide and the no-hosted-service stance rejects. Belongs to a
  shared-deployment satellite if anywhere.

### No observability at all

Keep stderr diagnostics only.

#### Disadvantages

- Reads as ops-blind and gives operators no structured signal or error
  reporting; the need is real even if the hosted shape is wrong.

Opt-in structured logs plus bring-your-own error reporting, no engine scrape
endpoint, is selected.

## Relationship to Other Decisions

- ADR-031, ADR-032: the stdio, stateless, one-process-per-developer model that
  rules out a scrape endpoint in the engine.
- ADR-035: error reporting is bring-your-own DSN, no RAC-hosted sink.
- ADR-084: structured logs carry no content beyond the audit recorder's governed
  fields.
- ADR-086: error reporting honours the enterprise telemetry lock.
- ADR-090: a scrape endpoint, if ever needed, lives in a shared-deployment
  satellite.
- ADR-085: observability delivered as opt-in configuration, for everyone, not a
  mode.
