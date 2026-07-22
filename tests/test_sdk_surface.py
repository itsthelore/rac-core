"""Tests for the Python SDK public surface (v0.20.0, ADR-062).

The SDK contract is: every name in ``asdecided.__all__`` imports from ``asdecided``; the
service-layer subset imports from ``asdecided.services``; and every error a public
function raises derives from ``asdecided.errors.RACError``.
"""

from __future__ import annotations

import pytest

import asdecided
import asdecided.services
from asdecided import RACError


def test_top_level_all_names_are_importable():
    # The maintained public list cannot drift from what the package exports.
    missing = [name for name in asdecided.__all__ if not hasattr(asdecided, name)]
    assert missing == []


def test_service_subset_names_are_importable():
    missing = [name for name in asdecided.services.__all__ if not hasattr(asdecided.services, name)]
    assert missing == []


def test_canonical_imports_resolve():
    from asdecided import (  # noqa: F401 — importability is the assertion
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
        ("asdecided.services.create", "OutputPathExists"),
        ("asdecided.services.create", "MissingRepositoryConfig"),
        ("asdecided.services.ingest", "ConversionError"),
        ("asdecided.services.ingest", "UnsupportedDocument"),
        ("asdecided.services.init", "RepositoryKeyConflict"),
        ("asdecided.services.quickstart", "CorpusNotEmpty"),
        ("asdecided.services.hook", "HookFileExists"),
        ("asdecided.services.skill", "SkillFileExists"),
        ("asdecided.services.revisions", "NotAGitRepository"),
        ("asdecided.core.templates", "TemplateNotFound"),
        ("asdecided.core.skills", "SkillNotFound"),
        ("asdecided.core.hooks", "HookNotFound"),
        ("asdecided.core.operations", "OperationCancelled"),
        ("asdecided.output.portal", "PortalShellMissing"),
        ("asdecided.explorer.launch", "ExplorerUnavailable"),
    ],
)
def test_service_exceptions_derive_from_racerror(module_path, name):
    import importlib

    exc = getattr(importlib.import_module(module_path), name)
    assert issubclass(exc, RACError)


def test_raised_service_error_is_caught_as_racerror(tmp_path):
    # A real public call that fails surfaces as RACError without the consumer
    # importing the concrete exception type.
    from asdecided import create_artifact

    with pytest.raises(RACError):
        create_artifact("not-a-real-type", str(tmp_path / "x.md"))


def test_diff_is_exported_as_diff_artifacts():
    # The generic ``diff`` service name is re-exported under a clearer SDK name.
    assert hasattr(asdecided, "diff_artifacts")
    assert "diff_artifacts" in asdecided.__all__
