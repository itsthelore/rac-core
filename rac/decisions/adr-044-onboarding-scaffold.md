---
schema_version: 1
id: RAC-KV2E5A5E1F1H
type: decision
---
# ADR-044: Onboarding Scaffold Writes One Starter Artifact

## Status

Accepted

## Category

Product

## Context

The Adoption Surface requirement (`rac-growth-adoption`) wants a new
user at a first validated artifact in under five minutes, and REQ-005
proposes a guided first-run path that scaffolds the corpus in one step
(v0.13.0). Implementing it means `rac quickstart` writes an artifact
file during onboarding.

That collides with two standing decisions. ADR-018 establishes the
`rac/` directory as the knowledge root without RAC imposing structure on
the user. ADR-024 establishes that RAC is not a content store: it
manages identity and validates structure, but the words in artifacts
belong to the user, authored deliberately, never generated or owned by
the tool. `rac init` today honours this strictly — it writes only
`.rac/config.yaml`, never content.

A guided first run that writes a starter artifact is, on its face,
RAC creating content. The question is whether that is a violation of
ADR-024 or a bounded exception worth making for activation.

## Decision

`rac quickstart` may write exactly one starter artifact, and only as a
one-time onboarding convenience under tightly bounded conditions:

- It writes a single artifact, of the requested type (default
  `requirement`), to a conventional path under `rac/<family>/`.
- It writes only when the corpus is empty — zero recognised artifacts.
  If any artifact already exists, quickstart refuses and writes no
  content (exit 1).
- The starter artifact is the unmodified canonical template body plus a
  system-assigned opaque id (ADR-026) — identical to what
  `rac init` + `rac new` produce. RAC writes a starting point, not
  meaning: the file is TODO placeholders the user fills in.
- RAC never updates, tracks, re-scaffolds, or otherwise manages the
  artifact after creation. It is the user's content from the moment it
  exists.

This is an onboarding affordance, not a content-management capability.
ADR-024 stands: RAC is not a content store. The scaffold is a labelled
exception scoped to the empty-corpus first run, justified by activation.

## Consequences

### Positive

- The cold start drops from three commands to one, the central goal of
  `rac-growth-adoption` REQ-005, without weakening the no-overwrite and
  identity guarantees.
- The exception is small and legible: one artifact, empty corpus only,
  canonical template, never managed afterwards — easy to reason about
  and to test.
- `rac init` and `rac new` keep their exact current contracts; the
  scaffold composes them rather than changing them.

### Negative

- RAC now writes content in one narrow path, so the "never creates
  content" statement carries an explicit caveat. Accepted: the caveat is
  recorded here and bounded.
- A starter artifact in a conventional location may not match how a user
  wants to organise their corpus; they must move or delete it.

### Risks

- The exception could be cited to justify broader content generation
  later. Mitigated: this ADR scopes it to empty-corpus onboarding and
  reaffirms ADR-024 for everything else; any expansion needs its own
  decision.

## Alternatives Considered

### Quickstart writes only config, prints next steps

`rac quickstart` establishes the key and prints the `rac new` command to
run, writing no artifact.

#### Advantages

- No content written by RAC; ADR-024 untouched.

#### Disadvantages

- Does not collapse the command count — the user still runs `rac new`
  and `rac validate` themselves. It is `rac init` with extra text, and
  fails REQ-005's one-step goal.

### Generate a populated example artifact

Scaffold a fully-written sample requirement so the first `rac validate`
passes on real-looking content.

#### Advantages

- A richer first impression.

#### Disadvantages

- RAC authoring meaningful content is a direct ADR-024 violation, and
  invites the user to keep RAC's words rather than write their own. The
  template's TODO placeholders already validate; populated prose buys a
  better demo at the cost of the principle.

### Implicit init inside `rac new`

Make `rac new` establish identity if missing, so two commands suffice
without a new command.

#### Advantages

- No new command surface.

#### Disadvantages

- Reverses the deliberate v0.7.11 no-implicit-init contract and hides
  identity creation inside an unrelated command. A dedicated, explicit
  quickstart is clearer than overloading `rac new`.

## Success Measures

- `rac quickstart` on an empty corpus writes exactly one artifact and
  exits 0; on a non-empty corpus it writes nothing and exits 1.
- The scaffolded artifact is byte-compatible with `rac new` output of the
  same type.
- No code path lets `rac quickstart` overwrite or re-scaffold an existing
  artifact.

## Review Date

Revisit if onboarding ever needs more than one starter artifact, at
which point the empty-corpus bound and ADR-024 need re-examination
together.

## Related Requirements

- rac-growth-adoption

## Related Roadmaps

- v0.13.0-guided-first-run
