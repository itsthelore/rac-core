"""Release-version verifier tests (REQ-Release-Versioning, ADR-111).

Covers the SemVer identifier grammar (``vX.Y.Z``), the PEP 440 normalised
equivalence, SemVer precedence ordering, rejection of the reverted CalVer form,
and the fail-closed publish gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from asdecided.release import (
    changelog_has_entry,
    is_canonical_release_version,
    parse_release_version,
    verify_release,
)


@pytest.mark.parametrize("version", ["v0.22.0", "v0.22.1", "v1.0.0", "v2.3.10"])
def test_canonical_versions_accepted(version: str) -> None:
    assert is_canonical_release_version(version)
    assert parse_release_version(version) is not None


@pytest.mark.parametrize(
    "version",
    [
        "0.22.0",  # normalised (no v) — valid to parse, not canonical
        "v0.22",  # missing patch
        "v0.22.0.1",  # too many components
        "v01.2.3",  # leading-zero major
        "v0.02.3",  # leading-zero minor
        "2026.06.1",  # reverted CalVer form
        "2026.06.01",  # CalVer with leading-zero counter
        "",
    ],
)
def test_non_canonical_versions_rejected(version: str) -> None:
    assert not is_canonical_release_version(version)


def test_normalised_spelling_parses_equal_to_canonical() -> None:
    # PEP 440 drops the leading ``v`` on the published version; the two spellings
    # MUST map to the same tuple (REQ-009).
    assert parse_release_version("0.22.0") == parse_release_version("v0.22.0") == (0, 22, 0)


@pytest.mark.parametrize("bad", ["v0.22", "v01.2.3", "2026.06.1", "2026.06.01", "nope", ""])
def test_invalid_versions_do_not_parse(bad: str) -> None:
    assert parse_release_version(bad) is None


def test_precedence_is_semver_major_minor_patch() -> None:
    # REQ-003: SemVer precedence over (major, minor, patch) — 0.10.0 sorts above
    # 0.2.0, unlike a lexicographic string sort.
    versions = ["v0.22.1", "v0.2.0", "v0.10.0", "v0.2.1", "v1.0.0"]
    ordered = sorted(versions, key=parse_release_version)
    assert ordered == ["v0.2.0", "v0.2.1", "v0.10.0", "v0.22.1", "v1.0.0"]


def test_changelog_entry_detected_with_and_without_title() -> None:
    assert changelog_has_entry("v0.22.0", '# Changelog\n\n## v0.22.0 — the "scale" release\n')
    assert changelog_has_entry("v0.22.0", "## v0.22.0\n")
    assert not changelog_has_entry("v0.22.0", "## v0.22.1 — later\n")
    # A prefix must not match a longer version (word boundary).
    assert not changelog_has_entry("v0.22.1", "## v0.22.10 — other\n")


def test_verify_release_passes_for_wellformed_with_entry(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text('# Changelog\n\n## v0.22.0 — the "scale" release\n', encoding="utf-8")
    assert verify_release("v0.22.0", changelog) == []


def test_verify_release_fails_closed_on_calver_version(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## 2026.06.1\n", encoding="utf-8")
    errors = verify_release("2026.06.1", changelog)
    assert errors and "canonical" in errors[0]


def test_verify_release_fails_closed_on_missing_entry(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## v0.21.1 — earlier\n", encoding="utf-8")
    errors = verify_release("v0.22.0", changelog)
    assert errors and "no '## v0.22.0' entry" in errors[0]


def test_verify_release_fails_closed_on_unreadable_changelog(tmp_path: Path) -> None:
    errors = verify_release("v0.22.0", tmp_path / "does-not-exist.md")
    assert errors and "could not read changelog" in errors[0]
