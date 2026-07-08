"""SBOM tests — the verifiable dependency surface (v0.21.14, ADR-002).

The committed ``sbom.json`` is the machine-readable evidence behind RAC's
security posture (``docs/security.md``). These tests pin two things: the document
is a well-formed CycloneDX SBOM, and it has not drifted from the runtime
dependencies declared in ``pyproject.toml`` — so the SBOM can never silently fall
behind the deps it attests to. Offline and deterministic: the tests read only
committed files.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SBOM_PATH = REPO_ROOT / "sbom.json"
PYPROJECT = REPO_ROOT / "pyproject.toml"

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+")


def _sbom() -> dict:
    return json.loads(SBOM_PATH.read_text(encoding="utf-8"))


def _declared_dependency_names() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    names = []
    for requirement in data["project"]["dependencies"]:
        match = _NAME_RE.match(requirement.strip())
        assert match, f"cannot parse dependency name from {requirement!r}"
        names.append(match.group(0))
    return names


def test_sbom_is_cyclonedx():
    sbom = _sbom()
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"], "specVersion must be present"
    assert isinstance(sbom["components"], list)


def test_sbom_includes_the_package_as_root_component():
    root = _sbom()["metadata"]["component"]
    assert root["name"] == "rac-core"
    assert root["type"] == "library"


def test_sbom_covers_every_declared_runtime_dependency():
    # Drift guard: every dependency declared in pyproject must appear as an SBOM
    # component, so the SBOM cannot silently fall behind the declared deps.
    component_names = {c["name"] for c in _sbom()["components"]}
    for name in _declared_dependency_names():
        assert name in component_names, f"dependency {name!r} missing from sbom.json"


def test_sbom_is_deterministic_no_timestamp():
    # Determinism (ADR-002): no timestamp, and components sorted by name.
    sbom = _sbom()
    assert "timestamp" not in sbom.get("metadata", {})
    names = [c["name"] for c in sbom["components"]]
    assert names == sorted(names, key=str.casefold)


def test_sbom_root_version_is_the_latest_release():
    # The root component attests to the latest released version (the newest
    # CHANGELOG.md heading), never a setuptools-scm dev build that matches no
    # published artifact — an SBOM for an uninstallable version attests nothing.
    # The heading is SemVer `## vX.Y.Z` (ADR-111); the SBOM records its PEP 440
    # normalised spelling without the `v` (the form PyPI publishes).
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(r"^## v(\d+\.\d+\.\d+)\b", changelog, re.MULTILINE)
    assert heading, "no release heading (## vX.Y.Z) in CHANGELOG.md"
    root = _sbom()["metadata"]["component"]
    assert root["version"] == heading.group(1)
    assert ".dev" not in root["version"]
    assert root["purl"] == f"pkg:pypi/rac-core@{heading.group(1)}"
