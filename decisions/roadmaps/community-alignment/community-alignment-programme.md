---
schema_version: 1
id: RAC-KV7K127TT87W
type: roadmap
tags: [adoption, interop, standards, community]
---
# Community-Alignment Programme

## Outcomes

RAC neighbours a set of living community standards — one per artifact family.
This programme makes RAC's relationship to each of them explicit, coherent, and
recorded in one place, so that two things become true: a team can bring its
existing artifacts *into* RAC (onboarding), and RAC can emit each community's
canonical format and sit *inside* that community's tooling (dogfooding).

The framing is inherited from ADR-049: the markdown carrier and the per-type
schemas are *table stakes*; RAC's differentiator is deterministic, CI-enforced
validation of the corpus as a graph. Alignment therefore means *compatibility*
(recognise the format on the way in, emit it on the way out), never adopting a
community schema as RAC's source of truth.

For each family the programme records the same three things — the external
**authority**, the alignment **mechanism** (inbound recognition and/or an
outbound derived export), and the **corpus artifact** that holds the detail —
and then names where a gap remains:

- **decision ↔ MADR / Nygard / SMADR.** Mechanism: inbound field recognition
  (begun in v0.17.1) plus a new outbound derived MADR export. Record:
  `madr-decision-alignment` design (this programme's first concrete output).
  Gap closed here — decisions previously had no symmetric export, unlike
  prompts.
- **requirement ↔ ISO/IEC/IEEE 29148, EARS, BCP-14.** Mechanism: deterministic
  per-type checks (the decidable subset). Record: ADR-056 and the
  `per-type-standards-checks` design, scheduled in v0.17.1. No new work — the
  programme references it.
- **prompt ↔ dotprompt.** Mechanism: a derived `.prompt` export, source
  unchanged. Record: ADR-057. No new work — referenced.
- **carrier ↔ OKF.** Mechanism: an OKF-conformant bundle view and a
  conformance check, with `decision → ADR` already in the type map. Record:
  ADR-048, ADR-052, the `rac-okf-carrier-profile` requirement, and the
  v0.15.1 conformance gate. No new work — referenced.
- **roadmap ↔ ? and design ↔ ?.** No established external community authority
  is yet identified. Open: survey whether one exists (Now/Next/Later horizons
  and OKRs for roadmaps; RFC / design-doc conventions for designs) before
  proposing any alignment.

The outcome is a single map a reader can scan to see, per family, what RAC
already speaks, what it does not, and which artifact to read for the detail.

## Initiatives

### Initiative 1 — Decision ↔ MADR (the net-new gap)

Produce the `madr-decision-alignment` design: an exact MADR↔RAC field map, an
inbound recognition path that extends the v0.17.1 MADR-field work and the
`rac-import` skill, and an outbound derived MADR export that mirrors ADR-057's
dotprompt projection and ADR-048's OKF bundle. Bidirectional, deterministic,
source unchanged. This is the only family that lacked a symmetric design, and
it is delivered alongside this programme.

### Initiative 2 — Consolidate the already-recorded families

Reference, do not duplicate. Requirement (29148/EARS/BCP-14), prompt
(dotprompt), and carrier (OKF) alignment are already decided and designed; the
programme links to ADR-056 / `per-type-standards-checks`, ADR-057, and
ADR-048 / ADR-052 / `rac-okf-carrier-profile` / v0.15.1 respectively, and adds
nothing to them beyond the cross-cutting frame above.

### Initiative 3 — Survey the unaligned families

For roadmap and design, investigate whether a community authority worth
aligning to exists at all. If one does, record it as a new per-authority
design under `rac/designs/community-alignment/`; if none does, record that
finding so the question is not reopened without cause. **Done:** the
`roadmap-design-authority-survey` design records the result — neither family
has a qualifying authority (roadmap is dominated by methodologies and one
low-adoption schema; design has only whole-system frameworks and
project-specific RFC patterns, no cross-community per-artifact standard) — with
explicit reopen conditions. Both families stay RAC-native until a qualifying
standard emerges.

### Initiative 4 — Ecosystem presence and dogfooding

Establish RAC as a recognised tool in the adr ecosystem (the adr org index,
adr-manager / adr-log neighbours) and validate real community corpora —
MADR and adr-tools example repositories — as round-trip fixtures, so the
import/export claims are demonstrated against artifacts RAC did not author.
This is where the ADR-049 positioning line ("MADR validates one file; RAC
enforces the graph") is shown rather than asserted. Public-facing posting
stays behind the growth-programme's GATE-1.

## Success Measures

- A reader can name, for every RAC artifact family, its community authority,
  the alignment mechanism, and the artifact that records the detail — from this
  one document.
- Each per-authority design produced by the programme passes `rac validate`,
  and every relationship in this programme and its designs resolves under
  `rac relationships --validate`.
- Importing a real MADR or adr-tools decision yields a RAC artifact that
  validates; exporting a RAC decision yields a file a MADR consumer accepts.
- No community schema is adopted as a RAC source format; the ADR-049
  enforcement differentiator is preserved on every aligned family.

## Assumptions

- The programme is unscheduled: it lives in a named theme folder
  (`rac/roadmaps/community-alignment/`), not a version series, and feeds the
  adoption/interop releases rather than constituting one. Scheduling any
  outbound export is a later, separately recorded decision.
- This programme introduces the first `rac/designs/` subfolder
  (`community-alignment/`). Folder layout is ungoverned by any ADR and
  validation walks recursively, so the grouping is organizational only and
  changes no behaviour.
- The external standards remain as cited; the programme tracks the decidable,
  compatibility-level surface of each, not their evolving prose.

## Risks

- Scope sprawl across five families. Mitigated: only the decision/MADR gap is
  worked here; the rest are references, and the unaligned families are a survey
  before any commitment.
- Drift as upstream standards move (MADR, dotprompt, OKF are pre- or
  early-stable). Mitigated: each alignment is pinned and revisited in its own
  artifact, consistent with ADR-048's informative-dependency posture.
- Positioning confusion — alignment read as RAC conceding the differentiator.
  Mitigated: the ADR-049 frame is restated here and in each design; alignment
  is interop, not foundation.

## Related Decisions

- adr-049
- adr-048
- adr-052
- adr-057
- adr-056
- adr-036

## Related Requirements

- rac-cross-artifact-enforcement
- rac-okf-carrier-profile
- rac-growth-adoption
- rac-growth-positioning

## Related Designs

- madr-decision-alignment
- roadmap-design-authority-survey
- per-type-standards-checks

## Related Roadmaps

- growth-programme
- v0.17.0-single-document-import-skill
- v0.17.1-per-type-standards-enforcement
- v0.15.1-okf-conformance-check
