"""Repository state comparison — base vs head product knowledge (v0.12.0).

``load_state`` walks one repository state (any directory) into a
:class:`RepoState`; ``compare_states`` derives what changed between two
states: changed artifacts, a validation delta, a relationship delta, and a
statistics delta. Every number is read from the existing :class:`Repository`
model and relationship validation — comparison adds no independent analysis
(ADR-015).

Artifacts are matched by corpus-relative path, so the two states may live
anywhere on disk (a working tree and a materialized git revision, or two
fixture directories). A renamed artifact reports as removed plus added —
identity-based rename detection is a stated non-goal of v0.12.0.

The dataclasses here carry no ``to_dict``: the JSON contract lives with the
watchkeeper report that exposes them (ADR-007).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from asdecided.core.corpus import collect_corpus
from asdecided.core.models import Diff, Product
from asdecided.services.diff import diff as diff_products
from asdecided.services.relationships import (
    RelationshipIssue,
    RelationshipSummary,
    validation_from_corpus,
)
from asdecided.services.repository import Artifact, Repository, repository_from_corpus
from asdecided.services.validate import STATUS_INVALID, STATUS_VALID

# Stable change kinds (part of the watchkeeper JSON contract, ADR-007).
CHANGE_ADDED = "added"
CHANGE_MODIFIED = "modified"
CHANGE_REMOVED = "removed"

_CHANGE_ORDER = {CHANGE_ADDED: 0, CHANGE_MODIFIED: 1, CHANGE_REMOVED: 2}


@dataclass(frozen=True)
class RelationshipIssueRef:
    """One relationship-validation finding, keyed for cross-state set diffing.

    The fields mirror :class:`RelationshipIssue` with paths made
    corpus-relative, so the same broken reference compares equal across a
    materialized base revision and the working tree.
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
    raw: dict[str, str]  # file text — the change detector for modified artifacts
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
    raw: dict[str, str] = {}
    for entry in entries:
        rel = _rel(str(entry.path), directory)
        products[rel] = entry.product
        raw[rel] = Path(entry.path).read_text(encoding="utf-8")
    artifacts = {_rel(a.path, directory): a for a in repository.artifacts}
    issues = tuple(
        sorted(
            (_issue_ref(issue, directory) for issue in rel_validation.issues),
            key=_issue_sort_key,
        )
    )

    return RepoState(
        label=label if label is not None else directory,
        directory=directory,
        repository=repository,
        products=products,
        raw=raw,
        artifacts=artifacts,
        issues=issues,
    )


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


def compare_states(base: RepoState, head: RepoState) -> RepositoryComparison:
    """Derive every delta between two analysed repository states."""
    base_paths = set(base.raw)
    head_paths = set(head.raw)

    changes: list[ArtifactChange] = []
    for rel in sorted(head_paths - base_paths):
        artifact = head.artifacts.get(rel)
        changes.append(
            _change(
                CHANGE_ADDED,
                rel,
                artifact,
                base_status=None,
                head_status=artifact.status if artifact else None,
            )
        )
    for rel in sorted(base_paths & head_paths):
        if base.raw[rel] == head.raw[rel]:
            continue
        artifact = head.artifacts.get(rel)
        product_diff = diff_products(base.products[rel], head.products[rel])
        changes.append(
            _change(
                CHANGE_MODIFIED,
                rel,
                artifact,
                base_status=base.artifacts[rel].status if rel in base.artifacts else None,
                head_status=artifact.status if artifact else None,
                diff=None if product_diff.is_empty() else product_diff,
            )
        )
    for rel in sorted(base_paths - head_paths):
        artifact = base.artifacts.get(rel)
        changes.append(
            _change(
                CHANGE_REMOVED,
                rel,
                artifact,
                base_status=artifact.status if artifact else None,
                head_status=None,
            )
        )
    changes.sort(key=lambda c: (_CHANGE_ORDER[c.change], c.path))

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
    validation = ValidationDelta(
        base_valid=base.repository.portfolio.valid_artifacts,
        base_invalid=base.repository.portfolio.invalid_artifacts,
        head_valid=head.repository.portfolio.valid_artifacts,
        head_invalid=head.repository.portfolio.invalid_artifacts,
        newly_invalid=newly_invalid,
        newly_valid=newly_valid,
    )

    base_issues = set(base.issues)
    head_issues = set(head.issues)
    relationships = RelationshipDelta(
        base=base.repository.portfolio.relationships,
        head=head.repository.portfolio.relationships,
        new_issues=tuple(sorted(head_issues - base_issues, key=_issue_sort_key)),
        resolved_issues=tuple(sorted(base_issues - head_issues, key=_issue_sort_key)),
    )

    base_by_type = base.repository.portfolio.by_type
    head_by_type = head.repository.portfolio.by_type
    by_type: dict[str, tuple[int, int]] = {}
    for type_name in list(head_by_type) + [t for t in base_by_type if t not in head_by_type]:
        by_type[type_name] = (base_by_type.get(type_name, 0), head_by_type.get(type_name, 0))
    stats = StatsDelta(
        by_type=by_type,
        total=(
            base.repository.portfolio.total_artifacts,
            head.repository.portfolio.total_artifacts,
        ),
    )

    return RepositoryComparison(
        base=base,
        head=head,
        changes=changes,
        validation=validation,
        relationships=relationships,
        stats=stats,
    )
