"""Artifact inspection — classify a Markdown document and report its structure.

`rac inspect <file>` answers three questions about a single document: what kind
of artifact is it, how confident is the classifier, and which expected sections
are present or missing. Decisions additionally surface lightweight metadata
(status, category, supersedes) when they declare it. `rac inspect <dir>`
aggregates the classified type across a directory into counts.

Inspection is strictly observational: it never rewrites content and never
recommends changes (that is `rac improve`'s job). Classification is delegated to
the shared, AI-optional heuristic in :mod:`rac.core.classification`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.artifacts import ARTIFACT_SPECS, spec_for
from rac.core.classification import classify
from rac.core.corpus import walk_corpus
from rac.core.markdown import parse, parse_file
from rac.core.models import Product

from .relationships import extract_relationships


@dataclass
class InspectionResult:
    """Typed single-file inspection result (ADR-003).

    Section names are held normalized (e.g. ``"success metrics"``) and the
    renderers format them. ``to_dict`` is the JSON contract: decision metadata
    and the relationships block are additive, appearing only when populated so
    that documents without them serialize exactly as before those fields existed.
    """

    type: str  # an artifact name, or "unknown"
    confidence: float  # 0.0 - 1.0, already rounded to 2dp by the classifier
    present_sections: list[str]
    missing_sections: list[str]
    # Decision metadata — set only for decisions that declare these sections.
    status: str | None = None
    category: str | None = None
    # ``supersedes`` is a relationship section but stays a top-level scalar for
    # backwards compatibility (v0.4.2 / ADR-007) — the documented exception to
    # the v0.7.0 relationships model.
    supersedes: str | None = None
    # Cross-artifact relationship metadata (v0.7.0): {snake_section -> [refs]}.
    # The ``related_*`` sections only; never resolved or validated here.
    relationships: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "type": self.type,
            "confidence": self.confidence,
            "present_sections": [_snake(s) for s in self.present_sections],
            "missing_sections": [_snake(s) for s in self.missing_sections],
        }
        for key in ("status", "category", "supersedes"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.relationships:
            payload["relationships"] = self.relationships
        return payload


@dataclass
class FileInspection:
    """One file's entry inside a directory inspection — path/type/confidence only."""

    path: str
    type: str
    confidence: float


@dataclass
class DirectoryInspection:
    """Aggregated inspection across a directory of Markdown files."""

    directory: str
    recursive: bool
    files: list[FileInspection]

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def counts(self) -> dict[str, int]:
        # Known types first in ARTIFACT_SPECS order, then unknown, so the tally is
        # stable regardless of which types the directory happens to hold.
        counts = {spec.name: 0 for spec in ARTIFACT_SPECS}
        counts["unknown"] = 0
        for f in self.files:
            counts[f.type] = counts.get(f.type, 0) + 1
        return counts

    @property
    def unknown_count(self) -> int:
        return self.counts.get("unknown", 0)


def _snake(section: str) -> str:
    return section.replace(" ", "_")


def _first_line(body: str) -> str:
    """First non-empty line of a section body — used for single-value metadata."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def canonical_value(raw: str, allowed: tuple[str, ...]) -> str:
    """Return the canonical spelling of ``raw`` drawn from ``allowed``.

    The first non-empty line of ``raw`` is matched against ``allowed`` case-
    insensitively. An unrecognized value is returned stripped rather than dropped,
    leaving it for validation to flag. Shared with ``export`` and ``stats``.
    """
    candidate = _first_line(raw)
    for value in allowed:
        if value.casefold() == candidate.casefold():
            return value
    return candidate


def _attach_decision_metadata(result: InspectionResult, product: Product) -> None:
    """Populate a decision's status/category/supersedes from its sections."""
    spec = spec_for("decision")
    if spec is None:  # pragma: no cover - the decision spec always exists
        return
    for field_name, allowed in spec.metadata.items():
        body = product.sections.get(field_name)
        if body:
            setattr(result, field_name, canonical_value(body, allowed))
    supersedes = product.sections.get("supersedes")
    if supersedes:
        # Metadata only (REQ-003): normalize the value, do not resolve the target.
        result.supersedes = _first_line(supersedes)


def build_inspection(product: Product) -> InspectionResult:
    """Classify ``product`` and attach decision metadata and relationships."""
    c = classify(product)
    result = InspectionResult(
        type=c.type,
        confidence=c.confidence,
        present_sections=c.present_sections,
        missing_sections=c.missing_sections,
    )
    if c.type == "decision":
        _attach_decision_metadata(result, product)
    # Relationship metadata is spec-driven, so it applies to any recognized type;
    # unknown has no spec and therefore no relationships.
    spec = spec_for(c.type)
    if spec is not None:
        result.relationships = extract_relationships(product, spec)
    return result


def inspect_text(text: str) -> InspectionResult:
    return build_inspection(parse(text))


def inspect_file(path: str) -> InspectionResult:
    return build_inspection(parse_file(path))


def inspect_directory(directory: str, recursive: bool = True) -> DirectoryInspection:
    """Inspect every Markdown file under ``directory`` and aggregate the types.

    The corpus walk classifies each file once; the directory view reads that
    result rather than re-running the classifier.
    """
    files = [
        FileInspection(
            path=str(entry.path),
            type=entry.classification.type,
            confidence=entry.classification.confidence,
        )
        for entry in walk_corpus(directory, recursive=recursive)
    ]
    return DirectoryInspection(directory=directory, recursive=recursive, files=files)
