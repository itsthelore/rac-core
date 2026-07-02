"""Release-version verification — the fail-closed CalVer gate (ADR-076).

RAC releases use a CalVer identifier ``YYYY.MM.N`` (REQ-Release-Versioning):
the UTC year and zero-padded month a release is cut, plus a within-month
counter starting at 1. The identifier carries no compatibility signal — that
lives on ``schema_version`` (ADR-007). This module is the fail-closed check
REQ-007 requires: a release whose version is not a well-formed ``YYYY.MM.N``
identifier, or that has no matching ``CHANGELOG.md`` entry, must not publish.

This is internal release tooling, outside RAC's public CLI and SDK surface
(ADR-005, ADR-062): the publish workflow invokes it as ``python -m rac.release
<version>``; it is never exported through ``rac.__all__``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Canonical identifier: four-digit year, zero-padded month 01-12, and a counter
# from 1 with no leading zero and no `.0`. This is the form a release tag MUST
# use (REQ-001/002/009).
_CANONICAL_RE = re.compile(r"^(?P<year>\d{4})\.(?P<month>0[1-9]|1[0-2])\.(?P<minor>[1-9]\d*)$")

# Lenient parse: also accepts the PEP 440 normalised spelling (unpadded month,
# e.g. `2026.6.1`) that packaging tools emit, so both spellings compare equal
# (REQ-009). The counter still rejects `.0` and a leading zero.
_PARSE_RE = re.compile(r"^(?P<year>\d{4})\.(?P<month>\d{1,2})\.(?P<minor>[1-9]\d*)$")


def parse_release_version(version: str) -> tuple[int, int, int] | None:
    """Return ``(year, month, minor)`` for a release version, else ``None``.

    Accepts the canonical zero-padded form (``2026.06.1``) and its PEP 440
    normalised spelling (``2026.6.1``) so both map to the same tuple (REQ-009).
    Rejects an out-of-range month and any non-``YYYY.MM.N`` string.
    """
    match = _PARSE_RE.match(version.strip())
    if match is None:
        return None
    year, month, minor = int(match["year"]), int(match["month"]), int(match["minor"])
    if not 1 <= month <= 12:
        return None
    return (year, month, minor)


def is_canonical_release_version(version: str) -> bool:
    """True when ``version`` is the canonical, zero-padded ``YYYY.MM.N`` tag form."""
    return _CANONICAL_RE.match(version.strip()) is not None


def changelog_has_entry(version: str, changelog: str) -> bool:
    """True when the changelog text has a ``## <version>`` heading (REQ-005).

    The trailing class after the version is a word boundary, so ``## 2026.06.10``
    does not satisfy a lookup for ``2026.06.1``.
    """
    pattern = rf"^##\s+{re.escape(version.strip())}(?:\s|—|-|$)"
    return re.search(pattern, changelog, re.MULTILINE) is not None


def verify_release(version: str, changelog_path: Path) -> list[str]:
    """Return the reasons ``version`` must not publish; empty means it may.

    Fail-closed (REQ-007): an ill-formed version or a missing changelog entry is
    an error, and an unreadable changelog is treated as a missing entry rather
    than waved through. A malformed version stops the check before the changelog
    is even read — it could not have a meaningful entry.
    """
    if not is_canonical_release_version(version):
        return [
            f"version {version!r} is not a canonical CalVer release identifier "
            "(expected YYYY.MM.N, zero-padded month, counter from 1)"
        ]
    try:
        changelog = changelog_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"could not read changelog at {changelog_path}: {exc}"]
    if not changelog_has_entry(version, changelog):
        return [f"no '## {version}' entry found in {changelog_path.name} (REQ-005)"]
    return []


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m rac.release <version> [changelog-path]``."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m rac.release <version> [changelog-path]", file=sys.stderr)
        return 2
    version = args[0]
    changelog_path = Path(args[1]) if len(args) > 1 else Path("CHANGELOG.md")
    errors = verify_release(version, changelog_path)
    if errors:
        print(f"✗ release {version} rejected:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"✓ release {version} is well-formed and has a changelog entry")
    return 0


if __name__ == "__main__":  # pragma: no cover - module CLI shim
    raise SystemExit(main())
