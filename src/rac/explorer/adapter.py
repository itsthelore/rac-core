"""Explorer adapter — the boundary between RAC services and the TUI (v0.8.0).

The adapter invokes RAC services, translates Core models into UI state, and
owns no repository intelligence (ADR-015). It is the single place the
Explorer touches ``rac.services`` / ``rac.core``; widgets depend on
:mod:`rac.explorer.state` only. This module never imports Textual, so it is
testable without a terminal.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path, PurePath

from rac.core.frontmatter import split_frontmatter
from rac.core.fs import find_markdown_files
from rac.core.operations import CancelToken, OperationCancelled, Progress
from rac.core.schema import SchemaReference, available_schemas, schema_reference
from rac.services.improve import improve_file
from rac.services.ingest import ConversionError, UnsupportedDocument, ingest
from rac.services.repository import Artifact, Repository, load_repository
from rac.services.resolve import (
    OUTCOME_DUPLICATE,
    OUTCOME_RESOLVED,
    resolve_in_index,
    search_index,
)
from rac.services.review import (
    ATTENTION_BROKEN_RELATIONSHIP,
    ATTENTION_INVALID,
    ATTENTION_MISSING_RECOMMENDED,
    REVIEW_UNKNOWN_ARTIFACT,
    ReviewIssue,
    review_from_portfolio,
)

from . import editor as editor_mod
from .editor import EditorOutcome
from .preferences import (
    GROUPING_FLAT,
    GROUPING_FOLDERS,
    Preferences,
    load_preferences,
    save_preferences,
)
from .state import (
    ArtifactRow,
    AttentionRow,
    BrowserState,
    ContextState,
    DirectoryNode,
    HealthAreaState,
    HealthState,
    ImportPreview,
    LoadErrorState,
    LoadProgressState,
    LookupState,
    RecommendationRow,
    RecommendationsState,
    RelationshipLink,
    RelationshipsView,
    RepositorySummaryState,
    health_label,
)
from .workspace import Workspace, load_workspace, save_workspace

# Presentation labels for the analysis phases that follow the scan.
_PHASE_LABELS = {
    "index": "Indexing artifacts",
    "validate": "Validating artifacts",
    "relationships": "Analyzing relationships",
    "portfolio": "Calculating portfolio",
}

# Validation status → text-bearing label (never colour or symbol alone).
# One chip casing everywhere (DESIGN-visual-system, v0.8.8).
_STATUS_LABELS = {
    "valid": "✓ Valid",
    "invalid": "✗ Invalid",
    "skipped": "– Unknown",
}

ProgressHandler = Callable[[LoadProgressState], None]


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def _area_label(has_findings: bool, *, error: bool = False) -> str:
    """A health area's status from a Core fact (no Explorer thresholds)."""
    if not has_findings:
        return "✓ Healthy"
    return "✗ Error" if error else "! Needs Attention"


# The four recommendation categories (DESIGN-recommendations), fixed order.
_CATEGORY_ORDER = ("Validation", "Relationships", "Repository Health", "Quality")

# Core review finding code → presentation category.
_CODE_CATEGORY = {
    ATTENTION_INVALID: "Validation",
    REVIEW_UNKNOWN_ARTIFACT: "Validation",
    ATTENTION_BROKEN_RELATIONSHIP: "Relationships",
    ATTENTION_MISSING_RECOMMENDED: "Quality",
}

# Core severity → the three presentation tiers (definitions stay in Core).
_SEVERITY_LABEL = {
    "error": "✗ Critical",
    "warning": "! Warning",
    "info": "· Suggestion",
}

# "Why it matters" — fixed presentation copy keyed by the Core finding code
# (display text, like the status and phase labels; not analysis).
_IMPACT = {
    ATTENTION_INVALID: "The artifact fails its schema, so tooling and validation cannot trust it.",
    ATTENTION_BROKEN_RELATIONSHIP: (
        "A declared reference does not resolve, leaving traceability incomplete."
    ),
    ATTENTION_MISSING_RECOMMENDED: (
        "Recommended sections are empty, weakening the artifact's completeness."
    ),
    REVIEW_UNKNOWN_ARTIFACT: "No schema matched, so required structure cannot be checked.",
}


def _recommendation(issue: ReviewIssue) -> RecommendationRow:
    return RecommendationRow(
        path=issue.path,
        identifier=issue.identifier,
        category=_CODE_CATEGORY.get(issue.code, "Quality"),
        severity_label=_SEVERITY_LABEL.get(issue.severity, issue.severity),
        finding=issue.message,
        impact=_IMPACT.get(issue.code, "This finding affects repository quality."),
        action=issue.action,
    )


def _row(artifact: Artifact) -> ArtifactRow:
    return ArtifactRow(
        path=artifact.path,
        id=artifact.id,
        type=artifact.type,
        title=artifact.title,
        status_label=_status_label(artifact.status),
    )


def _directory_tree(rows: tuple[ArtifactRow, ...], directory: str) -> DirectoryNode:
    """The repository directory tree from artifact paths (folders grouping).

    Paths are taken relative to the repository root and pinned to posix so
    the sidebar's expansion keys stay stable across platforms. Empty
    directories cannot occur — the tree is derived from the artifacts. A
    path outside the root (cannot happen from the scanner; normalized
    defensively) lands at the top level.
    """
    root: dict = {"dirs": {}, "rows": []}
    for row in rows:
        rel = PurePath(os.path.relpath(row.path, directory)).as_posix()
        parts = [part for part in rel.split("/") if part]
        if parts and parts[0] == "..":
            parts = parts[-1:]
        node = root
        for part in parts[:-1]:
            node = node["dirs"].setdefault(part, {"dirs": {}, "rows": []})
        node["rows"].append(row)

    def freeze(name: str, path: str, node: dict) -> DirectoryNode:
        dirs = tuple(
            freeze(child, f"{path}/{child}" if path else child, node["dirs"][child])
            for child in sorted(node["dirs"])
        )
        return DirectoryNode(name=name, path=path, dirs=dirs, rows=tuple(node["rows"]))

    return freeze("", "", root)


def _progress_state(progress: Progress) -> LoadProgressState:
    if progress.phase == "scan":
        counter = f" ({progress.completed}/{progress.total})" if progress.total else ""
        label = f"Scanning artifacts{counter}"
    else:
        label = _PHASE_LABELS.get(progress.phase, progress.phase.title())
    return LoadProgressState(
        phase=progress.phase,
        completed=progress.completed,
        total=progress.total,
        label=label,
    )


class ExplorerAdapter:
    """Loads a repository through Core services and yields UI state.

    Failures surface as :class:`LoadErrorState` (Initiative 6 — recoverable,
    never a crash); a cancelled load returns ``None`` so workers can discard
    it without handling Core exception types. The last successful
    :class:`Repository` is kept for navigation milestones (v0.8.1+).
    """

    def __init__(self, directory: str, recursive: bool = True) -> None:
        self.directory = directory
        self.recursive = recursive
        self.repository: Repository | None = None
        # Local config and continuity (v0.8.6) — read-only at construction;
        # writes happen on explicit launch/navigation events.
        self.preferences: Preferences = load_preferences()
        self.workspace: Workspace = load_workspace()

    # --- workspace continuity (v0.8.6) -------------------------------------

    def record_open(self) -> None:
        """Remember this repository as recently opened (Initiative 1)."""
        self.workspace.record_open(self.directory)
        save_workspace(self.workspace)

    def record_artifact(self, path: str) -> None:
        """Remember the last artifact opened in this repository."""
        self.workspace.record_artifact(self.directory, path)
        save_workspace(self.workspace)

    def record_view(self, view: str) -> None:
        """Remember the active view so resume can restore it (v0.8.8)."""
        self.workspace.record_view(self.directory, view)
        save_workspace(self.workspace)

    def resume_view(self) -> str | None:
        """The last recorded view for this repository, if any."""
        return self.workspace.resume_view(self.directory)

    def recent_rows(self, limit: int = 5) -> tuple[ArtifactRow, ...]:
        """Recently opened artifacts here that still exist, newest first (v0.8.9)."""
        repository = self.repository
        if repository is None:
            return ()
        by_path = {a.path: a for a in repository.artifacts}
        rows = tuple(
            _row(by_path[path])
            for path in self.workspace.recent_artifacts_for(self.directory)
            if path in by_path
        )
        return rows[:limit]

    def resume_path(self) -> str | None:
        """The last artifact opened here, if it still exists in the load."""
        path = self.workspace.resume_artifact(self.directory)
        if path is None or self.repository is None:
            return None
        return path if any(a.path == path for a in self.repository.artifacts) else None

    def load(
        self,
        *,
        on_progress: ProgressHandler | None = None,
        cancel: CancelToken | None = None,
    ) -> RepositorySummaryState | LoadErrorState | None:
        def relay(progress: Progress) -> None:
            if on_progress is not None:
                on_progress(_progress_state(progress))

        try:
            repository = load_repository(
                self.directory,
                recursive=self.recursive,
                on_progress=relay,
                cancel=cancel,
            )
        except OperationCancelled:
            return None  # discarded by the caller; not an error
        except Exception as exc:  # noqa: BLE001 — the recoverable boundary (Initiative 6)
            return LoadErrorState(
                title="Could not load repository",
                detail=f"{type(exc).__name__}: {exc}",
                can_retry=True,
            )

        self.repository = repository
        return self._summary(repository)

    def fingerprint(self) -> tuple[tuple[str, int], ...] | None:
        """A snapshot of the corpus files for change detection (v0.8.9).

        Paths and mtimes from the same discovery the loader uses
        (``find_markdown_files``) — no parsing, so a scan stays cheap enough
        to repeat on a timer. ``None`` means the directory could not be
        listed; callers treat that as no signal, never as a change.
        """
        try:
            paths = find_markdown_files(self.directory, recursive=self.recursive)
        except OSError:
            return None
        entries: list[tuple[str, int]] = []
        for path in paths:
            try:
                entries.append((str(path), path.stat().st_mtime_ns))
            except OSError:
                continue  # deleted between listing and stat; the next scan settles it
        return tuple(entries)

    @staticmethod
    def _summary(repository: Repository) -> RepositorySummaryState:
        portfolio = repository.portfolio
        severities = [d.severity for d in repository.diagnostics]
        incomplete = sum(1 for a in repository.artifacts if a.missing_recommended)
        attention = tuple(
            line
            for count, noun in (
                (portfolio.invalid_artifacts, "invalid artifact"),
                (portfolio.relationships.broken, "broken relationship"),
                (incomplete, "incomplete artifact"),
            )
            if count
            for line in (_plural(count, noun),)
        )
        return RepositorySummaryState(
            directory=repository.directory,
            artifact_total=portfolio.total_artifacts,
            by_type=tuple((name, count) for name, count in portfolio.by_type.items() if count),
            relationship_total=portfolio.relationships.total,
            broken_relationships=portfolio.relationships.broken,
            error_count=severities.count("error"),
            warning_count=severities.count("warning"),
            health_score=repository.health_score,
            attention=attention,
        )

    # --- navigation state (v0.8.1) — requires a loaded repository -----------

    def browser_state(self, artifact_type: str | None = None) -> BrowserState | None:
        """Artifacts grouped by type for the browser, or None before a load.

        ``artifact_type`` narrows the browser to one group.
        """
        if self.repository is None:
            return None
        repository = self.repository
        if artifact_type is None and self.preferences.artifact_grouping == GROUPING_FOLDERS:
            # Folders grouping (the default, v0.8.10): the tree mirrors the
            # repository's directory structure; groups stay populated so
            # status lookups need no second path.
            rows = tuple(_row(a) for a in repository.artifacts)
            return BrowserState(
                directory=repository.directory,
                groups=(("all", rows),),
                total=len(rows),
                tree=_directory_tree(rows, repository.directory),
            )
        if artifact_type is None and self.preferences.artifact_grouping == GROUPING_FLAT:
            # Flat grouping (preference): one list, no type headers.
            rows = tuple(_row(a) for a in repository.artifacts)
            return BrowserState(
                directory=repository.directory,
                groups=(("all", rows),),
                total=len(rows),
            )
        groups = tuple(
            (group_type, tuple(_row(a) for a in repository.artifacts_of_type(group_type)))
            for group_type, count in repository.portfolio.by_type.items()
            if count and (artifact_type is None or group_type == artifact_type)
        )
        return BrowserState(
            directory=repository.directory,
            groups=groups,
            total=sum(len(rows) for _, rows in groups),
        )

    def open_ref(self, ref: str) -> LookupState:
        """Exact lookup for `/open`, with `rac resolve` semantics (ADR-026).

        One row resolves unambiguously; duplicates list every file so the
        user chooses; not-found explains and suggests search.
        """
        repository = self.repository
        if repository is None:
            return LookupState(rows=(), message="Repository not loaded yet")
        result = resolve_in_index(repository.artifacts, ref)
        if result.outcome == OUTCOME_RESOLVED and result.artifact is not None:
            artifact = next(a for a in repository.artifacts if a.path == result.artifact.path)
            return LookupState(rows=(_row(artifact),))
        if result.outcome == OUTCOME_DUPLICATE:
            rows = tuple(_row(a) for a in repository.artifacts if a.path in result.duplicate_paths)
            return LookupState(rows=rows, message=f"Duplicate identifier: {ref} — choose a file")
        return LookupState(rows=(), message=f"Not found: {ref} — try a search")

    def search_rows(self, args: str) -> LookupState:
        """Search for `/find` and bare input, with `rac find` semantics.

        A trailing word naming an artifact type filters to it
        (``find payments decision``).
        """
        repository = self.repository
        if repository is None:
            return LookupState(rows=(), message="Repository not loaded yet")
        query, artifact_type = args.strip(), None
        tokens = query.split()
        if len(tokens) > 1 and tokens[-1].casefold() in repository.portfolio.by_type:
            artifact_type = tokens[-1].casefold()
            query = " ".join(tokens[:-1])
        result = search_index(repository.artifacts, query, artifact_type=artifact_type)
        by_path = {a.path: a for a in repository.artifacts}
        rows = tuple(_row(by_path[m.path]) for m in result.matches)
        if not rows:
            return LookupState(rows=(), message=f"No matches for '{args.strip()}'")
        return LookupState(rows=rows)

    def type_rows(self, artifact_type: str) -> LookupState:
        """Every artifact of one type, for `/browse <type>` (v0.8.10).

        Rendered in the results view in every grouping mode — browsing by
        type no longer depends on the sidebar having type groups.
        """
        repository = self.repository
        if repository is None:
            return LookupState(rows=(), message="Repository not loaded yet")
        rows = tuple(_row(a) for a in repository.artifacts_of_type(artifact_type))
        if not rows:
            return LookupState(rows=(), message=f"Nothing to browse: {artifact_type}")
        return LookupState(rows=rows)

    def health_state(self) -> HealthState | None:
        """The repository health screen, or None before a load (v0.8.2).

        Every value is read from the loaded portfolio summary; Explorer adds
        no scoring (ADR-015). Area status derives from Core facts, not from
        Explorer-invented thresholds.
        """
        repository = self.repository
        if repository is None:
            return None
        portfolio = repository.portfolio
        rel = portfolio.relationships

        completeness_pct = round(portfolio.completeness * 100)
        coverage_pct = round(rel.coverage * 100)
        areas = (
            HealthAreaState(
                name="Completeness",
                status_label=_area_label(portfolio.filled_slots < portfolio.recommended_slots),
                detail=(
                    f"{completeness_pct}% "
                    f"({portfolio.filled_slots}/{portfolio.recommended_slots} recommended sections)"
                ),
            ),
            HealthAreaState(
                name="Relationships",
                status_label=_area_label(rel.broken > 0),
                detail=f"{rel.valid} resolved, {rel.broken} broken of {rel.total}",
            ),
            HealthAreaState(
                name="Validation",
                status_label=_area_label(portfolio.invalid_artifacts > 0, error=True),
                detail=f"{portfolio.valid_artifacts} valid, {portfolio.invalid_artifacts} invalid",
            ),
            HealthAreaState(
                name="Coverage",
                status_label=_area_label(rel.orphaned > 0),
                detail=f"{coverage_pct}% of artifacts linked, {rel.orphaned} orphaned",
            ),
        )
        attention = tuple(
            AttentionRow(
                path=item.path,
                identifier=item.identifier,
                severity_label="✗ Error" if item.severity == "error" else "! Warning",
                message=item.message,
            )
            for item in portfolio.attention
        )
        return HealthState(
            directory=repository.directory,
            score=portfolio.health_score,
            score_label=health_label(portfolio.health_score),
            areas=areas,
            attention=attention,
        )

    def recommendations_state(self) -> RecommendationsState | None:
        """Recommendations grouped by category, or None before a load (v0.8.3).

        Built from Core's review findings over the loaded portfolio — Explorer
        adds explanation and grouping, never new findings (ADR-015).
        """
        repository = self.repository
        if repository is None:
            return None
        report = review_from_portfolio(
            repository.directory, repository.portfolio, recursive=repository.recursive
        )
        rows = [_recommendation(issue) for issue in report.issues]
        groups = tuple(
            (category, tuple(r for r in rows if r.category == category))
            for category in _CATEGORY_ORDER
            if any(r.category == category for r in rows)
        )
        return RecommendationsState(
            directory=repository.directory,
            groups=groups,
            total=len(rows),
        )

    def schema_overview(self) -> tuple[tuple[str, str], ...]:
        """(type, one-line structure summary) for every registered schema (v0.8.9).

        Reference data straight from the core schema registry — the same
        facts `rac schema` reports (ADR-015). Needs no loaded repository.
        """
        rows: list[tuple[str, str]] = []
        for name in available_schemas():
            ref = schema_reference(name)
            if ref is None:  # pragma: no cover - registry names always resolve
                continue
            rows.append(
                (
                    name,
                    f"{_plural(len(ref.required), 'required section')}, "
                    f"{len(ref.recommended)} recommended",
                )
            )
        return tuple(rows)

    def schema_detail(self, name: str) -> str | None:
        """The expected structure of artifact type ``name``, or None if unknown."""
        ref = schema_reference(name.strip().casefold())
        if ref is None:
            return None
        lines = [f"{ref.display} ({ref.type})", "", "Required sections"]
        lines.extend(self._schema_section(ref, s) for s in ref.required)
        if ref.recommended:
            lines.extend(["", "Recommended sections"])
            lines.extend(self._schema_section(ref, s) for s in ref.recommended)
        if ref.optional:
            lines.extend(["", "Optional sections"])
            lines.extend(self._schema_section(ref, s) for s in ref.optional)
        return "\n".join(lines)

    @staticmethod
    def _schema_section(ref: SchemaReference, section: str) -> str:
        description = ref.descriptions.get(section)
        values = ref.metadata.get(section)
        line = f"  {section.title()}"
        if description:
            line += f" — {description}"
        if values:
            line += f" ({' | '.join(values)})"
        return line

    def improvement_rows(self, path: str) -> tuple[RecommendationRow, ...]:
        """Improvement suggestions for the artifact at ``path`` (v0.8.9).

        Core's improve analysis (`rac improve`) rendered as findings rows
        under the Improvement group — Explorer shows suggestions, it never
        applies them (ADR-024). Empty for paths outside the load, types the
        improve service does not support, and analysis trouble.
        """
        repository = self.repository
        if repository is None:
            return ()
        artifact = next((a for a in repository.artifacts if a.path == path), None)
        if artifact is None:
            return ()
        try:
            result = improve_file(path)
        except (OSError, ValueError):
            return ()  # unreadable mid-edit — the findings simply stay review-only
        if not result.supported:
            return ()
        rows: list[RecommendationRow] = []
        groups = ((True, result.missing_required), (False, result.missing_recommended))
        for required, sections in groups:
            for section in sections:
                guidance = result.guidance.get(section, [])
                rows.append(
                    RecommendationRow(
                        path=path,
                        identifier=artifact.id,
                        category="Improvement",
                        severity_label="! Warning" if required else "· Suggestion",
                        finding=f"Missing {'required' if required else 'recommended'} "
                        f"section: {section.title()}",
                        impact=(
                            "The schema requires this section; validation fails without it."
                            if required
                            else "Filling recommended sections strengthens completeness."
                        ),
                        action=guidance[0] if guidance else f"Add a {section.title()} section.",
                    )
                )
        return tuple(rows)

    def open_in_editor(self, path: str, *, blocking: bool = False) -> EditorOutcome:
        """Open ``path`` in the user's configured editor (v0.8.4, ADR-024).

        The `editor` preference (v0.8.8) beats `$VISUAL`/`$EDITOR`;
        ``blocking`` runs terminal editors in the foreground (the caller
        suspends the application around it).
        """
        return editor_mod.open_in_editor(path, self.preferences.editor, blocking=blocking)

    def resolved_editor(self) -> str | None:
        """The editor command the next open would use, if any."""
        return editor_mod.resolve_editor(self.preferences.editor)

    def save_preferences(self, preferences: Preferences) -> None:
        """Persist updated preferences and adopt them for this session.

        Explorer writes its own configuration only — never artifacts
        (ADR-024); failures stay silent like every preference write.
        """
        save_preferences(preferences)
        self.preferences = preferences

    def import_preview(self, source: str, target: str | None = None) -> ImportPreview | str:
        """Convert ``source`` via Core ingest for review (v0.8.4).

        Returns an :class:`ImportPreview` to confirm, or an error message
        string — conversion never raises into the UI (Initiative 5/6). The
        default target is the source stem as ``.md`` in the current directory;
        nothing is written here (Initiative 4).
        """
        try:
            result = ingest(source)
        except UnsupportedDocument as exc:
            return str(exc)
        except ConversionError as exc:
            return f"Could not convert {source}: {exc}"
        except OSError as exc:
            return f"Could not read {source}: {exc}"
        resolved_target = target or f"{Path(source).stem}.md"
        return ImportPreview(
            source=source,
            converter=result.converter,
            target=resolved_target,
            markdown=result.markdown,
        )

    def export_recommendations(self, target: str = "recommendations.md") -> ImportPreview | str:
        """Render current recommendations as Markdown for export (v0.8.4).

        Returns an :class:`ImportPreview` to confirm and write, or a message
        when there is nothing to export. Writing goes through
        :meth:`write_import`, so it previews and never overwrites.
        """
        recommendations = self.recommendations_state()
        if recommendations is None or recommendations.total == 0:
            return "No recommendations to export"
        lines = [f"# Recommendations — {recommendations.directory}", ""]
        for category, rows in recommendations.groups:
            lines.append(f"## {category}")
            lines.append("")
            for row in rows:
                lines.append(f"- **{row.severity_label}** {row.identifier} — {row.finding}")
                lines.append(f"  - Impact: {row.impact}")
                lines.append(f"  - Action: {row.action}")
            lines.append("")
        return ImportPreview(
            source="recommendations",
            converter="export",
            target=target,
            markdown="\n".join(lines),
        )

    def write_import(self, preview: ImportPreview) -> str:
        """Write a confirmed import; never overwrites (Initiative 4)."""
        path = Path(preview.target)
        if path.exists():
            return f"Refusing to overwrite existing file: {preview.target}"
        try:
            if path.parent != Path():
                path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(preview.markdown, encoding="utf-8")
        except OSError as exc:
            return f"Could not write {preview.target}: {exc}"
        return f"Imported {preview.source} → {preview.target}"

    def relationships_view(self, path: str) -> RelationshipsView | None:
        """The knowledge-graph view for the artifact at ``path`` (v0.8.5).

        Renders the loaded model's relationships — outgoing edges, impact
        (artifacts that depend on this one), and lineage (Supersedes /
        Superseded By). Explorer traverses; it infers nothing (ADR-016).
        """
        repository = self.repository
        if repository is None:
            return None
        artifact = next((a for a in repository.artifacts if a.path == path), None)
        if artifact is None:
            return None
        titles = {a.path: (a.title or a.id) for a in repository.artifacts}

        def label(kind: str) -> str:
            return kind.replace("_", " ").title()

        outgoing: list[RelationshipLink] = []
        lineage: list[str] = []
        for rel in repository.relationships:
            if rel.source_path != path:
                continue
            if rel.resolved_path is not None:
                outgoing.append(
                    RelationshipLink(
                        kind=label(rel.relationship),
                        label=titles[rel.resolved_path],
                        target_path=rel.resolved_path,
                        navigable=True,
                    )
                )
                if rel.relationship == "supersedes":
                    lineage.append(f"Supersedes → {titles[rel.resolved_path]}")
            else:
                phrase = (rel.issue or "unresolved").replace("-", " ").replace("_", " ")
                outgoing.append(
                    RelationshipLink(
                        kind=label(rel.relationship),
                        label=f"{rel.target} (✗ {phrase})",
                        target_path="",
                        navigable=False,
                    )
                )

        impact: list[RelationshipLink] = []
        for rel in repository.relationships:
            if rel.resolved_path != path:
                continue
            impact.append(
                RelationshipLink(
                    kind=label(rel.relationship),
                    label=titles.get(rel.source_path, rel.source_path),
                    target_path=rel.source_path,
                    navigable=True,
                )
            )
            if rel.relationship == "supersedes":
                lineage.append(f"Superseded By ← {titles.get(rel.source_path, rel.source_path)}")

        return RelationshipsView(
            id=artifact.id,
            title=artifact.title,
            path=artifact.path,
            outgoing=tuple(outgoing),
            impact=tuple(impact),
            lineage=tuple(lineage),
        )

    def artifact_markdown(self, path: str) -> str | None:
        """The artifact's Markdown body for the Content tab (v0.8.7).

        Read-only presentation of the document itself (ADR-024); only paths
        in the loaded repository resolve. The leading YAML frontmatter is
        stripped (Core's split, ADR-025): identity metadata already lives in
        the panel title, the sidebar type tag, and the Inspection tab. A read
        failure returns a message rather than raising into the UI
        (Initiative 6).
        """
        repository = self.repository
        if repository is None:
            return None
        if not any(a.path == path for a in repository.artifacts):
            return None
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            return f"Could not read {path}: {exc}"
        return split_frontmatter(text).body.lstrip("\n")

    def resolve_link(self, href: str, source_path: str) -> str | None:
        """Resolve a Markdown link inside an artifact to another artifact (v0.8.8).

        Tries reference resolution (IDs and aliases, `rac resolve` semantics),
        then a path relative to the linking document, then the linked file's
        stem as a reference. External URLs and unresolvable links return
        None — the Explorer reports rather than guesses.
        """
        repository = self.repository
        if repository is None:
            return None
        target = href.partition("#")[0].strip()
        if not target or "://" in target:
            return None
        lookup = self.open_ref(target)
        if len(lookup.rows) == 1 and lookup.message is None:
            return lookup.rows[0].path
        candidate = (Path(source_path).parent / target).as_posix()
        normalized = str(Path(candidate))
        for artifact in repository.artifacts:
            if str(Path(artifact.path)) == normalized:
                return artifact.path
        stem = Path(target).stem
        if stem and stem != target:
            lookup = self.open_ref(stem)
            if len(lookup.rows) == 1 and lookup.message is None:
                return lookup.rows[0].path
        return None

    def context_state(self, path: str) -> ContextState | None:
        """The context view for the artifact at ``path``, or None if unknown."""
        repository = self.repository
        if repository is None:
            return None
        artifact = next((a for a in repository.artifacts if a.path == path), None)
        if artifact is None:
            return None

        titles = {a.path: a.title or a.id for a in repository.artifacts}
        outgoing: list[str] = []
        incoming: list[str] = []
        for rel in repository.relationships_for(path):
            label = rel.relationship.replace("_", " ").title()
            if rel.source_path == path:
                if rel.resolved_path is not None:
                    outgoing.append(f"{label} → {rel.target} ({titles[rel.resolved_path]})")
                else:
                    phrase = (rel.issue or "unresolved").replace("-", " ")
                    outgoing.append(f"{label} → {rel.target} (✗ {phrase})")
            else:
                incoming.append(f"← {titles.get(rel.source_path, rel.source_path)} ({label})")

        diagnostics = tuple(
            f"{'✗' if d.severity == 'error' else '!'} {d.severity}: {d.message}"
            for d in repository.diagnostics_for(path)
        )
        return ContextState(
            id=artifact.id,
            type=artifact.type,
            title=artifact.title,
            path=artifact.path,
            aliases=artifact.aliases,
            status_label=_status_label(artifact.status),
            missing_recommended=artifact.missing_recommended,
            outgoing=tuple(outgoing),
            incoming=tuple(incoming),
            diagnostics=diagnostics,
        )
