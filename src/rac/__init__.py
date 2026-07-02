"""RAC — Requirements As Code.

A small CLI *and* Python SDK for linting, diffing, and reasoning about
product-management artifacts written in Markdown. Markdown is the source of
truth; the Product AST (:mod:`rac.core.models`) is the internal model that
validation, diffing, and the higher-level services operate on.

The names bound here are the SDK's public surface (ADR-062): the members of
:data:`__all__` are exactly what a consumer may import from ``rac`` —

    from rac import validate_directory, collect_stats, RACError

    result = validate_directory("rac/")
    if not result.ok:
        ...

Every error a public function raises derives from :class:`rac.errors.RACError`,
so a single ``except RACError`` catches the whole family. Result objects expose
a stable ``to_dict()`` JSON contract (ADR-007). Anything not listed in
:data:`__all__` — modules under :mod:`rac.core`, :mod:`rac.cli`, the output
renderers — is internal and may change without notice.
"""

from __future__ import annotations

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

# ``__version__`` is a live, runtime-settable module global. The distribution is
# ``rac-core`` (not ``rac``); ``rac --version`` and every payload that stamps a
# version — the export JSON, the eval scorecard, the SARIF tool block, the
# anonymous ping — read this name at call time. Tests monkeypatch it, so it must
# stay a plain reassignable attribute, never frozen behind a captured local.
try:
    __version__ = version("rac-core")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    # The root every RAC exception derives from (ADR-062).
    "RACError",
    # Core authoring primitives: Markdown <-> Product AST.
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
    # Portfolio and repository intelligence.
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
    # Authoring and lifecycle.
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
