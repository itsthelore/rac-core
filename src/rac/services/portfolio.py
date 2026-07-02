"""Repository intelligence summary — `rac portfolio` (v0.7.3).

``build_portfolio_summary`` walks a directory once and gathers:

- Artifact counts (by type + unknown)
- Validation (valid / invalid, severity overrides applied)
- Completeness (filled recommended slots / total recommended slots)
- Relationship health (from the relationship summary)
- Attention items (invalid artifacts, missing recommended sections, broken refs)
- A weighted composite health score

All analysis is deterministic and belongs to Core (ADR-015): the CLI renders the
result and calculates nothing of its own.

Health score (each sub-score in [0, 1], and 1.0 when its denominator is 0):

    score = round(100 * (0.5*validity + 0.25*completeness + 0.25*rel_integrity))

    validity      = valid_artifacts / total_artifacts
    completeness  = filled_recommended_slots / total_recommended_slots
    rel_integrity = (total_refs - broken_refs) / total_refs
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.artifacts import ARTIFACT_SPECS, spec_for
from rac.core.classification import missing_sections
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.identity import artifact_identifier
from rac.core.overrides import apply_overrides
from rac.core.validation import has_errors, validate
from rac.services.init import load_overrides

from .relationships import (
    ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS,
    ISSUE_TARGET_NOT_FOUND,
    RelationshipSummary,
    summary_from_corpus,
    validation_from_corpus,
)

# Stable attention codes (part of the JSON contract, ADR-007).
ATTENTION_INVALID = "invalid-artifact"
ATTENTION_MISSING_RECOMMENDED = "missing-recommended-sections"
ATTENTION_BROKEN_RELATIONSHIP = "broken-relationship"

# Human phrasing for each relationship-resolution issue in attention messages.
_REL_ISSUE_PHRASE = {
    ISSUE_TARGET_NOT_FOUND: "references missing artifact",
    ISSUE_TARGET_AMBIGUOUS: "has an ambiguous reference to",
    ISSUE_SELF_REFERENCE: "references itself via",
}

# Attention ordering: errors before warnings, then path, then code.
_SEV_ORDER = {"error": 0, "warning": 1}


@dataclass
class AttentionItem:
    """One actionable finding surfaced by ``rac portfolio``."""

    path: str
    identifier: str  # the artifact identifier, or the filename stem
    severity: str  # "error" | "warning"
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

    ``to_dict`` is the stable JSON contract (ADR-007): all fields are additive and
    schema_version-gated so consumers can detect breaking changes.
    """

    directory: str
    recursive: bool
    by_type: dict[str, int]  # {type: count}, including unknown
    valid_artifacts: int
    invalid_artifacts: int
    recommended_slots: int
    filled_slots: int
    relationships: RelationshipSummary
    attention: list[AttentionItem] = field(default_factory=list)
    # Paths of unknown-type files (v0.7.9, additive): counted in ``by_type`` but
    # neither validated nor completeness-scored, so consumers like ``rac review``
    # can surface them without a second walk.
    unknown_paths: list[str] = field(default_factory=list)
    # Full relationship-validation gate result (v0.16.0, additive): whether every
    # referential, edge-legality, range, status-consistency, and acyclicity check
    # passes. Broader than ``relationships.broken`` (referential resolution only),
    # so the summary can report the same verdict as `rac relationships --validate`.
    relationships_ok: bool = True

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
        checked = self.relationships.total
        rel_integrity = (checked - self.relationships.broken) / checked if checked else 1.0
        raw = 0.5 * validity + 0.25 * self.completeness + 0.25 * rel_integrity
        return round(100 * raw)

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            # Additive in v0.13.1 (ADR-007): a day-one empty-corpus marker.
            "empty": self.total_artifacts == 0,
            "artifacts": {
                "total": self.total_artifacts,
                "by_type": self.by_type,
                # Additive in v0.7.9 (ADR-007): unknown files listed by path.
                "unknown_paths": self.unknown_paths,
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
            # Additive (v0.16.0, ADR-007): the repository validation gate, so an
            # agent over MCP (`get_summary`) can read pass/fail without a second
            # tool. ``relationships_ok`` reflects the full relationship-validation
            # gate (referential + edge-legality + range + status + acyclicity).
            "validation_status": {
                "artifacts_ok": self.invalid_artifacts == 0,
                "relationships_ok": self.relationships_ok,
                "ok": self.invalid_artifacts == 0 and self.relationships_ok,
            },
        }


def build_portfolio_summary(directory: str, recursive: bool = True) -> PortfolioSummary:
    """Walk ``directory`` and compute a full repository intelligence summary."""
    entries = list(walk_corpus(directory, recursive=recursive))
    return portfolio_from_corpus(directory, entries, recursive=recursive)


def portfolio_from_corpus(
    directory: str, entries: list[CorpusEntry], recursive: bool = True
) -> PortfolioSummary:
    """Summarize an already-walked corpus snapshot (v0.8.0).

    Produces the same result as :func:`build_portfolio_summary`; the snapshot also
    feeds the relationship analysis, so a portfolio costs one walk, not two.
    """
    # Repository-wide severity overrides (ADR-053): review/portfolio/watchkeeper
    # honour the same .rac/config.yaml policy as `rac validate`.
    overrides = load_overrides(directory)

    # Seed every known type plus unknown at zero so the count is stable regardless
    # of which types the corpus actually contains.
    by_type: dict[str, int] = {spec.name: 0 for spec in ARTIFACT_SPECS}
    by_type["unknown"] = 0

    valid_count = 0
    invalid_count = 0
    recommended_slots = 0
    filled_slots = 0
    attention: list[AttentionItem] = []
    unknown_paths: list[str] = []
    # Relationship issues carry a source path that is always a known artifact;
    # this map recovers its identifier without a second identifier pass.
    path_to_identifier: dict[str, str] = {}

    for entry in entries:
        path, product = entry.path, entry.product
        artifact_type = entry.artifact_type
        by_type[artifact_type] = by_type.get(artifact_type, 0) + 1

        spec = spec_for(artifact_type)
        if spec is None:
            # Unknown artifacts are counted but neither validated nor scored.
            unknown_paths.append(str(path))
            continue

        identifier = artifact_identifier(product, spec, str(path))
        path_to_identifier[str(path)] = identifier

        # Validation, with severity overrides applied (ADR-053).
        issues = apply_overrides(validate(product), artifact_type, overrides)
        if has_errors(issues):
            invalid_count += 1
            error_codes = [i.code for i in issues if i.severity == "error"]
            attention.append(
                AttentionItem(
                    path=str(path),
                    identifier=identifier,
                    severity="error",
                    code=ATTENTION_INVALID,
                    message=f"Validation errors: {', '.join(error_codes)}",
                )
            )
        else:
            valid_count += 1

        # Completeness scores recommended sections only: a missing *required*
        # section is already an error above, and counting it here too would
        # double-penalise the health score.
        slots = len(spec.recommended)
        recommended_slots += slots
        _, missing_rec = missing_sections(product, spec)
        filled_slots += slots - len(missing_rec)
        if missing_rec:
            names = ", ".join(s.title() for s in missing_rec)
            attention.append(
                AttentionItem(
                    path=str(path),
                    identifier=identifier,
                    severity="warning",
                    code=ATTENTION_MISSING_RECOMMENDED,
                    message=f"Missing recommended sections: {names}",
                )
            )

    # Relationship health reuses the snapshot (no second walk). The referential
    # summary drives the counts and the broken-reference attention items; the
    # full gate verdict is a separate, broader check (v0.16.0).
    rel_summary = summary_from_corpus(entries)
    relationships_ok = validation_from_corpus(directory, entries, recursive=recursive).ok
    for issue in rel_summary.issues:
        source = issue.source_path or ""
        label = (issue.relationship or "").replace("_", " ").title()
        phrase = _REL_ISSUE_PHRASE.get(issue.code, "has an unresolved reference")
        attention.append(
            AttentionItem(
                path=source,
                identifier=path_to_identifier.get(source, source),
                severity="warning",
                code=ATTENTION_BROKEN_RELATIONSHIP,
                message=f"{label} {phrase}: {issue.target}",
            )
        )

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
        unknown_paths=unknown_paths,
        relationships_ok=relationships_ok,
    )
