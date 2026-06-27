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

PACKAGE_NAME = "rac-core"

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

    The package itself is the root metadata component; the runtime dependencies
    are the ``components`` list, sorted by name for determinism. No timestamp is
    emitted so the document is byte-stable across runs (ADR-002).
    """
    root = _component(PACKAGE_NAME, _installed_version(PACKAGE_NAME))

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
