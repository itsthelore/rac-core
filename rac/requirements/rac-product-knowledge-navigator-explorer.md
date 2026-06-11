---
schema_version: 1
id: RAC-KTR62H8T7SRR
type: requirement
---
# Requirement: Product Knowledge Navigator (Explorer)

## Status

Proposed

## Problem

As repositories grow, product knowledge becomes increasingly difficult to understand.

Teams accumulate:

- Requirements

- Decisions

- Roadmaps

- Designs

- Prompts

Over time these artifacts form a connected knowledge system rather than a collection of individual documents.

RAC provides intelligence for understanding product knowledge through capabilities including:

- validation

- inspection

- relationship analysis

- repository review

- repository statistics

- improvement recommendations

These capabilities are accessible through individual commands.

However, users often need to understand the repository as a whole rather than through isolated command execution.

Common questions include:

- What product knowledge exists?

- How do artifacts relate to one another?

- What areas of the repository require attention?

- What is the overall health of the repository?

- What actions should be taken next?

A dedicated navigation and maintenance experience is required.

## Requirements

- [REQ-001] RAC shall provide an interactive product knowledge navigation environment called RAC Explorer.

- [REQ-002] Explorer shall help users discover, understand, assess, and act upon product knowledge stored within RAC repositories.

## Product Goal

Move RAC from:

> Individual command execution.

toward:

> Continuous repository understanding and maintenance.

## Product Model

RAC provides multiple surfaces over the same underlying intelligence.

```text

RAC Core

    |

    +-- Explorer

    |     Understand repository state

    |

    +-- Watchkeeper

          Understand repository change

```

Explorer answers:

> What exists and what needs attention?

Watchkeeper answers:

> What changed and does it require review?

## User Story

As a team managing product knowledge in Git,

I want to explore repository content, understand relationships, assess repository health, and navigate to areas requiring attention,

so that I can effectively maintain product knowledge over time.

## Dependency

Explorer consumes existing RAC capabilities.

Including:

- Artifact validation

- Artifact inspection

- Relationship analysis

- Repository review

- Repository statistics

- Improvement recommendations

- Portfolio intelligence

Explorer shall not implement independent repository intelligence.

All repository intelligence shall remain within RAC Core.

## Core Capabilities

Explorer shall enable users to:

### Discover

Understand what product knowledge exists within a repository.

### Understand

Explore relationships and dependencies between artifacts.

### Assess

Evaluate repository quality, completeness, and health.

### Act

Navigate efficiently from findings to remediation workflows.

## Action Principles

Explorer shall not merely identify repository issues.

Explorer shall help users move from findings to action.

Explorer is responsible for:

- surfacing findings

- explaining findings

- presenting recommendations

- locating affected artifacts

- navigating related artifacts

Explorer shall reduce the effort required to move from repository insight to repository maintenance.

## Editing Model

Explorer shall not implement a proprietary artifact editor.

Explorer shall integrate with existing authoring and editing workflows.

Explorer is responsible for:

- discovery

- understanding

- assessment

- navigation

External tools remain responsible for:

- editing content

- authoring content

- applying changes

## Architecture Requirements

Explorer shall operate as a consumer of RAC capabilities.

Repository intelligence shall remain accessible through RAC Core services and commands.

Explorer shall not become the sole interface to repository intelligence.

Capabilities surfaced through Explorer should remain accessible through RAC commands and machine-readable outputs.

## Design Authority

The Explorer experience is defined through dedicated architectural and design artifacts.

This requirement defines the purpose, capabilities, and intended outcomes of Explorer.

Interaction models, onboarding experiences, visual systems, navigation workflows, recommendation presentation, action workflows, editor integration, and mascot behaviour are delegated to associated design artifacts.

## Related Decisions

- ADR-015

- ADR-028

## Related Designs

- explorer-first-run-experience

- explorer-command-surface

- explorer-health-model

- explorer-knowledge-graph

- explorer-recommendations

- explorer-action-workflows

- explorer-editor-integrations

- explorer-import-workflow

- explorer-visual-system

- explorer-mascot

- explorer-mascot-interaction

- explorer-mascot-animations

## Related Roadmaps

- v0.8.0-explorer-foundation

- v0.8.1-explorer-navigation

- v0.8.2-explorer-health

- v0.8.3-explorer-recommendations

- v0.8.4-explorer-action-workflow

- v0.8.5-explorer-relationship-navigation

- v0.8.6-explorer-maturity

## Non-Goals

Explorer shall not:

- duplicate RAC intelligence

- replace Markdown editors

- become a document authoring environment

- replace Git workflows

- replace Watchkeeper

- require hosted infrastructure

- become the system of record for product knowledge

## Acceptance Criteria

A user can:

1. Launch Explorer.

2. Discover repository artifacts.

3. Understand relationships between artifacts.

4. Assess repository health.

5. Review repository recommendations.

6. Navigate from findings to remediation workflows.

without manually inspecting repository structure or executing numerous individual RAC commands.

## Success Measures

Explorer succeeds when:

- repository understanding becomes faster

- relationship discovery becomes easier

- repository health becomes visible

- repository findings become actionable

- users spend less time locating relevant artifacts

- RAC intelligence becomes more discoverable

- teams maintain product knowledge more effectively

## Related Requirements

- rac-repository-review-mode

- rac-product-intent-ci-watchkeeper

- rac-agent-context-guide

## Related Artifacts

### Depends On

- Portfolio Intelligence

- Relationship Navigation

## Future Considerations

Future versions may introduce additional Explorer delivery surfaces while preserving the Explorer capability model and its role as a consumer of RAC intelligence.