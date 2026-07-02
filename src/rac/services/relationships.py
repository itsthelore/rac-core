"""Cross-artifact relationships: extraction, validation, graph, neighbourhood.

Relationships are explicit Markdown sections (``## Related Decisions``,
``## Supersedes``, ``## Related Tickets``, ...) whose body lines reference other
artifacts (ADR-016). This module is the single home for turning those sections
into edges, and it layers four responsibilities on one primitive — section text
to reference strings:

1. **Extraction** — the parse of a section body into references, plus the
   spec-driven views ``rac inspect`` and ``rac stats`` consume.
2. **Repository report** — ``rac relationships`` (what edges exist, counted).
3. **Validation** — ``rac relationships --validate`` (which edges are broken,
   illegal, or graph-inconsistent), the SARIF/gate severity map, and the
   pre-edit-hook seam.
4. **Graph objects** — the navigable :class:`Relationship` list plus the
   ``get_related`` outgoing/incoming/neighbourhood views.

Everything here is pure and deterministic (ADR-002 / ADR-016): it parses corpus
bytes and never resolves by inference, only against declared identifiers. The
raw reference text stays the source of truth; resolution reuses the one identity
model (ADR-026) so a reference resolves in the graph exactly when validation
reports no integrity issue for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

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

# --- Vocabulary --------------------------------------------------------------
#
# The relationship-section vocabulary is a single source of truth mirrored by
# core.relationship_types.REGISTRY and by each type's ArtifactSpec.optional
# (test_schema_agreement pins the three in lockstep).

# The per-artifact-type ``related <type>s`` sections — exactly one per artifact
# type, so every peer type can be referenced. These populate the ``relationships``
# dict in ``rac inspect``.
RELATED_SECTIONS: tuple[str, ...] = (
    "related requirements",
    "related decisions",
    "related roadmaps",
    "related prompts",
    "related designs",
)

# External-reference sections (ADR-087 / ADR-096): the target is an external
# identifier — a ticket key or a file/trace path — not a peer artifact. They are
# extracted and graphed like the rest but format-linted, never resolved, so they
# are kept separate from RELATED_SECTIONS (the per-type vocabulary).
EXTERNAL_SECTIONS: tuple[str, ...] = ("related tickets", "verified by")

# The full vocabulary and its canonical ordering: the per-type ``related *``
# sections, then ``supersedes``, then the external sections. This module owns the
# order; ``stats`` and ``rac relationships`` render by-type output in it.
# ``supersedes`` is the one section absent from the ``rac inspect`` relationships
# dict — there it stays a top-level scalar for backwards compatibility (ADR-007).
RELATIONSHIP_SECTIONS: tuple[str, ...] = RELATED_SECTIONS + ("supersedes",) + EXTERNAL_SECTIONS

# A *well-formed* leading Markdown list marker (``-``, ``*``, ``+``, or ``N.``
# then whitespace). Only these are stripped; any other leading text is kept
# verbatim, so ``REQ-001 (blocked)``, ``../decisions/adr-004.md``, and
# ``-no-space`` all survive intact — the whole line is the reference (ADR-016).
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+\.)\s+")


def _snake(section: str) -> str:
    return section.replace(" ", "_")


# --- Extraction primitives ---------------------------------------------------


def parse_references(body: str) -> list[str]:
    """Split a relationship section body into individual reference strings.

    One reference per non-empty line. A well-formed leading list marker is
    stripped; otherwise the line is kept verbatim. No ID parsing and no
    resolution — the line text *is* the reference (ADR-016).
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

    Returns ``{snake_section -> [references]}`` in the artifact's own
    ``spec.optional`` order, keeping only sections present with at least one
    parsed reference. The single core behind the two public extractors.
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
    (ADR-007). External sections (``related tickets``, ``verified by``) are
    included. Order follows ``spec.optional``.
    """
    return _collect(product, spec, RELATED_SECTIONS + EXTERNAL_SECTIONS)


def extract_relationships_full(product: Product, spec: ArtifactSpec) -> dict[str, list[str]]:
    """Cross-artifact references for ``rac relationships`` — *including* Supersedes.

    The repository-level command treats Supersedes as a first-class relationship
    (REQ-003), so it is reported alongside the ``related_*`` and external
    sections. Order follows ``spec.optional``.
    """
    return _collect(product, spec, RELATIONSHIP_SECTIONS)


def present_relationship_sections(product: Product, spec: ArtifactSpec) -> list[str]:
    """Relationship sections ``product`` declares *and* populates.

    Spec-driven and inclusive of ``supersedes``: a section counts only when
    present with at least one parsed reference (REQ-011). Returns the normalized
    (space-form) section names in ``spec.optional`` order, for ``rac stats``
    declared-presence counts.
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
    reference whose name is *not* in this type's ``spec.optional`` produces no
    edge and must not be silently dropped (ADR-049 edge-legality). Returns the
    canonical (space-form) section names in :data:`RELATIONSHIP_SECTIONS` order,
    so the finding is deterministic.
    """
    unsupported: list[str] = []
    for section in RELATIONSHIP_SECTIONS:
        if section in spec.optional:
            continue
        body = product.sections.get(section)
        if body and parse_references(body):
            unsupported.append(section)
    return unsupported


# --- Materialised corpus items -----------------------------------------------
#
# Every analysis below works over ``(path, product, spec)`` triples in the
# corpus's sorted-path order (``walk_corpus`` is deterministic). ``spec is None``
# marks an Unknown document (ADR-010): it is still a valid *target* but declares
# no relationships of its own.

_Item = tuple[str, Product, ArtifactSpec | None]


def _parsed_items(paths: list[str]) -> list[_Item]:
    """Parse and classify each path into ``(path, product, spec)``."""
    items: list[_Item] = []
    for path in paths:
        product = parse_file(str(path))
        spec = spec_for(classify(product).type)
        items.append((str(path), product, spec))
    return items


def _corpus_items(directory: str, recursive: bool) -> list[_Item]:
    """Every document under ``directory`` as ``(path, product, spec)`` (one walk)."""
    return _entry_items(list(walk_corpus(directory, recursive=recursive)))


def _entry_items(entries: list[CorpusEntry]) -> list[_Item]:
    """An already-walked corpus snapshot as ``(path, product, spec)`` items."""
    return [(str(entry.path), entry.product, spec_for(entry.artifact_type)) for entry in entries]


# --- Identity indexes --------------------------------------------------------
#
# Two indexes over the same items, both keyed by casefolded identifier to
# ``[(path, display_ident), ...]``:
#   * the *identifier* index — canonical id only, one entry per file, so only a
#     canonical identifier can collide (duplicate detection, ADR-026);
#   * the *resolution* index — canonical id plus every legacy alias, so a
#     human-readable reference (``ADR-015``) keeps resolving after an artifact
#     adopts a canonical frontmatter id (migration support).

_IdentIndex = dict[str, list[tuple[str, str]]]


def _build_resolution_index(items: list[_Item]) -> _IdentIndex:
    """Reference-resolution index: canonical identifiers plus legacy aliases.

    Kept as a standalone helper because ``rac rename`` and the graph builders
    resolve references through the same alias index (one identity model).
    """
    index: _IdentIndex = {}
    for path, product, spec in items:
        for ident in artifact_identifiers(product, spec, path):
            index.setdefault(ident.casefold(), []).append((path, ident))
    return index


def _build_indexes(items: list[_Item]) -> tuple[_IdentIndex, _IdentIndex]:
    """The identifier and resolution indexes in a single pass over ``items``.

    Duplicate detection reads the identifier index (canonical only); reference
    resolution reads the resolution index (canonical + aliases). Building both in
    one walk keeps ``_validate`` to a single pass while preserving each index's
    exact contents.
    """
    identifier_index: _IdentIndex = {}
    resolution_index: _IdentIndex = {}
    for path, product, spec in items:
        canonical = artifact_identifier(product, spec, path)
        identifier_index.setdefault(canonical.casefold(), []).append((path, canonical))
        for ident in artifact_identifiers(product, spec, path):
            resolution_index.setdefault(ident.casefold(), []).append((path, ident))
    return identifier_index, resolution_index


def _unique_target(index: _IdentIndex, ref: str, source_path: str) -> str | None:
    """The path ``ref`` resolves to uniquely and non-self, or None.

    Unresolved, ambiguous, and self references all return None — the graph
    checks reason only about real directed edges; referential integrity owns the
    rest.
    """
    targets = [p for p, _ in index.get(ref.casefold(), [])]
    if len(targets) == 1 and targets[0] != source_path:
        return targets[0]
    return None


def _classify_reference(
    index: _IdentIndex, ref: str, source_path: str
) -> tuple[str | None, str | None]:
    """Resolve ``ref`` to ``(resolved_path, issue_code)`` — exactly one is set.

    A unique non-self match yields ``(path, None)``; every other outcome yields
    ``(None, code)`` with the stable integrity code. The one place the
    not-found / ambiguous / self-reference distinction is drawn.
    """
    targets = [p for p, _ in index.get(ref.casefold(), [])]
    if not targets:
        return None, ISSUE_TARGET_NOT_FOUND
    if len(targets) > 1:
        return None, ISSUE_TARGET_AMBIGUOUS
    if targets[0] == source_path:
        return None, ISSUE_SELF_REFERENCE
    return targets[0], None


# --- Repository-level relationship inspection (`rac relationships`) -----------
#
# Discovers the explicit relationships declared across a tree (ADR-015):
# read-only and deterministic — it reports the references that exist but never
# resolves, validates, or graphs them.


@dataclass
class ArtifactRelationships:
    """One artifact's relationships in a repository report.

    ``relationships`` includes Supersedes (unlike ``rac inspect``) and is keyed
    by snake_case section name in the artifact's own ``spec.optional`` order.
    """

    path: str
    type: str
    relationships: dict[str, list[str]]


@dataclass
class RelationshipReport:
    """Repository-level relationship inspection result (ADR-003).

    ``total_files`` counts every Markdown file considered — including files with
    no relationships and Unknown artifacts. ``artifacts`` lists only those with
    at least one relationship. Counts are *reference* counts (each declared
    target is one relationship), aggregated by type in canonical
    :data:`RELATIONSHIP_SECTIONS` order.
    """

    directory: str
    recursive: bool
    total_files: int
    artifacts: list[ArtifactRelationships] = field(default_factory=list)
    # Human-friendly resolution: {casefold(ref) -> "Title (type · canonical_id)"}
    # for every reference that resolves uniquely. Presentation context only — the
    # stored reference stays the source of truth, and JSON never includes labels
    # (ADR-007: resolved fields would be an additive, explicitly versioned change).
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
    artifacts: list[ArtifactRelationships], items: list[_Item]
) -> dict[str, str]:
    """Human-friendly labels for every uniquely-resolved reference.

    Resolution runs over the same alias index ``--validate`` uses (one identity
    model); ambiguous and unknown references get no label — ``--validate`` is the
    place that reports them.
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
                paths = {p for p, _ in index.get(key, [])}
                if len(paths) != 1:
                    continue
                canonical, spec, title = info[next(iter(paths))]
                type_name = spec.name if spec else "unknown"
                labels[key] = f"{title or canonical} ({type_name} · {canonical})"
    return labels


def _build_report(directory: str, items: list[_Item], recursive: bool) -> RelationshipReport:
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
    """Inspect relationships in an already-walked corpus snapshot.

    Same result as :func:`build_relationship_report`; the snapshot lets one walk
    feed several analyses (repository model, incremental refresh).
    """
    return _build_report(directory, _entry_items(entries), recursive)


def build_relationship_report_file(path: str) -> RelationshipReport:
    """Inspect relationships in a single file (REQ-009), ``recursive=False``."""
    return _build_report(path, _parsed_items([path]), recursive=False)


# --- Relationship validation (`rac relationships --validate`) -----------------
#
# Resolves every explicit reference against the identifiers of artifacts in the
# repository and reports missing / ambiguous / self / superseded targets, illegal
# and out-of-range edges, cycles, and duplicate identifiers — deterministically,
# read-only, no inference (ADR-016).

# Stable issue codes (part of the JSON contract).
ISSUE_DUPLICATE_IDENTIFIER = "duplicate-artifact-identifier"
ISSUE_TARGET_NOT_FOUND = "relationship-target-not-found"
ISSUE_TARGET_AMBIGUOUS = "relationship-target-ambiguous"
ISSUE_SELF_REFERENCE = "relationship-self-reference"
# Edge-legality (ADR-049): a relationship section the artifact's type does not
# declare produces no edge and is reported, not silently dropped.
ISSUE_EDGE_UNSUPPORTED = "relationship-edge-unsupported"
# Status-consistency (ADR-049, generalised under ADR-051): a live artifact
# references a target the team has retired, other than via ``supersedes``.
ISSUE_TARGET_SUPERSEDED = "relationship-target-superseded"
# Range (ADR-055): a resolved target whose type is not in the edge's range
# (e.g. a ``## Related Decisions`` reference that resolves to a requirement).
ISSUE_TARGET_TYPE_MISMATCH = "relationship-target-type-mismatch"
# Acyclicity (ADR-055): a cycle in a directional, acyclic edge kind (``supersedes``).
ISSUE_RELATIONSHIP_CYCLE = "relationship-cycle"

# Canonical intrinsic severity per finding. Referential-integrity and
# graph-shape breakages are errors; advisory consistency findings (self-reference,
# unsupported edge, retired-target reference) are warnings. Single source of
# truth for the annotation severity — the SARIF renderer and the ``rac gate``
# enforcement layer both read it, so they cannot disagree. It is the *intrinsic*
# severity only: relationship findings still fail ``--validate`` (and gate, by
# default) regardless of severity; the enforcement class is decided separately
# under the corpus policy (ADR-049).
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
    set, so every type's retired states are honoured (and a live terminal status
    like an Achieved roadmap, ADR-061, is not retired). Matches case-insensitively
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

    ``to_dict`` emits only the keys relevant to ``code`` (ADR-007): a duplicate
    carries ``identifier``/``paths``, an unsupported edge carries
    ``source_path``/``relationship``, a cycle carries ``relationship``/``paths``,
    and every reference finding carries ``source_path``/``relationship``/``target``.
    """

    code: str
    source_path: str | None = None
    relationship: str | None = None
    target: str | None = None
    identifier: str | None = None
    paths: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.code == ISSUE_DUPLICATE_IDENTIFIER:
            return {"identifier": self.identifier, "paths": self.paths, "code": self.code}
        if self.code == ISSUE_EDGE_UNSUPPORTED:
            return {
                "source_path": self.source_path,
                "relationship": self.relationship,
                "code": self.code,
            }
        if self.code == ISSUE_RELATIONSHIP_CYCLE:
            return {"relationship": self.relationship, "paths": self.paths, "code": self.code}
        return {
            "source_path": self.source_path,
            "relationship": self.relationship,
            "target": self.target,
            "code": self.code,
        }


@dataclass
class RelationshipValidation:
    """Repository-level relationship validation result (REQ-006).

    ``relationships_checked`` counts every reference examined (external edges are
    not checked). ``validation_issues`` counts *all* findings, since each makes
    the declared relationship metadata unreliable.
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


def _extract_by_path(items: list[_Item]) -> dict[str, dict[str, list[str]]]:
    """Extract each typed item's full relationships once, keyed by path.

    The graph and integrity passes below each reason over the same extraction;
    computing it once (rather than re-parsing per pass) keeps large-corpus
    validation cheap without changing any result.
    """
    return {
        path: extract_relationships_full(product, spec)
        for path, product, spec in items
        if spec is not None
    }


def _resolve_references(
    items: list[_Item],
    index: _IdentIndex,
    extracted: dict[str, dict[str, list[str]]],
) -> tuple[int, list[RelationshipIssue], set[str]]:
    """Resolve every explicit (non-external) reference against ``index``.

    Returns ``(checked, issues, resolved_target_paths)`` where
    ``resolved_target_paths`` is every path that is the *resolved* target of at
    least one uniquely-matched reference — used by ``summarize_relationships`` for
    orphan detection.
    """
    issues: list[RelationshipIssue] = []
    resolved_targets: set[str] = set()
    checked = 0

    for path, _product, spec in items:
        if spec is None:
            continue
        for section, refs in extracted[path].items():
            edge = edge_spec(section)
            if edge is not None and edge.external:
                continue  # external refs (ADR-087/096) are format-linted, not resolved
            for ref in refs:
                checked += 1
                resolved, code = _classify_reference(index, ref, path)
                if resolved is not None:
                    resolved_targets.add(resolved)
                    continue
                # ``resolved is None`` means ``_classify_reference`` set a code.
                if code is not None:
                    issues.append(
                        RelationshipIssue(
                            code=code, source_path=path, relationship=section, target=ref
                        )
                    )

    return checked, issues, resolved_targets


def _acyclic_adjacency(
    items: list[_Item],
    resolution_index: _IdentIndex,
    kind: str,
    extracted: dict[str, dict[str, list[str]]],
) -> dict[str, list[str]]:
    """``{source_path -> sorted unique target paths}`` for edge ``kind``.

    Only uniquely-resolved, non-self edges contribute (self/ambiguous/unresolved
    are owned by referential integrity), so the graph reflects real directed edges.
    """
    adjacency: dict[str, list[str]] = {}
    for path, _product, spec in items:
        if spec is None:
            continue
        targets: set[str] = set()
        for ref in extracted[path].get(kind, []):
            resolved = _unique_target(resolution_index, ref, path)
            if resolved is not None:
                targets.add(resolved)
        if targets:
            adjacency[path] = sorted(targets)
    return adjacency


def _cyclic_components(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Strongly-connected components of size > 1, each a sorted node list.

    A cycle exists exactly within an SCC larger than one node (self-loops are
    excluded upstream). Deterministic: Tarjan with sorted node/neighbour
    visitation, and the components returned sorted by first node.
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
    items: list[_Item],
    resolution_index: _IdentIndex,
    extracted: dict[str, dict[str, list[str]]],
) -> list[RelationshipIssue]:
    """One ``relationship-cycle`` per cyclic component of each acyclic edge kind."""
    issues: list[RelationshipIssue] = []
    for kind in sorted(name for name, edge in REGISTRY.items() if edge.acyclic):
        adjacency = _acyclic_adjacency(items, resolution_index, kind, extracted)
        for component in _cyclic_components(adjacency):
            issues.append(
                RelationshipIssue(code=ISSUE_RELATIONSHIP_CYCLE, relationship=kind, paths=component)
            )
    return issues


def _validate(directory: str, items: list[_Item], recursive: bool) -> RelationshipValidation:
    """The whole validation pass, with test-visible issue ordering.

    Findings are appended in fixed order so the report is deterministic:
    (1) duplicate identifiers, (2) unsupported edges, (3) range/type mismatch,
    (4) retired-target references, (5) cycles, (6) per-reference integrity.
    """
    identifier_index, resolution_index = _build_indexes(items)
    extracted = _extract_by_path(items)
    by_path = {path: (product, spec) for path, product, spec in items}

    issues: list[RelationshipIssue] = []

    # (1) Duplicate identifiers (repo-level), sorted by identifier casefold; each
    # entry's paths sorted, and the display casing taken from the min-path file.
    duplicates: list[tuple[str, list[str]]] = []
    for entries in identifier_index.values():
        if len(entries) > 1:
            display = min(entries, key=lambda e: e[0])[1]
            duplicates.append((display, sorted(p for p, _ in entries)))
    for display, dup_paths in sorted(duplicates, key=lambda d: d[0].casefold()):
        issues.append(
            RelationshipIssue(code=ISSUE_DUPLICATE_IDENTIFIER, identifier=display, paths=dup_paths)
        )

    # (2) Edge-legality (ADR-049): report relationship sections an artifact's type
    # does not declare instead of dropping them. Items are already in sorted-path
    # order; sections come back in canonical RELATIONSHIP_SECTIONS order.
    for path, product, spec in items:
        if spec is None:
            continue
        for section in unsupported_relationship_sections(product, spec):
            issues.append(
                RelationshipIssue(
                    code=ISSUE_EDGE_UNSUPPORTED, source_path=path, relationship=_snake(section)
                )
            )

    # (3) Range (ADR-055): a resolved target whose type is not in the edge's
    # declared range is an illegal edge. External edges carry no artifact range;
    # an untyped target (ADR-010) is not a range violation.
    for path, _product, spec in items:
        if spec is None:
            continue
        for section, refs in extracted[path].items():
            edge = edge_spec(section)
            if edge is None or edge.external:
                continue
            for ref in refs:
                target = _unique_target(resolution_index, ref, path)
                if target is None:
                    continue
                _, target_spec = by_path[target]
                if target_spec is None:
                    continue
                if target_spec.name not in edge.range:
                    issues.append(
                        RelationshipIssue(
                            code=ISSUE_TARGET_TYPE_MISMATCH,
                            source_path=path,
                            relationship=section,
                            target=ref,
                        )
                    )

    # (4) Status-consistency (ADR-049/ADR-051): a live artifact must not reference
    # a retired target, except through an edge that permits it (``supersedes`` /
    # external, ``forbids_target_status=False``). A retired *source* is exempt —
    # its outbound references are a historical chain. Target status is read from
    # the materialised items, so there is no second walk.
    for path, product, spec in items:
        if spec is None or _is_retired_artifact(product, spec):
            continue
        for section, refs in extracted[path].items():
            edge = edge_spec(section)
            if edge is None or edge.external or not edge.forbids_target_status:
                continue
            for ref in refs:
                target = _unique_target(resolution_index, ref, path)
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

    # (5) Acyclicity (ADR-055): a cycle in a directional, acyclic edge kind
    # (today ``supersedes``), reported per strongly-connected component.
    issues.extend(_cycle_issues(items, resolution_index, extracted))

    # (6) Per-reference integrity: not-found / ambiguous / self-reference.
    checked, ref_issues, _ = _resolve_references(items, resolution_index, extracted)
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

    When a per-invocation ``cache`` is supplied the corpus is served through it,
    so artifacts parsed in an earlier phase of the same run are not reparsed
    (WS8); the result is byte-identical to the uncached walk.
    """
    if cache is not None:
        return validation_from_corpus(
            directory, cache.collect(directory, recursive=recursive), recursive
        )
    return _validate(directory, _corpus_items(directory, recursive), recursive)


def validation_from_corpus(
    directory: str, entries: list[CorpusEntry], recursive: bool = True
) -> RelationshipValidation:
    """Validate relationships in an already-walked corpus snapshot.

    Same result as :func:`validate_relationships`; the snapshot lets one walk
    feed several analyses.
    """
    return _validate(directory, _entry_items(entries), recursive)


def validate_relationships_file(path: str) -> RelationshipValidation:
    """Validate a single file (REQ-009).

    The identifier index contains only this file, so cross-file references will
    not resolve — repository validation needs a directory.
    """
    return _validate(path, _parsed_items([path]), recursive=False)


def validate_document_against_corpus(
    product: Product,
    source_path: str,
    directory: str,
    recursive: bool = True,
) -> RelationshipValidation:
    """Resolve one *proposed* document's outbound references against a live corpus.

    The seam the Claude Code ``PreToolUse`` pre-edit hook needs (ADR-067): a
    document held only in memory has its cross-artifact references resolved
    against the whole corpus index, so a reference to a retired or missing
    decision is reported even though the proposed document is not yet on disk.

    It reuses the repository resolution (:func:`_validate`) rather than
    reimplementing it (ADR-016 / ADR-063): the proposed document is folded into
    the corpus snapshot, and the findings are filtered to those anchored on the
    proposed document — pre-existing corpus issues are not the hook's concern,
    only the references this edit introduces.

    Editing an existing artifact, the proposed document usually shares its
    canonical identifier with the on-disk artifact. That on-disk counterpart is
    *excluded* from the snapshot (matched on canonical identifier, casefolded), so
    the proposed document stands in for it. That prevents two spurious findings —
    a duplicate identifier against the file being edited, and a self-reference
    when the document references its own identity — and validates the edit *as if*
    it replaces the committed version. A brand-new document matches nothing here
    and simply joins the corpus.
    """
    spec = spec_for(classify(product).type)
    proposed_ident = artifact_identifier(product, spec, source_path).casefold()
    kept = [
        item
        for item in _corpus_items(directory, recursive)
        if artifact_identifier(item[1], item[2], item[0]).casefold() != proposed_ident
    ]
    result = _validate(directory, [*kept, (source_path, product, spec)], recursive)
    own = [issue for issue in result.issues if issue.source_path == source_path]
    return RelationshipValidation(
        directory=directory,
        recursive=recursive,
        relationships_checked=result.relationships_checked,
        issues=own,
    )


# --- Repository relationship summary (`rac portfolio`) ------------------------


@dataclass
class RelationshipSummary:
    """Repository-level relationship health for ``PortfolioSummary``.

    ``total`` counts every checked reference; ``broken`` counts those that could
    not be uniquely resolved (not-found, ambiguous, or self-reference), with
    ``valid = total - broken``. ``orphaned`` counts known artifacts that are the
    target of no resolved reference. ``coverage`` is the fraction of known
    (non-unknown) artifacts declaring at least one outbound relationship — 1.0
    when there are no known artifacts. ``issues`` holds the per-reference findings
    (``broken == len(issues)``), so consumers turn them into attention items
    without a second walk.
    """

    total: int
    valid: int
    broken: int
    orphaned: int
    coverage: float  # 0.0 – 1.0
    issues: list[RelationshipIssue] = field(default_factory=list)


def summarize_relationships(directory: str, recursive: bool = True) -> RelationshipSummary:
    """Aggregate relationship health across a directory."""
    return _summarize(_corpus_items(directory, recursive))


def summary_from_corpus(entries: list[CorpusEntry]) -> RelationshipSummary:
    """Aggregate relationship health for an already-walked snapshot.

    Same result as :func:`summarize_relationships`.
    """
    return _summarize(_entry_items(entries))


def _summarize(items: list[_Item]) -> RelationshipSummary:
    if not items:
        return RelationshipSummary(total=0, valid=0, broken=0, orphaned=0, coverage=1.0)

    index = _build_resolution_index(items)
    extracted = _extract_by_path(items)
    checked, ref_issues, resolved_targets = _resolve_references(items, index, extracted)

    broken = len(ref_issues)
    known_paths = {path for path, _, spec in items if spec is not None}
    orphaned = len(known_paths - resolved_targets)
    with_rels = sum(1 for path in known_paths if extracted.get(path))
    coverage = with_rels / len(known_paths) if known_paths else 1.0

    return RelationshipSummary(
        total=checked,
        valid=checked - broken,
        broken=broken,
        orphaned=orphaned,
        coverage=round(coverage, 4),
        issues=ref_issues,
    )


# --- Relationship objects for the repository model ---------------------------
#
# The repository model needs every declared reference as one navigable object:
# where it points from, what it says, and where it resolves to. The raw text
# stays the source of truth (ADR-016); resolution reuses the ``--validate`` alias
# index, so a reference resolves here exactly when validation reports no issue.


@dataclass(frozen=True)
class Relationship:
    """One declared cross-artifact reference, with its resolution outcome.

    ``resolved_path`` is set only when the reference resolves uniquely to another
    artifact; otherwise ``issue`` carries the stable code (not-found / ambiguous /
    self-reference). An external edge (ADR-087/096) has neither: it resolves to no
    in-corpus artifact by design and is never "broken".
    """

    source_path: str
    relationship: str  # snake_case section name ("related_decisions", ...)
    target: str  # raw reference text (source of truth, ADR-016)
    resolved_path: str | None
    issue: str | None


def relationships_from_corpus(entries: list[CorpusEntry]) -> list[Relationship]:
    """Every declared reference in a corpus snapshot as a :class:`Relationship`.

    Deterministic order: source artifacts in snapshot (sorted-path) order,
    sections in each artifact's own schema order, references in declaration order.
    """
    items = _entry_items(entries)
    index = _build_resolution_index(items)
    relationships: list[Relationship] = []
    for path, product, spec in items:
        if spec is None:
            continue
        for section, refs in extract_relationships_full(product, spec).items():
            edge = edge_spec(section)
            external = edge is not None and edge.external
            for ref in refs:
                if external:
                    resolved, issue = None, None
                else:
                    resolved, issue = _classify_reference(index, ref, path)
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


def inbound_counts_from_corpus(entries: list[CorpusEntry]) -> dict[str, int]:
    """``{artifact path -> count of resolved edges pointing at it}``.

    The canonical inbound-degree signal: resolved, unique, non-self edges only —
    the same definition ``rac doctor``'s orphan/hub pass and the search graph
    boost consume, so they cannot drift. Artifacts with no inbound edge are absent
    (count 0).
    """
    counts: dict[str, int] = {}
    for rel in relationships_from_corpus(entries):
        if rel.resolved_path is not None:
            counts[rel.resolved_path] = counts.get(rel.resolved_path, 0) + 1
    return counts


# --- Bounded neighbourhood (get_related) -------------------------------------
#
# The references an artifact declares (outgoing) and the artifacts whose
# references resolve to it (incoming), plus the bounded multi-hop neighbourhood.
# This is the single source of truth for the ``get_related`` MCP tool and the
# grounding-eval benchmark that guards it (ADR-031, ADR-067): both consume these
# functions, so the scored surface cannot drift from the served one.

# Canonical relationship-section order (snake_case), for deterministic
# get_related ordering (REQ-006): edges sort by their section's position in the
# vocabulary, then ascending id.
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
    the snake_case section the reference sits in, and ``target`` — the reference
    text as stored (the edge that surfaced it).
    """

    id: str
    type: str
    title: str | None
    path: str
    section: str
    target: str


@dataclass(frozen=True)
class IncomingReferences:
    """Capped, ordered incoming edges plus the full pre-cap count (REQ-004/007).

    ``items`` is ordered by relationship type then ascending id and capped at the
    per-call edge limit; ``total`` is the full count so a caller can signal
    overflow via the truncation marker.
    """

    items: list[IncomingReference]
    total: int


@dataclass(frozen=True)
class OutgoingReferences:
    """Capped outgoing references grouped by section, plus the full count."""

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
    source of truth (ADR-016). Collection stops storing after ``limit`` edges so a
    pathological artifact cannot build an unbounded list (REQ-007), while the full
    count is still tallied. ``limit=None`` resolves to :data:`MAX_RELATED_EDGES`
    *read from the module global at call time* — the value tests monkeypatch.
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
    Collection stops storing after ``limit`` edges to bound work (REQ-007), while
    the full count is still tallied; the kept edges are ordered by relationship
    type then ascending id (REQ-006), so tail-truncation drops the lowest-priority
    edges deterministically (REQ-008). ``limit=None`` resolves to
    :data:`MAX_RELATED_EDGES` *read from the module global at call time*.
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
    """One artifact reachable from the origin, with its hop distance."""

    id: str
    type: str
    title: str | None
    path: str
    hops: int


@dataclass(frozen=True)
class Neighborhood:
    """The bounded multi-hop neighbourhood of an origin artifact.

    ``nodes`` excludes the origin and is ordered by ``(hops, type, id)`` so
    response-budget truncation drops the farthest, lowest-priority artifacts
    first. ``truncated`` is True when the work budget or a frontier cap stopped
    the walk from expanding fully.
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
    """Artifacts within ``depth`` hops of ``origin_path`` (breadth-first).

    A BFS over resolved relationship edges in both directions, bounded by the
    traversal caps (``rac-parser-traversal-robustness`` REQ-010): the requested
    ``depth`` is clamped to :data:`MAX_TRAVERSAL_DEPTH` (read from the module
    global at call time), a visited set makes the walk cycle-safe, and
    ``work_budget`` caps the edges examined across the whole walk.

    ``max_frontier`` is an *expansion* cap, not an output cap: every discovered
    neighbour is emitted into ``nodes`` and marked visited, but only the first
    ``max_frontier`` of a level are pushed onto the next frontier to expand.
    Hitting either the work budget or a frontier cap flips ``truncated``.

    Deterministic and offline (ADR-002): identical corpus bytes yield a
    byte-identical, ordered result.
    """
    depth = max(0, min(depth, MAX_TRAVERSAL_DEPTH))

    # Undirected adjacency over resolved edges; each entry carries the edge's
    # relationship rank so discovery order is deterministic (REQ-004).
    adjacency: dict[str, list[tuple[str, int]]] = {}
    for rel in relationships:
        if rel.resolved_path is None or rel.source_path == rel.resolved_path:
            continue
        rank = _relationship_order(rel.relationship)
        adjacency.setdefault(rel.source_path, []).append((rel.resolved_path, rank))
        adjacency.setdefault(rel.resolved_path, []).append((rel.source_path, rank))

    visited: set[str] = {origin_path}
    # (hops, rank, id, path): discovery order is keyed on rank/id/path first so
    # tail-truncation under the response budget is deterministic; the emitted
    # nodes are re-sorted by (hops, type, id) below.
    discovered: list[tuple[int, int, str, str]] = []
    frontier = [origin_path]
    work = 0
    truncated = False
    budget_exhausted = False

    for current_depth in range(1, depth + 1):
        next_frontier: list[str] = []
        for path in sorted(frontier):
            for neighbor_path, rank in sorted(set(adjacency.get(path, []))):
                work += 1
                if work > work_budget:
                    truncated = True
                    budget_exhausted = True
                    break
                if neighbor_path in visited:
                    continue
                visited.add(neighbor_path)
                identity = identity_by_path.get(neighbor_path)
                if identity is None:  # pragma: no cover — every edge target is indexed
                    continue
                discovered.append((current_depth, rank, identity[0], neighbor_path))
                # Emit the node regardless; only bound how many expand next hop.
                if len(next_frontier) >= max_frontier:
                    truncated = True
                else:
                    next_frontier.append(neighbor_path)
            if budget_exhausted:
                break
        frontier = next_frontier
        if not frontier:
            break

    discovered.sort()
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
