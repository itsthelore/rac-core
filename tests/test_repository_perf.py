"""Repository model at scale — the 1000+ artifact target (v0.8.0).

Generates a synthetic corpus once per session and validates correctness,
progress, and cancellation at repository scale. Wall-clock time is asserted
only against a generous ceiling — CI runners are noisy, and the goal is
catching pathological slowdowns, not benchmarking.
"""

from __future__ import annotations

import time

import pytest

from asdecided.core.operations import CancellationToken, OperationCancelled, Progress
from asdecided.services.repository import SOURCE_RELATIONSHIPS, load_repository

DECISIONS = 600
REQUIREMENTS = 600
BROKEN_REFS = 10
TOTAL = DECISIONS + REQUIREMENTS


def _decision(i: int) -> str:
    return (
        f"# ADR-{i:04d} Decision {i}\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nGenerated corpus entry.\n\n"
        "## Decision\n\nUse the generated approach.\n\n"
        "## Consequences\n\nNone — synthetic fixture.\n"
    )


def _requirement(i: int, reference: str) -> str:
    return (
        f"# Feature {i}\n\n"
        "## Problem\n\nGenerated corpus entry.\n\n"
        "## Requirements\n\n"
        f"[REQ-{i:04d}] The system shall handle case {i}.\n\n"
        "## Related Decisions\n\n"
        f"- {reference}\n"
    )


@pytest.fixture(scope="session")
def large_corpus(tmp_path_factory) -> str:
    root = tmp_path_factory.mktemp("large_corpus")
    for i in range(DECISIONS):
        (root / f"adr-{i:04d}.md").write_text(_decision(i), encoding="utf-8")
    for i in range(REQUIREMENTS):
        # The last BROKEN_REFS requirements reference artifacts that do not
        # exist, so the corpus carries findings as well as clean links.
        if i >= REQUIREMENTS - BROKEN_REFS:
            reference = f"ADR-MISSING-{i:04d}"
        else:
            reference = f"ADR-{i % DECISIONS:04d}"
        (root / f"req-{i:04d}.md").write_text(_requirement(i, reference), encoding="utf-8")
    return str(root)


def test_scale_counts_and_diagnostics(large_corpus):
    started = time.monotonic()
    repo = load_repository(large_corpus)
    elapsed = time.monotonic() - started

    assert len(repo.artifacts) == TOTAL
    assert len(repo.artifacts_of_type("decision")) == DECISIONS
    assert len(repo.artifacts_of_type("requirement")) == REQUIREMENTS
    assert len(repo.relationships) == REQUIREMENTS

    broken = [d for d in repo.diagnostics if d.source == SOURCE_RELATIONSHIPS]
    assert len(broken) == BROKEN_REFS
    assert repo.portfolio.relationships.broken == BROKEN_REFS

    # Generous ceiling: catch pathological slowdowns only.
    assert elapsed < 60


def test_scale_progress_is_monotonic_and_complete(large_corpus):
    reports: list[Progress] = []
    load_repository(large_corpus, on_progress=reports.append)

    scan = [r for r in reports if r.phase == "scan"]
    assert [r.completed for r in scan] == list(range(1, TOTAL + 1))
    assert {r.total for r in scan} == {TOTAL}
    assert [r.phase for r in reports if r.phase != "scan"] == [
        "index",
        "validate",
        "relationships",
        "portfolio",
    ]


def test_scale_cancellation_aborts_early(large_corpus):
    token = CancellationToken()
    reports: list[Progress] = []

    def cancel_after_fifty(progress: Progress) -> None:
        reports.append(progress)
        if progress.completed == 50:
            token.cancel()

    with pytest.raises(OperationCancelled):
        load_repository(large_corpus, on_progress=cancel_after_fifty, cancel=token)
    assert len(reports) == 50
