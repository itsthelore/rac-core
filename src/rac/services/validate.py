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
from .relationships import RelationshipIssue, validate_document_against_corpus

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


@dataclass
class StdinCorpusValidation:
    """Combined structural + corpus-relationship validation of a proposed document.

    The result of ``rac validate - --corpus DIR`` (v0.21.17, ADR-067): the
    single-document structural findings (:class:`Issue`) *and* the proposed
    document's outbound relationship findings resolved against the live corpus
    (:class:`RelationshipIssue`) — references to retired (superseded/deprecated)
    or missing decisions, range/edge violations, etc. Both finding sets are
    additive and ``schema_version``-gated (ADR-007); the proposed document is
    identified as ``source_path`` ("-" for stdin).

    ``ok`` is False — and the CLI exits non-zero — when *either* a structural
    error or *any* relationship finding is present. Relationship findings are all
    blocking here regardless of intrinsic severity: a reference to a retired
    decision is a structural contradiction the pre-edit hook exists to stop
    (ADR-067), so it blocks just like a missing target. Structural *warnings* do
    not block, mirroring single-file ``rac validate``.
    """

    source_path: str
    structural_issues: list[Issue]
    relationship_issues: list[RelationshipIssue]

    @property
    def ok(self) -> bool:
        return not has_errors(self.structural_issues) and not self.relationship_issues

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "file": self.source_path or None,
            "valid": self.ok,
            "errors": [asdict(i) for i in self.structural_issues if i.severity == "error"],
            "warnings": [asdict(i) for i in self.structural_issues if i.severity == "warning"],
            "relationship_issues": [i.to_dict() for i in self.relationship_issues],
        }


def validate_stdin_against_corpus(
    product: Product,
    corpus_dir: str,
    source_path: str = "-",
    recursive: bool = True,
) -> StdinCorpusValidation:
    """Validate a proposed document structurally *and* against a live corpus.

    The engine seam behind ``rac validate - --corpus DIR`` and the generated
    Claude Code ``PreToolUse`` pre-edit hook (v0.21.17, ADR-067): plain
    ``rac validate -`` is single-document and cannot resolve cross-artifact
    references, so a proposed edit introducing a reference to a *retired* or
    *missing* decision would slip through. This composes the two existing
    deterministic checks — it computes nothing new (ADR-063):

    1. structural validation with the corpus' severity overrides applied
       (:func:`validate_product` anchored at ``corpus_dir``, so policy matches a
       normal ``rac validate`` in that repository, ADR-053); and
    2. the proposed document's outbound relationship references resolved against
       the whole corpus (:func:`validate_document_against_corpus`), which already
       flags retired-target and missing-target references.

    The on-disk counterpart of an edited artifact is excluded from the corpus
    index by canonical identity, so an edit is validated as if it replaces the
    committed version (see :func:`validate_document_against_corpus`).
    """
    structural = validate_product(product, start=corpus_dir)
    relationships = validate_document_against_corpus(
        product, source_path, corpus_dir, recursive=recursive
    )
    return StdinCorpusValidation(
        source_path=source_path,
        structural_issues=structural,
        relationship_issues=relationships.issues,
    )


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
