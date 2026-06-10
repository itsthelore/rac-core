"""CI battery guard (v0.7.14): every tests/test_*.py runs in CI.

ADR-027 makes the battery matrix in .github/workflows/tests.yml an explicit,
static enumeration, and accepts that the list must be kept in sync by hand.
This test is the enforcement it anticipated: it fails whenever a test file
is missing from the matrix (a silent orphan that CI would never run) or is
listed in more than one battery.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
TESTS_DIR = REPO_ROOT / "tests"


def _battery_paths() -> list[str]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    batteries = data["jobs"]["pytest"]["strategy"]["matrix"]["battery"]
    paths: list[str] = []
    for battery in batteries:
        paths.extend(battery["paths"].split())
    return paths


def test_every_test_file_belongs_to_exactly_one_battery():
    listed = _battery_paths()

    duplicates = sorted({p for p in listed if listed.count(p) > 1})
    assert duplicates == [], f"test files in more than one battery: {duplicates}"

    actual = sorted(str(p.relative_to(REPO_ROOT)) for p in TESTS_DIR.glob("test_*.py"))
    orphans = sorted(set(actual) - set(listed))
    assert orphans == [], f"test files missing from the CI battery matrix: {orphans}"

    stale = sorted(set(listed) - set(actual))
    assert stale == [], f"battery entries with no matching test file: {stale}"
