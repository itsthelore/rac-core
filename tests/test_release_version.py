"""Release-version verifier tests (REQ-Release-Versioning, ADR-076).

Covers the CalVer identifier grammar (YYYY.MM.N), the PEP 440 normalised
equivalence, precedence ordering, and the fail-closed publish gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.release import (
    changelog_has_entry,
    is_canonical_release_version,
    parse_release_version,
    verify_release,
)


@pytest.mark.parametrize("version", ["2026.06.1", "2026.06.2", "2026.12.1", "2027.01.10"])
def test_canonical_versions_accepted(version: str) -> None:
    assert is_canonical_release_version(version)
    assert parse_release_version(version) is not None


@pytest.mark.parametrize(
    "version",
    [
        "2026.13.1",  # month out of range
        "2026.00.1",  # month zero
        "2026.06.0",  # minor zero
        "2026.06.01",  # leading-zero minor
        "2026.06",  # bare month, no counter
        "2026.6.1",  # not zero-padded — valid to parse, not canonical
        "v0.19.0",  # SemVer tag
        "0.19.0",  # SemVer version
        "",
    ],
)
def test_non_canonical_versions_rejected(version: str) -> None:
    assert not is_canonical_release_version(version)


def test_normalised_spelling_parses_equal_to_canonical() -> None:
    # PEP 440 drops the leading zero on the published version; the two spellings
    # MUST map to the same tuple (REQ-009).
    assert parse_release_version("2026.6.1") == parse_release_version("2026.06.1") == (2026, 6, 1)


@pytest.mark.parametrize("bad", ["2026.13.1", "2026.00.1", "2026.06.0", "2026.06.01", "nope"])
def test_invalid_versions_do_not_parse(bad: str) -> None:
    assert parse_release_version(bad) is None


def test_precedence_is_year_month_minor() -> None:
    # REQ-003: lexicographic over (YYYY, MM, N).
    versions = ["2026.07.1", "2026.06.2", "2026.06.10", "2026.06.1", "2027.01.1"]
    ordered = sorted(versions, key=parse_release_version)
    assert ordered == ["2026.06.1", "2026.06.2", "2026.06.10", "2026.07.1", "2027.01.1"]


def test_changelog_entry_detected_with_and_without_title() -> None:
    assert changelog_has_entry("2026.06.1", "# Changelog\n\n## 2026.06.1 — CalVer cutover\n")
    assert changelog_has_entry("2026.06.1", "## 2026.06.1\n")
    assert not changelog_has_entry("2026.06.1", "## 2026.06.2 — later\n")
    # A prefix must not match a longer version (word boundary).
    assert not changelog_has_entry("2026.06.1", "## 2026.06.10 — other\n")


def test_verify_release_passes_for_wellformed_with_entry(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## 2026.06.1 — CalVer cutover\n", encoding="utf-8")
    assert verify_release("2026.06.1", changelog) == []


def test_verify_release_fails_closed_on_bad_version(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## 2026.06.1\n", encoding="utf-8")
    errors = verify_release("v0.20.0", changelog)
    assert errors and "canonical" in errors[0]


def test_verify_release_fails_closed_on_missing_entry(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## 2026.05.1 — earlier\n", encoding="utf-8")
    errors = verify_release("2026.06.1", changelog)
    assert errors and "no '## 2026.06.1' entry" in errors[0]


def test_verify_release_fails_closed_on_unreadable_changelog(tmp_path: Path) -> None:
    errors = verify_release("2026.06.1", tmp_path / "does-not-exist.md")
    assert errors and "could not read changelog" in errors[0]
