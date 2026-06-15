"""Tests for the Python SDK public surface (v0.20.0, ADR-062).

The SDK contract is: every name in ``rac.__all__`` imports from ``rac``; the
service-layer subset imports from ``rac.services``; and every error a public
function raises derives from ``rac.errors.RACError``.
"""

from __future__ import annotations

import pytest

import rac
import rac.services
from rac import RACError


def test_top_level_all_names_are_importable():
    # The maintained public list cannot drift from what the package exports.
    missing = [name for name in rac.__all__ if not hasattr(rac, name)]
    assert missing == []


def test_service_subset_names_are_importable():
    missing = [name for name in rac.services.__all__ if not hasattr(rac.services, name)]
    assert missing == []


def test_canonical_imports_resolve():
    from rac import (  # noqa: F401 — importability is the assertion
        Product,
        RACError,
        build_review,
        collect_stats,
        create_artifact,
        find_artifacts,
        parse,
        resolve_artifact,
        validate_directory,
        validate_product,
    )


def test_racerror_is_an_exception():
    assert issubclass(RACError, Exception)


@pytest.mark.parametrize(
    "module_path, name",
    [
        ("rac.services.create", "OutputPathExists"),
        ("rac.services.create", "MissingRepositoryConfig"),
        ("rac.services.ingest", "ConversionError"),
        ("rac.services.ingest", "UnsupportedDocument"),
        ("rac.services.init", "RepositoryKeyConflict"),
        ("rac.services.quickstart", "CorpusNotEmpty"),
        ("rac.services.hook", "HookFileExists"),
        ("rac.services.skill", "SkillFileExists"),
        ("rac.services.revisions", "NotAGitRepository"),
        ("rac.core.templates", "TemplateNotFound"),
        ("rac.core.skills", "SkillNotFound"),
        ("rac.core.hooks", "HookNotFound"),
        ("rac.core.operations", "OperationCancelled"),
        ("rac.output.portal", "PortalShellMissing"),
        ("rac.explorer.launch", "ExplorerUnavailable"),
    ],
)
def test_service_exceptions_derive_from_racerror(module_path, name):
    import importlib

    exc = getattr(importlib.import_module(module_path), name)
    assert issubclass(exc, RACError)


def test_raised_service_error_is_caught_as_racerror(tmp_path):
    # A real public call that fails surfaces as RACError without the consumer
    # importing the concrete exception type.
    from rac import create_artifact

    with pytest.raises(RACError):
        create_artifact("not-a-real-type", str(tmp_path / "x.md"))


def test_diff_is_exported_as_diff_artifacts():
    # The generic ``diff`` service name is re-exported under a clearer SDK name.
    assert hasattr(rac, "diff_artifacts")
    assert "diff_artifacts" in rac.__all__
