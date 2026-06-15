"""RAC — Requirements As Code.

A small CLI *and* Python SDK for linting, diffing, and reasoning about
product-management artifacts written in Markdown. Markdown is the source format;
the Product AST (see :mod:`rac.core.models`) is the internal model that
validation and diffing operate on.

The names exported here are the SDK's public surface (ADR-062): everything in
:data:`__all__` is importable directly from ``rac`` —

    from rac import validate_directory, collect_stats, RACError

    result = validate_directory("rac/")
    if not result.ok:
        ...

Every error a public function raises derives from :class:`rac.errors.RACError`,
so one ``except RACError`` catches the whole family. Result objects expose a
stable ``to_dict()`` JSON contract (ADR-007). Anything not listed in
:data:`__all__` (modules under :mod:`rac.core`, ``rac.cli``, output renderers)
is internal and may change without notice.
"""

from importlib.metadata import PackageNotFoundError, version

from rac.core.classification import classify
from rac.core.markdown import parse, parse_file
from rac.core.models import Issue, Product
from rac.core.validation import has_errors, validate
from rac.errors import RACError
from rac.services import (
    CreatedArtifact,
    artifact_recency,
    build_corpus_export,
    build_inspection,
    build_portfolio_summary,
    build_relationship_report,
    build_repository_index,
    build_review,
    build_watchkeeper_report,
    collect_stats,
    create_artifact,
    diff_artifacts,
    find_artifacts,
    improve_product,
    ingest,
    init_repository,
    inspect_directory,
    migrate_metadata,
    quickstart,
    relationships_from_corpus,
    resolve_artifact,
    summarize_relationships,
    validate_directory,
    validate_product,
    validate_relationships,
)

try:
    # Single source of truth: the version declared in pyproject.toml and
    # baked into the installed distribution. Keeps `rac --version` in sync.
    __version__ = version("requirements-as-code")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    # Errors — the root every RAC exception derives from (ADR-062).
    "RACError",
    # Core authoring primitives (Markdown ↔ Product AST).
    "Product",
    "Issue",
    "parse",
    "parse_file",
    "classify",
    "validate",
    "has_errors",
    # Validation services.
    "validate_product",
    "validate_directory",
    "validate_relationships",
    # Portfolio / repository intelligence.
    "collect_stats",
    "build_review",
    "build_portfolio_summary",
    "build_repository_index",
    "summarize_relationships",
    "build_relationship_report",
    "relationships_from_corpus",
    "artifact_recency",
    "build_watchkeeper_report",
    # Lookup.
    "resolve_artifact",
    "find_artifacts",
    # Authoring / lifecycle.
    "create_artifact",
    "CreatedArtifact",
    "quickstart",
    "init_repository",
    "improve_product",
    "build_inspection",
    "inspect_directory",
    "ingest",
    "diff_artifacts",
    "migrate_metadata",
    "build_corpus_export",
]
