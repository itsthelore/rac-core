"""Corpus and single-document validation — the engine behind ``rac validate``.

Four public entry points share one classification-dispatched rule set so the
verdict never drifts between surfaces (ADR-015):

- :func:`validate_product` — one parsed artifact, with repository severity
  overrides applied (the single-file ``rac validate`` and SDK path).
- :func:`validate_directory` — walk a directory and validate every recognized
  artifact; unknown-type files are *skipped*, not failed (portfolio semantics).
- :func:`validate_corpus` — the same directory verdict over an already-walked
  snapshot, so one walk can feed several analyses (repository model, gate).
- :func:`validate_stdin_against_corpus` — a proposed document validated
  structurally *and* against a live corpus (the pre-edit hook seam, ADR-067).

All analysis is deterministic and offline (ADR-002); the CLI and output layer
render these dataclasses and compute nothing of their own.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from rac.core.artifacts import spec_for
from rac.core.classification import classify
from rac.core.corpus import CorpusCache, CorpusEntry, walk_corpus
from rac.core.models import Issue, Product
from rac.core.overrides import SeverityOverrides, apply_overrides
from rac.core.validation import has_errors, validate

from .init import load_overrides, load_ticketing_provider
from .okf_conformance import OkfConformanceReport, check_okf_conformance
from .relationships import RelationshipIssue, validate_document_against_corpus

# Per-file outcomes carried in the JSON contract (ADR-007). "skipped" is an
# unknown-type document that portfolio semantics decline to validate.
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
    """Repository-level validation result.

    ``to_dict`` is the stable, schema_version-gated JSON contract (ADR-007);
    the ``okf`` block is additive and optional so a snapshot built without OKF
    conformance still renders.
    """

    directory: str
    recursive: bool
    files: list[FileValidation]
    # OKF v0.1 conformance over the same snapshot (ADR-048, Layer 0). Optional so
    # alternate constructions stay valid; folded into the pass/fail verdict below.
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
        # OKF conformance is part of the verdict (ADR-048): a reserved-filename
        # collision fails the run even with zero structural errors. Absent OKF
        # (a non-conformance-computing construction) is treated as conformant.
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
        # Additive (ADR-007): the OKF block appears only when it was computed.
        if self.okf is not None:
            payload["okf"] = self.okf.to_dict()
        return payload


@dataclass
class StdinCorpusValidation:
    """Structural + corpus-relationship validation of a proposed document.

    The result of ``rac validate - --corpus DIR`` and the generated pre-edit
    hook (ADR-067): the proposed document's own structural findings *and* its
    outbound relationship references resolved against the live corpus — a
    reference to a retired (superseded/deprecated) or missing decision, a range
    or edge violation, etc. The document is identified by ``source_path``
    (``"-"`` for stdin); both finding sets are additive and schema_version-gated
    (ADR-007).

    Two severity policies coexist here. A structural *error* blocks; a structural
    *warning* does not (matching single-file ``rac validate``). But *every*
    relationship finding blocks regardless of intrinsic severity: a reference to
    a retired decision is warning-severity yet is exactly the contradiction the
    pre-edit hook exists to stop, so it blocks like a missing target.
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
    """Validate a proposed document structurally and against a live corpus.

    The seam behind ``rac validate - --corpus DIR`` and the Claude Code
    ``PreToolUse`` pre-edit hook (ADR-067). Plain ``rac validate -`` is
    single-document and cannot resolve cross-artifact references, so a proposed
    edit that points at a retired or missing decision would slip through. This
    composes two existing deterministic checks and computes nothing new
    (ADR-063):

    1. structural validation with the corpus' severity overrides applied
       (:func:`validate_product` anchored at ``corpus_dir``, so policy matches a
       normal ``rac validate`` in that repository, ADR-053); and
    2. the proposed document's outbound references resolved against the whole
       corpus (:func:`validate_document_against_corpus`), which already flags
       retired-target and missing-target references and excludes the on-disk
       counterpart of an edited artifact so the edit validates as a replacement.
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

    The single-file analogue of :func:`validate_directory` and the one place
    single-file analysis lives: run the classification-dispatched rules and apply
    the repository's severity overrides (ADR-053) loaded from ``start`` — the
    directory whose ``.rac/config.yaml`` governs policy. Sharing this one
    composition keeps behind-the-gate analysis from drifting from what the
    interface reports (ADR-015).
    """
    return apply_overrides(
        validate(product, ticketing_provider=load_ticketing_provider(start)),
        classify(product).type,
        load_overrides(start),
    )


def validate_directory(
    directory: str, recursive: bool = True, *, cache: CorpusCache | None = None
) -> DirectoryValidation:
    """Validate every recognized artifact under ``directory``.

    Files are processed in sorted path order (``walk_corpus``), so the result —
    and everything rendered from it — is deterministic. A supplied per-run
    ``cache`` serves the walk from artifacts already parsed earlier in the same
    run; the result is byte-identical either way (pinned by ``test_idempotent``).
    """
    entries = (
        cache.collect(directory, recursive=recursive)
        if cache is not None
        else list(walk_corpus(directory, recursive=recursive))
    )
    overrides = load_overrides(directory)
    return validate_corpus(directory, entries, recursive=recursive, overrides=overrides)


def validate_corpus(
    directory: str,
    entries: list[CorpusEntry],
    recursive: bool = True,
    overrides: SeverityOverrides | None = None,
) -> DirectoryValidation:
    """Validate an already-walked corpus snapshot.

    Same verdict as :func:`validate_directory`; the snapshot seam lets one walk
    feed several analyses (repository model, gate). Severity overrides (ADR-053)
    are repository-wide: when ``None`` they are loaded from ``directory`` so the
    repository model behind gate / review / portfolio honours the same policy as
    ``rac validate``; pass :data:`~rac.core.overrides.EMPTY` to opt out. Overrides
    apply before status and exit code are derived (ADR-053).
    """
    if overrides is None:
        overrides = load_overrides(directory)
    # The external ticket format-lint (ADR-087) reads the configured provider
    # once for the whole corpus — an organisation standardises on one.
    provider = load_ticketing_provider(directory)
    files = [_validate_entry(entry, provider, overrides) for entry in entries]
    okf = check_okf_conformance(directory, entries, recursive=recursive, overrides=overrides)
    return DirectoryValidation(directory=directory, recursive=recursive, files=files, okf=okf)


def _validate_entry(
    entry: CorpusEntry, provider: str | None, overrides: SeverityOverrides
) -> FileValidation:
    """Validate one walked entry, or skip it when its type is unrecognized.

    Unknown-type documents are skipped rather than failed (portfolio semantics);
    the single-file requirement fallback is a compatibility path that does not
    apply inside a directory walk.
    """
    path = str(entry.path)
    artifact_type = entry.artifact_type
    if spec_for(artifact_type) is None:
        return FileValidation(path, artifact_type, STATUS_SKIPPED, issues=[])
    issues = apply_overrides(
        validate(entry.product, ticketing_provider=provider), artifact_type, overrides
    )
    status = STATUS_INVALID if has_errors(issues) else STATUS_VALID
    return FileValidation(path, artifact_type, status, issues)
