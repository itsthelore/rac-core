"""OKF v0.1 conformance — the write-time gate (ADR-048, ADR-049).

ADR-048 requires every RAC repository to be a conformant OKF v0.1 bundle, and
ADR-049 makes deterministic, CI-enforced validation RAC's core. Until now
conformance was only a side-effect of ``rac export --okf``; this check makes it
a write-time gate, surfaced through ``rac validate`` over a corpus.

The check is deterministic and per-artifact (Layer 0). It runs over the same
corpus snapshot as directory validation and reports, with file-named
diagnostics and stable codes:

- ``okf-unmapped-type`` — a typed RAC artifact whose ``type`` has no OKF mapping.
  Guards future type additions: a new type added without an OKF mapping fails
  here instead of being silently excluded from the bundle.
- ``okf-reserved-filename-collision`` — a typed artifact whose filename is an OKF
  reserved entry point (``index.md``/``log.md``), which would collide with the
  generated bundle file.

Untyped documents are excluded (ADR-010): they are legitimately skipped and the
OKF bundle already omits them, so ``index.md``/``log.md`` that are untyped
documents are recognized reserved entry points, never findings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from rac.core.artifacts import spec_for
from rac.core.corpus import CorpusEntry
from rac.core.okf import OKF_TYPE, RESERVED_FILENAMES

# Stable finding codes (part of the JSON contract, ADR-007).
CODE_UNMAPPED_TYPE = "okf-unmapped-type"
CODE_RESERVED_FILENAME = "okf-reserved-filename-collision"


@dataclass
class OkfFinding:
    """One OKF conformance finding, file-named for actionable diagnostics."""

    code: str
    path: str
    message: str

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
        return not self.findings

    def to_dict(self) -> dict:
        return {
            "conformant": self.ok,
            "artifacts_checked": self.artifacts_checked,
            "findings": [f.to_dict() for f in self.findings],
        }


def check_okf_conformance(
    directory: str, entries: list[CorpusEntry], recursive: bool = True
) -> OkfConformanceReport:
    """Check OKF v0.1 conformance over an already-walked corpus snapshot.

    Deterministic: entries arrive in sorted path order, so findings do too. Only
    typed artifacts are checked; untyped documents are excluded (ADR-010), which
    also exempts untyped ``index.md``/``log.md`` reserved entry points.
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
            findings.append(
                OkfFinding(
                    CODE_UNMAPPED_TYPE,
                    path,
                    f"artifact type {artifact_type!r} has no OKF type mapping; add "
                    f"it to rac.core.okf.OKF_TYPE so the artifact is carried in the "
                    f"OKF bundle (ADR-048)",
                )
            )
        if entry.path.name in RESERVED_FILENAMES:
            findings.append(
                OkfFinding(
                    CODE_RESERVED_FILENAME,
                    path,
                    f"a typed artifact named {entry.path.name!r} collides with the "
                    f"generated OKF bundle entry point; rename the file — OKF "
                    f"reserves index.md and log.md (ADR-048)",
                )
            )
    return OkfConformanceReport(
        directory=directory,
        recursive=recursive,
        artifacts_checked=checked,
        findings=findings,
    )
