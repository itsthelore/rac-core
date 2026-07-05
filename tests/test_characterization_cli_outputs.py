"""Characterization pins for CLI surfaces with no byte-level golden (rebuild).

The frozen suite is about to become the spec for a full internal rebuild. A
handful of read-only commands publish human and ``--json`` output that other
golden tests never byte-pin: ``index``, ``portfolio``, ``coverage``,
``inspect``, and ``improve``. Their ordering, field set, and formatting are an
observable contract (ADR-007) that the rebuild could silently drift.

Each case runs one CLI invocation through the same harness the goldens use
(plain output, repo-root cwd) and compares stdout byte-for-byte against a
committed expected file under ``tests/fixtures/characterization/``. The fixtures
these run against are static Markdown (no git-derived recency), so the output is
deterministic without controlling git state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.cli import main

REPO_ROOT = Path(__file__).parent.parent
EXPECTED_DIR = Path(__file__).parent / "fixtures" / "characterization"

# (name, argv, expected exit code). Paths are relative to the repository root
# (the test chdirs there) so expected files stay machine-independent.
CASES = [
    ("index_human", ["index", "tests/fixtures/portfolio_summary/all_types"], 0),
    ("index_json", ["index", "tests/fixtures/portfolio_summary/all_types", "--json"], 0),
    ("portfolio_human", ["portfolio", "tests/fixtures/portfolio_summary/all_types"], 0),
    ("portfolio_json", ["portfolio", "tests/fixtures/portfolio_summary/all_types", "--json"], 0),
    ("coverage_human", ["coverage", "tests/fixtures/portfolio_summary/all_types"], 0),
    ("coverage_json", ["coverage", "tests/fixtures/portfolio_summary/all_types", "--json"], 0),
    ("inspect_human", ["inspect", "tests/fixtures/valid/feature.md"], 0),
    ("inspect_json", ["inspect", "tests/fixtures/valid/feature.md", "--json"], 0),
    ("improve_human", ["improve", "tests/fixtures/valid/feature.md"], 0),
    ("improve_json", ["improve", "tests/fixtures/valid/feature.md", "--json"], 0),
]


@pytest.mark.parametrize("name,argv,expected_rc", CASES, ids=[c[0] for c in CASES])
def test_cli_output_is_byte_stable(name, argv, expected_rc, capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    # Force plain output: expected files must not depend on whether the test
    # runner happens to attach a TTY (same seam the goldens pin against).
    monkeypatch.setattr("rac.output.human._USE_COLOR", False)

    rc = main(argv)
    out = capsys.readouterr().out

    expected = (EXPECTED_DIR / f"{name}.txt").read_text(encoding="utf-8")
    assert rc == expected_rc
    assert out == expected, f"Output of `rac {' '.join(argv)}` drifted from the frozen pin."
