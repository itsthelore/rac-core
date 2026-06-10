"""JSON rendering for RAC command results.

JSON outputs are a public, versioned contract (ADR-007): field names are stable
and must not change without an explicit versioning strategy. Each renderer is a
thin, deterministic projection of a service result into ``json.dumps`` output.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from rac.core.models import Diff, Issue, Product
from rac.core.schema import SchemaReference
from rac.services.create import CreatedArtifact
from rac.services.improve import ImprovementResult
from rac.services.index import RepositoryIndex
from rac.services.ingest import IngestResult
from rac.services.init import InitResult
from rac.services.inspect import DirectoryInspection, InspectionResult
from rac.services.migrate import MigrationReport
from rac.services.portfolio import PortfolioSummary
from rac.services.relationships import RelationshipReport, RelationshipValidation
from rac.services.resolve import ResolutionResult, SearchResult
from rac.services.review import ReviewReport
from rac.services.stats import PortfolioStats
from rac.services.validate import DirectoryValidation

# --- validate ---------------------------------------------------------------


def render_validation_json(product: Product, issues: list[Issue]) -> str:
    errors = [asdict(i) for i in issues if i.severity == "error"]
    warnings = [asdict(i) for i in issues if i.severity == "warning"]
    payload = {
        "file": product.source_path or None,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    return json.dumps(payload, indent=2)


def render_validate_dir_json(result: DirectoryValidation) -> str:
    """JSON directory `rac validate` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


# --- review -----------------------------------------------------------------


def render_review_json(report: ReviewReport) -> str:
    """JSON `rac review` output (stable contract, ADR-007)."""
    return json.dumps(report.to_dict(), indent=2)


# --- diff -------------------------------------------------------------------


def render_diff_json(d: Diff, old_path: str, new_path: str) -> str:
    payload = {
        "old": old_path,
        "new": new_path,
        "added_requirements": [asdict(r) for r in d.added_requirements],
        "removed_requirements": [asdict(r) for r in d.removed_requirements],
        "modified_requirements": [asdict(c) for c in d.modified_requirements],
        "added_metrics": d.added_metrics,
        "removed_metrics": d.removed_metrics,
        "added_risks": d.added_risks,
        "removed_risks": d.removed_risks,
    }
    return json.dumps(payload, indent=2)


# --- stats -------------------------------------------------------------------


def render_stats_json(s: PortfolioStats) -> str:
    largest = s.largest_feature
    payload = {
        "directory": s.directory,
        "features": s.files_found,
        "valid_features": s.valid_features,
        "invalid_features": s.invalid_features,
        "requirements": s.total_requirements,
        "metrics": s.total_metrics,
        "risks": s.total_risks,
        "features_missing_metrics": s.features_missing_metrics,
        "features_missing_risks": s.features_missing_risks,
        "missing_metrics": s.missing_metrics,
        "missing_risks": s.missing_risks,
        "average_requirements_per_feature": round(s.average_requirements, 1),
        "largest_feature": (
            {"name": largest.name, "requirements": largest.requirements}
            if largest is not None
            else None
        ),
        "requirements_by_feature": [
            {"name": f.name, "requirements": f.requirements} for f in s.requirements_by_feature
        ],
        "invalid": [{"file": f.path, "errors": f.error_codes} for f in s.invalid],
    }
    # Additive: only present when the portfolio actually contains decisions, so
    # requirement-only output is unchanged.
    if s.decisions:
        payload["decisions"] = {
            "count": s.decision_count,
            "by_status": s.decision_status_counts,
            "by_category": s.decision_category_counts,
        }
    # Additive: only present when the portfolio contains roadmaps. Lightweight by
    # design — count and validity only (no section-completeness breakdown).
    if s.roadmaps:
        payload["roadmaps"] = {
            "count": s.roadmap_count,
            "valid": s.valid_roadmaps,
            "invalid": [{"file": r.path, "errors": r.error_codes} for r in s.invalid_roadmaps],
        }
    # Additive: only present when the portfolio contains prompts. Lightweight by
    # design — count and validity only (no prompt quality metrics).
    if s.prompts:
        payload["prompts"] = {
            "count": s.prompt_count,
            "valid": s.valid_prompts,
            "invalid": [{"file": p.path, "errors": p.error_codes} for p in s.invalid_prompts],
        }
    # Additive: only present when the portfolio contains designs. Lightweight by
    # design — count and validity only (no design quality or rendering metrics).
    if s.designs:
        payload["designs"] = {
            "count": s.design_count,
            "valid": s.valid_designs,
            "invalid": [{"file": d.path, "errors": d.error_codes} for d in s.invalid_designs],
        }
    # Additive: only present when the portfolio contains documents that matched
    # no known artifact schema (ADR-010). Surfaced, not errors; ``confidence`` is
    # the best-fit classification score for each document.
    if s.unrecognized:
        payload["unrecognized"] = {
            "count": s.unrecognized_count,
            "files": [
                {"file": u.path, "name": u.name, "confidence": round(u.confidence, 2)}
                for u in s.unrecognized
            ],
        }
    # Additive: only present when some artifact declares a relationship section.
    # Declared-presence counts (REQ-011), snake_case keys — not resolution.
    if s.relationship_counts:
        payload["relationships"] = {
            section.replace(" ", "_"): count for section, count in s.relationship_counts.items()
        }
    return json.dumps(payload, indent=2)


# --- inspect -----------------------------------------------------------------


def render_inspect_json(result: InspectionResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def render_dir_inspect_json(d: DirectoryInspection) -> str:
    payload = {
        "schema_version": "1",
        "directory": d.directory,
        "recursive": d.recursive,
        "summary": {
            "total_files": d.total_files,
            "counts": d.counts,
            "unknown": d.unknown_count,
        },
        "files": [{"path": f.path, "type": f.type, "confidence": f.confidence} for f in d.files],
    }
    return json.dumps(payload, indent=2)


# --- improve -----------------------------------------------------------------


def render_improve_json(result: ImprovementResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


# --- schema ------------------------------------------------------------------


def render_schema_list_json(names: list[str]) -> str:
    return json.dumps({"schemas": names}, indent=2)


def render_schema_json(ref: SchemaReference) -> str:
    return json.dumps(ref.to_dict(), indent=2)


# --- relationships -----------------------------------------------------------


def render_relationships_json(report: RelationshipReport) -> str:
    payload = {
        "directory": report.directory,
        "recursive": report.recursive,
        "total_files": report.total_files,
        "artifacts_with_relationships": report.artifacts_with_relationships,
        "relationship_count": report.relationship_count,
        "counts": report.counts,
        "artifacts": [
            {
                "path": artifact.path,
                "type": artifact.type,
                "relationships": artifact.relationships,
            }
            for artifact in report.artifacts
        ],
    }
    return json.dumps(payload, indent=2)


def render_relationship_validation_json(report: RelationshipValidation) -> str:
    payload = {
        "directory": report.directory,
        "recursive": report.recursive,
        "relationships_checked": report.relationships_checked,
        "validation_issues": report.validation_issues,
        "issues": [issue.to_dict() for issue in report.issues],
    }
    return json.dumps(payload, indent=2)


# --- ingest ------------------------------------------------------------------


def render_ingest_json(result: IngestResult, output_path: str | None) -> str:
    payload = {
        "source": result.source_path,
        "converter": result.converter,
        "output": output_path,
        "markdown": result.markdown,
    }
    return json.dumps(payload, indent=2)


# --- portfolio ---------------------------------------------------------------


def render_portfolio_json(s: PortfolioSummary) -> str:
    """JSON `rac portfolio` output (stable contract, ADR-007)."""
    return json.dumps(s.to_dict(), indent=2)


# --- index -------------------------------------------------------------------


def render_index_json(index: RepositoryIndex) -> str:
    """JSON `rac index` output (stable contract, ADR-007)."""
    return json.dumps(index.to_dict(), indent=2)


# --- create (rac new / rac templates, v0.7.10) -------------------------------


def render_templates_json(names: list[str]) -> str:
    """JSON `rac templates` output (stable contract, ADR-007)."""
    return json.dumps({"schema_version": "1", "templates": names}, indent=2)


def render_new_json(created: CreatedArtifact) -> str:
    """JSON `rac new` output (stable contract, ADR-007)."""
    return json.dumps(created.to_dict(), indent=2)


def render_init_json(result: InitResult) -> str:
    """JSON `rac init` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


# --- resolve / find (v0.7.12) -------------------------------------------------


def render_resolve_json(result: ResolutionResult) -> str:
    """JSON `rac resolve` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


def render_find_json(result: SearchResult) -> str:
    """JSON `rac find` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


# --- migrate (v0.7.13) ----------------------------------------------------------


def render_migrate_json(report: MigrationReport) -> str:
    """JSON `rac migrate metadata` output (stable contract, ADR-007)."""
    return json.dumps(report.to_dict(), indent=2)
