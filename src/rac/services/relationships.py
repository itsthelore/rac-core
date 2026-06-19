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

import re
from dataclasses import dataclass, field

from rac.core.artifacts import ArtifactSpec, spec_for
from rac.core.classification import classify
from rac.core.corpus import CorpusCache, CorpusEntry, walk_corpus
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.limits import MAX_RELATED_EDGES
from rac.core.markdown import parse_file
from rac.core.models import Product
from rac.core.relationship_types import REGISTRY, edge_spec

# The cross-artifact "Related X" sections. These populate the ``relationships``
# dict in ``rac inspect`` output. ``related designs`` is included so every peer
# artifact type can be referenced.
RELATED_SECTIONS: tuple[str, ...] = (
    "related requirements",
    "related decisions",
    "related roadmaps",
    "related prompts",
    "related designs",
)

# The full relationship-section vocabulary and its canonical ordering, including
# ``supersedes``. This module owns the ordering; ``stats`` and the
# ``relationships`` command both render by-type output in this order. ``supersedes``
# is the one section that does *not* appear in the inspect ``relationships`` dict:
# there it stays a top-level scalar for backwards compatibility (ADR-007).
RELATIONSHIP_SECTIONS: tuple[str, ...] = RELATED_SECTIONS + ("supersedes",)

# A *well-formed* leading Markdown list marker: ``-``, ``*``, ``+``, or ``N.``
# followed by whitespace. Only these are stripped; any other leading text is
# preserved verbatim, so references like "REQ-001 (blocked)" or a path beginning
# with "../" survive intact (the whole line is the reference, per ADR-016).
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")


def _snake(section: str) -> str:
    return section.replace(" ", "_")


def parse_references(body: str) -> list[str]:
    """Split a relationship section body into individual reference strings.

    One reference per non-empty line. A well-formed leading list marker is
    stripped; otherwise the line is preserved verbatim. No ID parsing and no
    resolution — the line text *is* the reference.
    """
    references: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        references.append(_LIST_MARKER_RE.sub("", stripped, count=1).strip())
    return references


def _collect(
    product: Product, spec: ArtifactSpec, allowed: tuple[str, ...]
) -> dict[str, list[str]]:
    """References for the relationship sections in ``spec.optional`` ∩ ``allowed``.

    Returns ``{snake_section -> [references]}`` in ``spec.optional`` order (each
    artifact's own schema order), including only sections present with at least
    one parsed reference. The single core behind the two public extractors.
    """
    relationships: dict[str, list[str]] = {}
    for section in spec.optional:
        if section not in allowed:
            continue
        body = product.sections.get(section)
        if not body:
            continue
        refs = parse_references(body)
        if refs:
            relationships[_snake(section)] = refs
    return relationships


def extract_relationships(product: Product, spec: ArtifactSpec) -> dict[str, list[str]]:
    """Cross-artifact references for ``rac inspect``.

    Excludes ``supersedes`` — that stays a top-level scalar in inspect output
    (ADR-007). Order follows ``spec.optional`` (the artifact's own schema order).
    """
    return _collect(product, spec, RELATED_SECTIONS)


def extract_relationships_full(product: Product, spec: ArtifactSpec) -> dict[str, list[str]]:
    """Cross-artifact references for ``rac relationships`` — *including* Supersedes.

    The repository-level relationship command treats Supersedes as a first-class
    relationship (REQ-003), so it is reported here alongside the ``related_*``
    sections. Order follows ``spec.optional``.
    """
    return _collect(product, spec, RELATIONSHIP_SECTIONS)


def present_relationship_sections(product: Product, spec: ArtifactSpec) -> list[str]:
    """Relationship sections ``product`` declares *and* populates.

    Spec-driven and inclusive of ``supersedes`` (unlike
    :func:`extract_relationships`). A section counts only when present with at
    least one parsed reference (REQ-011). Returns the normalized section names in
    ``spec.optional`` order, for ``rac stats`` declared-presence counts.
    """
    present: list[str] = []
    for section in spec.optional:
        if section not in RELATIONSHIP_SECTIONS:
            continue
        body = product.sections.get(section)
        if body and parse_references(body):
            present.append(section)
    return present


def unsupported_relationship_sections(product: Product, spec: ArtifactSpec) -> list[str]:
    """Relationship sections ``product`` declares that its type does not support.

    A ``## Related <Type>`` / ``## Supersedes`` section present with at least one
    reference whose name is *not* in this type's ``spec.optional`` produces no edge
    today and is silently dropped (ADR-049 edge-legality;
    ``rac-cross-artifact-enforcement`` REQ-004). Returns the canonical section
    names in :data:`RELATIONSHIP_SECTIONS` order so the finding is deterministic.
    """
    unsupported: list[str] = []
    for section in RELATIONSHIP_SECTIONS:
        if section in spec.optional:
            continue
        body = product.sections.get(section)
        if body and parse_references(body):
            unsupported.append(section)
    return unsupported


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
    index = _build_resolution_index(items)
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


def _build_identifier_index(
    items: list[tuple[str, Product, ArtifactSpec | None]],
) -> _IdentIndex:
    """Canonical-identifier index over *all* files (Unknown included).

    One entry per file — duplicate-identity detection runs over this index,
    so only the canonical identifier can collide (ADR-026).
    """
    index: _IdentIndex = {}
    for path, product, spec in items:
        ident = artifact_identifier(product, spec, path)
        index.setdefault(ident.casefold(), []).append((path, ident))
    return index


def _build_resolution_index(
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


def _resolve_references(
    items: list[tuple[str, Product, ArtifactSpec | None]],
    index: _IdentIndex,
) -> tuple[int, list[RelationshipIssue], set[str]]:
    """Resolve every explicit reference in ``items`` against ``index``.

    Returns ``(checked, issues, resolved_target_paths)`` where
    ``resolved_target_paths`` is the set of paths that appear as a *resolved*
    target of at least one uniquely-matched reference — used by
    ``summarize_relationships`` for orphan detection.
    """
    issues: list[RelationshipIssue] = []
    resolved_targets: set[str] = set()
    checked = 0

    for path, product, spec in items:
        if spec is None:
            continue
        for section, refs in extract_relationships_full(product, spec).items():
            for ref in refs:
                checked += 1
                targets = [p for p, _ in index.get(ref.casefold(), [])]
                if not targets:
                    code = ISSUE_TARGET_NOT_FOUND
                elif len(targets) > 1:
                    code = ISSUE_TARGET_AMBIGUOUS
                elif targets == [path]:
                    code = ISSUE_SELF_REFERENCE
                else:
                    resolved_targets.add(targets[0])
                    continue  # resolved uniquely to another artifact
                issues.append(
                    RelationshipIssue(code=code, source_path=path, relationship=section, target=ref)
                )

    return checked, issues, resolved_targets


def _acyclic_adjacency(
    items: list[tuple[str, Product, ArtifactSpec | None]],
    resolution_index: _IdentIndex,
    kind: str,
) -> dict[str, list[str]]:
    """``{source_path -> sorted unique target paths}`` for edge ``kind``.

    Only uniquely-resolved, non-self edges contribute (self/ambiguous/unresolved
    are owned by referential integrity), so the graph reflects real directed edges.
    """
    adjacency: dict[str, list[str]] = {}
    for path, product, spec in items:
        if spec is None:
            continue
        targets: set[str] = set()
        for ref in extract_relationships_full(product, spec).get(kind, []):
            resolved = [p for p, _ in resolution_index.get(ref.casefold(), [])]
            if len(resolved) == 1 and resolved[0] != path:
                targets.add(resolved[0])
        if targets:
            adjacency[path] = sorted(targets)
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
    items: list[tuple[str, Product, ArtifactSpec | None]],
    resolution_index: _IdentIndex,
) -> list[RelationshipIssue]:
    """One ``relationship-cycle`` per cyclic component of each acyclic edge kind."""
    issues: list[RelationshipIssue] = []
    for kind in sorted(name for name, edge in REGISTRY.items() if edge.acyclic):
        adjacency = _acyclic_adjacency(items, resolution_index, kind)
        for component in _cyclic_components(adjacency):
            issues.append(
                RelationshipIssue(code=ISSUE_RELATIONSHIP_CYCLE, relationship=kind, paths=component)
            )
    return issues


def _validate(
    directory: str,
    items: list[tuple[str, Product, ArtifactSpec | None]],
    recursive: bool,
) -> RelationshipValidation:
    index = _build_identifier_index(items)

    issues: list[RelationshipIssue] = []

    # Duplicate identifiers (repo-level), emitted first, sorted by identifier.
    duplicates: list[tuple[str, list[str]]] = []
    for entries in index.values():
        if len(entries) > 1:
            display = min(entries, key=lambda e: e[0])[1]  # first path's casing
            duplicates.append((display, sorted(p for p, _ in entries)))
    for display, dup_paths in sorted(duplicates, key=lambda d: d[0].casefold()):
        issues.append(
            RelationshipIssue(code=ISSUE_DUPLICATE_IDENTIFIER, identifier=display, paths=dup_paths)
        )

    # Edge-legality (v0.14.0, ADR-049): report relationship sections an artifact's
    # type does not declare instead of silently dropping them. Deterministic —
    # items in sorted-path order, sections in canonical RELATIONSHIP_SECTIONS order.
    for path, product, spec in items:
        if spec is None:
            continue
        for section in unsupported_relationship_sections(product, spec):
            issues.append(
                RelationshipIssue(
                    code=ISSUE_EDGE_UNSUPPORTED, source_path=path, relationship=_snake(section)
                )
            )

    resolution_index = _build_resolution_index(items)
    by_path = {path: (product, spec) for path, product, spec in items}

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
    for path, product, spec in items:
        if spec is None:
            continue
        for section, refs in extract_relationships_full(product, spec).items():
            edge = edge_spec(section)
            if edge is None:
                continue
            for ref in refs:
                target = _resolved(ref, path)
                if target is None:
                    continue
                _, target_spec = by_path[target]
                if target_spec is None:
                    continue  # untyped document (ADR-010) — not a range violation
                if target_spec.name not in edge.range:
                    issues.append(
                        RelationshipIssue(
                            code=ISSUE_TARGET_TYPE_MISMATCH,
                            source_path=path,
                            relationship=section,
                            target=ref,
                        )
                    )

    # Status-consistency (v0.14.1, generalised in v0.16.0/ADR-051): a live artifact
    # must not reference a retired target, except via an edge that permits it
    # (``supersedes``, ``forbids_target_status=False``). Reads the resolved
    # target's status from the materialised items — no second walk.
    for path, product, spec in items:
        if spec is None or _is_retired_artifact(product, spec):
            continue  # unknown file, or a retired source (historical chains exempt)
        for section, refs in extract_relationships_full(product, spec).items():
            edge = edge_spec(section)
            if edge is None or not edge.forbids_target_status:
                continue  # supersedes legitimately points at the retired one
            for ref in refs:
                target = _resolved(ref, path)
                if target is None:
                    continue
                target_product, target_spec = by_path[target]
                if _is_retired_artifact(target_product, target_spec):
                    issues.append(
                        RelationshipIssue(
                            code=ISSUE_TARGET_SUPERSEDED,
                            source_path=path,
                            relationship=section,
                            target=ref,
                        )
                    )

    # Acyclicity (v0.16.0, ADR-055): a cycle in a directional, acyclic edge kind
    # (today ``supersedes``) is illegal — an ordering/replacement edge must not
    # form a loop. Reported per strongly-connected component, deterministically.
    issues.extend(_cycle_issues(items, resolution_index))

    checked, ref_issues, _ = _resolve_references(items, resolution_index)
    issues.extend(ref_issues)

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
    directory: str, entries: list[CorpusEntry], recursive: bool = True
) -> RelationshipValidation:
    """Validate relationships in an already-walked corpus snapshot (v0.8.0).

    Same result as :func:`validate_relationships`; the snapshot lets one walk
    feed several analyses (repository model, future incremental refresh).
    """
    return _validate(directory, _entry_items(entries), recursive)


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


def summary_from_corpus(entries: list[CorpusEntry]) -> RelationshipSummary:
    """Aggregate relationship health for an already-walked snapshot (v0.8.0).

    Same result as :func:`summarize_relationships`; the snapshot lets one walk
    feed several analyses (repository model, future incremental refresh).
    """
    return _summarize(_entry_items(entries))


def _summarize(items: list[tuple[str, Product, ArtifactSpec | None]]) -> RelationshipSummary:
    if not items:
        return RelationshipSummary(total=0, valid=0, broken=0, orphaned=0, coverage=1.0)

    index = _build_resolution_index(items)
    checked, ref_issues, resolved_targets = _resolve_references(items, index)

    broken = len(ref_issues)
    valid = checked - broken

    # Orphan = known (spec is not None) artifact whose path never appears as a
    # resolved target of another artifact's reference.
    all_known_paths = {path for path, _, spec in items if spec is not None}
    orphaned = len(all_known_paths - resolved_targets)

    # Coverage = fraction of known artifacts that declare >=1 outbound relationship.
    artifacts_with_rels = sum(
        1
        for path, product, spec in items
        if spec is not None and extract_relationships_full(product, spec)
    )
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


def relationships_from_corpus(entries: list[CorpusEntry]) -> list[Relationship]:
    """Every declared reference in a corpus snapshot as :class:`Relationship`.

    Ordering is deterministic: source artifacts in snapshot (sorted path)
    order, sections in each artifact's own schema order, references in
    declaration order — matching ``_resolve_references``.
    """
    items = _entry_items(entries)
    index = _build_resolution_index(items)
    relationships: list[Relationship] = []
    for path, product, spec in items:
        if spec is None:
            continue
        for section, refs in extract_relationships_full(product, spec).items():
            for ref in refs:
                targets = [p for p, _ in index.get(ref.casefold(), [])]
                resolved: str | None = None
                issue: str | None = None
                if not targets:
                    issue = ISSUE_TARGET_NOT_FOUND
                elif len(targets) > 1:
                    issue = ISSUE_TARGET_AMBIGUOUS
                elif targets == [path]:
                    issue = ISSUE_SELF_REFERENCE
                else:
                    resolved = targets[0]
                relationships.append(
                    Relationship(
                        source_path=path,
                        relationship=section,
                        target=ref,
                        resolved_path=resolved,
                        issue=issue,
                    )
                )
    return relationships


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
