---
schema_version: 1
id: RAC-KW47GJ749PKC
type: decision
---
# ADR-088: Enterprise Profile Scaffold (`rac init --profile`)

## Status

Accepted

## Category

Product

## Context

Adoption follows the path of least resistance. A team that must think for an hour
about which ADR fields to use, how to wire `.mcp.json`, and how to gate CI will
fall back to a Confluence page. A one-command, firm-shaped start removes that
friction.

Two recorded decisions bound how far a scaffold may go. ADR-044 binds onboarding
to writing exactly one starter artifact into an empty corpus, as the unmodified
canonical template. ADR-024 forbids content-store behaviour. ADR-085 settles that
"enterprise" is configuration, not a mode, and that a profile must emit only what
a careful admin would hand-write.

## Decision

`rac init --profile <name>` writes **configuration only, never authored prose**.

- What a profile emits:
  - `.rac/config.yaml` enforcement policy (ADR-049) and validation severity
    (ADR-053) stanzas;
  - `.mcp.json` wired for Claude Code and Cursor;
  - optionally a CI gate stanza (for example a Bitbucket Pipelines block) as
    configuration;
  - when federation exists (ADR-089), a parent-corpus declaration line.
- Profiles are built-in, named bundles shipped with the package (`default`,
  `enterprise`). A profile must emit exactly the files a careful admin would
  hand-write (the ADR-085 cultural backstop): it adds no code path a solo
  developer cannot reach.
- It writes no ADR or prompt prose. Firm ADR templates and standards prompts
  live in the firm's standards corpus and are *referenced* (via federation,
  ADR-089), not generated — preserving ADR-044 and ADR-024.
- The one-starter-artifact scaffold (ADR-044, `rac quickstart`) is unchanged;
  `--profile` is configuration layering, composable with it.
- **Hollow-on-parent:** until ADR-089 ships, `--profile enterprise` emits no
  parent-corpus line. A preset cannot configure a mechanism that does not exist.

## Consequences

### Positive

- A firm-shaped start is one command, lowering the activation energy that
  otherwise sends teams back to Confluence.
- The auditor and the new team get one committed, git-diffable configuration
  artifact rather than a checklist to apply per machine.

### Negative

- Built-in named profiles must be maintained as the config surface evolves.
- "Profiles write config, not content" is a line that must be held against
  requests to also scaffold starter ADR prose.

### Risks

- A profile grows into a content generator. Mitigation: ADR-044 and ADR-024 bound
  it; the profile emits configuration and references, never authored prose.
- A profile smuggles in behaviour. Mitigation: the ADR-085 backstop — no code
  path the solo developer cannot reach.

## Alternatives Considered

### A richer scaffold that writes starter ADRs and prompts

Generate firm-styled content files on init.

#### Disadvantages

- Reopens ADR-024 and exceeds ADR-044's one-artifact bound; the firm's standards
  belong in a referenced corpus, not in generated prose.

### Documentation only ("do these nine steps")

Ship a setup guide instead of a command.

#### Disadvantages

- At scale, adherence to a doc you must apply is materially worse than to a
  command you run; the profile is the discoverable, repeatable artifact.

A config-only, built-in named profile, composable with the existing scaffold, is
selected.

## Relationship to Other Decisions

- ADR-044, ADR-024: the bounds the profile respects; it writes config, not
  content, and leaves the one-artifact scaffold unchanged.
- ADR-049, ADR-053: the existing config knobs a profile presets.
- ADR-085: the profile is the concrete mechanism of "enterprise is
  configuration, not a mode".
- ADR-089: supplies the parent-corpus declaration the profile is hollow on until
  it ships.

## Related Requirements

- rac-trust-transparency
