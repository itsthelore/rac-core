---
schema_version: 1
id: RAC-KV2KYJ60TJ1C
type: requirement
---
# REQ-OKF-Carrier-Profile

> The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY in this document are
> to be interpreted as described in BCP 14 (RFC 2119, RFC 8174) when, and only
> when, they appear in all capitals.

## Status

Proposed

## Problem

RAC stores product knowledge as a Git tree of typed Markdown artifacts with YAML
front matter. Google Cloud's Open Knowledge Format (OKF v0.1 Draft) describes the
same carrier and is gaining tooling, so a RAC repository is *almost* an OKF
bundle already. The gap is small but real: OKF requires every artifact to carry a
non-empty `type`, and RAC's `type` is currently optional in front matter. Without
a guaranteed `type` and a derived bundle view, RAC forfeits free
interoperability and an independent, external validation of its carrier — for the
cost of a single field. ADR-048 decides RAC adopts OKF as an informative carrier
profile and derived export target; this requirement scopes that adoption as
checkable behaviour without loosening any RAC guarantee.

## Requirements

- [REQ-001] Every RAC artifact MUST carry a non-empty `type` drawn from the enumerated set (`requirement`, `decision`, `roadmap`, `prompt`, `design`), so that a RAC repository is a conformant OKF v0.1 bundle.

- [REQ-002] RAC MUST provide a derived OKF bundle view that maps RAC `type` to OKF `type` (`requirement`→`Requirement`, `decision`→`ADR`, `design`→`Design`, `roadmap`→`Roadmap`, `prompt`→`Prompt`); the OKF view MUST be a derived contract parallel to the JSON/Portal export (ADR-007), never a new source format, with RAC front matter and `## Related <Type>` sections remaining authoritative.

- [REQ-003] In the derived OKF view, each resolved structural relationship MUST appear as a body link, so that relationship information survives for permissive OKF consumers while the typed sections stay the source of truth.

- [REQ-004] RAC normativity MUST NOT be loosened to satisfy OKF: `rac validate` and `rac relationships --validate` MUST keep rejecting exactly what they reject today, and structural references MUST NOT be replaced by prose links (ADR-016).

- [REQ-005] RAC SHOULD adopt OKF's progressive-disclosure `index.md`, date-grouped `log.md` history (derived from Git per ADR-045), and `# Citations` body convention where RAC has gaps; the dependency on OKF MUST remain informative and pinned to OKF v0.1, with no code, package, or network dependency on OKF or Google tooling.

## Acceptance Criteria

- `rac validate rac/` reports zero artifacts with a missing or empty `type`.
- A derived OKF export emits one bundle entry per artifact, each with an OKF
  `type` equal to the mapped RAC `type` for all five types.
- For every relationship that `rac relationships --validate` resolves, the
  derived OKF view contains a corresponding body link to the target.
- Re-running `rac validate` and `rac relationships --validate` before and after
  the OKF work yields identical exit codes and findings on the same corpus state
  (no loosening).
- The repository declares no build, runtime, or test dependency on any OKF or
  Google package, and the OKF profile cites OKF v0.1 explicitly.

## Success Metrics

- A RAC repository passes an independent OKF v0.1 conformance check unmodified.
- The OKF export and the JSON/Portal export agree on artifact identity, `type`,
  and resolved relationships for the same corpus.

## Risks

- OKF is a pre-1.0, single-vendor draft; its conventions may change. Mitigated by
  keeping the dependency informative and pinned, and reassessing at OKF 1.0 via a
  new ADR (ADR-048, decision point 5).
- Treating the OKF bundle as a frozen contract would extend RAC's stability
  obligations (ADR-007). Mitigated by keeping the OKF view a derived contract and
  routing any promotion to a frozen contract through a new ADR.

## Assumptions

- The relationship model stays "structural references in Markdown sections"
  (ADR-016); this requirement concerns conformance and export, not the mechanism.
- The base metadata contract (ADR-025) can guarantee a non-empty `type` without
  otherwise changing front matter; the precise mechanism is implementation,
  scoped to a future release.

## Priority

This sits in the same band as the JSON/derived-contract work it parallels
(ADR-007): valuable interoperability that is additive and non-blocking, below
RAC's core validation guarantees. The conformance field (REQ-001) is the
higher-priority half because it is a one-field change that unlocks the rest; the
derived export (REQ-002, REQ-003) follows at the derived-contract band.

## Related Decisions

- ADR-048
- ADR-004
- ADR-016
- ADR-007
- ADR-014

## Related Requirements

- rac-portal-citation-links
