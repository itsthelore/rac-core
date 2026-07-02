"""JSON renderers for RAC command results.

Every JSON shape RAC emits is a public, versioned contract (ADR-007): field
names and their order are stable and change only behind an explicit version
bump. Each renderer is a pure, deterministic projection of an already-computed
service/core result into ``json.dumps`` text — presentation only, never a
second source of truth (ADR-003).

Two shapes live here:

* **Delegators** — the payload dict is owned by the result object's
  ``to_dict()``; this module only pins the serialization via ``_dump``.
* **Inline builders** — the field set *and its order* are defined here, so they
  must be reproduced exactly (``render_validation_json``, ``render_diff_json``,
  ``render_stats_json``, ``render_dir_inspect_json``, the relationship pair, the
  ingest/list builders, ``render_documents_jsonl``).

``render_documents_jsonl`` is the sole exception to ``_dump``: it is compact and
UTF-8 (``ensure_ascii=False``), one object per line.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only: the renderers read each result's attributes and ``to_dict()`` at
    # runtime, never the class objects, so the presentation layer does not force
    # the whole service layer to import just to serialize.
    from rac.core.hooks import HookSpec
    from rac.core.models import Diff, Issue, Product
    from rac.core.schema import SchemaReference
    from rac.core.skills import SkillSpec
    from rac.mcp.telemetry import TelemetrySummary as MCPTelemetrySummary
    from rac.services.agent_rules import AgentRulesResult
    from rac.services.create import CreatedArtifact
    from rac.services.export import CorpusExport, DocumentsExport, GraphExport
    from rac.services.gate import GateReport
    from rac.services.hook import InstalledHook
    from rac.services.improve import ImprovementResult
    from rac.services.index import RepositoryIndex
    from rac.services.ingest import IngestResult
    from rac.services.init import InitResult
    from rac.services.inspect import DirectoryInspection, InspectionResult
    from rac.services.migrate import MigrationReport
    from rac.services.portfolio import PortfolioSummary
    from rac.services.quickstart import QuickstartResult
    from rac.services.relationships import RelationshipReport, RelationshipValidation
    from rac.services.rename import RenamePlan, RenameResult
    from rac.services.resolve import ResolutionResult, SearchResult
    from rac.services.review import ReviewReport
    from rac.services.skill import SkillInstallation
    from rac.services.stats import PortfolioStats
    from rac.services.validate import DirectoryValidation, StdinCorpusValidation
    from rac.services.watchkeeper import WatchkeeperReport


def _dump(payload: object) -> str:
    """Serialize a payload as canonical RAC JSON.

    The single seam every non-JSONL renderer funnels through, so ``indent`` and
    the ``ensure_ascii`` default are pinned in exactly one place (ADR-007).
    """
    return json.dumps(payload, indent=2)


# --- validate ----------------------------------------------------------------


def render_validation_json(product: Product, issues: list[Issue]) -> str:
    """Single-file ``rac validate --json``.

    The ``schema_version`` stamp is shared with the directory and stdin-corpus
    forms, so every ``rac validate --json`` shape is version-gated.
    """
    errors = [asdict(i) for i in issues if i.severity == "error"]
    warnings = [asdict(i) for i in issues if i.severity == "warning"]
    return _dump(
        {
            "schema_version": "1",
            "file": product.source_path or None,
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        }
    )


def render_validate_dir_json(result: DirectoryValidation) -> str:
    """Directory ``rac validate --json``."""
    return _dump(result.to_dict())


def render_stdin_corpus_json(result: StdinCorpusValidation) -> str:
    """``rac validate - --corpus --json`` (ADR-067).

    Additive over single-file validate JSON: the same ``file`` / ``valid`` /
    ``errors`` / ``warnings`` keys plus ``relationship_issues`` for the proposed
    document resolved against the corpus.
    """
    return _dump(result.to_dict())


# --- review ------------------------------------------------------------------


def render_review_json(report: ReviewReport) -> str:
    """``rac review --json``."""
    return _dump(report.to_dict())


# --- gate --------------------------------------------------------------------


def render_gate_json(report: GateReport) -> str:
    """``rac gate --json``."""
    return _dump(report.to_dict())


# --- diff --------------------------------------------------------------------


def render_diff_json(d: Diff, old_path: str, new_path: str) -> str:
    """``rac diff --json`` — field order owned here (ADR-007)."""
    return _dump(
        {
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
    )


# --- stats -------------------------------------------------------------------


def render_stats_json(s: PortfolioStats) -> str:
    """``rac stats --json`` — field order owned here (ADR-007).

    The requirement block is always present. The decisions / roadmaps / prompts
    / designs / unrecognized / relationships blocks are additive and emitted
    *only when non-empty*, in this fixed order, so a requirement-only portfolio's
    output is unchanged.
    """
    largest = s.largest_feature
    payload: dict[str, object] = {
        "directory": s.directory,
        # Additive day-one empty-corpus marker (v0.13.1, ADR-007).
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
    if s.decisions:
        payload["decisions"] = {
            "count": s.decision_count,
            "by_status": s.decision_status_counts,
            "by_category": s.decision_category_counts,
        }
    # Roadmaps / prompts / designs are lightweight by design — count and
    # validity only, no per-type quality breakdown.
    if s.roadmaps:
        payload["roadmaps"] = {
            "count": s.roadmap_count,
            "valid": s.valid_roadmaps,
            "invalid": [{"file": r.path, "errors": r.error_codes} for r in s.invalid_roadmaps],
        }
    if s.prompts:
        payload["prompts"] = {
            "count": s.prompt_count,
            "valid": s.valid_prompts,
            "invalid": [{"file": p.path, "errors": p.error_codes} for p in s.invalid_prompts],
        }
    if s.designs:
        payload["designs"] = {
            "count": s.design_count,
            "valid": s.valid_designs,
            "invalid": [{"file": d.path, "errors": d.error_codes} for d in s.invalid_designs],
        }
    # Documents that matched no known schema (ADR-010): surfaced, not errored;
    # ``confidence`` is each document's best-fit classification score.
    if s.unrecognized:
        payload["unrecognized"] = {
            "count": s.unrecognized_count,
            "files": [
                {"file": u.path, "name": u.name, "confidence": round(u.confidence, 2)}
                for u in s.unrecognized
            ],
        }
    # Declared-presence counts (REQ-011), snake_case keys — not resolution.
    if s.relationship_counts:
        payload["relationships"] = {
            section.replace(" ", "_"): count for section, count in s.relationship_counts.items()
        }
    return _dump(payload)


# --- inspect -----------------------------------------------------------------


def render_inspect_json(result: InspectionResult) -> str:
    """``rac inspect <file> --json``."""
    return _dump(result.to_dict())


def render_dir_inspect_json(d: DirectoryInspection) -> str:
    """``rac inspect <dir> --json`` — field order owned here (ADR-007)."""
    return _dump(
        {
            "schema_version": "1",
            "directory": d.directory,
            "recursive": d.recursive,
            "summary": {
                "total_files": d.total_files,
                "counts": d.counts,
                "unknown": d.unknown_count,
            },
            "files": [
                {"path": f.path, "type": f.type, "confidence": f.confidence} for f in d.files
            ],
        }
    )


# --- improve -----------------------------------------------------------------


def render_improve_json(result: ImprovementResult) -> str:
    """``rac improve --json``."""
    return _dump(result.to_dict())


# --- schema ------------------------------------------------------------------


def render_schema_list_json(names: list[str]) -> str:
    """``rac schema --json`` (the name list)."""
    return _dump({"schemas": names})


def render_schema_json(ref: SchemaReference) -> str:
    """``rac schema <type> --json``."""
    return _dump(ref.to_dict())


# --- relationships -----------------------------------------------------------


def render_relationships_json(report: RelationshipReport) -> str:
    """``rac relationships --json`` — field order owned here (ADR-007)."""
    return _dump(
        {
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
    )


def render_relationship_validation_json(report: RelationshipValidation) -> str:
    """``rac relationships --validate --json`` — field order owned here (ADR-007)."""
    return _dump(
        {
            "directory": report.directory,
            "recursive": report.recursive,
            "relationships_checked": report.relationships_checked,
            "validation_issues": report.validation_issues,
            "issues": [issue.to_dict() for issue in report.issues],
        }
    )


# --- rename ------------------------------------------------------------------


def render_rename_json(plan: RenamePlan) -> str:
    """``rac rename --dry-run --json`` — the plan is the additive contract (ADR-007)."""
    return _dump(plan.to_dict())


def render_rename_result_json(result: RenameResult) -> str:
    """``rac rename --json`` — the applied-rename outcome (ADR-007)."""
    return _dump(result.to_dict())


# --- ingest ------------------------------------------------------------------


def render_ingest_json(result: IngestResult, output_path: str | None) -> str:
    """``rac ingest --json`` — field order owned here (ADR-007)."""
    return _dump(
        {
            "source": result.source_path,
            "converter": result.converter,
            "output": output_path,
            "markdown": result.markdown,
        }
    )


# --- portfolio ---------------------------------------------------------------


def render_portfolio_json(s: PortfolioSummary) -> str:
    """``rac portfolio --json``."""
    return _dump(s.to_dict())


# --- index -------------------------------------------------------------------


def render_index_json(index: RepositoryIndex) -> str:
    """``rac index --json``."""
    return _dump(index.to_dict())


# --- export ------------------------------------------------------------------


def render_export_json(export: CorpusExport) -> str:
    """``rac export --json``.

    This payload *is* the product: the Portal shell embeds it and external
    viewers consume it (ADR-014).
    """
    return _dump(export.to_dict())


def render_documents_jsonl(export: DocumentsExport) -> str:
    """``rac export --documents`` (JSON Lines).

    One compact JSON object per line — the ingestion shape memory/RAG backends
    consume. Records arrive in sorted-path order and carry a Markdown body, so
    the stream is deterministic (ADR-002). This is the only renderer that turns
    ``ensure_ascii`` off, so bodies emit as UTF-8 rather than escaped; there is
    no trailing newline (the CLI's ``print`` adds one).
    """
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in export.to_records())


def render_graph_json(export: GraphExport) -> str:
    """``rac export --graph`` (ADR-074).

    A single whole-graph object — nodes and typed, directed edges — for graph
    backends. Edges carry the registry kind rather than the viewer's flattened
    ``relates-to``. Deterministic ordering, no timestamps.
    """
    return _dump(export.to_dict())


def render_agent_rules_json(result: AgentRulesResult) -> str:
    """``rac export --agent-rules [--check] --json``.

    The editor and CI consume ``mode``, the corpus ``digest``, the output
    ``root``, and per-target ``files`` with their ``state``.
    """
    return _dump(result.to_dict())


# --- create (rac new / rac templates) ----------------------------------------


def render_templates_json(names: list[str]) -> str:
    """``rac templates --json`` — field order owned here (ADR-007)."""
    return _dump({"schema_version": "1", "templates": names})


def render_new_json(created: CreatedArtifact) -> str:
    """``rac new --json``."""
    return _dump(created.to_dict())


def render_init_json(result: InitResult) -> str:
    """``rac init --json``."""
    return _dump(result.to_dict())


def render_quickstart_json(result: QuickstartResult) -> str:
    """``rac quickstart --json``."""
    return _dump(result.to_dict())


# --- resolve / find ----------------------------------------------------------


def render_resolve_json(result: ResolutionResult) -> str:
    """``rac resolve --json``."""
    return _dump(result.to_dict())


def render_find_json(result: SearchResult, *, explain: bool = False) -> str:
    """``rac find --json``.

    ``explain`` adds the additive per-match ``evidence`` object (WS2), off by
    default so the standard ``rac find --json`` shape stays byte-stable.
    ``rac find --explain --json`` emits the same ``evidence`` the MCP
    ``search_artifacts`` tool emits — one source of truth (REQ-004).
    """
    return _dump(result.to_dict(include_evidence=explain))


# --- migrate -----------------------------------------------------------------


def render_migrate_json(report: MigrationReport) -> str:
    """``rac migrate metadata --json``."""
    return _dump(report.to_dict())


# --- skill -------------------------------------------------------------------


def render_skill_install_json(installation: SkillInstallation) -> str:
    """``rac skill install --json``."""
    return _dump(installation.to_dict())


def render_skill_list_json(specs: list[SkillSpec]) -> str:
    """``rac skill list --json`` — field order owned here (ADR-007)."""
    return _dump(
        {
            "schema_version": "1",
            "skills": [{"skill": spec.name, "description": spec.description} for spec in specs],
        }
    )


# --- hook --------------------------------------------------------------------


def render_hook_install_json(installation: InstalledHook) -> str:
    """``rac hook install --json``."""
    return _dump(installation.to_dict())


def render_hook_list_json(specs: list[HookSpec]) -> str:
    """``rac hook list --json`` — field order owned here (ADR-007)."""
    return _dump(
        {
            "schema_version": "1",
            "hooks": [{"style": spec.style, "description": spec.description} for spec in specs],
        }
    )


# --- mcp-stats ---------------------------------------------------------------


def render_mcp_stats_json(summary: MCPTelemetrySummary) -> str:
    """``rac mcp-stats --json``.

    Also the voluntary export: ``--share`` URL-encodes this payload (minus the
    local log path) into a prefilled usage-report issue.
    """
    return _dump(summary.to_dict())


# --- watchkeeper -------------------------------------------------------------


def render_watchkeeper_json(report: WatchkeeperReport) -> str:
    """``rac watchkeeper --json``."""
    return _dump(report.to_dict())
