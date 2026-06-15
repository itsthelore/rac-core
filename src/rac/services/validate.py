"""Directory validation — `rac validate <directory>` (v0.7.9).

``validate_directory`` walks a directory and validates every *recognized*
artifact with the same classification-dispatched rules as single-file
``rac validate``. Unknown-type files are reported as skipped, not failed —
the same semantics as ``rac portfolio`` (unknown is a valid outcome, and the
legacy requirement fallback only applies to explicit single-file validation).

All analysis is deterministic and belongs to Core (ADR-015). The CLI renders
the result; it calculates nothing independently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from rac.core.artifacts import spec_for
from rac.core.classification import classify
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.models import Issue, Product
from rac.core.overrides import SeverityOverrides, apply_overrides
from rac.core.validation import has_errors, validate

from .init import load_overrides
from .okf_conformance import OkfConformanceReport, check_okf_conformance

# Stable per-file statuses (part of the JSON contract, ADR-007).
STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_SKIPPED = "skipped"


@dataclass
class FileValidation:
    """Validation outcome for one Markdown file in a directory walk."""

    path: str
    artifact_type: str  # canonical artifact name, or "unknown"
    status: str  # STATUS_VALID | STATUS_INVALID | STATUS_SKIPPED
    issues: list[Issue]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "artifact_type": self.artifact_type,
            "status": self.status,
            "issues": [asdict(i) for i in self.issues],
        }


@dataclass
class DirectoryValidation:
    """Repository-level validation result (v0.7.9).

    ``to_dict`` is the stable JSON contract (ADR-007); fields are additive and
    schema_version-gated so consumers can detect breaking changes.
    """

    directory: str
    recursive: bool
    files: list[FileValidation]
    # OKF v0.1 conformance over the same snapshot (ADR-048, Layer 0). Additive
    # (ADR-007): optional so other constructors stay valid; folded into ``ok``.
    okf: OkfConformanceReport | None = None

    @property
    def checked(self) -> int:
        return sum(1 for f in self.files if f.status != STATUS_SKIPPED)

    @property
    def valid(self) -> int:
        return sum(1 for f in self.files if f.status == STATUS_VALID)

    @property
    def invalid(self) -> int:
        return sum(1 for f in self.files if f.status == STATUS_INVALID)

    @property
    def skipped(self) -> int:
        return sum(1 for f in self.files if f.status == STATUS_SKIPPED)

    @property
    def ok(self) -> bool:
        # A run passes only when every artifact validates *and* the corpus is OKF
        # v0.1 conformant (ADR-048). Conformance is treated as ok when not
        # computed, so single-purpose constructions are unaffected.
        return self.invalid == 0 and (self.okf is None or self.okf.ok)

    def to_dict(self) -> dict:
        payload = {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            "summary": {
                "total_files": len(self.files),
                "checked": self.checked,
                "valid": self.valid,
                "invalid": self.invalid,
                "skipped_unknown": self.skipped,
            },
            "valid": self.ok,
            "files": [f.to_dict() for f in self.files],
        }
        # Additive (ADR-007): OKF v0.1 conformance, present when computed.
        if self.okf is not None:
            payload["okf"] = self.okf.to_dict()
        return payload


def validate_product(product: Product, start: str = ".") -> list[Issue]:
    """Validate one parsed artifact with repository severity overrides applied.

    The single-file analogue of :func:`validate_directory`: run the
    classification-dispatched rules (:func:`validate`) and apply the repository's
    severity overrides (ADR-053) loaded from ``start`` (the directory whose
    ``.rac/config.yaml`` governs policy). The CLI's single-file ``rac validate``
    and SDK callers share this one composition, so behind-the-gate analysis never
    drifts from what the interface reports (ADR-015).
    """
    return apply_overrides(validate(product), classify(product).type, load_overrides(start))


def validate_directory(directory: str, recursive: bool = True) -> DirectoryValidation:
    """Validate every recognized artifact under ``directory``.

    Files are processed in sorted path order (``walk_corpus``), so the
    result — and everything rendered from it — is deterministic.
    """
    entries = list(walk_corpus(directory, recursive=recursive))
    overrides = load_overrides(directory)
    return validate_corpus(directory, entries, recursive=recursive, overrides=overrides)


def validate_corpus(
    directory: str,
    entries: list[CorpusEntry],
    recursive: bool = True,
    overrides: SeverityOverrides | None = None,
) -> DirectoryValidation:
    """Validate an already-walked corpus snapshot (v0.8.0).

    Same result as :func:`validate_directory`; the snapshot lets one walk
    feed several analyses (repository model, future incremental refresh).
    Severity overrides (ADR-053) are repository-wide: when not supplied they are
    loaded from the directory's ``.rac/config.yaml``, so the repository model
    behind review / watchkeeper / portfolio honours the same policy as
    ``rac validate``. Pass :data:`~rac.core.overrides.EMPTY` to opt out. Overrides
    are applied before status and exit code are computed, so a downgraded type or
    rule keeps the run green.
    """
    if overrides is None:
        overrides = load_overrides(directory)
    files: list[FileValidation] = []
    for entry in entries:
        path, product = entry.path, entry.product
        artifact_type = entry.artifact_type
        if spec_for(artifact_type) is None:
            # Unknown artifacts: not validated (portfolio semantics) — the
            # requirement fallback is a single-file compatibility path only.
            files.append(
                FileValidation(
                    path=str(path),
                    artifact_type=artifact_type,
                    status=STATUS_SKIPPED,
                    issues=[],
                )
            )
            continue
        issues = apply_overrides(validate(product), artifact_type, overrides)
        files.append(
            FileValidation(
                path=str(path),
                artifact_type=artifact_type,
                status=STATUS_INVALID if has_errors(issues) else STATUS_VALID,
                issues=issues,
            )
        )
    okf = check_okf_conformance(directory, entries, recursive=recursive, overrides=overrides)
    return DirectoryValidation(directory=directory, recursive=recursive, files=files, okf=okf)
