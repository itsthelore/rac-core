"""Relationship metadata service — extract cross-artifact references (v0.7.0).

Relationships are explicit Markdown sections (``## Related Decisions``,
``## Supersedes``, ...) that reference other artifacts (ADR-016). This module is
the single home for turning those sections into reference strings, shared by
``rac inspect`` (which exposes them as the additive ``relationships`` field) and
``rac stats`` (which counts their presence).

It is pure and deterministic (ADR-002 / ADR-016): it parses section text only and
never resolves, validates, or graphs the references — v0.7.0 is metadata only.

Recognition is spec-driven (REQ-002): only the relationship sections an artifact
type declares in :attr:`ArtifactSpec.optional` are considered, so a section is
recognized exactly where its schema allows it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.artifacts import ArtifactSpec, spec_for
from rac.core.classification import classify
from rac.core.corpus import CorpusCache, CorpusEntry, walk_corpus
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.limits import (
    MAX_RELATED_EDGES,
    MAX_TRAVERSAL_DEPTH,
    MAX_TRAVERSAL_FRONTIER,
    MAX_TRAVERSAL_WORK,
)
from rac.core.markdown import parse_file
from rac.core.models import Product
from rac.core.relationship_types import REGISTRY, edge_spec

# The relationship-section vocabulary and pure reference extraction now live in
# :mod:`rac.services.references`. They are re-exported here so the module remains
# the single import surface every relationship consumer has always used
# (``rac.services.relationships.RELATIONSHIP_SECTIONS`` and friends resolve
# unchanged, ADR-062).
from rac.services.references import EXTERNAL_SECTIONS as EXTERNAL_SECTIONS
from rac.services.references import RELATED_SECTIONS as RELATED_SECTIONS
from rac.services.references import (
    RELATIONSHIP_SECTIONS,
    _snake,
    extract_relationships_full,
    unsupported_relationship_sections,
)
from rac.services.references import SCOPE_SECTIONS as SCOPE_SECTIONS
from rac.services.references import extract_relationships as extract_relationships
from rac.services.references import parse_references as parse_references
from rac.services.references import (
    present_relationship_sections as present_relationship_sections,
)

# The filesystem-scope path helpers (``## Applies To`` entry classification, path
# normalisation, repository-root discovery) live in
# :mod:`rac.services.scope_paths`, a home shared with ``rac.services.scope`` so
# neither reaches across a module boundary for the other's internals.
from rac.services.scope_paths import (
    classify_scope_entry,
    normalized_scope_path,
    repository_root,
)

# --- Repository-level relationship inspection (v0.7.1) -----------------------
#
# `rac relationships <path>` discovers the explicit relationships declared across
# a tree of artifacts (ADR-015: repository intelligence in Core, exposed via CLI +
# JSON for future consumers). It is read-only and deterministic: it reports the
# references that exist, but never resolves, validates, or graphs them.


@dataclass
class ArtifactRelationships:
    """One artifact's relationships in a repository report.

    ``relationships`` includes Supersedes (unlike ``rac inspect``) and is keyed by
    snake_case section name in the artifact's own ``spec.optional`` order.
    """

    path: str
    type: str
    relationships: dict[str, list[str]]


@dataclass
class RelationshipReport:
    """Repository-level relationship inspection result (ADR-003).

    ``total_files`` counts every Markdown file considered — including files with
    no relationships and Unknown artifacts. ``artifacts`` lists only those with at
    least one relationship. Counts are *reference* counts (each declared target is
    one relationship), aggregated by type in the canonical
    :data:`RELATIONSHIP_SECTIONS` order.
    """

    directory: str
    recursive: bool
    total_files: int
    artifacts: list[ArtifactRelationships] = field(default_factory=list)
    # Human-friendly resolution (v0.7.12): {casefold(ref) -> "Title (type · ID)"}
    # for every reference that resolves uniquely. Presentation context only —
    # the stored reference remains the source of truth, and JSON output does
    # not include labels (ADR-007: resolved fields would be an additive,
    # explicitly versioned change).
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def artifacts_with_relationships(self) -> int:
        return len(self.artifacts)

    @property
    def counts(self) -> dict[str, int]:
        """References per relationship type, canonical order, zero types omitted."""
        totals: dict[str, int] = {}
        for artifact in self.artifacts:
            for section, refs in artifact.relationships.items():
                totals[section] = totals.get(section, 0) + len(refs)
        return {
            _snake(section): totals[_snake(section)]
            for section in RELATIONSHIP_SECTIONS
            if _snake(section) in totals
        }

    @property
    def relationship_count(self) -> int:
        """Total references found across all artifacts (sum of ``counts``)."""
        return sum(self.counts.values())


def _resolution_labels(
    artifacts: list[ArtifactRelationships],
    items: list[tuple[str, Product, ArtifactSpec | None]],
) -> dict[str, str]:
    """Human-friendly labels for every uniquely-resolved reference (v0.7.12).

    Resolution runs over the same alias index relationship validation uses
    (one identity model); ambiguous and unknown references get no label —
    `--validate` is the place that reports them.
    """
    index = build_resolution_index(items)
    info = {
        path: (artifact_identifier(product, spec, path), spec, product.title)
        for path, product, spec in items
    }
    labels: dict[str, str] = {}
    for artifact in artifacts:
        for refs in artifact.relationships.values():
            for ref in refs:
                key = ref.casefold()
                if key in labels:
                    continue
                entries = index.get(key, [])
                paths = {p for p, _ in entries}
                if len(paths) != 1:
                    continue
                canonical, spec, title = info[next(iter(paths))]
                type_name = spec.name if spec else "unknown"
                labels[key] = f"{title or canonical} ({type_name} · {canonical})"
    return labels


def _build_report(
    directory: str,
    items: list[tuple[str, Product, ArtifactSpec | None]],
    recursive: bool,
) -> RelationshipReport:
    """Assemble a :class:`RelationshipReport` from ``items`` (already ordered)."""
    artifacts: list[ArtifactRelationships] = []
    for path, product, spec in items:
        relationships = extract_relationships_full(product, spec) if spec else {}
        if relationships:
            artifacts.append(
                ArtifactRelationships(
                    path=path,
                    type=spec.name if spec else "unknown",
                    relationships=relationships,
                )
            )
    return RelationshipReport(
        directory=directory,
        recursive=recursive,
        total_files=len(items),
        artifacts=artifacts,
        labels=_resolution_labels(artifacts, items),
    )


def build_relationship_report(directory: str, recursive: bool = True) -> RelationshipReport:
    """Inspect explicit relationships across a directory of Markdown files."""
    return _build_report(directory, _corpus_items(directory, recursive), recursive)


def report_from_corpus(
    directory: str, entries: list[CorpusEntry], recursive: bool = True
) -> RelationshipReport:
    """Inspect relationships in an already-walked corpus snapshot (v0.8.0).

    Same result as :func:`build_relationship_report`; the snapshot lets one
    walk feed several analyses (repository model, future incremental refresh).
    """
    return _build_report(directory, _entry_items(entries), recursive)


def build_relationship_report_file(path: str) -> RelationshipReport:
    """Inspect relationships in a single file (REQ-009).

    Same model as a directory report, with one file and ``recursive=False``.
    """
    return _build_report(path, _parsed_items([path]), recursive=False)


# --- Relationship validation (v0.7.2) ----------------------------------------
#
# `rac relationships <path> --validate` resolves every explicit reference against
# the identifiers of artifacts discovered in the repository, reporting missing,
# ambiguous, and self-referencing targets plus duplicate identifiers. Read-only
# and deterministic; no resolution heuristics, inference, or graphs (ADR-016).

# Stable issue codes (part of the JSON contract).
ISSUE_DUPLICATE_IDENTIFIER = "duplicate-artifact-identifier"
ISSUE_TARGET_NOT_FOUND = "relationship-target-not-found"
ISSUE_TARGET_AMBIGUOUS = "relationship-target-ambiguous"
ISSUE_SELF_REFERENCE = "relationship-self-reference"
# Edge-legality (v0.14.0, ADR-049): a relationship section the artifact's type
# does not declare produces no edge and is reported, not silently dropped.
ISSUE_EDGE_UNSUPPORTED = "relationship-edge-unsupported"
# Status-consistency (v0.14.1, ADR-049; generalised in v0.16.0/ADR-051): a live
# artifact references a target the team has retired, other than via ``supersedes``.
ISSUE_TARGET_SUPERSEDED = "relationship-target-superseded"
# Range (v0.16.0, ADR-055): a resolved target whose type is not in the edge's range
# (e.g. a ``## Related Decisions`` reference that resolves to a requirement).
ISSUE_TARGET_TYPE_MISMATCH = "relationship-target-type-mismatch"
# Acyclicity (v0.16.0, ADR-055): a cycle in a directional, acyclic edge kind
# (``supersedes``), which an ordering/replacement relationship must not contain.
ISSUE_RELATIONSHIP_CYCLE = "relationship-cycle"
# Code-scope existence (decision-to-code-proximity, Initiative 1): a filesystem-
# scoped ``## Applies To`` literal path/directory entry that does not exist in the
# repository working tree. Declared, never inferred (ADR-065/066); glob and
# component-name entries are recorded without existence-checking, so they never
# raise this.
ISSUE_SCOPE_TARGET_NOT_FOUND = "applies-to-target-not-found"

# Canonical intrinsic severity per relationship finding (v0.21.14). Referential
# integrity and graph-shape breakages are errors; advisory consistency findings
# (self-reference, unsupported edge, retired-target reference) are warnings. This
# is the single source of truth for the annotation severity: the SARIF renderer
# and the `rac gate` enforcement layer both read it, so they can never disagree.
# It is the *intrinsic* severity only — relationship findings still fail
# `--validate` (and gate, by default) regardless of severity; the enforcement
# class is decided separately under the corpus policy (ADR-049).
RELATIONSHIP_SEVERITY: dict[str, str] = {
    ISSUE_TARGET_NOT_FOUND: "error",
    ISSUE_TARGET_AMBIGUOUS: "error",
    ISSUE_TARGET_TYPE_MISMATCH: "error",
    ISSUE_RELATIONSHIP_CYCLE: "error",
    ISSUE_DUPLICATE_IDENTIFIER: "error",
    ISSUE_SCOPE_TARGET_NOT_FOUND: "error",
    ISSUE_TARGET_SUPERSEDED: "warning",
    ISSUE_SELF_REFERENCE: "warning",
    ISSUE_EDGE_UNSUPPORTED: "warning",
}


def _is_retired_artifact(product: Product, spec: ArtifactSpec | None) -> bool:
    """True when ``product``'s ``## Status`` is one of its type's retired states.

    Spec-driven (ADR-051): reads ``spec.retired_status`` rather than a hard-coded
    set, so every type's retired states are honoured. Matches case-insensitively
    against the first non-empty status line — the same first-line rule
    ``rac inspect`` uses, inlined to avoid importing ``inspect`` (which imports
    this module).
    """
    if spec is None or not spec.retired_status:
        return False
    body = product.sections.get("status")
    if not body:
        return False
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return any(first.casefold() == s.casefold() for s in spec.retired_status)


@dataclass
class RelationshipIssue:
    """One relationship-validation finding (ADR-003).

    ``to_dict`` emits only the keys relevant to ``code``: duplicate-identifier
    issues carry ``identifier``/``paths``; reference issues carry
    ``source_path``/``relationship``/``target``.
    """

    code: str
    source_path: str | None = None
    relationship: str | None = None
    target: str | None = None
    identifier: str | None = None
    paths: list[str] | None = None

    def to_dict(self) -> dict:
        if self.code == ISSUE_DUPLICATE_IDENTIFIER:
            return {
                "identifier": self.identifier,
                "paths": self.paths,
                "code": self.code,
            }
        if self.code == ISSUE_EDGE_UNSUPPORTED:
            return {
                "source_path": self.source_path,
                "relationship": self.relationship,
                "code": self.code,
            }
        if self.code == ISSUE_RELATIONSHIP_CYCLE:
            return {
                "relationship": self.relationship,
                "paths": self.paths,
                "code": self.code,
            }
        return {
            "source_path": self.source_path,
            "relationship": self.relationship,
            "target": self.target,
            "code": self.code,
        }


@dataclass
class RelationshipValidation:
    """Repository-level relationship validation result (REQ-006).

    ``relationships_checked`` counts every reference examined. ``validation_issues``
    counts *all* findings — missing/ambiguous/self references and duplicate
    identifiers — because each makes the declared relationship metadata unreliable.
    """

    directory: str
    recursive: bool
    relationships_checked: int
    issues: list[RelationshipIssue] = field(default_factory=list)

    @property
    def validation_issues(self) -> int:
        return len(self.issues)

    @property
    def ok(self) -> bool:
        return not self.issues


def _parsed_items(paths: list) -> list[tuple[str, Product, ArtifactSpec | None]]:
    """Parse and classify each path into ``(path, product, spec)``."""
    items: list[tuple[str, Product, ArtifactSpec | None]] = []
    for path in paths:
        product = parse_file(str(path))
        spec = spec_for(classify(product).type)
        items.append((str(path), product, spec))
    return items


def _corpus_items(
    directory: str, recursive: bool
) -> list[tuple[str, Product, ArtifactSpec | None]]:
    """Every document under ``directory`` as ``(path, product, spec)`` (one walk)."""
    return _entry_items(list(walk_corpus(directory, recursive=recursive)))


def _entry_items(
    entries: list[CorpusEntry],
) -> list[tuple[str, Product, ArtifactSpec | None]]:
    """An already-walked corpus snapshot as ``(path, product, spec)`` items."""
    return [(str(entry.path), entry.product, spec_for(entry.artifact_type)) for entry in entries]


# Identifier index: {casefold(ident) -> [(path, display_ident), ...]}
_IdentIndex = dict[str, list[tuple[str, str]]]
# Public alias for the reference-resolution index, so a caller can build it once
# and share it across the consumers that would otherwise each rebuild it.
ResolutionIndex = _IdentIndex


def build_resolution_index(
    items: list[tuple[str, Product, ArtifactSpec | None]],
) -> _IdentIndex:
    """Reference-resolution index: canonical identifiers plus legacy aliases.

    Migration support (v0.7.11, Initiative 7): an artifact that adopts a
    canonical frontmatter ID keeps answering to its legacy identifiers
    (``## ID`` value, filename prefix, stem), so existing human-readable
    references like ``ADR-015`` continue to resolve.
    """
    index: _IdentIndex = {}
    for path, product, spec in items:
        for ident in artifact_identifiers(product, spec, path):
            index.setdefault(ident.casefold(), []).append((path, ident))
    return index


def resolution_index_from_entries(entries: list[CorpusEntry]) -> ResolutionIndex:
    """The reference-resolution index for a snapshot, to build once and share.

    A pure, deterministic function of the snapshot's items. Passing the result
    into ``relationships_from_corpus``, ``summary_from_corpus``, and
    ``validation_from_corpus`` lets a derived build resolve over one index rather
    than each consumer rebuilding an identical one — byte-identical output, since
    the index is the same object every consumer would otherwise construct.
    """
    return build_resolution_index(_entry_items(entries))


# --- Compact validation rows (ADR-108) ---------------------------------------
#
# The repository validation gate and the relationship summary both read a small,
# fixed projection of each document: its identity, whether it is retired, the
# relationship sections it declares (and any its type does not support), and its
# declared edges. ``ValidationRow`` is exactly that projection with the
# ``Product`` dropped, so the gate and summary run over compact rows a worker can
# ship (ADR-108) instead of parsed products. The serial paths build the rows from
# their items and route through the same cores, so the merge and the serial build
# validate and summarise the graph identically by construction.


@dataclass(frozen=True)
class ValidationRow:
    """One document's compact projection for validation and summary (ADR-108).

    ``spec_name`` is the artifact type's name, or ``None`` for an Unknown/untyped
    document (the ``spec is None`` skip). ``canonical_id`` is the single identifier
    duplicate detection collides on; ``identifiers`` is the full alias set the
    resolution index is built from. ``retired`` is the type-aware retired-status
    flag; ``unsupported_sections`` are the declared relationship sections the type
    does not support (canonical ``RELATIONSHIP_SECTIONS`` names); ``edges`` are the
    declared ``(snake_section, refs)`` rows in schema order, empty for Unknown.
    """

    path: str
    spec_name: str | None
    canonical_id: str
    identifiers: tuple[str, ...]
    retired: bool
    unsupported_sections: tuple[str, ...]
    edges: tuple[tuple[str, tuple[str, ...]], ...]


def validation_row(path: str, product: Product, spec: ArtifactSpec | None) -> ValidationRow:
    """The compact :class:`ValidationRow` projection of one ``(path, product, spec)``.

    Pure and deterministic: every field is read straight from the product, so a
    row built here in the parent and a row shipped from a worker over the same
    document are identical. An Unknown document (``spec is None``) carries its
    identifiers — so it still populates the resolution index and can collide — but
    no edges and no unsupported sections (it declares no typed relationships).
    """
    identifiers = tuple(artifact_identifiers(product, spec, path))
    canonical_id = artifact_identifier(product, spec, path)
    if spec is None:
        return ValidationRow(
            path=path,
            spec_name=None,
            canonical_id=canonical_id,
            identifiers=identifiers,
            retired=False,
            unsupported_sections=(),
            edges=(),
        )
    edges = tuple(
        (section, tuple(refs))
        for section, refs in extract_relationships_full(product, spec).items()
    )
    return ValidationRow(
        path=path,
        spec_name=spec.name,
        canonical_id=canonical_id,
        identifiers=identifiers,
        retired=_is_retired_artifact(product, spec),
        unsupported_sections=tuple(unsupported_relationship_sections(product, spec)),
        edges=edges,
    )


def _validation_rows_from_items(
    items: list[tuple[str, Product, ArtifactSpec | None]],
) -> list[ValidationRow]:
    """Build the compact validation rows for a materialised item list."""
    return [validation_row(path, product, spec) for path, product, spec in items]


def _resolve_row_from_validation(row: ValidationRow) -> ResolveRow:
    """The :class:`ResolveRow` view of a validation row (shared resolve seam).

    Byte-identical to :func:`resolve_row` over the same document: the identifiers
    are the row's, and each edge's external flag is recomputed from its section
    exactly as :func:`resolve_row` does, so referential resolution runs through the
    one :func:`resolve_relationships` seam whichever row type it started from.
    """
    edges: list[tuple[str, bool, tuple[str, ...]]] = []
    for section, refs in row.edges:
        edge = edge_spec(section)
        external = edge is not None and edge.external
        edges.append((section, external, refs))
    return ResolveRow(path=row.path, identifiers=row.identifiers, edges=tuple(edges))


def _resolve_references(
    rows: list[ValidationRow],
    index: _IdentIndex,
) -> tuple[int, list[RelationshipIssue], set[str]]:
    """Resolve every explicit reference in ``rows`` against ``index``.

    Returns ``(checked, issues, resolved_target_paths)`` where
    ``resolved_target_paths`` is the set of paths that appear as a *resolved*
    target of at least one uniquely-matched reference — used by
    ``summarize_relationships`` for orphan detection.
    """
    issues: list[RelationshipIssue] = []
    resolved_targets: set[str] = set()
    checked = 0

    for row in rows:
        if row.spec_name is None:
            continue
        for section, refs in row.edges:
            edge = edge_spec(section)
            if edge is not None and edge.external:
                continue  # external refs (ADR-087) are format-linted, not resolved
            for ref in refs:
                checked += 1
                targets = [p for p, _ in index.get(ref.casefold(), [])]
                if not targets:
                    code = ISSUE_TARGET_NOT_FOUND
                elif len(targets) > 1:
                    code = ISSUE_TARGET_AMBIGUOUS
                elif targets == [row.path]:
                    code = ISSUE_SELF_REFERENCE
                else:
                    resolved_targets.add(targets[0])
                    continue  # resolved uniquely to another artifact
                issues.append(
                    RelationshipIssue(
                        code=code, source_path=row.path, relationship=section, target=ref
                    )
                )

    return checked, issues, resolved_targets


def _acyclic_adjacency(
    rows: list[ValidationRow],
    resolution_index: _IdentIndex,
    kind: str,
) -> dict[str, list[str]]:
    """``{source_path -> sorted unique target paths}`` for edge ``kind``.

    Only uniquely-resolved, non-self edges contribute (self/ambiguous/unresolved
    are owned by referential integrity), so the graph reflects real directed edges.
    """
    adjacency: dict[str, list[str]] = {}
    for row in rows:
        if row.spec_name is None:
            continue
        targets: set[str] = set()
        for ref in dict(row.edges).get(kind, ()):
            resolved = [p for p, _ in resolution_index.get(ref.casefold(), [])]
            if len(resolved) == 1 and resolved[0] != row.path:
                targets.add(resolved[0])
        if targets:
            adjacency[row.path] = sorted(targets)
    return adjacency


def _cyclic_components(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Strongly-connected components of size > 1, each a sorted node list.

    A cycle exists exactly within an SCC larger than one node (self-loops are
    already excluded upstream). Deterministic: nodes and neighbours are visited in
    sorted order (Tarjan), and the components are returned sorted.
    """
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = [0]
    components: list[list[str]] = []

    nodes = sorted(set(adjacency) | {t for ts in adjacency.values() for t in ts})

    def strongconnect(v: str) -> None:
        indices[v] = lowlink[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adjacency.get(v, []):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in nodes:
        if node not in indices:
            strongconnect(node)
    return sorted(components, key=lambda c: c[0])


def _cycle_issues(
    rows: list[ValidationRow],
    resolution_index: _IdentIndex,
) -> list[RelationshipIssue]:
    """One ``relationship-cycle`` per cyclic component of each acyclic edge kind."""
    issues: list[RelationshipIssue] = []
    for kind in sorted(name for name, edge in REGISTRY.items() if edge.acyclic):
        adjacency = _acyclic_adjacency(rows, resolution_index, kind)
        for component in _cyclic_components(adjacency):
            issues.append(
                RelationshipIssue(code=ISSUE_RELATIONSHIP_CYCLE, relationship=kind, paths=component)
            )
    return issues


# --- Filesystem-scoped edges (decision-to-code-proximity, Initiative 1) ------
#
# ``## Applies To`` entries are code paths/components a decision governs. They ride
# the relationship machinery (extracted, graphed, surfaced via get_related) but are
# resolved against the *file tree*, not the identifier index: a literal path or
# directory entry is existence-checked relative to the repository root. Declared,
# never inferred (ADR-065/066); a pure function of the declared entry and the tree
# (ADR-066). Glob patterns (matched at lookup, #275) and component-name labels
# (no registry this cycle) are recorded without existence-checking. The pure entry
# helpers (``classify_scope_entry``/``normalized_scope_path``/``repository_root``)
# live in :mod:`rac.services.scope_paths`, shared with ``rac.services.scope``.


def _scope_validation_issues(
    directory: str,
    rows: list[ValidationRow],
) -> list[RelationshipIssue]:
    """One ``applies-to-target-not-found`` per missing literal path/dir entry.

    Checks only filesystem-scoped edges (``edge.filesystem_scoped``) and only
    their literal ``path`` entries: each is checked to exist relative to the
    repository root. Glob patterns and component labels are recorded without
    existence-checking. Deterministic — rows in sorted-path order, entries in
    declared order.
    """
    root = repository_root(directory)
    issues: list[RelationshipIssue] = []
    for row in rows:
        if row.spec_name is None:
            continue
        for section, refs in row.edges:
            edge = edge_spec(section)
            if edge is None or not edge.filesystem_scoped:
                continue
            for ref in refs:
                if classify_scope_entry(ref) != "path":
                    continue
                normalized = normalized_scope_path(ref)
                if normalized is not None and (root / normalized).exists():
                    continue
                issues.append(
                    RelationshipIssue(
                        code=ISSUE_SCOPE_TARGET_NOT_FOUND,
                        source_path=row.path,
                        relationship=section,
                        target=ref,
                    )
                )
    return issues


def resolution_index_from_rows(rows: list[ValidationRow]) -> ResolutionIndex:
    """The reference-resolution index over validation rows' identifiers (ADR-108).

    Byte-identical to ``build_resolution_index`` over the same documents in the
    same order — the rows' ``identifiers`` are the ``artifact_identifiers`` tuple.
    Passing the result into :func:`summary_from_rows` and :func:`validation_from_rows`
    lets the portfolio resolve over one shared index, as the derived build does.
    """
    index: _IdentIndex = {}
    for row in rows:
        for ident in row.identifiers:
            index.setdefault(ident.casefold(), []).append((row.path, ident))
    return index


def _validate(
    directory: str,
    items: list[tuple[str, Product, ArtifactSpec | None]],
    recursive: bool,
    *,
    resolution_index: ResolutionIndex | None = None,
) -> RelationshipValidation:
    """Validate a materialised item list via the compact-row core (ADR-108)."""
    return validation_from_rows(
        directory,
        _validation_rows_from_items(items),
        recursive,
        resolution_index=resolution_index,
    )


def validation_from_rows(
    directory: str,
    rows: list[ValidationRow],
    recursive: bool = True,
    *,
    resolution_index: ResolutionIndex | None = None,
) -> RelationshipValidation:
    """The repository relationship-validation gate over compact rows (ADR-108).

    The single core the serial :func:`_validate` and the parallel merge both run,
    so both produce the same findings in the same order by construction. Every
    check reads only the rows' compact projection — canonical identifier, retired
    flag, declared edges, unsupported sections — plus the working tree for scope
    existence, so no parsed ``Product`` is needed.
    """
    issues: list[RelationshipIssue] = []

    # Duplicate identifiers (repo-level), emitted first, sorted by identifier. One
    # entry per document — only the canonical identifier can collide (ADR-026).
    ident_index: _IdentIndex = {}
    for row in rows:
        ident_index.setdefault(row.canonical_id.casefold(), []).append((row.path, row.canonical_id))
    duplicates: list[tuple[str, list[str]]] = []
    for entries in ident_index.values():
        if len(entries) > 1:
            display = min(entries, key=lambda e: e[0])[1]  # first path's casing
            duplicates.append((display, sorted(p for p, _ in entries)))
    for display, dup_paths in sorted(duplicates, key=lambda d: d[0].casefold()):
        issues.append(
            RelationshipIssue(code=ISSUE_DUPLICATE_IDENTIFIER, identifier=display, paths=dup_paths)
        )

    # Edge-legality (v0.14.0, ADR-049): report relationship sections an artifact's
    # type does not declare instead of silently dropping them. Deterministic —
    # rows in sorted-path order, sections in canonical RELATIONSHIP_SECTIONS order.
    for row in rows:
        if row.spec_name is None:
            continue
        for section in row.unsupported_sections:
            issues.append(
                RelationshipIssue(
                    code=ISSUE_EDGE_UNSUPPORTED, source_path=row.path, relationship=_snake(section)
                )
            )

    if resolution_index is None:
        resolution_index = resolution_index_from_rows(rows)
    by_path = {row.path: row for row in rows}

    def _resolved(ref: str, source_path: str) -> str | None:
        """The unique non-self target path for ``ref``, or None.

        Unresolved/ambiguous/self references are owned by referential integrity;
        the graph checks below only reason about uniquely-resolved edges.
        """
        targets = [p for p, _ in resolution_index.get(ref.casefold(), [])]
        if len(targets) != 1 or targets[0] == source_path:
            return None
        return targets[0]

    # Range (v0.16.0, ADR-055): a resolved target whose type is not in the edge's
    # declared range is an illegal edge — e.g. a ``## Related Decisions`` reference
    # that resolves to a requirement. Deterministic (sorted-path / spec.optional).
    for row in rows:
        if row.spec_name is None:
            continue
        for section, refs in row.edges:
            edge = edge_spec(section)
            if edge is None or edge.external:
                continue  # external edges (ADR-087) carry no artifact range
            for ref in refs:
                target = _resolved(ref, row.path)
                if target is None:
                    continue
                target_spec_name = by_path[target].spec_name
                if target_spec_name is None:
                    continue  # untyped document (ADR-010) — not a range violation
                if target_spec_name not in edge.range:
                    issues.append(
                        RelationshipIssue(
                            code=ISSUE_TARGET_TYPE_MISMATCH,
                            source_path=row.path,
                            relationship=section,
                            target=ref,
                        )
                    )

    # Status-consistency (v0.14.1, generalised in v0.16.0/ADR-051): a live artifact
    # must not reference a retired target, except via an edge that permits it
    # (``supersedes``, ``forbids_target_status=False``). Reads the resolved
    # target's retired flag from the rows — no second walk.
    for row in rows:
        if row.spec_name is None or row.retired:
            continue  # unknown file, or a retired source (historical chains exempt)
        for section, refs in row.edges:
            edge = edge_spec(section)
            if edge is None or edge.external or not edge.forbids_target_status:
                continue  # supersedes/external edges never gate on target status
            for ref in refs:
                target = _resolved(ref, row.path)
                if target is None:
                    continue
                if by_path[target].retired:
                    issues.append(
                        RelationshipIssue(
                            code=ISSUE_TARGET_SUPERSEDED,
                            source_path=row.path,
                            relationship=section,
                            target=ref,
                        )
                    )

    # Acyclicity (v0.16.0, ADR-055): a cycle in a directional, acyclic edge kind
    # (today ``supersedes``) is illegal — an ordering/replacement edge must not
    # form a loop. Reported per strongly-connected component, deterministically.
    issues.extend(_cycle_issues(rows, resolution_index))

    checked, ref_issues, _ = _resolve_references(rows, resolution_index)
    issues.extend(ref_issues)

    # Code-scope existence (decision-to-code-proximity, Initiative 1): filesystem-
    # scoped ``## Applies To`` literal paths are checked against the working tree.
    # Appended last, so existing finding order is unchanged (ADR-007).
    issues.extend(_scope_validation_issues(directory, rows))

    return RelationshipValidation(
        directory=directory,
        recursive=recursive,
        relationships_checked=checked,
        issues=issues,
    )


def validate_relationships(
    directory: str, recursive: bool = True, *, cache: CorpusCache | None = None
) -> RelationshipValidation:
    """Validate explicit relationship references across a directory.

    When a per-invocation ``cache`` is supplied, the corpus is served through it
    so artifacts already parsed in an earlier phase of the same run are not
    reparsed (WS8); the result is byte-identical to the uncached walk.
    """
    if cache is not None:
        return validation_from_corpus(
            directory, cache.collect(directory, recursive=recursive), recursive
        )
    items = _corpus_items(directory, recursive)
    return _validate(directory, items, recursive)


def validation_from_corpus(
    directory: str,
    entries: list[CorpusEntry],
    recursive: bool = True,
    *,
    resolution_index: ResolutionIndex | None = None,
) -> RelationshipValidation:
    """Validate relationships in an already-walked corpus snapshot (v0.8.0).

    Same result as :func:`validate_relationships`; the snapshot lets one walk
    feed several analyses (repository model, future incremental refresh). A
    prebuilt ``resolution_index`` is used when supplied (byte-identical output).
    """
    return _validate(directory, _entry_items(entries), recursive, resolution_index=resolution_index)


def validate_relationships_file(path: str) -> RelationshipValidation:
    """Validate a single file (REQ-009).

    The identifier index contains only this file, so cross-file references will not
    resolve — repository validation needs a directory.
    """
    return _validate(path, _parsed_items([path]), recursive=False)


def validate_document_against_corpus(
    product: Product,
    source_path: str,
    directory: str,
    recursive: bool = True,
) -> RelationshipValidation:
    """Resolve one *proposed* document's outbound references against a live corpus.

    The single seam the Claude Code ``PreToolUse`` pre-edit hook needs
    (v0.21.17, ADR-067): a document held only in memory — typically piped to
    ``rac validate - --corpus`` from the hook before the edit lands — has its
    cross-artifact references resolved against the *whole* corpus index, so a
    reference to a retired (superseded/deprecated) or missing decision is
    reported even though the proposed document is not yet on disk.

    This reuses the existing repository resolution (:func:`_validate`) rather
    than reimplementing it (ADR-016 / ADR-063): the proposed document is folded
    into the corpus snapshot as ``(source_path, product, spec)`` and the run's
    findings are then filtered to those whose ``source_path`` is the proposed
    document — pre-existing corpus issues are not the pre-edit hook's concern,
    only the references the edit introduces.

    Identifier collision (editing an existing artifact): the proposed document
    usually shares its canonical identifier with the on-disk artifact being
    edited. The on-disk counterpart is *excluded* from the corpus snapshot
    (matched on canonical identifier, case-insensitively), so the proposed
    document stands in for it. This prevents two spurious findings — a
    ``duplicate-artifact-identifier`` against the very file being edited, and a
    ``relationship-self-reference`` when the proposed document references its own
    identity — and means an edit is validated *as if* it replaces the committed
    version. A brand-new document (no identifier match) simply joins the corpus.
    """
    corpus = _corpus_items(directory, recursive)
    spec = spec_for(classify(product).type)
    proposed_ident = artifact_identifier(product, spec, source_path).casefold()
    # Drop the on-disk counterpart of the document being edited (same canonical
    # identity) so the proposed document replaces it rather than colliding with
    # it. A new artifact matches nothing here and the corpus is unchanged.
    kept = [
        item
        for item in corpus
        if artifact_identifier(item[1], item[2], item[0]).casefold() != proposed_ident
    ]
    items = [*kept, (source_path, product, spec)]
    result = _validate(directory, items, recursive)
    # Only the proposed document's own outbound references are the hook's
    # concern; pre-existing corpus findings (and repo-level duplicate/cycle
    # findings not anchored to this document) are filtered out so the pre-edit
    # signal is exactly "what this edit introduces".
    own = [issue for issue in result.issues if issue.source_path == source_path]
    return RelationshipValidation(
        directory=directory,
        recursive=recursive,
        relationships_checked=result.relationships_checked,
        issues=own,
    )


# --- Repository relationship summary (v0.7.3) ---------------------------------
#
# Aggregate relationship health for ``rac portfolio``. Returns counts and an
# orphan count. An artifact is *orphaned* when no other artifact references it
# with a successfully-resolved relationship — it may still declare outbound
# relationships, but nothing points back to it. Coverage is the fraction of
# non-unknown artifacts that declare at least one relationship.


@dataclass
class RelationshipSummary:
    """Repository-level relationship health for ``PortfolioSummary``.

    ``total`` counts every declared reference (same unit as
    ``RelationshipReport.relationship_count``).  ``broken`` counts references
    that could not be uniquely resolved (target-not-found, ambiguous, or
    self-reference).  ``orphaned`` counts artifacts that are not the target of
    any resolved reference.  ``coverage`` is the fraction of known (non-unknown)
    artifacts that declare at least one outbound relationship; 1.0 when there
    are no known artifacts.  ``issues`` holds the per-reference resolution
    findings (``broken == len(issues)``); consumers like ``rac portfolio`` turn
    them into attention items without a second relationship walk.
    """

    total: int
    valid: int
    broken: int
    orphaned: int
    coverage: float  # 0.0 – 1.0
    issues: list[RelationshipIssue] = field(default_factory=list)


def summarize_relationships(directory: str, recursive: bool = True) -> RelationshipSummary:
    """Aggregate relationship health across a directory (v0.7.3)."""
    return _summarize(_corpus_items(directory, recursive))


def summary_from_corpus(
    entries: list[CorpusEntry], *, resolution_index: ResolutionIndex | None = None
) -> RelationshipSummary:
    """Aggregate relationship health for an already-walked snapshot (v0.8.0).

    Same result as :func:`summarize_relationships`; the snapshot lets one walk
    feed several analyses (repository model, future incremental refresh). A
    prebuilt ``resolution_index`` is used when supplied (byte-identical output).
    """
    return _summarize(_entry_items(entries), resolution_index=resolution_index)


def _summarize(
    items: list[tuple[str, Product, ArtifactSpec | None]],
    *,
    resolution_index: ResolutionIndex | None = None,
) -> RelationshipSummary:
    """Summarise a materialised item list via the compact-row core (ADR-108)."""
    return summary_from_rows(_validation_rows_from_items(items), resolution_index=resolution_index)


def summary_from_rows(
    rows: list[ValidationRow], *, resolution_index: ResolutionIndex | None = None
) -> RelationshipSummary:
    """Aggregate relationship health over compact rows (ADR-108).

    The single core the serial :func:`_summarize` and the parallel merge both run.
    Byte-identical to the item-based summary: the same references resolve against
    the same index, and coverage/orphan counts read the rows' spec/edge projection.
    """
    if not rows:
        return RelationshipSummary(total=0, valid=0, broken=0, orphaned=0, coverage=1.0)

    index = resolution_index if resolution_index is not None else resolution_index_from_rows(rows)
    checked, ref_issues, resolved_targets = _resolve_references(rows, index)

    broken = len(ref_issues)
    valid = checked - broken

    # Orphan = known (spec is not None) artifact whose path never appears as a
    # resolved target of another artifact's reference.
    all_known_paths = {row.path for row in rows if row.spec_name is not None}
    orphaned = len(all_known_paths - resolved_targets)

    # Coverage = fraction of known artifacts that declare >=1 outbound relationship.
    artifacts_with_rels = sum(1 for row in rows if row.spec_name is not None and row.edges)
    coverage = artifacts_with_rels / len(all_known_paths) if all_known_paths else 1.0

    return RelationshipSummary(
        total=checked,
        valid=valid,
        broken=broken,
        orphaned=orphaned,
        coverage=round(coverage, 4),
        issues=ref_issues,
    )


# --- Relationship objects for the repository model (v0.8.0) -------------------
#
# The repository model (rac.services.repository) needs every declared reference
# as one navigable object: where it points from, what it says, and where it
# resolves to. The raw reference text remains the source of truth (ADR-016);
# resolution reuses the same alias index as `--validate`, so a reference is
# resolved here exactly when validation reports no issue for it.


@dataclass(frozen=True)
class Relationship:
    """One declared cross-artifact reference, with its resolution outcome.

    ``resolved_path`` is set only when the reference resolves uniquely to
    another artifact; otherwise ``issue`` carries the stable validation code
    (:data:`ISSUE_TARGET_NOT_FOUND`, :data:`ISSUE_TARGET_AMBIGUOUS`, or
    :data:`ISSUE_SELF_REFERENCE`).
    """

    source_path: str
    relationship: str  # snake_case section name ("related_decisions", ...)
    target: str  # raw reference text (source of truth, ADR-016)
    resolved_path: str | None
    issue: str | None


# --- Compact resolve seam (ADR-108) ------------------------------------------
#
# The parallel merge ships compact per-document rows across the process boundary,
# not parsed ``Product`` objects. ``ResolveRow`` is exactly what the resolve loop
# reads about one document — its resolution identifiers and its declared edges,
# with the ``Product`` dropped. Both the serial ``relationships_from_corpus`` and
# the merge feed the same :func:`resolve_relationships` over these rows, so the
# two paths resolve the graph identically by construction rather than by
# coincidence — the parity the merge rests on is structural.


@dataclass(frozen=True)
class ResolveRow:
    """One document's compact projection for relationship resolution (ADR-108).

    ``identifiers`` are the document's canonical identifier plus its legacy
    aliases — the same tuple :func:`build_resolution_index` reads via
    ``artifact_identifiers`` — carried for *every* document (Unknown included) so
    the resolution index and its duplicate collisions are reproduced exactly.
    ``edges`` are the declared relationship sections as ``(section, external,
    refs)`` rows, in the artifact's own schema order; Unknown documents carry no
    edges. This is the whole input the resolve loop needs, with the ``Product``
    dropped.
    """

    path: str
    identifiers: tuple[str, ...]
    edges: tuple[tuple[str, bool, tuple[str, ...]], ...]


def resolve_row(path: str, product: Product, spec: ArtifactSpec | None) -> ResolveRow:
    """The compact :class:`ResolveRow` projection of one ``(path, product, spec)``.

    Pure and deterministic: the identifiers and declared edges are read straight
    from the product, so a row built here in the parent from a parsed entry and a
    row shipped from a worker over the same document are identical.
    """
    identifiers = tuple(artifact_identifiers(product, spec, path))
    if spec is None:
        return ResolveRow(path=path, identifiers=identifiers, edges=())
    edges: list[tuple[str, bool, tuple[str, ...]]] = []
    for section, refs in extract_relationships_full(product, spec).items():
        edge = edge_spec(section)
        external = edge is not None and edge.external
        edges.append((section, external, tuple(refs)))
    return ResolveRow(path=path, identifiers=identifiers, edges=tuple(edges))


def _index_from_resolve_rows(rows: list[ResolveRow]) -> _IdentIndex:
    """The reference-resolution index over ``rows`` (Unknown documents included).

    Byte-identical to ``build_resolution_index`` run over the same documents in
    the same order: each row contributes its identifiers, in order, as
    ``(path, ident)`` under the casefolded key.
    """
    index: _IdentIndex = {}
    for row in rows:
        for ident in row.identifiers:
            index.setdefault(ident.casefold(), []).append((row.path, ident))
    return index


def resolve_relationships(
    rows: list[ResolveRow], *, resolution_index: ResolutionIndex | None = None
) -> list[Relationship]:
    """Resolve compact :class:`ResolveRow` items into :class:`Relationship` objects.

    The single resolve loop shared by the serial corpus path and the parallel
    merge (ADR-108). Ordering is deterministic: rows in snapshot (sorted path)
    order, sections in each row's schema order, references in declaration order.
    A prebuilt ``resolution_index`` is used when supplied; otherwise it is built
    from the rows' identifiers (:func:`_index_from_resolve_rows`), which equals
    ``build_resolution_index`` over the same documents.
    """
    index = resolution_index if resolution_index is not None else _index_from_resolve_rows(rows)
    relationships: list[Relationship] = []
    for row in rows:
        for section, external, refs in row.edges:
            for ref in refs:
                resolved: str | None = None
                issue: str | None = None
                if external:
                    # External references (ADR-087) resolve to no in-corpus
                    # artifact by design — an edge for the graph, never "broken".
                    relationships.append(
                        Relationship(
                            source_path=row.path,
                            relationship=section,
                            target=ref,
                            resolved_path=None,
                            issue=None,
                        )
                    )
                    continue
                targets = [p for p, _ in index.get(ref.casefold(), [])]
                if not targets:
                    issue = ISSUE_TARGET_NOT_FOUND
                elif len(targets) > 1:
                    issue = ISSUE_TARGET_AMBIGUOUS
                elif targets == [row.path]:
                    issue = ISSUE_SELF_REFERENCE
                else:
                    resolved = targets[0]
                relationships.append(
                    Relationship(
                        source_path=row.path,
                        relationship=section,
                        target=ref,
                        resolved_path=resolved,
                        issue=issue,
                    )
                )
    return relationships


def relationships_from_corpus(
    entries: list[CorpusEntry], *, resolution_index: ResolutionIndex | None = None
) -> list[Relationship]:
    """Every declared reference in a corpus snapshot as :class:`Relationship`.

    Ordering is deterministic: source artifacts in snapshot (sorted path)
    order, sections in each artifact's own schema order, references in
    declaration order — matching ``_resolve_references``. A prebuilt
    ``resolution_index`` (from :func:`resolution_index_from_entries`) is used when
    supplied, so a shared build resolves over one index; the output is identical.
    Resolution runs through the shared :func:`resolve_relationships` seam so the
    serial path and the parallel merge (ADR-108) cannot drift.
    """
    rows = [resolve_row(path, product, spec) for path, product, spec in _entry_items(entries)]
    return resolve_relationships(rows, resolution_index=resolution_index)


def relationships_from_rows(
    rows: list[ValidationRow], *, resolution_index: ResolutionIndex | None = None
) -> list[Relationship]:
    """Resolve compact :class:`ValidationRow` items into :class:`Relationship` objects.

    The parallel merge (ADR-108) holds validation rows, not corpus entries; this
    routes them through the same :func:`resolve_relationships` seam the serial
    :func:`relationships_from_corpus` uses, so the resolved graph is byte-identical
    whichever row type it started from.
    """
    return resolve_relationships(
        [_resolve_row_from_validation(row) for row in rows], resolution_index=resolution_index
    )


def inbound_counts_from_relationships(rels: list[Relationship]) -> dict[str, int]:
    """``{artifact path -> count of resolved edges that point at it}`` from resolved edges.

    The counting half of :func:`inbound_counts_from_corpus`, split out so a caller
    that has already resolved the graph (the derived-index build) computes inbound
    degree without a second resolution pass. Same definition — resolved, unique,
    non-self edges only; artifacts with no inbound edge are absent (count 0).
    """
    counts: dict[str, int] = {}
    for rel in rels:
        if rel.resolved_path is not None:
            counts[rel.resolved_path] = counts.get(rel.resolved_path, 0) + 1
    return counts


def inbound_counts_from_corpus(entries: list[CorpusEntry]) -> dict[str, int]:
    """``{artifact path -> count of resolved edges that point at it}``.

    The canonical inbound-degree signal: resolved, unique, non-self edges only
    (the same definition ``rac doctor``'s orphan/hub pass and the search graph
    boost both consume, so they cannot drift). Artifacts with no inbound edge are
    absent (count 0).
    """
    return inbound_counts_from_relationships(relationships_from_corpus(entries))


# --- 1-hop neighborhood (get_related) ----------------------------------------
#
# The references an artifact declares (outgoing) and the artifacts whose
# references resolve to it (incoming). This is the single source of truth for
# the ``get_related`` MCP tool's view and for the grounding-eval benchmark that
# guards it (ADR-031, ADR-067): both consume these functions, so the scored
# surface cannot drift from the served one. Resolution stays Core-owned — an
# incoming edge exists exactly when a reference resolved uniquely to the target.


# Canonical relationship-section order (snake_case), for deterministic
# get_related ordering (WS4, REQ-006): incoming edges sort by their section's
# position in the artifact's spec/section vocabulary, then ascending id.
_RELATIONSHIP_ORDER: dict[str, int] = {
    _snake(section): index for index, section in enumerate(RELATIONSHIP_SECTIONS)
}


def _relationship_order(section: str) -> int:
    """Rank of a snake_case relationship section in the canonical order."""
    return _RELATIONSHIP_ORDER.get(section, len(_RELATIONSHIP_ORDER))


@dataclass(frozen=True)
class IncomingReference:
    """An artifact whose declared reference resolves to a target artifact.

    The ``get_related`` ``incoming`` shape: the referencing artifact's identity,
    the snake_case relationship section the reference sits in, and ``target`` —
    the reference text as stored (WS2 evidence: the edge that surfaced it).
    """

    id: str
    type: str
    title: str | None
    path: str
    section: str
    target: str


@dataclass(frozen=True)
class IncomingReferences:
    """Capped, ordered incoming edges plus the full pre-cap count (WS4).

    ``items`` is ordered by relationship type then ascending id (REQ-006) and
    capped at the per-call edge limit (REQ-007); ``total`` is the full count so a
    caller can signal overflow via the truncation marker.
    """

    items: list[IncomingReference]
    total: int


@dataclass(frozen=True)
class OutgoingReferences:
    """Capped outgoing references grouped by section, plus the full count (WS4)."""

    by_section: dict[str, list[str]]
    total: int

    @property
    def kept(self) -> int:
        return sum(len(targets) for targets in self.by_section.values())


def outgoing_references(
    relationships: list[Relationship],
    source_path: str,
    *,
    limit: int | None = None,
) -> OutgoingReferences:
    """The references ``source_path`` declares, grouped by section, as stored.

    Keys are snake_case section names in the source artifact's own spec order
    (``relationships_from_corpus`` yields references in that order, so a
    first-seen-wins dict preserves it). References are the raw stored text — the
    source of truth (ADR-016). Collection stops after ``limit`` edges so a
    pathological artifact cannot build an unbounded list (WS4, REQ-007); the
    default resolves to :data:`MAX_RELATED_EDGES` at call time.
    """
    if limit is None:
        limit = MAX_RELATED_EDGES
    by_section: dict[str, list[str]] = {}
    total = 0
    kept = 0
    for rel in relationships:
        if rel.source_path != source_path:
            continue
        total += 1
        if kept < limit:
            by_section.setdefault(rel.relationship, []).append(rel.target)
            kept += 1
    return OutgoingReferences(by_section=by_section, total=total)


def incoming_references(
    relationships: list[Relationship],
    identity_by_path: dict[str, tuple[str, str, str | None]],
    target_path: str,
    *,
    limit: int | None = None,
) -> IncomingReferences:
    """Artifacts whose declared references resolve uniquely to ``target_path``.

    ``identity_by_path`` maps each artifact path to ``(id, type, title)`` (the
    caller builds it from the repository index). Self-references are excluded.
    Collection stops storing after ``limit`` edges to bound work (WS4, REQ-007),
    while the full count is still tallied so overflow can be signalled; the kept
    edges are ordered by relationship type then ascending id (REQ-006) so
    tail-truncation drops the lowest-priority edges deterministically (REQ-008).
    The default resolves to :data:`MAX_RELATED_EDGES` at call time.
    """
    if limit is None:
        limit = MAX_RELATED_EDGES
    incoming: list[IncomingReference] = []
    total = 0
    for rel in relationships:
        if rel.resolved_path != target_path:
            continue
        if rel.source_path == target_path:  # self-references are not incoming edges
            continue
        identity = identity_by_path.get(rel.source_path)
        if identity is None:  # pragma: no cover — every relationship source is indexed
            continue
        total += 1
        if len(incoming) < limit:
            source_id, source_type, source_title = identity
            incoming.append(
                IncomingReference(
                    id=source_id,
                    type=source_type,
                    title=source_title,
                    path=rel.source_path,
                    section=rel.relationship,
                    target=rel.target,
                )
            )
    incoming.sort(key=lambda e: (_relationship_order(e.section), e.id, e.path))
    return IncomingReferences(items=incoming, total=total)


@dataclass(frozen=True)
class NeighborhoodNode:
    """One artifact reachable from the origin, with its hop distance (v0.24, WS-D)."""

    id: str
    type: str
    title: str | None
    path: str
    hops: int


@dataclass(frozen=True)
class Neighborhood:
    """The bounded multi-hop neighbourhood of an origin artifact.

    ``nodes`` excludes the origin and is ordered deterministically by
    ``(hops, type, id)`` so response-budget truncation drops the farthest,
    lowest-priority artifacts first. ``truncated`` is True when any traversal
    cap stopped the walk early.
    """

    nodes: list[NeighborhoodNode]
    truncated: bool


def neighborhood(
    relationships: list[Relationship],
    identity_by_path: dict[str, tuple[str, str, str | None]],
    origin_path: str,
    *,
    depth: int,
    max_frontier: int = MAX_TRAVERSAL_FRONTIER,
    work_budget: int = MAX_TRAVERSAL_WORK,
) -> Neighborhood:
    """Artifacts within ``depth`` hops of ``origin_path`` (v0.24, WS-D).

    A breadth-first walk over resolved relationship edges in both directions,
    bounded by the four caps from ``rac-parser-traversal-robustness`` REQ-010:
    the requested ``depth`` is clamped to :data:`MAX_TRAVERSAL_DEPTH`, each level
    admits at most ``max_frontier`` nodes, a visited set makes the walk
    cycle-safe, and ``work_budget`` caps the edges examined across the whole
    walk. The origin is never included. Deterministic and offline (ADR-002):
    identical corpus bytes yield a byte-identical, ordered result.
    """
    depth = max(0, min(depth, MAX_TRAVERSAL_DEPTH))

    # Undirected adjacency over resolved edges; each entry carries the relationship
    # rank of the edge so discovery order is deterministic (REQ-004).
    adjacency: dict[str, list[tuple[str, int]]] = {}
    for rel in relationships:
        if rel.resolved_path is None or rel.source_path == rel.resolved_path:
            continue
        rank = _relationship_order(rel.relationship)
        adjacency.setdefault(rel.source_path, []).append((rel.resolved_path, rank))
        adjacency.setdefault(rel.resolved_path, []).append((rel.source_path, rank))

    visited: set[str] = {origin_path}
    discovered: list[tuple[int, int, str, str]] = []  # (hops, rank, id, path)
    frontier = [origin_path]
    work = 0
    truncated = False

    for current_depth in range(1, depth + 1):
        next_frontier: list[str] = []
        for path in sorted(frontier):
            for neighbor_path, rank in sorted(set(adjacency.get(path, []))):
                work += 1
                if work > work_budget:
                    truncated = True
                    break
                if neighbor_path in visited:
                    continue
                visited.add(neighbor_path)
                identity = identity_by_path.get(neighbor_path)
                if identity is None:  # pragma: no cover — every edge target is indexed
                    continue
                discovered.append((current_depth, rank, identity[0], neighbor_path))
                if len(next_frontier) >= max_frontier:
                    truncated = True
                else:
                    next_frontier.append(neighbor_path)
            if truncated and work > work_budget:
                break
        frontier = next_frontier
        if not frontier:
            break

    discovered.sort()  # (hops, rank, id, path) — deterministic, stable truncation
    nodes = [
        NeighborhoodNode(
            id=identity_by_path[path][0],
            type=identity_by_path[path][1],
            title=identity_by_path[path][2],
            path=path,
            hops=hops,
        )
        for hops, _rank, _id, path in discovered
    ]
    nodes.sort(key=lambda n: (n.hops, n.type, n.id))
    return Neighborhood(nodes=nodes, truncated=truncated)
