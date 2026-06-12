"""Watchkeeper — RAC's product knowledge review surface (v0.12.0).

``build_watchkeeper_report`` resolves the base and head of a comparison —
each either an existing directory or a git revision materialized through
:mod:`rac.services.revisions` — loads both states, and assembles the report
the ``rac watchkeeper`` command renders. Watchkeeper consumes Core
intelligence; it computes nothing the comparison services do not already
provide (ADR-015).

``WatchkeeperReport.to_dict`` is the stable JSON contract (ADR-007): fields
are additive across the v0.12.x series and schema_version-gated.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path

from rac.core.models import Diff
from rac.services.compare import (
    ArtifactChange,
    RelationshipIssueRef,
    RepositoryComparison,
    compare_states,
    load_state,
)
from rac.services.relationships import RelationshipSummary
from rac.services.revisions import materialized_revision, repository_root


@dataclass
class WatchkeeperReport:
    """One product knowledge review: base state, head state, what changed."""

    directory: str
    base: str  # base label: revision name or directory path
    head: str  # head label: revision name or directory path (working tree)
    comparison: RepositoryComparison

    @property
    def has_changes(self) -> bool:
        return bool(self.comparison.changes)

    def to_dict(self) -> dict:
        validation = self.comparison.validation
        relationships = self.comparison.relationships
        stats = self.comparison.stats
        return {
            "schema_version": "1",
            "directory": self.directory,
            "base": self.base,
            "head": self.head,
            "changes": [_change_dict(change) for change in self.comparison.changes],
            "validation": {
                "base": {"valid": validation.base_valid, "invalid": validation.base_invalid},
                "head": {"valid": validation.head_valid, "invalid": validation.head_invalid},
                "newly_invalid": list(validation.newly_invalid),
                "newly_valid": list(validation.newly_valid),
            },
            "relationships": {
                "base": _summary_dict(relationships.base),
                "head": _summary_dict(relationships.head),
                "new_issues": [_issue_dict(issue) for issue in relationships.new_issues],
                "resolved_issues": [_issue_dict(issue) for issue in relationships.resolved_issues],
            },
            "stats": {
                "total": {"base": stats.total[0], "head": stats.total[1]},
                "by_type": {
                    type_name: {"base": counts[0], "head": counts[1]}
                    for type_name, counts in stats.by_type.items()
                },
            },
        }


def _change_dict(change: ArtifactChange) -> dict:
    payload: dict = {
        "change": change.change,
        "type": change.type,
        "id": change.id,
        "title": change.title,
        "path": change.path,
        "base_status": change.base_status,
        "head_status": change.head_status,
    }
    if change.diff is not None:
        payload["diff"] = _diff_dict(change.diff)
    return payload


def _diff_dict(diff: Diff) -> dict:
    # Mirrors the `rac diff` JSON fields so the requirement-level shape is
    # the same wherever a diff appears.
    return {
        "added_requirements": [asdict(r) for r in diff.added_requirements],
        "removed_requirements": [asdict(r) for r in diff.removed_requirements],
        "modified_requirements": [asdict(c) for c in diff.modified_requirements],
        "added_metrics": diff.added_metrics,
        "removed_metrics": diff.removed_metrics,
        "added_risks": diff.added_risks,
        "removed_risks": diff.removed_risks,
    }


def _summary_dict(summary: RelationshipSummary) -> dict:
    return {
        "total": summary.total,
        "valid": summary.valid,
        "broken": summary.broken,
        "orphaned": summary.orphaned,
        "coverage": summary.coverage,
    }


def _issue_dict(issue: RelationshipIssueRef) -> dict:
    return {
        "code": issue.code,
        "relationship": issue.relationship,
        "target": issue.target,
        "path": issue.path,
        "identifier": issue.identifier,
    }


def _resolve_side(stack: ExitStack, directory: str, ref: str) -> str:
    """A directory for one comparison side: ``ref`` itself, or a materialization."""
    if Path(ref).is_dir():
        return ref
    root = repository_root(directory)
    subpath = os.path.relpath(os.path.abspath(directory), root)
    return str(stack.enter_context(materialized_revision(root, ref, subpath)))


def build_watchkeeper_report(
    directory: str, *, base: str, head: str | None = None
) -> WatchkeeperReport:
    """Compare ``directory``'s corpus between ``base`` and ``head``.

    ``base`` and ``head`` each name an existing directory (used as-is) or a
    git revision of the repository containing ``directory``; ``head`` of
    ``None`` means the working tree at ``directory``.
    """
    head_label = head if head is not None else directory
    with ExitStack() as stack:
        base_dir = _resolve_side(stack, directory, base)
        head_dir = _resolve_side(stack, directory, head) if head is not None else directory
        base_state = load_state(base_dir, label=base)
        head_state = load_state(head_dir, label=head_label)
        comparison = compare_states(base_state, head_state)
    return WatchkeeperReport(directory=directory, base=base, head=head_label, comparison=comparison)
