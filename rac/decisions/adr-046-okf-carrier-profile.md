---
schema_version: 1
id: RAC-KV2KWK55FC49
type: decision
---
# ADR-046: OKF as an Informative Carrier Profile

## Status

Proposed

## Category

Architecture

## Context

Google Cloud has published the Open Knowledge Format (OKF) — `okf/SPEC.md`,
v0.1 Draft — in the `GoogleCloudPlatform/knowledge-catalog` samples repository.
OKF and RAC independently arrived at the same carrier: a Git tree of Markdown
files with YAML front matter, human-readable and reviewable in a pull request.
For interop that convergence is a gift; RAC artifacts are already shaped like
OKF bundles.

But OKF is the inverse of RAC exactly where RAC's value lives:

- **Permissive consumption.** OKF consumers MUST NOT reject a bundle for missing
  fields, an unknown `type`, unknown keys, or broken links. RAC is
  schema-normative: `rac validate` rejects malformed artifacts, and `rac
  relationships --validate` rejects broken or ambiguous references.
- **Untyped links.** In OKF the relationship kind lives in prose. In RAC,
  relationships are explicit structural references declared in `## Related
  <Type>` sections, resolved against artifact identity and validated (ADR-016).
  They are not as richly typed as a labelled-edge graph, but they are *typed by
  target type and machine-resolved* — the opposite of prose.
- **Free `type`.** OKF's `type` is an unregistered free string. RAC has five
  enumerated artifact types (`requirement`, `decision`, `roadmap`, `prompt`,
  `design`) that drive classification and validation.
- **No findings model.** OKF defines no review or findings output. RAC ships
  `rac review` / `rac watchkeeper` with a deterministic, prioritised findings
  model.
- **Maturity.** OKF is a pre-1.0, single-vendor draft. RAC's contracts are
  governed and stability-tested (ADR-007).

The question is how RAC should relate to OKF without surrendering any of the
properties above. Founding RAC on OKF would dissolve typed structural references
(ADR-016) and the strict consumption model that make RAC trustworthy. Ignoring
OKF would forfeit cheap interoperability and a second, independent validation of
RAC's carrier — for the sake of one field (`type`) RAC almost already emits.

This decision interprets the artifact model (ADR-004), its metadata contract
(ADR-025), and the derived-contract posture behind the JSON/Portal export
(ADR-007, ADR-014); it must respect the relationship model (ADR-016) and the
Git-native carrier (ADR-013).

## Decision

RAC adopts OKF as an **informative carrier profile** and a **derived export
target** — never a foundation. RAC Core remains the single source of truth.
Specifically:

1. **Conformance.** Every RAC repository MUST be a conformant OKF v0.1 bundle.
   Every artifact MUST carry a non-empty `type`. The OKF bundle view maps RAC's
   `type` to OKF's `type`: `requirement` → `Requirement`, `decision` → `ADR`,
   `design` → `Design`, `roadmap` → `Roadmap`, `prompt` → `Prompt`.

2. **Conventions (SHOULD).** Where RAC has gaps, it SHOULD adopt OKF's
   conventions: an `index.md` progressive-disclosure entry point, a date-grouped
   `log.md` corpus history (derived from Git, consistent with ADR-045), and a
   `# Citations` body convention for human-facing references.

3. **Derived contract.** The OKF bundle view MUST be a *derived* contract,
   parallel to the existing JSON/Portal export (ADR-007), not a new source
   format. RAC's typed front matter and `## Related <Type>` sections stay
   authoritative; in the OKF view, structural relationships degrade gracefully to
   derived body links.

4. **No loosening.** RAC's normativity MUST NOT be loosened to accommodate OKF.
   `rac validate` keeps rejecting what it rejects today; `rac relationships
   --validate` keeps rejecting broken and ambiguous references; structural
   references are not replaced by prose links (ADR-016 stands unchanged).

5. **Informative, pinned dependency.** The dependency on OKF is informative and
   pinned to OKF v0.1. RAC takes no code, package, or network dependency on OKF
   or Google tooling. The single-vendor, pre-1.0 risk is accepted and tracked;
   any move to treat the OKF bundle as a frozen contract is reassessed at OKF 1.0
   and recorded as a *new* ADR (the governed change path), never a silent edit
   to an accepted decision.

## Consequences

### Positive

- RAC gains cheap, standards-aligned interop: a RAC repo is readable by any OKF
  consumer, and OKF tooling becomes a second, independent check on RAC's carrier.
- The work is additive and small — RAC already emits almost everything OKF asks
  for; the gap is a guaranteed non-empty `type` and a derived bundle view.
- RAC's strict guarantees are untouched; nothing a user relies on for trust
  changes.

### Negative

- RAC carries an OKF profile and a derived export to keep in step with a pre-1.0
  spec that may change under it.
- The mapping (`decision` ↔ `ADR`, etc.) is one more contract surface to test and
  document.

### Neutral

- The SHOULD conventions (`index.md`, `log.md`, `# Citations`) are recorded as
  intent here; whether and when to implement their generators is scoped by the
  related requirement and fenced to a future release.
- If OKF diverges materially at 1.0, RAC can drop or re-pin the profile without
  touching Core — the dependency is informative by construction.

## Alternatives Considered

- **Found RAC on OKF.** Rejected. OKF's permissive consumption and prose links
  are incompatible with RAC's reason to exist: it would destroy the typed
  structural-reference model (ADR-016) and the strict validation users trust.
- **Ignore OKF entirely.** Rejected. RAC already produces an OKF-shaped tree;
  declining the profile forfeits free interoperability and an external validation
  of the carrier for the cost of a single guaranteed field.

## Related Decisions

- ADR-004
- ADR-025
- ADR-016
- ADR-007
- ADR-014
- ADR-013

## Related Requirements

- rac-okf-carrier-profile
