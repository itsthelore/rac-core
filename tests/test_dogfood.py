"""Dogfood gate: RAC's own corpus must pass RAC (v0.7.9).

REQ-Trust-Transparency FR-9: the planning artifacts under ``rac/`` "shall be
validated by RAC itself where practical". These tests are that enforcement —
they fail CI whenever corpus validation or relationship integrity regresses.

Classification is deliberately not gated: legacy corpus documents that
classify as Unknown remain Unknown (a valid outcome, surfaced as advisory
priority-3 findings by ``rac review``). Normalizing them to their schemas is
deferred — see rac/roadmaps/v0.7.9-repository-review.md, Risks.

The examples corpus under ``examples/guide/rac/`` is also gated here
(v0.10.1): it doubles as the v0.10.2 demo substrate and must stay valid.
"""

from __future__ import annotations

from pathlib import Path

from rac.services.relationships import validate_relationships
from rac.services.review import build_review
from rac.services.validate import validate_directory

CORPUS = str(Path(__file__).parent.parent / "rac")
GUIDE_CORPUS = str(Path(__file__).parent.parent / "examples" / "guide" / "rac")


def test_corpus_artifacts_validate_clean():
    result = validate_directory(CORPUS)
    invalid = [f.path for f in result.files if f.status == "invalid"]
    assert invalid == [], f"invalid corpus artifacts: {invalid}"


def test_corpus_relationships_resolve():
    report = validate_relationships(CORPUS)
    issues = [f"{i.code}: {i.target or i.identifier} ({i.source_path})" for i in report.issues]
    assert report.ok, f"corpus relationship issues: {issues}"


def test_corpus_reviews_ok():
    # The top-level acceptance check: one command, nothing demands attention.
    report = build_review(CORPUS)
    blocking = [i.message for i in report.issues if i.priority <= 2]
    assert report.ok, f"blocking review findings: {blocking}"


# --- examples/guide corpus gate (v0.10.1) ------------------------------------


def test_guide_corpus_artifacts_validate_clean():
    """examples/guide/rac/ must validate clean — it is the demo substrate."""
    result = validate_directory(GUIDE_CORPUS)
    invalid = [f.path for f in result.files if f.status == "invalid"]
    assert invalid == [], f"invalid guide corpus artifacts: {invalid}"


def test_guide_corpus_relationships_resolve():
    """examples/guide/rac/ relationships must resolve without issues."""
    report = validate_relationships(GUIDE_CORPUS)
    issues = [f"{i.code}: {i.target or i.identifier} ({i.source_path})" for i in report.issues]
    assert report.ok, f"guide corpus relationship issues: {issues}"


def test_guide_corpus_has_one_of_each_type():
    """The guide corpus must contain exactly one requirement, decision, design,
    and roadmap — the connected four the implementation contract pins."""
    from rac.services.index import build_repository_index

    index = build_repository_index(GUIDE_CORPUS, recursive=True)
    by_type: dict[str, int] = {}
    for entry in index.artifacts:
        by_type[entry.type] = by_type.get(entry.type, 0) + 1

    for artifact_type in ("requirement", "decision", "design", "roadmap"):
        count = by_type.get(artifact_type, 0)
        assert count == 1, f"guide corpus must have exactly 1 {artifact_type}, found {count}"
