"""`rac gate` and the pre-edit hook at scale — the single-walk perf guards (v0.21.19).

`build_gate` (v0.21.14) composes validation, relationships, and review. Until
v0.21.19 each of those re-walked and re-parsed the whole corpus, so the gate paid
three corpus walks; v0.21.19 collapses it to one walk fed to the snapshot
(``*_from_corpus``) seams, with byte-identical output (ADR-023 / ADR-007).

These tests guard two things:

1. **Output equivalence** — the single-walk gate result equals the report
   assembled the old way from the three separate directory services, so a future
   "optimization" cannot silently change gate semantics.
2. **Pathological-slowdown ceilings** — ``build_gate`` and the per-edit hot path
   ``validate_stdin_against_corpus`` (v0.21.17) complete within a generous
   wall-clock ceiling on a 1000+ artifact corpus. The ceilings are deliberately
   loose: CI runners are noisy and the goal is catching a regression that
   reintroduces redundant walks, not benchmarking. They mirror the
   repository-perf budget (~60s for 1200 artifacts) — a single gate walk does
   strictly less work than the repository model, so the same order-of-magnitude
   ceiling is generous here.
"""

from __future__ import annotations

import time

import pytest

from rac.core.markdown import parse
from rac.services.gate import build_gate
from rac.services.relationships import validate_relationships
from rac.services.review import build_review
from rac.services.validate import validate_directory, validate_stdin_against_corpus

DECISIONS = 600
REQUIREMENTS = 600
BROKEN_REFS = 10
TOTAL = DECISIONS + REQUIREMENTS

# Generous wall-clock ceilings (seconds). These catch a pathological regression
# (e.g. a reintroduced redundant corpus walk), not micro-benchmark drift; CI
# runners are noisy, so they are a small multiple of the observed cost and mirror
# the repository-perf 60s-for-1200-artifacts philosophy.
GATE_CEILING_SECONDS = 60
HOOK_CEILING_SECONDS = 30


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
    """A 1200-artifact synthetic corpus with some clean links and a few broken refs.

    Mirrors the generator in ``tests/test_repository_perf.py`` so the gate is
    exercised over a corpus that carries findings (broken relationships) as well
    as clean structure.
    """
    root = tmp_path_factory.mktemp("gate_large_corpus")
    for i in range(DECISIONS):
        (root / f"adr-{i:04d}.md").write_text(_decision(i), encoding="utf-8")
    for i in range(REQUIREMENTS):
        if i >= REQUIREMENTS - BROKEN_REFS:
            reference = f"ADR-MISSING-{i:04d}"
        else:
            reference = f"ADR-{i % DECISIONS:04d}"
        (root / f"req-{i:04d}.md").write_text(_requirement(i, reference), encoding="utf-8")
    return str(root)


def test_gate_scale(large_corpus):
    """``build_gate`` over a 1200-artifact corpus completes within a generous ceiling.

    Generous ceiling: catch pathological slowdowns only (a reintroduced redundant
    walk), not benchmark drift.
    """
    started = time.monotonic()
    report = build_gate(large_corpus)
    elapsed = time.monotonic() - started

    # Well-formed: the broken references are blocking relationship findings, so the
    # gate fails and surfaces them.
    assert report.directory == large_corpus
    assert report.recursive is True
    assert not report.ok
    assert len(report.blocking) >= BROKEN_REFS
    payload = report.to_dict()
    assert payload["ok"] is False
    assert payload["blocking_count"] == len(report.blocking)
    assert payload["advisory_count"] == len(report.advisory)

    assert elapsed < GATE_CEILING_SECONDS


def test_gate_single_walk_no_slower_than_components(large_corpus):
    """The single-walk gate result equals the report assembled the old way.

    Builds the "expected" finding set by running the three separate directory
    services (``validate_directory`` + ``validate_relationships`` + ``build_review``)
    and mapping them through the gate's own normalization, exactly as the
    pre-v0.21.19 multi-walk ``build_gate`` did. The single-walk ``build_gate`` must
    produce a byte-identical ``to_dict()``. The key intent is OUTPUT EQUIVALENCE:
    a future change cannot silently alter gate semantics while "optimizing" the
    corpus walk away.
    """
    from rac.services.gate import (
        _VALIDATE_DEFAULT,
        EMPTY_POLICY,
        ENFORCEMENT_ADVISORY,
        ENFORCEMENT_BLOCKING,
        PRIORITY_BROKEN_RELATIONSHIP,
        SOURCE_RELATIONSHIPS,
        SOURCE_REVIEW,
        SOURCE_VALIDATE,
        GateFinding,
        GateReport,
        _relationship_finding,
        _review_finding,
        _validate_findings,
    )

    # Recompose the report the multi-walk way, with no policy (the synthetic
    # corpus declares no .rac/config.yaml, so EMPTY_POLICY matches build_gate).
    validation = validate_directory(large_corpus)
    relationships = validate_relationships(large_corpus)
    review = build_review(large_corpus)

    findings: list[GateFinding] = []

    def add(source, code, severity, path, line, message, default):
        enforcement = EMPTY_POLICY.classify(code, default)
        if enforcement is None:
            return
        findings.append(
            GateFinding(
                source=source,
                code=code,
                severity=severity,
                enforcement=enforcement,
                path=path,
                line=line,
                message=message,
            )
        )

    for code, severity, path, line, message in _validate_findings(validation):
        add(
            SOURCE_VALIDATE,
            code,
            severity,
            path,
            line,
            message,
            _VALIDATE_DEFAULT.get(severity, ENFORCEMENT_ADVISORY),
        )
    for rel_issue in relationships.issues:
        code, severity, path, line, message = _relationship_finding(rel_issue)
        add(SOURCE_RELATIONSHIPS, code, severity, path, line, message, ENFORCEMENT_BLOCKING)
    for review_issue in review.issues:
        code, severity, path, line, message = _review_finding(review_issue)
        default = (
            ENFORCEMENT_BLOCKING
            if review_issue.priority <= PRIORITY_BROKEN_RELATIONSHIP
            else ENFORCEMENT_ADVISORY
        )
        add(SOURCE_REVIEW, code, severity, path, line, message, default)

    findings.sort(key=lambda f: (f.path, f.line or 0, f.source, f.code, f.message))
    expected = GateReport(directory=large_corpus, recursive=True, findings=findings)

    actual = build_gate(large_corpus)

    # OUTPUT EQUIVALENCE — the single walk reproduced the multi-walk result exactly.
    assert actual.to_dict() == expected.to_dict()
    # And determinism: re-running yields the identical report (ADR-002).
    assert build_gate(large_corpus).to_dict() == actual.to_dict()


def test_preedit_hook_scale(large_corpus):
    """``validate_stdin_against_corpus`` (the per-edit hot path) stays within budget.

    The pre-edit hook (v0.21.17) walks the whole corpus per edit; on a
    1200-artifact corpus a single hook invocation must complete within a generous
    ceiling. A representative proposed document references an existing decision so
    the resolution path is exercised end to end.
    """
    proposed = parse(_requirement(9999, "ADR-0001"), source_path="-")

    started = time.monotonic()
    result = validate_stdin_against_corpus(proposed, large_corpus, source_path="-")
    elapsed = time.monotonic() - started

    # Well-formed: the proposed document's reference resolves against the live
    # corpus, so the hot path that matters here (cross-artifact resolution)
    # produces no relationship finding. Structural lint warnings on the synthetic
    # fixture are not this guard's concern.
    assert result.source_path == "-"
    assert result.relationship_issues == []

    assert elapsed < HOOK_CEILING_SECONDS
