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

import hashlib
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from rac.core.artifacts import spec_for
from rac.core.classification import classify
from rac.core.corpus import CorpusCache, CorpusEntry, walk_corpus
from rac.core.fs import find_markdown_files
from rac.core.markdown import parse_file
from rac.core.models import Issue, Product
from rac.core.overrides import SeverityOverrides, apply_overrides
from rac.core.validation import has_errors, validate

from .init import find_config_file, load_overrides, load_ticketing_provider
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
    # Classify once and reuse for both dispatch and override resolution: the walk
    # already pays for this on the directory path, and the single-file path should
    # not re-derive the same pure result twice.
    artifact_type = classify(product).type
    return apply_overrides(
        validate(
            product, ticketing_provider=load_ticketing_provider(start), artifact_type=artifact_type
        ),
        artifact_type,
        load_overrides(start),
    )


def validate_directory(
    directory: str, recursive: bool = True, *, cache: CorpusCache | None = None
) -> DirectoryValidation:
    """Validate every recognized artifact under ``directory``.

    Files are processed in sorted path order (``walk_corpus``), so the
    result — and everything rendered from it — is deterministic. When a
    per-invocation ``cache`` is supplied, the walk is served through it so an
    artifact already parsed in an earlier phase of the same run is not reparsed
    (WS8); the result is byte-identical either way.
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
    # The external ticket format-lint (ADR-087) reads the repository's configured
    # provider once for the whole corpus — organisations standardise on one.
    provider = load_ticketing_provider(directory)
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
        # The walk already classified this entry; thread that type into
        # ``validate`` so it is not re-derived per file (3× classify → 1×).
        issues = apply_overrides(
            validate(product, ticketing_provider=provider, artifact_type=artifact_type),
            artifact_type,
            overrides,
        )
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


# =============================================================================
# Incremental directory validation — `rac validate DIR --cache` (ADR-106).
# =============================================================================
#
# Directory validation is a pure per-file computation: every ``FileValidation``
# is a pure function of ``(file bytes, resolved config)`` (core-validate §4) and
# OKF conformance is per-file. There is no cross-file layer in ``rac validate DIR``
# — duplicate-identifier / relationship-resolution / cycle checks live in the
# relationships subsystem (``rac relationships --validate`` / ``rac gate``), not
# here — so a changeset-bound re-validate needs only a per-file result cache, no
# corpus-global index. The refindex / transition-class (T1–T8) machinery the
# performance lens describes (v2 §3.2) belongs to that other subsystem's future
# incremental bundle; ADR-106 records the design, this bundle does not build it,
# because it has no consumer on the validate path.
#
# Opt-in and byte-identical: with the cache off (the default) the untouched
# :func:`validate_directory` path runs. With it on, unchanged files reuse their
# cached result and only the changed set is re-parsed and re-validated, producing
# the same ``DirectoryValidation`` — same issues, order, statuses, OKF findings,
# and therefore the same human / JSON / SARIF bytes and exit code.

_TIMING_ENV = "RAC_TIMING"


def _relposix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _config_fingerprint(directory: str) -> str:
    """A fingerprint of the ancestor-walked ``.rac/config.yaml`` governing ``directory``.

    The per-file result cache key is ``content_hash(file) × this fingerprint``
    (core-validate audit, v2 §3.1): the same bytes can validate differently under
    a different governing config (severity overrides, ticketing provider), and the
    governing config may live in an **ancestor** of the validated directory — so
    the fingerprint hashes the *resolved* ``find_config_file(directory)`` path
    (relative starts bind to the CWD via ``.resolve()``) together with its bytes.
    An ancestor-config edit, or the same tree validated from a CWD that resolves a
    different config, changes the fingerprint and invalidates the whole cache.
    """
    config_path = find_config_file(directory)
    hasher = hashlib.sha256()
    if config_path is None:
        hasher.update(b"\x00no-config")
    else:
        hasher.update(str(config_path).encode("utf-8"))
        hasher.update(b"\0")
        try:
            hasher.update(config_path.read_bytes())
        except OSError:
            hasher.update(b"\x00unreadable-config")
    return hasher.hexdigest()


def _root_key(directory: str) -> str:
    """A stable per-corpus-root store key: the SHA-256 of the resolved absolute path.

    Resolved so any spelling of the same tree (``.`` vs an absolute path, any CWD)
    shares one store, and two different trees never collide.
    """
    return hashlib.sha256(str(Path(directory).resolve()).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _OkfShim:
    """A minimal stand-in exposing only the fields ``check_okf_conformance`` reads.

    OKF conformance depends on ``(artifact_type, path)`` alone — never the parsed
    product — so the incremental path recomputes it from the cached artifact type
    and the current path without re-parsing unchanged files. Recompute (rather than
    cache) is required because a reserved-filename collision keys on the current
    basename, which a rename changes while the content hash does not.
    """

    artifact_type: str
    path: Path


def validate_directory_incremental(
    directory: str,
    recursive: bool = True,
    *,
    cache_dir: Path | None = None,
    verify: bool = False,
) -> DirectoryValidation:
    """Validate a directory, reusing per-file results across runs (ADR-106).

    Byte-identical to :func:`validate_directory` for the same corpus and config,
    but changeset-bound: a stat-manifest scan (the freshness rung reused from
    ``services/freshness``) detects the changed / added / removed set at O(files)
    stat cost, content-confirming only stat-changed files; unchanged files reuse
    their cached ``FileValidation`` verbatim while changed files are re-parsed and
    re-validated. Results are keyed by ``content_hash × config-fingerprint`` and
    persisted in the cache dir; a corrupt store or a config change is a miss that
    recomputes fresh, never a wrong answer.

    ``verify`` forces a full content re-hash (the S5-catching floor). When
    ``RAC_TIMING`` is set, one ``rac-timing:`` line is written to stderr with the
    detection and recompute wall-times and the changed-file count — opt-in and
    absent by default, so no frozen output byte moves.
    """
    from rac.services.derived_cache import default_cache_dir
    from rac.services.freshness import FileState, stat_scan
    from rac.services.index_store import (
        ValidationRow,
        open_validation_store,
        write_validation_store,
    )

    timing = _TIMING_ENV in os.environ
    detect_ns = 0
    recompute_ns = 0
    if cache_dir is None:
        cache_dir = default_cache_dir()
    root = Path(directory)
    root_key = _root_key(directory)
    config_hash = _config_fingerprint(directory)

    prev_rows = open_validation_store(cache_dir, root_key, config_hash) or {}
    prev_manifest = {
        rel: FileState(content_hash=row.content_hash, size=row.size, mtime_ns=row.mtime_ns)
        for rel, row in prev_rows.items()
    }

    detect_start = time.perf_counter_ns() if timing else 0
    new_manifest, changed = stat_scan(root, directory, prev_manifest, content_confirm_all=verify)
    if timing:
        detect_ns = time.perf_counter_ns() - detect_start

    overrides = load_overrides(directory)
    provider = load_ticketing_provider(directory)

    recompute_start = time.perf_counter_ns() if timing else 0
    new_rows: dict[str, ValidationRow] = {}
    for rel, state in new_manifest.items():
        prev = prev_rows.get(rel)
        if rel not in changed and prev is not None:
            # Unchanged content under an unchanged config: reuse the path-free
            # result verbatim, refreshing only the stat proxy in the row.
            new_rows[rel] = ValidationRow(
                size=state.size,
                mtime_ns=state.mtime_ns,
                content_hash=state.content_hash,
                artifact_type=prev.artifact_type,
                status=prev.status,
                issues=prev.issues,
            )
            continue
        product = parse_file(str(root / rel))
        artifact_type = classify(product).type
        issues: tuple[Issue, ...]
        if spec_for(artifact_type) is None:
            status, issues = STATUS_SKIPPED, ()
        else:
            computed = apply_overrides(
                validate(product, ticketing_provider=provider, artifact_type=artifact_type),
                artifact_type,
                overrides,
            )
            status = STATUS_INVALID if has_errors(computed) else STATUS_VALID
            issues = tuple(computed)
        new_rows[rel] = ValidationRow(
            size=state.size,
            mtime_ns=state.mtime_ns,
            content_hash=state.content_hash,
            artifact_type=artifact_type,
            status=status,
            issues=issues,
        )
    if timing:
        recompute_ns = time.perf_counter_ns() - recompute_start

    # Assemble in `find_markdown_files` sorted-path order — the exact fresh-walk
    # order — so the emitted issue and file order is byte-identical to a full run.
    files: list[FileValidation] = []
    okf_entries: list[_OkfShim] = []
    for path in find_markdown_files(directory, recursive=recursive):
        rel = _relposix(root, path)
        row = new_rows[rel]
        files.append(
            FileValidation(
                path=str(path),
                artifact_type=row.artifact_type,
                status=row.status,
                issues=list(row.issues),
            )
        )
        okf_entries.append(_OkfShim(artifact_type=row.artifact_type, path=path))

    # OKF conformance is per-file pure over `(artifact_type, path)`; recompute it
    # over the shims (no re-parse) through the same checker, so its findings and
    # sorted order match a full run exactly.
    okf = check_okf_conformance(
        directory,
        cast("list[CorpusEntry]", okf_entries),
        recursive=recursive,
        overrides=overrides,
    )

    write_validation_store(cache_dir, root_key, config_hash, new_rows)

    if timing:
        sys.stderr.write(
            f"rac-timing: detect_ms={detect_ns / 1_000_000:.3f} "
            f"recompute_ms={recompute_ns / 1_000_000:.3f} files_changed={len(changed)}\n"
        )

    return DirectoryValidation(directory=directory, recursive=recursive, files=files, okf=okf)
