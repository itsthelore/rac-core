#!/usr/bin/env python3
"""Generate a CycloneDX 1.5 SBOM for requirements-as-code (v0.21.14).

A Software Bill of Materials is the verifiable artifact behind RAC's security
posture (``docs/security.md``): it enumerates the package and its declared
runtime dependencies so a security office can review the dependency surface
without trusting a prose claim. The dependency *names* are read from
``pyproject.toml`` (``[project].dependencies`` — the single source of truth);
each version is resolved from the installed environment via
``importlib.metadata``.

Determinism and offline (ADR-002): no network access, no timestamps, and a
stable component ordering, so re-running on the same environment yields a
byte-identical ``sbom.json``. The committed ``sbom.json`` at the repository root
is produced by this script; ``tests/test_sbom.py`` guards it against drift from
the declared dependencies.

The root component's version is the latest release heading in ``CHANGELOG.md``,
not the installed package metadata: a working checkout carries a setuptools-scm
``.devN`` version that matches no published artifact, and an SBOM attesting to a
version nobody can install defeats its purpose. The committed document therefore
always describes the most recent release, in its PEP 440 normalised spelling
(``0.22.0``, dropping the ``v`` the tag carries — the form PyPI publishes).

Usage::

    python scripts/generate_sbom.py            # write sbom.json at the repo root
    python scripts/generate_sbom.py --stdout   # print to stdout instead
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
SBOM_PATH = REPO_ROOT / "sbom.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

PACKAGE_NAME = "rac-core"

# The latest release heading in CHANGELOG.md: `## vX.Y.Z — …` (ADR-111, which
# reverted the CalVer of ADR-076). The capture drops the ``v`` so the recovered
# version is the PEP 440 normalised spelling PyPI publishes (``0.22.0``).
_RELEASE_HEADING_RE = re.compile(r"^## v(\d+\.\d+\.\d+)\b", re.MULTILINE)

# A PEP 508 requirement string starts with the distribution name; strip any
# version specifier, extras, or environment marker to recover the bare name.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+")


def _dependency_names() -> list[str]:
    """The runtime dependency names declared in ``[project].dependencies``."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    requirements = data["project"]["dependencies"]
    names: list[str] = []
    for requirement in requirements:
        match = _NAME_RE.match(requirement.strip())
        if match:
            names.append(match.group(0))
    return names


def _installed_version(name: str) -> str:
    """The installed version of ``name``, or ``"unknown"`` when not installed.

    Offline: reads only local distribution metadata. A missing dependency yields
    ``"unknown"`` rather than failing, so the SBOM can still be generated in a
    partial environment; the test suite asserts the declared names are present.
    """
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def _released_version() -> str:
    """The most recent release version recorded in ``CHANGELOG.md``.

    Fails loud when no release heading parses: an SBOM with an unknown root
    version is worse than no SBOM.
    """
    match = _RELEASE_HEADING_RE.search(CHANGELOG.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("no release heading (## vX.Y.Z) found in CHANGELOG.md")
    return match.group(1)


def _component(name: str, version: str) -> dict:
    """One CycloneDX ``library`` component for ``name`` at ``version``."""
    return {
        "type": "library",
        "name": name,
        "version": version,
        "bom-ref": f"{name}@{version}",
        "purl": f"pkg:pypi/{name}@{version}",
    }


def build_sbom() -> dict:
    """The CycloneDX 1.5 SBOM document for RAC and its runtime dependencies.

    The package itself is the root metadata component, at the latest released
    version from ``CHANGELOG.md``; the runtime dependencies are the
    ``components`` list, sorted by name for determinism. No timestamp is emitted
    so the document is byte-stable across runs (ADR-002).
    """
    root = _component(PACKAGE_NAME, _released_version())

    dependencies = sorted(_dependency_names(), key=str.casefold)
    components = [_component(name, _installed_version(name)) for name in dependencies]

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        # No serialNumber and no metadata.timestamp: both would make the document
        # non-deterministic. The component list is the verifiable content.
        "metadata": {"component": root},
        "components": components,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the RAC CycloneDX SBOM.")
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the SBOM to stdout instead of writing sbom.json.",
    )
    args = parser.parse_args(argv)

    document = build_sbom()
    text = json.dumps(document, indent=2) + "\n"
    if args.stdout:
        sys.stdout.write(text)
    else:
        SBOM_PATH.write_text(text, encoding="utf-8")
        print(f"wrote {SBOM_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
