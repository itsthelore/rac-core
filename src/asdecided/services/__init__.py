"""RAC service layer.

Repository and artifact capabilities — inspection, improvement, relationship
operations, portfolio/repository intelligence, ingestion, and diffing. Services
provide stable APIs consumed by the CLI, Explorer, tests, and future
integrations (ADR-008, ADR-015). They depend on :mod:`asdecided.core`, never on the
CLI or output layers.

The names re-exported here are the SDK's service surface (ADR-062): a consumer
imports them flat — ``from asdecided.services import build_review`` — instead of
reaching into individual modules. The top-level :mod:`rac` package re-exports
the same set, so ``from asdecided import build_review`` is the canonical form.
"""

from asdecided.services.create import CreatedArtifact, create_artifact
from asdecided.services.diff import diff as diff_artifacts
from asdecided.services.export import build_corpus_export
from asdecided.services.improve import improve_product
from asdecided.services.index import build_repository_index
from asdecided.services.ingest import ingest
from asdecided.services.init import init_repository
from asdecided.services.inspect import build_inspection, inspect_directory
from asdecided.services.migrate import migrate_metadata
from asdecided.services.portfolio import build_portfolio_summary
from asdecided.services.quickstart import quickstart
from asdecided.services.recency import artifact_recency
from asdecided.services.relationships import (
    build_relationship_report,
    relationships_from_corpus,
    summarize_relationships,
    validate_relationships,
)
from asdecided.services.resolve import find_artifacts, resolve_artifact
from asdecided.services.review import build_review
from asdecided.services.stats import collect_stats
from asdecided.services.validate import validate_directory, validate_product
from asdecided.services.watchkeeper import build_watchkeeper_report

__all__ = [
    "CreatedArtifact",
    "create_artifact",
    "diff_artifacts",
    "build_corpus_export",
    "improve_product",
    "build_repository_index",
    "ingest",
    "init_repository",
    "build_inspection",
    "inspect_directory",
    "migrate_metadata",
    "build_portfolio_summary",
    "quickstart",
    "artifact_recency",
    "build_relationship_report",
    "relationships_from_corpus",
    "summarize_relationships",
    "validate_relationships",
    "find_artifacts",
    "resolve_artifact",
    "build_review",
    "collect_stats",
    "validate_directory",
    "validate_product",
    "build_watchkeeper_report",
]
