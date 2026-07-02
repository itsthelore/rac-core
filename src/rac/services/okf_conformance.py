"""OKF v0.1 conformance — the write-time gate (ADR-048, ADR-049).

ADR-048 requires every RAC repository to be a conformant OKF v0.1 bundle; ADR-049
makes deterministic, CI-enforced validation the core of RAC. Conformance used to
be observable only as a side effect of ``rac export --okf``. This check promotes
it to a write-time gate that folds into ``rac validate`` over a corpus.

The check is per-artifact and deterministic (Layer 0). It runs over the same
sorted corpus snapshot as directory validation, so its findings arrive in path
order. Two stable codes are emitted:

- ``okf-unmapped-type`` — a typed RAC artifact whose ``type`` has no entry in
  :data:`rac.core.okf.OKF_TYPE`. Without this gate a newly registered type would
  be silently dropped from the exported bundle; here it fails loudly instead.
- ``okf-reserved-filename-collision`` — a typed artifact whose filename is an OKF
  reserved entry point (``index.md`` / ``log.md``), which would collide with the
  generated bundle file.

Untyped documents are excluded entirely (ADR-010): the bundle omits them, so an
*untyped* ``index.md`` / ``log.md`` is a recognized reserved entry point, never a
finding — only a *typed* artifact at that filename collides.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from rac.core.artifacts import spec_for
from rac.core.corpus import CorpusEntry
from rac.core.okf import OKF_TYPE, RESERVED_FILENAMES
from rac.core.overrides import EMPTY, SeverityOverrides, resolve_severity

# Stable finding codes — part of the JSON contract (ADR-007).
CODE_UNMAPPED_TYPE = "okf-unmapped-type"
CODE_RESERVED_FILENAME = "okf-reserved-filename-collision"

# Every finding starts at error severity; the repository's overrides (ADR-053)
# may downgrade or suppress it before it counts against conformance.
_BASE_SEVERITY = "error"


@dataclass
class OkfFinding:
    """One OKF conformance finding, named to a file for actionable diagnostics.

    ``severity`` defaults to ``error`` but is the *resolved* severity: an override
    can downgrade a code or type to ``warning`` (or suppress it) during onboarding.
    """

    code: str
    path: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OkfConformanceReport:
    """Repository OKF v0.1 conformance result (additive to directory validate)."""

    directory: str
    recursive: bool
    artifacts_checked: int
    findings: list[OkfFinding]

    @property
    def ok(self) -> bool:
        # Conformant only while no finding survives at error severity. Overrides
        # may have downgraded some to warnings, which do not block.
        return not any(f.severity == "error" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "conformant": self.ok,
            "artifacts_checked": self.artifacts_checked,
            "findings": [f.to_dict() for f in self.findings],
        }


def check_okf_conformance(
    directory: str,
    entries: list[CorpusEntry],
    recursive: bool = True,
    overrides: SeverityOverrides = EMPTY,
) -> OkfConformanceReport:
    """Check OKF v0.1 conformance over an already-walked corpus snapshot.

    Entries arrive in sorted path order, so findings do too. Only typed artifacts
    are checked (``spec_for`` recognizes the type); untyped documents are excluded
    per ADR-010, which is also what exempts untyped reserved entry points.

    ``OKF_TYPE`` is read as a module-level name so a test can rebind
    ``rac.services.okf_conformance.OKF_TYPE`` to simulate a type registered
    without a bundle mapping.
    """
    findings: list[OkfFinding] = []
    checked = 0

    for entry in entries:
        artifact_type = entry.artifact_type
        if spec_for(artifact_type) is None:
            continue
        checked += 1
        path = str(entry.path)

        if artifact_type not in OKF_TYPE:
            _record(
                findings,
                CODE_UNMAPPED_TYPE,
                path,
                artifact_type,
                f"artifact type {artifact_type!r} has no OKF type mapping; add it to "
                f"rac.core.okf.OKF_TYPE so the artifact is carried in the OKF bundle "
                f"(ADR-048)",
                overrides,
            )
        if entry.path.name in RESERVED_FILENAMES:
            _record(
                findings,
                CODE_RESERVED_FILENAME,
                path,
                artifact_type,
                f"a typed artifact named {entry.path.name!r} collides with the generated "
                f"OKF bundle entry point; rename the file — OKF reserves index.md and "
                f"log.md (ADR-048)",
                overrides,
            )

    return OkfConformanceReport(
        directory=directory,
        recursive=recursive,
        artifacts_checked=checked,
        findings=findings,
    )


def _record(
    findings: list[OkfFinding],
    code: str,
    path: str,
    artifact_type: str,
    message: str,
    overrides: SeverityOverrides,
) -> None:
    """Append a finding at its overridden severity; an ``off`` override drops it."""
    severity = resolve_severity(_BASE_SEVERITY, code, artifact_type, overrides)
    if severity == "off":
        return
    findings.append(OkfFinding(code=code, path=path, message=message, severity=severity))
