"""Artifact drift detection — the git-native "suspect link" (phase 1).

A referenced target can change in git while the artifact that references it stays
untouched. The corpus already holds both the validated relationship graph
(ADR-074) and every artifact's last-committed time (ADR-045), but emits no signal
— the failure mode PR review alone is proven not to catch (the 27,772-PR evidence
in the `freshness-and-drift-detection` roadmap). Enterprise requirements tools
call this a "suspect link"; this is Lore's deterministic, git-native equivalent.

Drift is a pure function of the resolved relationship graph and git recency, with
no wall-clock input: a finding exists exactly when a validated, resolvable
reference points at a target whose last commit is newer than the referring
artifact's own last commit. It is advisory and never a verdict (ADR-034) — "review
recommended," not "wrong" — and never an auto-fix (a recorded non-goal).

Only declared, resolvable artifact references are considered. External-reference
sections (related tickets, verified by) are format-linted and never resolved
(ADR-087), so they carry ``resolved_path is None`` and are excluded — never dated.
Every value degrades to silence outside git, for untracked files, or in a shallow
clone missing the commits (ADR-045): no findings, never an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rac.core.corpus import CorpusEntry, walk_corpus
from rac.services.recency import artifact_recency
from rac.services.relationships import relationships_from_corpus


@dataclass(frozen=True)
class DriftFinding:
    """One suspect link: a resolvable reference whose target changed after its referrer.

    ``source_committed`` / ``target_committed`` are the evidencing commit times —
    reported facts, with ``target_committed > source_committed`` the finding's whole
    condition (REQ-004).
    """

    source_path: str
    target_path: str
    relationship: str  # snake_case section name ("related_decisions", ...)
    source_committed: datetime
    target_committed: datetime


def detect_drift(
    directory: str,
    recursive: bool = True,
    *,
    entries: list[CorpusEntry] | None = None,
) -> list[DriftFinding]:
    """Every suspect link in ``directory``, deterministically ordered.

    Computed solely from the git-derived recency service (ADR-045) and the
    validated relationship graph (ADR-074) — resolved, unique, non-self,
    in-corpus edges only, so external references are excluded by construction
    (ADR-087). A pre-walked ``entries`` snapshot is reused when given (the doctor
    pass supplies one) to avoid a second corpus walk. Outside git every
    last-committed time is ``None`` and the result is empty (REQ-005).
    """
    if entries is None:
        entries = list(walk_corpus(directory, recursive=recursive))
    last_by_path = {
        a.path: a.last_committed for a in artifact_recency(directory, recursive=recursive).artifacts
    }
    findings: list[DriftFinding] = []
    seen: set[tuple[str, str]] = set()
    for rel in relationships_from_corpus(entries):
        if rel.resolved_path is None:  # unresolved / external / self — excluded
            continue
        source = last_by_path.get(rel.source_path)
        target = last_by_path.get(rel.resolved_path)
        if source is None or target is None:  # git cannot date one side — silent
            continue
        if target <= source:  # referrer is at least as fresh — not suspect
            continue
        key = (rel.source_path, rel.resolved_path)
        if key in seen:  # one finding per drifted edge, even if referenced twice
            continue
        seen.add(key)
        findings.append(
            DriftFinding(
                source_path=rel.source_path,
                target_path=rel.resolved_path,
                relationship=rel.relationship,
                source_committed=source,
                target_committed=target,
            )
        )
    findings.sort(key=lambda f: (f.source_path, f.target_path))
    return findings
