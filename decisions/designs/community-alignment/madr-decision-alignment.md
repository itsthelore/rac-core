---
schema_version: 1
id: RAC-KV7K13484Z0P
type: design
tags: [decisions, madr, adr, interop, export]
---
# Design: MADR / ADR Decision Alignment

## Context

The decision artifact's community neighbour is the **ADR** (Architecture
Decision Record) ecosystem. Three authorities matter:

- **MADR (Markdown Any Decision Records), v4.0.0** — `github.com/adr/madr`,
  the most-adopted Markdown ADR template. Its full template (verified against
  `raw.githubusercontent.com/adr/madr/main/template/adr-template.md`,
  fetched 2026-06-16) carries optional YAML front matter `status`, `date`,
  `decision-makers`, `consulted`, `informed`, and the headings, in order:
  `# {short title}`, `## Context and Problem Statement`, `## Decision Drivers`,
  `## Considered Options`, `## Decision Outcome` (with `### Consequences` and
  `### Confirmation`), `## Pros and Cons of the Options`, `## More Information`.
  The **minimal** template keeps only `# {title}`, `## Context and Problem
  Statement`, `## Considered Options`, `## Decision Outcome`, `### Consequences`.
  Files are `NNNN-title-with-dashes.md` under `docs/decisions/`. MADR follows
  the community **immutability + supersede** convention: an accepted record is
  not edited; a changed decision is a new record that supersedes the old.
- **Nygard / adr-tools** — the original 2011 floor (Title, Status, Context,
  Decision, Consequences), plain Markdown, no front matter; tooled by
  `npryce/adr-tools` (`adr new`, `adr new -s` to supersede).
- **SMADR (Structured MADR)** — `smadr.dev`, a machine-readable superset that
  adds a JSON Schema and richer front matter (`title`, `type`, `category`,
  `tags`, `status`, `created`, `updated`, `author`, risk/audit sections).

RAC already records most of how it relates to this ecosystem, but
asymmetrically. ADR-049 positions MADR as *table-stakes interop*, not a
differentiator; ADR-048 maps RAC `decision → ADR` in the OKF bundle; v0.17.1
plans to *recognise* optional MADR fields on the way in. What is missing is the
mirror of what prompts already have: ADR-057 gives the prompt artifact a
derived `--dotprompt` export, but the decision artifact has no derived MADR
export — so RAC can read MADR-shaped decisions but cannot emit canonical MADR.
This design closes that gap and states the full bidirectional picture in one
place, under the community-alignment programme.

## User Need

Two audiences, matching the programme's two goals:

- **Onboarding (inbound).** A team with an existing `docs/decisions/` tree of
  MADR or Nygard ADRs wants those files to classify as RAC `decision`
  artifacts and pass `rac validate`, so it can adopt RAC's graph enforcement
  without rewriting its history.
- **Dogfooding (outbound).** A team standardised on the adr ecosystem (MADR
  templates, adr-manager, adr-log) wants RAC to emit canonical MADR files, so
  RAC-authored decisions drop into a MADR repository and are read by existing
  ADR tooling unchanged.

Neither audience should have to abandon its format, and neither path may
weaken RAC's strict validation.

## Design

### 1. MADR ↔ RAC field map

The two formats are close; the map is mostly one-to-one onto RAC's existing
Decision schema (`src/rac/core/artifacts.py`), with a few deliberate
non-mappings called out.

| MADR (full template) | RAC Decision section | Notes |
| --- | --- | --- |
| `# {short title}` | `# Title` | one H1, required both sides |
| `## Context and Problem Statement` | `## Context` | required ↔ required |
| `## Decision Outcome` | `## Decision` | required ↔ required (the "chosen option") |
| `### Consequences` | `## Consequences` | required ↔ required |
| `## Considered Options` + `## Pros and Cons of the Options` | `## Alternatives Considered` | recommended; the two MADR sections fold into one |
| `## Decision Drivers` | recognised optional | already named in v0.17.1 field recognition |
| `### Confirmation`, `## More Information` | recognised optional / `## Related <Type>` | recognised inbound; on export, links degrade to body prose (as in OKF) |
| front matter `status` | `## Status` | enum maps; **MADR `rejected` has no RAC value** (gap, see Open Questions) |
| front matter `date` | git-derived | RAC never stores dates in source (ADR-045); derived on export |
| front matter `decision-makers` / `consulted` / `informed` | no source home | ADR-025 uniform envelope holds; recognised inbound, derived or omitted outbound |
| — | `## Category` (Architecture/Product/Process/Technical/Other) | RAC-only; no MADR equivalent — dropped or emitted as a tag on export |

The **Nygard floor** (Title, Status, Context, Decision, Consequences) is a
strict subset of the RAC required sections plus Status, so RAC already
classifies and validates a Nygard ADR with no new work. **SMADR** is a
machine-readable superset; its extra front matter is out of scope here and
recorded as an Open Question rather than mapped.

### 2. Inbound — recognise MADR / Nygard on the way in

Recognition reuses the existing classifier rather than adding a branch. The
classifier scores `##` headings against `ArtifactSpec` (`classification.py`),
and the spec already carries a `synonyms` table. MADR's heading vocabulary is
added there as decision-section synonyms — `context and problem statement →
context`, `decision outcome → decision`, `considered options → alternatives
considered` — so a MADR or Nygard file classifies as a `decision` and routes
through the normal validator. This *extends* the v0.17.1 MADR-field-recognition
initiative and the `rac-import` skill's single-document flow; it does not
re-decide them, and it adds no new command. A recognised MADR file then
benefits from RAC's graph checks the moment it joins a corpus.

### 3. Outbound — a derived MADR export

RAC gains a derived MADR view, exactly parallel to ADR-057's `--dotprompt`
projection and ADR-048's OKF bundle: a `rac export … --madr` surface (the
exact flag fenced to implementation) projects each `decision` artifact into a
canonical MADR file — MADR front matter (`status` from `## Status`, `date`
git-derived) and the MADR heading layout, written as `NNNN-title.md`. The RAC
source stays the uniform ADR-025 envelope; the MADR file is a *derived,
deterministic* contract regenerable from the artifact, never a second source of
truth (ADR-002, ADR-007). Validation aligns the *contract*, not the prose: RAC
checks that a decision can produce a valid MADR projection (the required
sections exist), exactly as ADR-057 checks the dotprompt projection — no model
judges the decision text.

### 4. Dogfooding hooks

Two demonstrations make the alignment concrete rather than asserted: (a) round-
trip fixtures built from real MADR and adr-tools example repositories — import,
validate, export, diff — proving RAC reads and re-emits artifacts it did not
author; (b) RAC's own `rac/decisions/` corpus exported to MADR as a reference
bundle. Both reinforce the ADR-049 line: MADR validates a single file in
isolation; RAC additionally enforces the corpus as a graph.

## Constraints

- **No AI in core (ADR-002).** Recognition and export are pure parsing and
  projection; nothing judges decision prose. Deterministic: same artifact, same
  MADR output and ordering.
- **Uniform envelope (ADR-025).** No MADR-specific fields enter decision
  *source* front matter; `decision-makers`/`consulted`/`informed`/`date` stay
  out of source and are derived or omitted on export.
- **Derived-contract pattern (ADR-048, ADR-057).** The MADR view is an export,
  parallel to OKF and dotprompt — one mental model for interchange views.
- **Additive, contract-stable (ADR-007).** New synonyms and a new export only;
  no existing decision code, enum, or JSON contract changes.
- **Identity (ADR-026).** RAC keeps its opaque `id`; MADR's `NNNN` sequential
  number is an export-time concern, not a second identity in source.
- **Table-stakes positioning (ADR-049).** MADR compatibility is interop, not
  the pitch; the graph-enforcement differentiator is untouched.

## Rationale

Reusing the derived-contract pattern (OKF, SARIF, dotprompt) means the MADR
view inherits determinism, regenerability, and the existing export plumbing,
and gives users one model for "speak another tool's format". Folding MADR
headings into the classifier's synonym table — rather than a MADR-specific
parser — keeps recognition spec-driven and consistent with how RAC already
handles section aliases. Together they close the prompt/decision asymmetry
(prompts could already be emitted to dotprompt; decisions could not be emitted
to MADR) at low cost, serving both onboarding and dogfooding without conceding
the differentiator.

## Alternatives

- **Add MADR fields to decision source front matter.** Rejected for the same
  reasons ADR-057 rejected the dotprompt analogue: it forks the uniform ADR-025
  envelope and pulls per-type schema machinery (and SMADR's JSON Schema) into
  source. Reconsider only on real demand.
- **Inbound recognition only (the v0.17.1 floor).** Insufficient: it serves
  onboarding but not dogfooding — RAC could read MADR but never emit it, leaving
  the prompt/decision asymmetry in place.
- **A hand-authored MADR sidecar per decision.** Rejected: a second source that
  drifts; the derived export gives the same output without the drift.
- **Do nothing.** Rejected: MADR is the decision-interop frontrunner and the
  derived view is cheap given the OKF/dotprompt precedent.

## Open Questions

- Pin to MADR 4.0.0, and revisit on a new MADR release (as ADR-048 does for
  OKF)?
- Is SMADR (the machine-readable superset) worth a separate export profile, or
  out of scope until a user asks?
- How should MADR's `rejected` status map, given RAC's lifecycle is
  Proposed/Accepted/Superseded/Deprecated (ADR-051)? And does MADR's
  immutability + supersede convention reconcile cleanly with RAC's `supersedes`
  relationship and status-consistency check?
- What is the export filename / numbering source — derive `NNNN` from a stable
  ordering, reuse the legacy `adr-NNN` prefix, or keep the opaque id?
- Which release series schedules the `--madr` export (v0.15.x interop or
  v0.17.x adoption)? Recorded here as intent; scheduling is a separate decision.

## Related Decisions

- adr-049
- adr-048
- adr-057
- adr-025
- adr-051
- adr-026
- adr-006
- adr-002
- adr-007

## Related Requirements

- rac-cross-artifact-enforcement
- rac-okf-carrier-profile

## Related Roadmaps

- community-alignment-programme
- v0.17.0-single-document-import-skill
- v0.17.1-per-type-standards-enforcement
