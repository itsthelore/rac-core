"""Base-vs-head comparison of two analysed repository states.

``load_state`` walks one directory into a fully analysed :class:`RepoState`;
``compare_states`` derives every delta between a base and a head state — which
artifacts changed, how validation moved, how relationship integrity moved, and
how the per-type artifact counts moved. Comparison performs no analysis of its
own: every number is read back from the :class:`Repository` model and the
relationship validation that ``load_state`` already produced (ADR-015).

States are matched by corpus-relative path, so the two sides may live anywhere
on disk (a working tree against a materialised git revision, or two fixture
trees). A rename therefore surfaces as a removal plus an addition — content-
based rename detection is a deliberate non-goal.

None of these dataclasses carry ``to_dict``: the JSON contract belongs to the
watchkeeper report that renders them (ADR-007).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from rac.core.corpus import collect_corpus
from rac.core.models import Diff, Product
from rac.services.diff import diff as diff_products
from rac.services.relationships import (
    RelationshipIssue,
    RelationshipSummary,
    validation_from_corpus,
)
from rac.services.repository import Artifact, Repository, repository_from_corpus
from rac.services.validate import STATUS_INVALID, STATUS_VALID

# Stable change kinds — part of the watchkeeper JSON contract (ADR-007).
CHANGE_ADDED = "added"
CHANGE_MODIFIED = "modified"
CHANGE_REMOVED = "removed"

# Presentation order for the change list: additions, then edits, then removals.
_CHANGE_ORDER = {CHANGE_ADDED: 0, CHANGE_MODIFIED: 1, CHANGE_REMOVED: 2}


@dataclass(frozen=True)
class RelationshipIssueRef:
    """One relationship-validation finding, keyed for cross-state set diffing.

    The fields mirror :class:`RelationshipIssue` with paths made corpus-relative,
    so the same broken reference compares equal across a materialised base
    revision and the working tree.
    """

    code: str
    relationship: str | None
    target: str | None
    path: str  # corpus-relative source path ("" for repository-level findings)
    identifier: str | None


@dataclass(frozen=True)
class RepoState:
    """One fully analysed repository state, keyed by corpus-relative path."""

    label: str
    directory: str
    repository: Repository
    products: dict[str, Product]
    raw_text: dict[str, str]  # file text — the change detector for modified artifacts
    artifacts: dict[str, Artifact]
    issues: tuple[RelationshipIssueRef, ...]


@dataclass(frozen=True)
class ArtifactChange:
    """One artifact that differs between the base and head states."""

    change: str  # CHANGE_ADDED | CHANGE_MODIFIED | CHANGE_REMOVED
    type: str  # canonical artifact name, or "unknown"
    id: str | None
    title: str | None
    path: str  # corpus-relative path (the matching key)
    base_status: str | None  # valid | invalid | skipped; None when absent
    head_status: str | None
    diff: Diff | None  # requirement-level diff for modified artifacts


@dataclass(frozen=True)
class ValidationDelta:
    """How validation outcomes moved between the states."""

    base_valid: int
    base_invalid: int
    head_valid: int
    head_invalid: int
    newly_invalid: tuple[str, ...]  # invalid in head, not invalid (or absent) in base
    newly_valid: tuple[str, ...]  # invalid in base, valid in head


@dataclass(frozen=True)
class RelationshipDelta:
    """How relationship integrity moved between the states."""

    base: RelationshipSummary
    head: RelationshipSummary
    new_issues: tuple[RelationshipIssueRef, ...]
    resolved_issues: tuple[RelationshipIssueRef, ...]


@dataclass(frozen=True)
class StatsDelta:
    """How repository-level artifact counts moved between the states."""

    by_type: dict[str, tuple[int, int]]  # type -> (base, head)
    total: tuple[int, int]


@dataclass
class RepositoryComparison:
    """Everything that changed between a base and a head repository state."""

    base: RepoState
    head: RepoState
    changes: list[ArtifactChange]
    validation: ValidationDelta
    relationships: RelationshipDelta
    stats: StatsDelta


def _rel(path: str, directory: str) -> str:
    return os.path.relpath(path, directory).replace(os.sep, "/")


def _issue_ref(issue: RelationshipIssue, directory: str) -> RelationshipIssueRef:
    if issue.source_path is not None:
        path = _rel(issue.source_path, directory)
    elif issue.paths:
        # Duplicate-identifier findings span files; key on the sorted set.
        path = ", ".join(sorted(_rel(p, directory) for p in issue.paths))
    else:
        path = ""
    return RelationshipIssueRef(
        code=issue.code,
        relationship=issue.relationship,
        target=issue.target,
        path=path,
        identifier=issue.identifier,
    )


def _issue_sort_key(ref: RelationshipIssueRef) -> tuple[str, str, str, str, str]:
    return (ref.code, ref.path, ref.relationship or "", ref.target or "", ref.identifier or "")


def load_state(directory: str, *, label: str | None = None) -> RepoState:
    """Walk ``directory`` once and analyse it as one comparison side."""
    entries = collect_corpus(directory)
    repository = repository_from_corpus(directory, entries)
    rel_validation = validation_from_corpus(directory, entries)

    products: dict[str, Product] = {}
    raw_text: dict[str, str] = {}
    for entry in entries:
        rel = _rel(str(entry.path), directory)
        products[rel] = entry.product
        raw_text[rel] = Path(entry.path).read_text(encoding="utf-8")
    artifacts = {_rel(a.path, directory): a for a in repository.artifacts}
    issues = tuple(
        sorted(
            (_issue_ref(issue, directory) for issue in rel_validation.issues),
            key=_issue_sort_key,
        )
    )

    return RepoState(
        label=directory if label is None else label,
        directory=directory,
        repository=repository,
        products=products,
        raw_text=raw_text,
        artifacts=artifacts,
        issues=issues,
    )


def _status(artifact: Artifact | None) -> str | None:
    return artifact.status if artifact else None


def _change(
    kind: str,
    rel: str,
    artifact: Artifact | None,
    *,
    base_status: str | None,
    head_status: str | None,
    diff: Diff | None = None,
) -> ArtifactChange:
    return ArtifactChange(
        change=kind,
        type=artifact.type if artifact else "unknown",
        id=artifact.id if artifact else None,
        title=artifact.title if artifact else None,
        path=rel,
        base_status=base_status,
        head_status=head_status,
        diff=diff,
    )


def _artifact_changes(base: RepoState, head: RepoState) -> list[ArtifactChange]:
    """Every added / modified / removed artifact, in ``(kind, path)`` order."""
    base_paths = set(base.raw_text)
    head_paths = set(head.raw_text)
    changes: list[ArtifactChange] = []

    # Present only in head.
    for rel in head_paths - base_paths:
        artifact = head.artifacts.get(rel)
        changes.append(
            _change(
                CHANGE_ADDED,
                rel,
                artifact,
                base_status=None,
                head_status=_status(artifact),
            )
        )

    # Present in both, but the file bytes differ. The raw text — not the AST —
    # is the change detector: an edit whose parsed diff is empty still reports
    # as modified, only without a requirement-level diff.
    for rel in base_paths & head_paths:
        if base.raw_text[rel] == head.raw_text[rel]:
            continue
        artifact = head.artifacts.get(rel)
        product_diff = diff_products(base.products[rel], head.products[rel])
        changes.append(
            _change(
                CHANGE_MODIFIED,
                rel,
                artifact,
                base_status=_status(base.artifacts.get(rel)),
                head_status=_status(artifact),
                diff=None if product_diff.is_empty() else product_diff,
            )
        )

    # Present only in base.
    for rel in base_paths - head_paths:
        artifact = base.artifacts.get(rel)
        changes.append(
            _change(
                CHANGE_REMOVED,
                rel,
                artifact,
                base_status=_status(artifact),
                head_status=None,
            )
        )

    # A single total sort over a key that is unique per change (each path
    # appears under exactly one kind) makes insertion order above irrelevant.
    changes.sort(key=lambda change: (_CHANGE_ORDER[change.change], change.path))
    return changes


def _validation_delta(base: RepoState, head: RepoState) -> ValidationDelta:
    newly_invalid = tuple(
        sorted(
            rel
            for rel, artifact in head.artifacts.items()
            if artifact.status == STATUS_INVALID
            and (rel not in base.artifacts or base.artifacts[rel].status != STATUS_INVALID)
        )
    )
    newly_valid = tuple(
        sorted(
            rel
            for rel, artifact in head.artifacts.items()
            if artifact.status == STATUS_VALID
            and rel in base.artifacts
            and base.artifacts[rel].status == STATUS_INVALID
        )
    )
    return ValidationDelta(
        base_valid=base.repository.portfolio.valid_artifacts,
        base_invalid=base.repository.portfolio.invalid_artifacts,
        head_valid=head.repository.portfolio.valid_artifacts,
        head_invalid=head.repository.portfolio.invalid_artifacts,
        newly_invalid=newly_invalid,
        newly_valid=newly_valid,
    )


def _relationship_delta(base: RepoState, head: RepoState) -> RelationshipDelta:
    base_issues = set(base.issues)
    head_issues = set(head.issues)
    return RelationshipDelta(
        base=base.repository.portfolio.relationships,
        head=head.repository.portfolio.relationships,
        new_issues=tuple(sorted(head_issues - base_issues, key=_issue_sort_key)),
        resolved_issues=tuple(sorted(base_issues - head_issues, key=_issue_sort_key)),
    )


def _stats_delta(base: RepoState, head: RepoState) -> StatsDelta:
    base_by_type = base.repository.portfolio.by_type
    head_by_type = head.repository.portfolio.by_type
    # Head order first, then any type seen only in base, so the payload leads
    # with the current state's shape.
    ordered_types = list(head_by_type) + [t for t in base_by_type if t not in head_by_type]
    by_type = {
        type_name: (base_by_type.get(type_name, 0), head_by_type.get(type_name, 0))
        for type_name in ordered_types
    }
    return StatsDelta(
        by_type=by_type,
        total=(
            base.repository.portfolio.total_artifacts,
            head.repository.portfolio.total_artifacts,
        ),
    )


def compare_states(base: RepoState, head: RepoState) -> RepositoryComparison:
    """Derive every delta between two analysed repository states."""
    return RepositoryComparison(
        base=base,
        head=head,
        changes=_artifact_changes(base, head),
        validation=_validation_delta(base, head),
        relationships=_relationship_delta(base, head),
        stats=_stats_delta(base, head),
    )
