"""Golden output tests (v0.7.9) — REQ-Trust-Transparency FR-4.

Each case runs one CLI invocation and compares stdout byte-for-byte against a
committed golden file in ``tests/golden/``. RAC's output is a public contract
(human output for people, JSON for automation, ADR-007); any drift here is a
product change and must be reviewed as one.

To refresh the goldens after an intentional output change:

    RAC_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py

then commit the diff.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rac.cli import main

REPO_ROOT = Path(__file__).parent.parent
GOLDEN_DIR = Path(__file__).parent / "golden"

# (name, argv, expected exit code). Paths are relative to the repository root
# (the tests chdir there) so golden files stay machine-independent.
CASES = [
    ("validate_valid_human", ["validate", "tests/fixtures/valid/feature.md"], 0),
    ("validate_valid_json", ["validate", "tests/fixtures/valid/feature.md", "--json"], 0),
    ("validate_invalid_human", ["validate", "tests/fixtures/invalid/duplicate_ids.md"], 1),
    ("validate_invalid_json", ["validate", "tests/fixtures/invalid/duplicate_ids.md", "--json"], 1),
    ("validate_dir_human", ["validate", "tests/fixtures/portfolio"], 1),
    ("validate_dir_json", ["validate", "tests/fixtures/portfolio", "--json"], 1),
    ("stats_human", ["stats", "tests/fixtures/valid"], 0),
    ("stats_json", ["stats", "tests/fixtures/valid", "--json"], 0),
    (
        "diff_human",
        ["diff", "examples/example_dashboard_v1.md", "examples/example_dashboard_v2.md"],
        0,
    ),
    (
        "diff_json",
        ["diff", "examples/example_dashboard_v1.md", "examples/example_dashboard_v2.md", "--json"],
        0,
    ),
    ("schema_requirement_human", ["schema", "requirement"], 0),
    ("schema_requirement_template", ["schema", "requirement", "--template"], 0),
    ("review_human", ["review", "tests/fixtures/portfolio"], 1),
    ("review_json", ["review", "tests/fixtures/portfolio", "--json"], 1),
    # Directory-to-directory comparison: goldens never depend on git state.
    (
        "watchkeeper_human",
        [
            "watchkeeper",
            "tests/fixtures/watchkeeper/head",
            "--base",
            "tests/fixtures/watchkeeper/base",
        ],
        1,
    ),
    (
        "watchkeeper_json",
        [
            "watchkeeper",
            "tests/fixtures/watchkeeper/head",
            "--base",
            "tests/fixtures/watchkeeper/base",
            "--json",
        ],
        1,
    ),
    # Golden output captures stdout only; the github annotations stream to
    # stderr by design and are pinned by tests/test_watchkeeper.py instead.
    (
        "watchkeeper_github",
        [
            "watchkeeper",
            "tests/fixtures/watchkeeper/head",
            "--base",
            "tests/fixtures/watchkeeper/base",
            "--format",
            "github",
        ],
        1,
    ),
    ("templates_human", ["templates"], 0),
    ("templates_json", ["templates", "--json"], 0),
    ("resolve_human", ["resolve", "RAC-01JY4M8X2QZ7", "tests/fixtures/resolve"], 0),
    ("resolve_json", ["resolve", "RAC-01JY4M8X2QZ7", "tests/fixtures/resolve", "--json"], 0),
    (
        "resolve_not_found_json",
        ["resolve", "RAC-ZZZZZZZZZZZZ", "tests/fixtures/resolve", "--json"],
        1,
    ),
    ("find_human", ["find", "markdown", "tests/fixtures/resolve"], 0),
    ("find_json", ["find", "markdown", "tests/fixtures/resolve", "--json"], 0),
    ("relationships_resolved_human", ["relationships", "tests/fixtures/resolve"], 0),
    ("migrate_dry_run_human", ["migrate", "metadata", "tests/fixtures/migrate", "--dry-run"], 0),
    (
        "migrate_dry_run_json",
        ["migrate", "metadata", "tests/fixtures/migrate", "--dry-run", "--json"],
        0,
    ),
    ("mcp_stats_human", ["mcp-stats"], 0),
    ("mcp_stats_json", ["mcp-stats", "--json"], 0),
    ("mcp_stats_share", ["mcp-stats", "--share"], 0),
]


@pytest.mark.parametrize("name,argv,expected_rc", CASES, ids=[c[0] for c in CASES])
def test_golden(name, argv, expected_rc, capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    # Force plain output: golden files must not depend on whether the test
    # runner happens to attach a TTY.
    monkeypatch.setattr("rac.output.human._USE_COLOR", False)
    # Deterministic IDs for migrate cases (dry runs, so fixtures stay clean);
    # the suffix is valid Crockford base32. Same seam pattern as _USE_COLOR.
    monkeypatch.setattr(
        "rac.services.migrate._DEFAULT_ID_GENERATOR",
        lambda key: f"{key}-00000000TEST",
    )
    # A relative state home keeps the mcp-stats log path machine-independent
    # in golden output; only the mcp-stats cases read it.
    monkeypatch.setenv("XDG_STATE_HOME", "tests/fixtures/telemetry/state")

    rc = main(argv)
    out = capsys.readouterr().out

    golden = GOLDEN_DIR / f"{name}.txt"
    if os.environ.get("RAC_UPDATE_GOLDEN") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(out, encoding="utf-8")

    assert rc == expected_rc
    assert out == golden.read_text(encoding="utf-8"), (
        f"Output of `rac {' '.join(argv)}` drifted from {golden}.\n"
        "If the change is intentional, refresh with: "
        "RAC_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py"
    )
