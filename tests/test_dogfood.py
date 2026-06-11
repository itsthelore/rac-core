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

The v0.10.2 grounding demo additionally depends on the *searchability* of that
substrate: the natural keywords an agent would use for the demo task must
surface ADR-001 through the same search path ``search_artifacts`` uses, and the
decision must be retrievable with its content and its related artifacts. Those
mechanics are pinned here so a description or corpus change that silently breaks
the demo fails CI (``examples/guide/demo.md``).
"""

from __future__ import annotations

from pathlib import Path

from rac.services.relationships import validate_relationships
from rac.services.resolve import find_artifacts, resolve_artifact
from rac.services.review import build_review
from rac.services.validate import validate_directory

CORPUS = str(Path(__file__).parent.parent / "rac")
GUIDE_ROOT = str(Path(__file__).parent.parent / "examples" / "guide")
GUIDE_CORPUS = str(Path(__file__).parent.parent / "examples" / "guide" / "rac")

# The decision the grounding demo turns on (examples/guide/rac/, demo.md).
DEMO_DECISION_ID = "GUIDE-KTW9YBDWDBFM"


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


# --- grounding demo searchability gate (v0.10.2) -----------------------------
#
# The grounded run only works if a keyword the agent would naturally reach for
# hits the decision through the search path search_artifacts uses (find_artifacts
# semantics — id/title/path substring match, no body text). These pin the
# scenario named in examples/guide/demo.md so a corpus rename can't silently
# break the demo. The demo searches the whole guide root (--root examples/guide),
# matching the configured MCP server.


def test_demo_keywords_surface_the_decision():
    """The natural task keywords surface ADR-001 as the top decision match."""
    for query in ("delete user", "delete", "soft-delete"):
        result = find_artifacts(GUIDE_ROOT, query, artifact_type="decision")
        ids = [m.id for m in result.matches]
        assert DEMO_DECISION_ID in ids, f"{query!r} did not surface {DEMO_DECISION_ID}: {ids}"


def test_demo_decision_resolves_with_content():
    """get_artifact's resolver finds the decision and its content carries the
    hard-DELETE prohibition the grounded agent must cite."""
    resolution = resolve_artifact(GUIDE_ROOT, DEMO_DECISION_ID)
    assert resolution.outcome == "resolved"
    assert resolution.artifact is not None
    assert resolution.artifact.type == "decision"
    text = Path(resolution.artifact.path).read_text(encoding="utf-8")
    assert "Soft-Delete User Records" in text
    assert "prohibited" in text


def test_demo_decision_has_related_artifacts_to_show():
    """get_related has something to show: the decision is connected to the
    requirement, design, and roadmap the demo references."""
    report = validate_relationships(GUIDE_CORPUS)
    assert report.ok
    # The decision declares a requirement and a design (outgoing); the design and
    # roadmap point back at it (incoming) — enough for get_related to surface.
    resolution = resolve_artifact(GUIDE_CORPUS, DEMO_DECISION_ID)
    text = Path(resolution.artifact.path).read_text(encoding="utf-8")
    assert "## Related Requirements" in text
    assert "## Related Designs" in text
