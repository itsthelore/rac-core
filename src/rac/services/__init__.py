"""RAC service layer.

Repository and artifact capabilities — inspection, improvement, relationship
operations, portfolio/repository intelligence, ingestion, and diffing. Services
provide stable APIs consumed by the CLI, Explorer, tests, and future
integrations (ADR-008, ADR-015). They depend on :mod:`rac.core`, never on the
CLI or output layers.

The names re-exported here are the SDK's service surface (ADR-062): a consumer
imports them flat — ``from rac.services import build_review`` — instead of
reaching into individual modules. The top-level :mod:`rac` package re-exports
the same set, so ``from rac import build_review`` is the canonical form.
"""

from rac.services.create import CreatedArtifact, create_artifact
from rac.services.diff import diff as diff_artifacts
from rac.services.export import build_corpus_export
from rac.services.improve import improve_product
from rac.services.index import build_repository_index
from rac.services.ingest import ingest
from rac.services.init import init_repository
from rac.services.inspect import build_inspection, inspect_directory
from rac.services.migrate import migrate_metadata
from rac.services.portfolio import build_portfolio_summary
from rac.services.quickstart import quickstart
from rac.services.recency import artifact_recency
from rac.services.relationships import (
    build_relationship_report,
    relationships_from_corpus,
    summarize_relationships,
    validate_relationships,
)
from rac.services.resolve import find_artifacts, resolve_artifact
from rac.services.review import build_review
from rac.services.stats import collect_stats
from rac.services.validate import validate_directory, validate_product
from rac.services.watchkeeper import build_watchkeeper_report

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
