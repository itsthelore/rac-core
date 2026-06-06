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
from pathlib import Path

from .artifacts import ArtifactSpec, spec_for
from .classification import classify
from .fs import find_markdown_files
from .models import Product
from .parser import parse_file

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


def extract_relationships_full(
    product: Product, spec: ArtifactSpec
) -> dict[str, list[str]]:
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


def _artifact_relationships(path: str) -> tuple[str, dict[str, list[str]]]:
    """Classify the file at ``path`` and extract its full relationships.

    Returns ``(type, relationships)``. Unknown artifacts (no spec) yield an empty
    relationship dict — extraction stays spec-driven (REQ-007), no generic scan.
    """
    product = parse_file(path)
    artifact_type = classify(product).type
    spec = spec_for(artifact_type)
    relationships = extract_relationships_full(product, spec) if spec else {}
    return artifact_type, relationships


def _build_report(
    directory: str, paths: list, recursive: bool
) -> RelationshipReport:
    """Assemble a :class:`RelationshipReport` from ``paths`` (already ordered)."""
    artifacts: list[ArtifactRelationships] = []
    for path in paths:
        artifact_type, relationships = _artifact_relationships(str(path))
        if relationships:
            artifacts.append(
                ArtifactRelationships(
                    path=str(path), type=artifact_type, relationships=relationships
                )
            )
    return RelationshipReport(
        directory=directory,
        recursive=recursive,
        total_files=len(paths),
        artifacts=artifacts,
    )


def build_relationship_report(
    directory: str, recursive: bool = True
) -> RelationshipReport:
    """Inspect explicit relationships across a directory of Markdown files."""
    paths = find_markdown_files(directory, recursive=recursive)
    return _build_report(directory, paths, recursive)


def build_relationship_report_file(path: str) -> RelationshipReport:
    """Inspect relationships in a single file (REQ-009).

    Same model as a directory report, with one file and ``recursive=False``.
    """
    return _build_report(path, [path], recursive=False)


# --- Relationship validation (v0.7.2) ----------------------------------------
#
# `rac relationships <path> --validate` resolves every explicit reference against
# the identifiers of artifacts discovered in the repository, reporting missing,
# ambiguous, and self-referencing targets plus duplicate identifiers. Read-only
# and deterministic; no resolution heuristics, inference, or graphs (ADR-016).

# A recognized leading ID prefix in a filename stem: <letters>-<digits>, e.g.
# "adr-004" from "adr-004-parser-strategy". Case-insensitive at comparison time.
_ID_PREFIX_RE = re.compile(r"^[A-Za-z]+-\d+")

# The universal explicit-identifier section (normalized heading).
_ID_SECTION = "id"

# Stable issue codes (part of the JSON contract).
ISSUE_DUPLICATE_IDENTIFIER = "duplicate-artifact-identifier"
ISSUE_TARGET_NOT_FOUND = "relationship-target-not-found"
ISSUE_TARGET_AMBIGUOUS = "relationship-target-ambiguous"
ISSUE_SELF_REFERENCE = "relationship-self-reference"


def _first_value(body: str | None) -> str:
    """First non-empty line of a section body, leading list marker stripped."""
    if not body:
        return ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return _LIST_MARKER_RE.sub("", stripped, count=1).strip()
    return ""


def artifact_identifier(
    product: Product, spec: ArtifactSpec | None, path: str
) -> str:
    """The deterministic identifier for the artifact at ``path`` (v0.7.2).

    Precedence (first match wins); the discovered casing is preserved:

    1. an explicit ``## ID`` section value;
    2. the artifact type's declared ``spec.id_field`` section value;
    3. a recognized ``<letters>-<digits>`` prefix of the filename stem
       (e.g. ``adr-004`` from ``adr-004-parser-strategy.md``);
    4. the whole filename stem.

    The document title is never used, and inline ``[REQ-NNN]`` requirement lines
    are not identifiers — relationship targets are whole artifact files.
    """
    explicit = _first_value(product.sections.get(_ID_SECTION))
    if explicit:
        return explicit
    if spec is not None and spec.id_field:
        declared = _first_value(product.sections.get(spec.id_field))
        if declared:
            return declared
    stem = Path(path).stem
    prefix = _ID_PREFIX_RE.match(stem)
    return prefix.group(0) if prefix else stem


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


def _validate(
    directory: str,
    items: list[tuple[str, Product, ArtifactSpec | None]],
    recursive: bool,
) -> RelationshipValidation:
    # Identifier index over *all* files (Unknown included — they can be targets).
    index: dict[str, list[tuple[str, str]]] = {}
    for path, product, spec in items:
        ident = artifact_identifier(product, spec, path)
        index.setdefault(ident.casefold(), []).append((path, ident))

    issues: list[RelationshipIssue] = []

    # Duplicate identifiers (repo-level), emitted first, sorted by identifier.
    duplicates: list[tuple[str, list[str]]] = []
    for entries in index.values():
        if len(entries) > 1:
            display = min(entries, key=lambda e: e[0])[1]  # first path's casing
            duplicates.append((display, sorted(p for p, _ in entries)))
    for display, dup_paths in sorted(duplicates, key=lambda d: d[0].casefold()):
        issues.append(
            RelationshipIssue(
                code=ISSUE_DUPLICATE_IDENTIFIER, identifier=display, paths=dup_paths
            )
        )

    # Per-reference resolution from known artifacts only (spec-driven).
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
                    continue  # resolved uniquely to another artifact
                issues.append(
                    RelationshipIssue(
                        code=code, source_path=path, relationship=section, target=ref
                    )
                )

    return RelationshipValidation(
        directory=directory,
        recursive=recursive,
        relationships_checked=checked,
        issues=issues,
    )


def validate_relationships(
    directory: str, recursive: bool = True
) -> RelationshipValidation:
    """Validate explicit relationship references across a directory."""
    items = _parsed_items(find_markdown_files(directory, recursive=recursive))
    return _validate(directory, items, recursive)


def validate_relationships_file(path: str) -> RelationshipValidation:
    """Validate a single file (REQ-009).

    The identifier index contains only this file, so cross-file references will not
    resolve — repository validation needs a directory.
    """
    return _validate(path, _parsed_items([path]), recursive=False)
