"""Dogfood gate: RAC's own corpus must pass RAC (v0.7.9).

REQ-Trust-Transparency FR-9: the planning artifacts under ``rac/`` "shall be
validated by RAC itself where practical". These tests are that enforcement —
they fail CI whenever corpus validation or relationship integrity regresses.

Classification is deliberately not gated: legacy corpus documents that
classify as Unknown remain Unknown (a valid outcome, surfaced as advisory
priority-3 findings by ``rac review``). Normalizing them to their schemas is
deferred — see rac/roadmaps/v0.7.9-repository-review.md, Risks.
"""

from __future__ import annotations

from pathlib import Path

from rac.services.relationships import validate_relationships
from rac.services.review import build_review
from rac.services.validate import validate_directory

CORPUS = str(Path(__file__).parent.parent / "rac")


def test_corpus_artifacts_validate_clean():
    result = validate_directory(CORPUS)
    invalid = [f.path for f in result.files if f.status == "invalid"]
    assert invalid == [], f"invalid corpus artifacts: {invalid}"


def test_corpus_relationships_resolve():
    report = validate_relationships(CORPUS)
    issues = [
        f"{i.code}: {i.target or i.identifier} ({i.source_path})"
        for i in report.issues
    ]
    assert report.ok, f"corpus relationship issues: {issues}"


def test_corpus_reviews_ok():
    # The top-level acceptance check: one command, nothing demands attention.
    report = build_review(CORPUS)
    blocking = [i.message for i in report.issues if i.priority <= 2]
    assert report.ok, f"blocking review findings: {blocking}"
