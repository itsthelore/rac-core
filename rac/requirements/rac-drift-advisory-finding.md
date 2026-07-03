---
schema_version: 1
id: RAC-KWK4VDB1B7B4
type: requirement
---
# Requirement: Drift Advisory Finding

## Status

Proposed

Classification: `[internal]` — the git-native suspect link. Initiative 2
(phase 1) of the `freshness-and-drift-detection` roadmap.

## Problem

A target artifact can change while everything referencing it stays
untouched; the corpus holds both the relationship graph and the commit
dates, but emits no signal — the proven failure mode that PR review alone
does not catch (the 27,772-PR evidence in the roadmap). Enterprise tools
call this a "suspect link"; Lore has the raw material for a deterministic,
git-native equivalent and currently says nothing.

## Requirements

- [REQ-001] `rac doctor` MUST emit a new finding with a stable code (working name `suspect-artifact`, following the existing code-registry style) when a validated relationship target's last-committed change is newer than the referencing artifact's own last change — computed solely from the git-derived recency service (ADR-045) and the validated relationship graph (ADR-074).
- [REQ-002] The finding MUST be advisory: warning severity in the existing finding shape (path, code, severity, problem, fix), appended through the existing diagnose seam; warning-only runs exit 0; `rac review` MUST surface the same finding through its advisory channel beside the existing stale-corpus cadence advisory.
- [REQ-003] Drift MUST be computed only over declared, resolvable artifact references; external-reference sections (related tickets, verified by) are format-linted and never resolved (ADR-087) and MUST be excluded.
- [REQ-004] The finding MUST name the newer target and the evidencing commits and dates as reported facts, with a "review recommended" fix suggestion — never a correctness verdict, and never an auto-fix (ADR-034; auto-fix is a recorded non-goal).
- [REQ-005] Outside git, or where history cannot answer (shallow clones, untracked files), the check MUST produce no findings and no errors (the ADR-045 degrade posture).
- [REQ-006] Byte-pinned golden outputs MUST NOT depend on uncontrolled git state: drift findings appear only in fixtures whose git history the test controls, or stay out of byte-pinned goldens entirely.
- [REQ-007] This capability MUST NOT gate in this phase: no CI-failing mode ships; the gate form is a later-phase initiative under ADR-075's opt-in posture and, if needed, its own decision. The finding shape MUST admit additive extension to code-scope drift once `decision-to-code-proximity`'s declared scopes exist — the recorded phase-2 seam — without renaming the stable code.

## Acceptance Criteria

- Controlled-history fixture: committing a change to a target but not its
  referrer produces a deterministic suspect finding naming both,
  byte-identical across repeated runs.
- Committing a newer change to the referrer then clears the finding.
- `rac doctor` exits 0 with only suspect warnings present; `rac review`
  shows the advisory beside the cadence advisory.
- A no-git fixture yields zero findings and zero errors.
- The full byte-pinned golden suite passes unchanged.
- An artifact whose only references are external (tickets) yields no
  suspect finding.

## Success Metrics

- The corpus surfaces its own decay: a changed target reliably marks its
  stale referrers for review, and the team sees it before a reader trips
  over it.

## Risks

- Over-flagging trains people to ignore the signal. Mitigation: REQ-003
  scopes drift to declared, resolvable references; the stable code lets
  consumers filter; advisory-first is REQ-007's fence.
- Shallow CI clones silently weaken the signal. Mitigation: REQ-005's
  absent-rather-than-wrong posture, with the limitation documented.

## Assumptions

- Last-committed comparison over the relationship graph is a meaningful
  phase-1 drift proxy; finer-grained "meaningful change" scoping is tuned
  during phase 1 with real findings in hand.
- The Watchkeeper revision-materialisation seam (ADR-043) supplies
  per-artifact change sets if the comparison needs more than the recency
  service exposes.

## Related Decisions

- adr-002
- adr-034
- adr-043
- adr-045
- adr-065
- adr-066
- adr-074
- adr-075
- adr-087

## Related Roadmaps

- freshness-and-drift-detection
- decision-to-code-proximity

## Related Requirements

- rac-freshness-read-surfaces
- rac-doctor-diagnostic-validator
