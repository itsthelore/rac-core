"""First-class repository model — the navigable view of a RAC repository (v0.8.0).

``load_repository`` walks a directory once and composes the existing services
into one object a long-lived consumer can navigate without scanning files
(ADR-015): indexed artifacts, declared relationships with their resolution
outcomes, unified diagnostics, and the portfolio summary. It contains no CLI
or TUI concepts and adds no new intelligence — every number here is obtainable
through ``rac index`` / ``rac validate`` / ``rac relationships`` /
``rac portfolio``.

The model types carry no ``to_dict``: there is no new JSON contract until a
CLI command exposes one (ADR-007).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rac.core.artifacts import spec_for
from rac.core.classification import missing_sections
from rac.core.corpus import CorpusEntry, collect_corpus
from rac.core.models import SearchSection
from rac.core.operations import CancelToken, Progress, ProgressCallback, checkpoint

from .index import index_from_corpus
from .portfolio import PortfolioSummary, portfolio_from_corpus
from .relationships import (
    ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS,
    ISSUE_TARGET_NOT_FOUND,
    Relationship,
    RelationshipIssue,
    relationships_from_corpus,
    validation_from_corpus,
)
from .validate import validate_corpus

# Diagnostic sources (which analysis produced the finding).
SOURCE_VALIDATION = "validation"
SOURCE_RELATIONSHIPS = "relationships"

# Human phrasing for relationship findings, keyed by their stable issue codes.
_REL_PHRASE = {
    ISSUE_TARGET_NOT_FOUND: "target not found",
    ISSUE_TARGET_AMBIGUOUS: "ambiguous target",
    ISSUE_SELF_REFERENCE: "self-reference",
}


@dataclass(frozen=True)
class Artifact:
    """One artifact in the navigable repository view.

    A join of the index inventory (identity, type, title, path, aliases) and
    directory validation (``status``: ``valid`` / ``invalid`` / ``skipped``),
    covering every supported type plus ``unknown``.

    ``missing_recommended`` (v0.8.1) lists the schema-recommended sections the
    artifact does not fill — the same completeness rules ``rac inspect`` and
    ``rac portfolio`` report; always empty for unknown artifacts.
    """

    id: str
    type: str
    title: str | None
    path: str
    aliases: tuple[str, ...]
    status: str
    missing_recommended: tuple[str, ...] = ()
    # Searchable section headings/body lines, original text preserved (v0.10.3):
    # lets the repository model serve body-tier `rac find` searches through the
    # shared resolver seam without a second walk. Not part of any JSON contract.
    search_sections: tuple[SearchSection, ...] = ()
    # Inbound resolved-edge count, the graph signal the relevance ranker fuses
    # (ADR-078); carried so a repository-model search ranks like every other
    # surface. Not part of any JSON contract.
    inbound_count: int = 0


@dataclass(frozen=True)
class Diagnostic:
    """One finding about the repository, unified across analyses.

    ``code`` reuses the stable codes of the producing analysis verbatim
    (validation issue codes, relationship issue codes), so a diagnostic always
    corresponds to a finding the CLI reports.
    """

    source: str  # SOURCE_VALIDATION | SOURCE_RELATIONSHIPS
    severity: str  # "error" | "warning"
    code: str
    message: str
    path: str
    identifier: str | None


@dataclass
class Repository:
    """The navigable representation of a RAC repository (v0.8.0).

    Artifacts, relationships, and diagnostics arrive in deterministic
    (sorted-path walk) order; ``portfolio`` carries the repository-level
    intelligence (counts, completeness, attention, health score).
    """

    directory: str
    recursive: bool
    artifacts: list[Artifact]
    relationships: list[Relationship]
    diagnostics: list[Diagnostic]
    portfolio: PortfolioSummary

    @property
    def health_score(self) -> int:
        return self.portfolio.health_score

    def artifact(self, ref: str) -> Artifact | None:
        """The artifact uniquely answering to ``ref`` (id or alias), else None.

        Matching is casefolded. Ambiguous references return None — reporting
        ambiguity is relationship validation's job, ranking is ``rac find``'s.
        """
        key = ref.casefold()
        matches = [a for a in self.artifacts if key in (alias.casefold() for alias in a.aliases)]
        if len(matches) == 1:
            return matches[0]
        return None

    def artifacts_of_type(self, type: str) -> list[Artifact]:
        """Artifacts of ``type`` (including ``"unknown"``), walk order."""
        return [a for a in self.artifacts if a.type == type]

    def diagnostics_for(self, path: str) -> list[Diagnostic]:
        """Diagnostics concerning the artifact at ``path``."""
        return [d for d in self.diagnostics if d.path == path]

    def relationships_for(self, path: str) -> list[Relationship]:
        """Relationships declared by, or resolving to, the artifact at ``path``."""
        return [r for r in self.relationships if path in (r.source_path, r.resolved_path)]


def _relationship_diagnostic(issue: RelationshipIssue, identifiers: dict[str, str]) -> Diagnostic:
    """Translate one relationship-validation finding into a Diagnostic."""
    if issue.code == ISSUE_DUPLICATE_IDENTIFIER:
        paths = issue.paths or []
        return Diagnostic(
            source=SOURCE_RELATIONSHIPS,
            severity="warning",
            code=issue.code,
            message=f"Duplicate identifier shared by: {', '.join(paths)}",
            path=paths[0] if paths else "",
            identifier=issue.identifier,
        )
    label = (issue.relationship or "").replace("_", " ").title()
    phrase = _REL_PHRASE.get(issue.code, "unresolved reference")
    path = issue.source_path or ""
    return Diagnostic(
        source=SOURCE_RELATIONSHIPS,
        severity="warning",
        code=issue.code,
        message=f"{label} reference '{issue.target}': {phrase}",
        path=path,
        identifier=identifiers.get(path),
    )


def load_repository(
    directory: str,
    *,
    recursive: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel: CancelToken | None = None,
) -> Repository:
    """Walk ``directory`` once and compose the navigable repository model.

    Progress is per-file during the ``scan`` phase, then per-phase for the
    derived analyses (``index``, ``validate``, ``relationships``,
    ``portfolio``); cancellation is checked between files and phases.
    """

    def phase_done(phase: str) -> None:
        checkpoint(cancel)
        if on_progress is not None:
            on_progress(Progress(phase=phase, completed=1, total=1))

    entries = collect_corpus(directory, recursive=recursive, on_progress=on_progress, cancel=cancel)
    return repository_from_corpus(directory, entries, recursive=recursive, on_phase=phase_done)


def repository_from_corpus(
    directory: str,
    entries: list[CorpusEntry],
    *,
    recursive: bool = True,
    on_phase: Callable[[str], None] | None = None,
) -> Repository:
    """Compose the repository model from an already-walked corpus snapshot (v0.12.0).

    The corpus-once seam for consumers that hold their own snapshot — the
    watchkeeper comparison loads two states and must not pay (or interleave)
    a second walk per side. Same result as :func:`load_repository`.
    """

    def phase_done(phase: str) -> None:
        if on_phase is not None:
            on_phase(phase)

    index = index_from_corpus(directory, entries, recursive=recursive)
    identifiers = {entry.path: entry.id for entry in index.artifacts}
    phase_done("index")

    validation = validate_corpus(directory, entries, recursive=recursive)
    status_by_path = {f.path: f.status for f in validation.files}
    phase_done("validate")

    relationships = relationships_from_corpus(entries)
    rel_validation = validation_from_corpus(directory, entries, recursive=recursive)
    phase_done("relationships")

    portfolio = portfolio_from_corpus(directory, entries, recursive=recursive)
    phase_done("portfolio")

    missing_by_path: dict[str, tuple[str, ...]] = {}
    for corpus_entry in entries:
        spec = spec_for(corpus_entry.artifact_type)
        if spec is None:
            continue
        _, missing_recommended = missing_sections(corpus_entry.product, spec)
        missing_by_path[str(corpus_entry.path)] = tuple(missing_recommended)

    artifacts = [
        Artifact(
            id=entry.id,
            type=entry.type,
            title=entry.title,
            path=entry.path,
            aliases=tuple(entry.aliases),
            status=status_by_path[entry.path],
            missing_recommended=missing_by_path.get(entry.path, ()),
            search_sections=tuple(entry.search_sections),
            inbound_count=entry.inbound_count,
        )
        for entry in index.artifacts
    ]

    diagnostics: list[Diagnostic] = [
        Diagnostic(
            source=SOURCE_VALIDATION,
            severity=issue.severity,
            code=issue.code,
            message=issue.message,
            path=file.path,
            identifier=identifiers.get(file.path),
        )
        for file in validation.files
        for issue in file.issues
    ]
    diagnostics.extend(
        _relationship_diagnostic(issue, identifiers) for issue in rel_validation.issues
    )

    return Repository(
        directory=directory,
        recursive=recursive,
        artifacts=artifacts,
        relationships=relationships,
        diagnostics=diagnostics,
        portfolio=portfolio,
    )
