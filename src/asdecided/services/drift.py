"""Git-native suspect-artifact drift detection (freshness-and-drift phase 1).

A target artifact can change while everything referencing it stays untouched.
The corpus already holds both halves of the evidence — the validated
relationship graph (ADR-074) and git's commit dates (ADR-045) — but emits no
signal. This module joins the two into a deterministic, git-native equivalent of
the "suspect link" enterprise review tools surface: a referring artifact whose
resolved relationship target was committed *after* the referrer itself last
changed, so the reference may no longer reflect the target.

The computation is a pure function of git state and the resolved graph — no
wall-clock input — so a fixed git history yields byte-identical records across
runs (the golden-stability property the requirement leans on). It is advisory
only: it names facts (the newer target, both commit dates), never a correctness
verdict and never an auto-fix (ADR-034). Two consumers wrap the same records into
their own finding shapes — ``decided doctor`` and ``decided review`` — so the signal has
one source of truth.

Scope (REQ-003): only declared, resolvable artifact references participate.
External-reference sections (related tickets, verified by) resolve to no in-corpus
artifact by design (ADR-087), so they carry no ``resolved_path`` and are excluded
without a special case. Outside git, or where history cannot answer, every date is
``None`` and the result is empty — the ADR-045 degrade posture (REQ-005).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from asdecided.core.corpus import CorpusEntry
from asdecided.services.recency import last_committed_for_paths
from asdecided.services.relationships import relationships_from_corpus

# Stable finding code, shared by every surface that reports drift (ADR-007). The
# name is deliberately artifact-scoped, not link-scoped: phase 2 extends the same
# code to code-scope drift once declared scopes exist, without a rename (REQ-007).
CODE_SUSPECT_ARTIFACT = "suspect-artifact"


@dataclass(frozen=True)
class DriftRecord:
    """One suspect edge: a referrer whose resolved target changed more recently.

    ``target_ref`` is the reference text as declared (the source of truth,
    ADR-016); ``source_committed`` / ``target_committed`` are the evidencing
    git commit times, both known (a ``None`` on either side is not drift).
    """

    source_path: str
    target_path: str
    target_ref: str
    source_committed: datetime
    target_committed: datetime


def suspect_drift(directory: str, entries: list[CorpusEntry]) -> list[DriftRecord]:
    """Resolved relationship edges whose target was committed after the referrer.

    Deterministic and offline: reads the resolved graph (ADR-074) and one
    last-committed date per involved artifact (ADR-045), then keeps the edges
    where the target's date is strictly newer than the source's. Deduplicated per
    ``(source, target)`` pair — a source that references the same target in two
    sections yields one record — and sorted for a stable order. Empty outside git
    or when no reference resolves (REQ-003, REQ-005).
    """
    resolved = [rel for rel in relationships_from_corpus(entries) if rel.resolved_path is not None]
    if not resolved:
        return []

    involved: set[str] = set()
    for rel in resolved:
        involved.add(rel.source_path)
        involved.add(rel.resolved_path)  # type: ignore[arg-type]  # filtered non-None above
    committed = last_committed_for_paths(directory, involved)

    records: list[DriftRecord] = []
    seen: set[tuple[str, str]] = set()
    for rel in resolved:
        target_path = rel.resolved_path
        assert target_path is not None  # filtered above
        source_when = committed.get(rel.source_path)
        target_when = committed.get(target_path)
        if source_when is None or target_when is None:
            continue  # untracked / outside git — degrade to no finding (REQ-005)
        if target_when <= source_when:
            continue  # referrer is as new as its target — not suspect
        key = (rel.source_path, target_path)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            DriftRecord(
                source_path=rel.source_path,
                target_path=target_path,
                target_ref=rel.target,
                source_committed=source_when,
                target_committed=target_when,
            )
        )
    records.sort(key=lambda d: (d.source_path, d.target_path))
    return records


def drift_problem(record: DriftRecord) -> str:
    """The shared human-readable finding text: facts only, review recommended."""
    return (
        f"references {record.target_ref} which changed more recently "
        f"(target last committed {record.target_committed.isoformat()}, "
        f"this artifact {record.source_committed.isoformat()}) — review recommended"
    )
