---
schema_version: 1
id: RAC-KV7KKEY005V9
type: design
tags: [roadmap, design, interop, standards, survey]
---
# Design: Roadmap and Design Authority Survey

## Context

The community-alignment programme's Initiative 3 asks whether RAC's **roadmap**
and **design** artifact families have an external community authority worth
aligning to — a MADR-equivalent — and to record the finding so the question is
not reopened without cause.

Four of RAC's five families already have such an authority: decision ↔ MADR,
prompt ↔ dotprompt, requirement ↔ ISO/IEC/IEEE 29148 + EARS, carrier ↔ OKF.
Each clears a recognisable bar that makes bidirectional interop (inbound
recognition + an outbound derived export) meaningful. This survey applies the
same bar to the two remaining families and records the result.

Findings derive from web research conducted 2026-06-16; primary URLs are cited
inline. Adoption is characterised qualitatively (and conservatively) — the
durable basis for each verdict is structural, not a snapshot of star counts.

The bar — a candidate qualifies only if it meets most of these:

1. **Named and community-maintained** — an open, named spec/repo, not a single
   vendor's product and not merely a blog-post concept.
2. **A concrete per-artifact file format** — a defined Markdown/YAML template or
   schema RAC could recognise and emit, not a methodology or a process.
3. **Tooling** — a CLI, editor extension, linter, or generator exists.
4. **Real adoption** — meaningful ecosystem presence, not a niche solo project.
5. **Per-artifact fit** — represents one roadmap / one design as a discrete
   document (as MADR represents one decision), so RAC could map its sections.

## User Need

A maintainer deciding where to spend alignment effort needs a defensible,
recorded answer for the two unaligned families, so effort flows to the families
where a real standard exists and is not repeatedly re-litigated for families
where none does. A negative finding, recorded with its reopen conditions, is the
deliverable.

## Design

### Roadmap family — finding: NO qualifying authority

| Candidate | Kind | Verdict |
| --- | --- | --- |
| Now/Next/Later (ProdPad) | methodology / time-horizon framework | NOT-A-FORMAT |
| OKRs (Objectives & Key Results) | goal-setting methodology | NOT-A-FORMAT |
| RICE | prioritisation technique | NOT-A-FORMAT |
| GitHub public roadmap | issues + project board, platform-bound | NOT-A-FORMAT |
| SierraSoftworks/roadmap | YAML + JSON-schema file format with a CLI | ADJACENT — fails adoption (tens of stars; no ecosystem) |

The product/release roadmap space is dominated by *methodologies* (Now/Next/
Later, OKRs, RICE) and *proprietary tools* (ProdPad, Jira, ProductPlan), none of
which is a portable, interoperable file format. The only genuine open file
format found, `SierraSoftworks/roadmap` (a YAML schema with a graphviz CLI), has
negligible adoption and no community presence. **No external roadmap authority
clears the bar.** Sources:
[ProdPad](https://www.prodpad.com/blog/invented-now-next-later-roadmap/),
[SierraSoftworks/roadmap](https://github.com/SierraSoftworks/roadmap),
[github/roadmap](https://github.com/github/roadmap).

### Design family — finding: NO qualifying authority

| Candidate | Kind | Verdict |
| --- | --- | --- |
| arc42 | whole-system architecture documentation (12 sections) | ADJACENT — not per-artifact |
| IEEE 1016 (SDD) | formal whole-system design standard, paywalled | ADJACENT — not per-artifact, not community-maintained |
| RFC / RFD tradition (Rust, React, PEP, Oxide) | per-proposal pattern, project-specific templates | ADJACENT — no shared cross-community standard |
| C4 model | architecture diagramming notation | NOT-A-FORMAT |
| DESIGN.md (Google Labs) | design-system token format (UI), different domain | NOT-A-FORMAT |
| Diátaxis / DACI / TOGAF | doc-structure / decision-roles / enterprise framework | NOT-A-FORMAT |

The strongest signals — the RFC/RFD tradition (Rust RFCs, React RFCs, Python
PEPs, Oxide RFDs) — prove that per-artifact design-as-code is popular, but each
project maintains its own template in its own repo; there is no shared,
cross-community design-doc standard to interoperate with. arc42 and IEEE 1016
are mature and named, but document a *whole system* rather than one design, so
they are containers for many designs, not a per-artifact peer to MADR. **No
single cross-community per-design-document authority comparable to MADR or
dotprompt exists.** Sources:
[arc42](https://arc42.org/),
[rust-lang/rfcs](https://github.com/rust-lang/rfcs),
[Oxide RFD 1](https://oxide.computer/blog/rfd-1-requests-for-discussion),
[Pragmatic Engineer: RFCs and design docs](https://blog.pragmaticengineer.com/rfcs-and-design-docs/).

### Cross-family conclusion

Of RAC's five families, **four** have a real external authority and a clear
interop mechanism; **two — roadmap and design — have none**. The bidirectional
recognition-plus-derived-export mechanism the programme defines therefore
applies to four families. For roadmap and design there is, at the survey date,
nothing to align to: no recognition target on import, no canonical format to
emit on export. These families stay RAC-native until a qualifying standard
emerges.

## Constraints

- **Do not invent alignment where no authority exists.** Building a derived
  export to a niche or single-vendor format would contradict the ADR-049 frame
  (alignment is table-stakes interop with a *community*, not the differentiator)
  and pin RAC to a moving, low-adoption target (cf. ADR-048's informative,
  pinned-dependency posture).
- **The finding is dated.** It reflects the 2026-06-16 landscape; standards
  move, so the verdict is revisited under the reopen conditions below, not
  treated as permanent.
- **Analysis only.** This artifact records a survey result; it changes no code
  and schedules no work.

## Rationale

Recording the negative finding is itself the value Initiative 3 asked for: it
stops the question being reopened without cause and concentrates alignment
effort on the four families that have a real peer. The verdict rests on durable
structural distinctions — methodology vs. file format, whole-system framework
vs. per-artifact document, project-specific pattern vs. cross-community standard
— rather than on adoption counts that will drift, so it remains sound even as
the specific projects evolve.

## Alternatives

- **Adopt SierraSoftworks/roadmap as RAC's roadmap interop target.** Rejected:
  it fails the adoption bar; aligning to a tens-of-stars solo project is not
  interop with a community and pins RAC to a moving niche format.
- **Treat arc42 or the RFC pattern as the design authority.** Rejected: arc42
  is whole-system, not per-design; the RFC tradition has no shared template or
  tooling to interoperate with — only per-project variants.
- **Publish RAC's own roadmap/design format and seek to make it the standard.**
  Out of scope for an alignment survey — that is a leadership move, recorded if
  pursued as a separate decision (an ADR), not concluded here.
- **Do nothing and leave the question implicit.** Rejected: the programme
  explicitly wants the finding recorded so it is not silently reopened.

## Open Questions

These are the conditions under which the question should be reopened:

- **Roadmap.** A roadmap file format reaches MADR-class adoption and tooling —
  for example `SierraSoftworks/roadmap` crosses a real adoption threshold, or a
  new community standard emerges with an open spec and ecosystem.
- **Design.** A cross-community per-artifact design-doc Markdown standard
  emerges — for example the RFC traditions converge on a shared template, or
  arc42 ships a per-design sub-template usable as a discrete artifact.
- **Leadership.** Whether RAC should publish its own roadmap/design format
  (rather than align to one) is a separate, future decision, not part of this
  survey.

## Related Decisions

- adr-049
- adr-048
- adr-057

## Related Roadmaps

- community-alignment-programme
