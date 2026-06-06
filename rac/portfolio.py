"""Repository intelligence summary — `rac portfolio` (v0.7.3).

``build_portfolio_summary`` walks a directory once, gathering:

- Artifact counts (by type + unknown)
- Validation (valid / invalid)
- Completeness (filled recommended slots / total recommended slots)
- Relationship health (from ``summarize_relationships``)
- Attention items (broken refs, invalid artifacts, missing recommended sections)
- Health score (weighted composite)

All analysis is deterministic and belongs to Core (ADR-015). The CLI renders
the result; it calculates nothing independently.

Health score formula (each sub-score ∈ [0, 1], 1.0 when denominator is 0):

    score = round(100 × (0.5·validity + 0.25·completeness + 0.25·rel_integrity))

where:
    validity         = valid_artifacts / total_artifacts
    completeness     = filled_recommended_slots / total_recommended_slots
    rel_integrity    = (total_refs − broken_refs) / total_refs
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .artifacts import spec_for
from .classification import classify, missing_sections
from .fs import find_markdown_files
from .parser import parse_file
from .relationships import (
    RelationshipSummary,
    summarize_relationships,
)
from .validate import has_errors, validate

# Stable attention codes (part of the JSON contract, ADR-007).
ATTENTION_INVALID = "invalid-artifact"
ATTENTION_MISSING_RECOMMENDED = "missing-recommended-sections"
ATTENTION_BROKEN_RELATIONSHIP = "broken-relationship"


@dataclass
class AttentionItem:
    """One actionable finding surfaced by ``rac portfolio``."""

    path: str
    identifier: str  # artifact identifier or filename stem
    severity: str    # "error" | "warning"
    code: str
    message: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "identifier": self.identifier,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class PortfolioSummary:
    """Repository-level intelligence result (v0.7.3).

    ``to_dict`` is the stable JSON contract (ADR-007); all fields are additive
    and schema_version-gated so consumers can detect breaking changes.
    """

    directory: str
    recursive: bool
    by_type: dict[str, int]                           # {type: count} incl. unknown
    valid_artifacts: int
    invalid_artifacts: int
    recommended_slots: int
    filled_slots: int
    relationships: RelationshipSummary
    attention: list[AttentionItem] = field(default_factory=list)

    @property
    def total_artifacts(self) -> int:
        return sum(self.by_type.values())

    @property
    def completeness(self) -> float:
        if self.recommended_slots == 0:
            return 1.0
        return round(self.filled_slots / self.recommended_slots, 4)

    @property
    def health_score(self) -> int:
        total = self.total_artifacts
        validity = self.valid_artifacts / total if total else 1.0
        completeness = self.completeness
        checked = self.relationships.total
        rel_integrity = (
            (checked - self.relationships.broken) / checked if checked else 1.0
        )
        raw = 0.5 * validity + 0.25 * completeness + 0.25 * rel_integrity
        return round(100 * raw)

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            "artifacts": {
                "total": self.total_artifacts,
                "by_type": self.by_type,
            },
            "validation": {
                "valid": self.valid_artifacts,
                "invalid": self.invalid_artifacts,
            },
            "completeness": {
                "recommended_slots": self.recommended_slots,
                "filled": self.filled_slots,
                "ratio": self.completeness,
            },
            "relationships": {
                "total": self.relationships.total,
                "valid": self.relationships.valid,
                "broken": self.relationships.broken,
                "orphaned": self.relationships.orphaned,
                "coverage": self.relationships.coverage,
            },
            "attention": [item.to_dict() for item in self.attention],
            "health": {
                "score": self.health_score,
            },
        }


def _identifier_for(path: str, product) -> str:
    """Best display identifier for ``path``: title, else stem."""
    from pathlib import Path

    return product.title or Path(path).stem


def build_portfolio_summary(
    directory: str, recursive: bool = True
) -> PortfolioSummary:
    """Walk ``directory`` and compute a full repository intelligence summary."""
    from .artifacts import ARTIFACT_SPECS

    paths = find_markdown_files(directory, recursive=recursive)

    # --- per-artifact pass ---------------------------------------------------
    by_type: dict[str, int] = {spec.name: 0 for spec in ARTIFACT_SPECS}
    by_type["unknown"] = 0

    valid_count = 0
    invalid_count = 0
    recommended_slots = 0
    filled_slots = 0
    attention: list[AttentionItem] = []

    # Broken-relationship attention: resolved separately so we avoid a second
    # full walk. We collect the relationship summary after the artifact loop.

    for path in paths:
        product = parse_file(str(path))
        artifact_type = classify(product).type
        by_type[artifact_type] = by_type.get(artifact_type, 0) + 1

        spec = spec_for(artifact_type)
        if spec is None:
            # Unknown artifacts: not validated, not scored for completeness.
            continue

        # Validation
        issues = validate(product)
        if has_errors(issues):
            invalid_count += 1
            error_codes = [i.code for i in issues if i.severity == "error"]
            attention.append(
                AttentionItem(
                    path=str(path),
                    identifier=_identifier_for(str(path), product),
                    severity="error",
                    code=ATTENTION_INVALID,
                    message=f"Validation errors: {', '.join(error_codes)}",
                )
            )
        else:
            valid_count += 1

        # Completeness (recommended sections only — required failures are already
        # reported as validation errors above, counting them twice would double-
        # penalise in the health score).
        slots = len(spec.recommended)
        recommended_slots += slots
        _, missing_rec = missing_sections(product, spec)
        filled = slots - len(missing_rec)
        filled_slots += filled
        if missing_rec:
            names = ", ".join(s.title() for s in missing_rec)
            attention.append(
                AttentionItem(
                    path=str(path),
                    identifier=_identifier_for(str(path), product),
                    severity="warning",
                    code=ATTENTION_MISSING_RECOMMENDED,
                    message=f"Missing recommended sections: {names}",
                )
            )

    # --- relationship summary ------------------------------------------------
    rel_summary = summarize_relationships(directory, recursive=recursive)

    # Sort attention: errors before warnings, then path, then code (deterministic).
    _SEV_ORDER = {"error": 0, "warning": 1}
    attention.sort(key=lambda a: (_SEV_ORDER.get(a.severity, 2), a.path, a.code))

    return PortfolioSummary(
        directory=directory,
        recursive=recursive,
        by_type=by_type,
        valid_artifacts=valid_count,
        invalid_artifacts=invalid_count,
        recommended_slots=recommended_slots,
        filled_slots=filled_slots,
        relationships=rel_summary,
        attention=attention,
    )
