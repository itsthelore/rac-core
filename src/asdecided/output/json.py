"""JSON rendering for RAC command results.

JSON outputs are a public, versioned contract (ADR-007): field names are stable
and must not change without an explicit versioning strategy. Each renderer is a
thin, deterministic projection of a service result into ``json.dumps`` output.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from asdecided.core.hooks import HookSpec
from asdecided.core.models import Diff, Issue, Product
from asdecided.core.schema import SchemaReference
from asdecided.core.skills import SkillSpec
from asdecided.services.agent_rules import AgentRulesResult
from asdecided.services.create import CreatedArtifact
from asdecided.services.export import CorpusExport, DocumentsExport, GraphExport
from asdecided.services.gate import GateReport
from asdecided.services.hook import InstalledHook
from asdecided.services.improve import ImprovementResult
from asdecided.services.index import RepositoryIndex
from asdecided.services.ingest import IngestResult
from asdecided.services.init import InitResult
from asdecided.services.inspect import DirectoryInspection, InspectionResult
from asdecided.services.migrate import MigrationReport
from asdecided.services.note_ingest import VaultIngestResult
from asdecided.services.portfolio import PortfolioSummary
from asdecided.services.quickstart import QuickstartResult
from asdecided.services.relationships import RelationshipReport, RelationshipValidation
from asdecided.services.rename import RenamePlan, RenameResult
from asdecided.services.resolve import ResolutionResult, SearchResult
from asdecided.services.review import ReviewReport
from asdecided.services.scope import ScopeLookupResult
from asdecided.services.skill import SkillInstallation
from asdecided.services.stats import PortfolioStats
from asdecided.services.validate import DirectoryValidation, StdinCorpusValidation
from asdecided.services.watchkeeper import WatchkeeperReport

if TYPE_CHECKING:
    from asdecided.mcp.telemetry import TelemetrySummary as MCPTelemetrySummary

# --- validate ---------------------------------------------------------------


def render_validation_json(product: Product, issues: list[Issue]) -> str:
    """JSON single-file `decided validate` output (stable contract, ADR-007).

    Carries the same ``schema_version`` stamp as the directory and stdin-corpus
    forms, so every `decided validate --json` shape is version-gated.
    """
    errors = [asdict(i) for i in issues if i.severity == "error"]
    warnings = [asdict(i) for i in issues if i.severity == "warning"]
    payload = {
        "schema_version": "1",
        "file": product.source_path or None,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    return json.dumps(payload, indent=2)


def render_validate_dir_json(result: DirectoryValidation) -> str:
    """JSON directory `decided validate` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


def render_stdin_corpus_json(result: StdinCorpusValidation) -> str:
    """JSON `decided validate - --corpus` output (stable contract, ADR-007).

    Additive over single-file `decided validate` JSON: the same ``file`` / ``valid`` /
    ``errors`` / ``warnings`` keys, plus ``relationship_issues`` for the proposed
    document's references resolved against the corpus (v0.21.17, ADR-067).
    """
    return json.dumps(result.to_dict(), indent=2)


# --- review -----------------------------------------------------------------


def render_review_json(report: ReviewReport) -> str:
    """JSON `decided review` output (stable contract, ADR-007)."""
    return json.dumps(report.to_dict(), indent=2)


# --- gate --------------------------------------------------------------------


def render_gate_json(report: GateReport) -> str:
    """JSON `decided gate` output (stable contract, ADR-007)."""
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
        # Additive in v0.13.1 (ADR-007): a day-one empty-corpus marker.
        "empty": s.is_empty,
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


# --- rename ------------------------------------------------------------------


def render_rename_json(plan: RenamePlan) -> str:
    """The rename plan as the stable additive contract (ADR-007, v0.21.18)."""
    return json.dumps(plan.to_dict(), indent=2)


def render_rename_result_json(result: RenameResult) -> str:
    """The applied-rename outcome as the stable additive contract (ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


# --- ingest ------------------------------------------------------------------


def render_ingest_json(result: IngestResult, output_path: str | None) -> str:
    payload = {
        "source": result.source_path,
        "converter": result.converter,
        "output": output_path,
        "markdown": result.markdown,
    }
    return json.dumps(payload, indent=2)


def render_vault_ingest_json(
    result: VaultIngestResult,
    written: list[str],
    skipped: list[str],
    output_dir: str | None,
) -> str:
    """JSON `decided ingest <dir>` output (stable contract, ADR-007).

    Carries every draft's normalised Markdown and its candidate relationships and
    warnings, plus what was written or skipped, so a consumer can drive the review
    step programmatically. Order mirrors the deterministic note walk.
    """
    payload = {
        "converter": result.converter,
        "root": result.root,
        "output_dir": output_dir,
        "note_count": result.note_count,
        "resolved_link_count": result.resolved_link_count,
        "warning_count": result.warning_count,
        "skipped_sources": result.skipped_sources,
        "written": written,
        "skipped": skipped,
        "drafts": [
            {
                "source": draft.source_path,
                "suggested_filename": draft.suggested_filename,
                "related": draft.related,
                "warnings": draft.warnings,
                "markdown": draft.markdown,
            }
            for draft in result.drafts
        ],
    }
    return json.dumps(payload, indent=2)


# --- portfolio ---------------------------------------------------------------


def render_portfolio_json(s: PortfolioSummary) -> str:
    """JSON `decided portfolio` output (stable contract, ADR-007)."""
    return json.dumps(s.to_dict(), indent=2)


# --- index -------------------------------------------------------------------


def render_index_json(index: RepositoryIndex) -> str:
    """JSON `decided index` output (stable contract, ADR-007)."""
    return json.dumps(index.to_dict(), indent=2)


# --- export (v0.11.0) ---------------------------------------------------------


def render_export_json(export: CorpusExport) -> str:
    """JSON `decided export` output (stable contract, ADR-007).

    This payload *is* the product: it is what the Portal shell embeds and what
    external viewers consume (ADR-014).
    """
    return json.dumps(export.to_dict(), indent=2)


def render_documents_jsonl(export: DocumentsExport) -> str:
    """JSON Lines `decided export --documents` output (stable contract, ADR-007).

    One compact JSON object per line — the ingestion shape memory/RAG backends
    consume. Records are in sorted-path order and carry a Markdown body, so the
    output is deterministic (ADR-002); ``ensure_ascii`` is off so the body is
    emitted as UTF-8 rather than escaped.
    """
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in export.to_records())


def render_graph_json(export: GraphExport) -> str:
    """JSON `decided export --graph` output (stable contract, ADR-007, ADR-074).

    A single whole-graph object — nodes and typed, directed edges — for graph
    backends. Edges carry the registry kind rather than the viewer's flattened
    ``relates-to`` (which is unchanged). Deterministic ordering, no timestamps.
    """
    return json.dumps(export.to_dict(), indent=2)


def render_agent_rules_json(result: AgentRulesResult) -> str:
    """JSON `decided export --agent-rules [--check]` output (stable contract, ADR-007).

    The editor and CI consume this: ``mode``, the corpus ``digest``, the output
    ``root``, and per-target ``files`` with their ``state``.
    """
    return json.dumps(result.to_dict(), indent=2)


# --- create (rac new / rac templates, v0.7.10) -------------------------------


def render_templates_json(names: list[str]) -> str:
    """JSON `decided templates` output (stable contract, ADR-007)."""
    return json.dumps({"schema_version": "1", "templates": names}, indent=2)


def render_new_json(created: CreatedArtifact) -> str:
    """JSON `decided new` output (stable contract, ADR-007)."""
    return json.dumps(created.to_dict(), indent=2)


def render_init_json(result: InitResult) -> str:
    """JSON `decided init` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


def render_quickstart_json(result: QuickstartResult) -> str:
    """JSON `decided quickstart` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


# --- resolve / find (v0.7.12) -------------------------------------------------


def render_resolve_json(result: ResolutionResult) -> str:
    """JSON `decided resolve` output (stable contract, ADR-007)."""
    return json.dumps(result.to_dict(), indent=2)


def render_decisions_for_json(result: ScopeLookupResult) -> str:
    """JSON `decided decisions-for` output (stable contract, ADR-007).

    The same ``ScopeLookupResult`` the MCP ``find_decisions`` path argument
    serializes, so the two faces stay payload-consistent (ADR-031).
    """
    return json.dumps(result.to_dict(), indent=2)


def render_find_json(result: SearchResult, *, explain: bool = False) -> str:
    """JSON `decided find` output (stable contract, ADR-007).

    ``explain`` adds the additive per-match ``evidence`` object (WS2). It is
    off by default so the standard ``decided find --json`` shape stays byte-stable;
    ``decided find --explain --json`` emits the same ``evidence`` the MCP
    ``search_artifacts`` tool emits (one source of truth, REQ-004).
    """
    return json.dumps(result.to_dict(include_evidence=explain), indent=2)


# --- migrate (v0.7.13) ----------------------------------------------------------


def render_migrate_json(report: MigrationReport) -> str:
    """JSON `decided migrate metadata` output (stable contract, ADR-007)."""
    return json.dumps(report.to_dict(), indent=2)


# --- skill (rac skill install / list, v0.10.5) -------------------------------


def render_skill_install_json(installation: SkillInstallation) -> str:
    """JSON `decided skill install` output (stable contract, ADR-007)."""
    return json.dumps(installation.to_dict(), indent=2)


def render_skill_list_json(specs: list[SkillSpec]) -> str:
    """JSON `decided skill list` output (stable contract, ADR-007)."""
    payload = {
        "schema_version": "1",
        "skills": [{"skill": spec.name, "description": spec.description} for spec in specs],
    }
    return json.dumps(payload, indent=2)


def render_hook_install_json(installation: InstalledHook) -> str:
    """JSON `decided hook install` output (stable contract, ADR-007)."""
    return json.dumps(installation.to_dict(), indent=2)


def render_hook_list_json(specs: list[HookSpec]) -> str:
    """JSON `decided hook list` output (stable contract, ADR-007)."""
    payload = {
        "schema_version": "1",
        "hooks": [{"style": spec.style, "description": spec.description} for spec in specs],
    }
    return json.dumps(payload, indent=2)


# --- mcp-stats (v0.10.4) ----------------------------------------------------


def render_mcp_stats_json(summary: MCPTelemetrySummary) -> str:
    """JSON `decided mcp-stats` output (stable contract, ADR-007).

    This payload is also the voluntary export: `--share` URL-encodes it
    (minus the local log path) into a prefilled usage-report issue.
    """
    return json.dumps(summary.to_dict(), indent=2)


# --- watchkeeper --------------------------------------------------------------


def render_watchkeeper_json(report: WatchkeeperReport) -> str:
    """JSON `decided watchkeeper` output (stable contract, ADR-007)."""
    return json.dumps(report.to_dict(), indent=2)
