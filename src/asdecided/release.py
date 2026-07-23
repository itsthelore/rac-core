"""Release-version verification — the fail-closed SemVer gate.

RAC releases use a SemVer identifier ``vX.Y.Z`` (REQ-Release-Versioning,
ADR-111, which reverted the CalVer of ADR-076): major, minor, patch, with the
canonical tag form ``v``-prefixed and the PEP 440 normalised distribution form
dropping the prefix (``v0.22.0`` ⇔ ``0.22.0``). The identifier carries no
machine-resolved compatibility contract — that lives on ``schema_version``
(ADR-007). This module is the fail-closed verification REQ-007 requires: a
release whose version is not a well-formed ``vX.Y.Z`` identifier (a ``YYYY.MM.N``
CalVer tag is rejected), or that has no matching ``CHANGELOG.md`` entry, must not
be published.

This is internal release tooling, not part of RAC's public CLI or SDK surface
(ADR-005, ADR-062): it is invoked by the publish workflow as ``python -m
asdecided.release <version>``, never exported through ``asdecided.__all__``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# A SemVer component: ``0`` or a non-zero-leading run of digits (no leading
# zeros, REQ-001). Reused for major, minor, and patch.
_COMPONENT = r"(?:0|[1-9]\d*)"

# Canonical identifier: the ``v``-prefixed tag form a release MUST use
# (REQ-001/009), e.g. ``v0.22.0``.
_CANONICAL_RE = re.compile(
    rf"^v(?P<major>{_COMPONENT})\.(?P<minor>{_COMPONENT})\.(?P<patch>{_COMPONENT})$"
)

# Lenient parse: also accepts the PEP 440 normalised spelling without the ``v``
# prefix (``0.22.0``), which packaging tools emit, so the two spellings compare
# equal (REQ-009). Leading zeros are still rejected.
_PARSE_RE = re.compile(
    rf"^v?(?P<major>{_COMPONENT})\.(?P<minor>{_COMPONENT})\.(?P<patch>{_COMPONENT})$"
)


def parse_release_version(version: str) -> tuple[int, int, int] | None:
    """Return ``(major, minor, patch)`` for a release version, else ``None``.

    Accepts both the canonical ``v``-prefixed tag form (``v0.22.0``) and its
    PEP 440 normalised spelling (``0.22.0``) so they map to the same tuple
    (REQ-009). Rejects leading zeros, a missing component, and any non-SemVer
    string — a ``YYYY.MM.N`` CalVer tag such as ``2026.06.1`` fails because its
    zero-padded month is a leading-zero component.
    """
    match = _PARSE_RE.match(version.strip())
    if match is None:
        return None
    return (int(match["major"]), int(match["minor"]), int(match["patch"]))


def is_canonical_release_version(version: str) -> bool:
    """True when ``version`` is the canonical, ``v``-prefixed ``vX.Y.Z`` tag form."""
    return _CANONICAL_RE.match(version.strip()) is not None


def changelog_has_entry(version: str, changelog: str) -> bool:
    """True when ``CHANGELOG.md`` text has a ``## <version>`` heading (REQ-005)."""
    pattern = rf"^##\s+{re.escape(version.strip())}(?:\s|—|-|$)"
    return re.search(pattern, changelog, re.MULTILINE) is not None


def verify_release(version: str, changelog_path: Path) -> list[str]:
    """Return the reasons ``version`` must not publish; empty means it may.

    Fail-closed (REQ-007): an ill-formed version or a missing changelog entry is
    an error, and an unreadable changelog is treated as a missing entry rather
    than passed over.
    """
    errors: list[str] = []
    if not is_canonical_release_version(version):
        errors.append(
            f"version {version!r} is not a canonical SemVer release identifier "
            "(expected v-prefixed vX.Y.Z, no leading zeros; CalVer YYYY.MM.N is rejected)"
        )
        # A malformed version cannot have a meaningful changelog entry; stop here.
        return errors
    try:
        changelog = changelog_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"could not read changelog at {changelog_path}: {exc}")
        return errors
    if not changelog_has_entry(version, changelog):
        errors.append(f"no '## {version}' entry found in {changelog_path.name} (REQ-005)")
    return errors


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m asdecided.release <version> [changelog-path]``."""
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m asdecided.release <version> [changelog-path]", file=sys.stderr)
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
