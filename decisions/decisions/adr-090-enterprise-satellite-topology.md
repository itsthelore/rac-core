---
schema_version: 1
id: RAC-KW47GN4SB403
type: decision
---
# ADR-090: Enterprise Integration Surfaces and Boundaries

## Status

Accepted

## Category

Architecture

## Context

Beyond configuration, the enterprise asks are network, SDK, and write-back work:
ingest from and publish to Confluence, resolve and comment on Jira, gate CI on
Bitbucket and Jenkins, aggregate audit logs to a sink, and package the whole for
Kubernetes. ADR-002 keeps that work out of the engine; ADR-063/073 make each
piece a consumer of the published contracts. ADR-092 sets where the pieces live:
one repo per concern, subdir per member — so these are **members of the
consolidated repos, not standalone satellite repos**. This decision records the
enterprise integration *surfaces* (which member lives where) and the *boundaries*
every one of them honours, so the engine-side contracts they imply are visible in
one place.

## Decision

Enterprise integrations are members of the `rac-*` family repos (ADR-092), not a
constellation of per-integration satellite repositories.

- **Atlassian suite → `rac-connectors/atlassian/`** (shared Cloud auth, one
  subdir spanning both directions):
  - inbound Confluence ingest, feeding `rac ingest` and the existing human-review
    loop (ADR-072, ADR-006);
  - outbound Confluence publish as a managed block, reusing the `agent_rules`
    managed-block pattern;
  - Jira external-ticket resolution and state checks (ADR-087);
  - comment-mode, posting a blocking decision to the linked Jira ticket and
    Confluence page.
- **CI on Bitbucket and Jenkins → `rac-ci` platform subtrees** (`bitbucket/`,
  `jenkins/`) of the `gatekeeper`/`watchkeeper` capabilities, over the
  CI-neutral `rac gate` / `rac watchkeeper` (ADR-049, ADR-054). There is no
  separate pipelines repo — a capability is never split across repos by platform
  (ADR-092).
- **Audit collector → `rac-ci/audit/`** — tails the ADR-084 audit JSONL to a sink
  (Loki, S3, Elastic), shipped per platform like the other CI capabilities.
- Optional Helm/ArgoCD packaging lays down the watchkeeper, audit, and Confluence
  sync surfaces as deployable applications (built from their subdirs).

Boundaries every enterprise integration honours:

- Consumes only published contracts — the CLI, the `--documents` and `--graph`
  exports, and the audit JSONL — never engine internals (ADR-063, ADR-073).
- All write-back is propose-only through human pull-request review (ADR-065,
  ADR-077); RAC never becomes a write-through path into a document platform.
- Adds no network code to the engine; the integrations own all network and SDK
  dependencies (ADR-002).

Engine-side contracts this implies (each built under its own ADR): the audit JSONL
(ADR-084), the external-edge graph marker (ADR-087, ADR-074), and a Bitbucket
Code-Insights output format alongside SARIF (an ADR-054 extension).

## Consequences

### Positive

- One place names the enterprise integration surfaces and the rules they obey, so
  the engine stays the engine and the contracts they need are explicit.
- Placing them as members of the family repos (ADR-092) matches the shared auth
  (Atlassian one subdir) and avoids a per-integration repo sprawl.

### Negative

- The family repos pin the export contract, so each engine release carries a
  conformance-test cost against its consumer subdirs (ADR-073); real, not free.
- A cross-integration bug spans subdirs of different repos; coordination falls to
  the contracts and the reference configuration (ADR-091, the paved-path example).

### Risks

- An integration grows a network dependency back into the engine. Mitigation:
  the boundary rules are recorded here; the engine gains no network import
  (ADR-002).
- Write-back becomes a bypass of PR review. Mitigation: propose-only via PR is a
  named boundary (ADR-065, ADR-077).

## Alternatives Considered

### A constellation of per-integration satellite repos

Separate `lore-atlassian`, `lore-pipelines`, `lore-audit` repositories (the
earlier draft of this ADR).

#### Disadvantages

- A repo per integration is the sprawl ADR-092 exists to prevent; deployment and
  multi-direction do not force a repo boundary. The integrations are members of
  the consolidated family repos instead.

### In-engine connectors

Build the network/SDK work into `rac-core`.

#### Disadvantages

- Contradicts ADR-002 and the single-fenced-ping rule; the engine stops being
  offline and deterministic. Rejected.

Enterprise integrations as members of the `rac-*` family repos, under fixed
boundaries, is selected.

## Relationship to Other Decisions

- ADR-092: the repository topology this decision places its integrations within
  (Atlassian a `rac-connectors` subdir; CI/audit `rac-ci` subtrees).
- ADR-063, ADR-073: the contract-consumer boundary every integration honours.
- ADR-084: the audit JSONL the `rac-ci/audit/` collector consumes.
- ADR-087, ADR-074: the external-edge graph marker Atlassian resolves.
- ADR-049, ADR-054: the CI-neutral gate and SARIF output the CI subtrees wrap.
- ADR-065, ADR-077: write-back is propose-only via PR.
- ADR-072, ADR-006: inbound ingest reuses the conversion and human-review loop.
- ADR-085: the distribution half of "configuration plus distribution, not a
  mode".

## Related Decisions

- adr-092
- adr-063
- adr-073
- adr-084
- adr-087
- adr-049
- adr-065
- adr-077
- adr-085
