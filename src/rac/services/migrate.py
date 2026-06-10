"""Metadata migration — `rac migrate metadata` (v0.7.13).

The repeatable path onto canonical frontmatter identity (ADR-025 staged
migration, step 3): every recognized artifact without frontmatter gains the
canonical envelope — ``schema_version``, one newly generated opaque ID, its
classified ``type`` — prepended in stable key order, with the Markdown body
preserved byte-for-byte. Idempotent by construction: artifacts that already
carry frontmatter are reported untouched, documents that do not classify are
reported rather than guessed at (ADR-010), and a repaired document is picked
up by the next run.

``dry_run`` produces the identical report without writing a single file, so
users can preview a bulk rewrite. IDs are deduplicated within the run and
against the repository index — the same contract as ``rac new``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rac.core.artifacts import spec_for
from rac.core.corpus import walk_corpus
from rac.core.idgen import generate_id
from rac.services.create import (
    IdGenerationExhausted,
    MissingRepositoryConfig,
    render_frontmatter,
)
from rac.services.index import build_repository_index
from rac.services.init import load_repository_config

# Stable per-file statuses (part of the JSON contract, ADR-007).
STATUS_MIGRATED = "migrated"
STATUS_ALREADY_CANONICAL = "already-canonical"
STATUS_SKIPPED_UNKNOWN = "skipped-unknown"

# Bounded regeneration attempts per file (same rationale as rac new).
_MAX_ID_ATTEMPTS = 5

# Module-level seam so golden tests can inject a deterministic generator
# (the v0.7.11 pattern); the default is the real offline generator.
_DEFAULT_ID_GENERATOR = generate_id


@dataclass
class FileMigration:
    """Migration outcome for one Markdown file in a directory walk."""

    path: str
    status: str  # STATUS_MIGRATED | STATUS_ALREADY_CANONICAL | STATUS_SKIPPED_UNKNOWN
    id: str | None = None  # assigned ID; None unless migrated
    type: str | None = None  # classified type; None unless migrated

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "status": self.status,
            "id": self.id,
            "type": self.type,
        }


@dataclass
class MigrationReport:
    """Repository-level migration result (stable JSON contract, ADR-007)."""

    directory: str
    recursive: bool
    dry_run: bool
    files: list[FileMigration] = field(default_factory=list)

    def _count(self, status: str) -> int:
        return sum(1 for f in self.files if f.status == status)

    @property
    def migrated(self) -> int:
        return self._count(STATUS_MIGRATED)

    @property
    def already_canonical(self) -> int:
        return self._count(STATUS_ALREADY_CANONICAL)

    @property
    def skipped_unknown(self) -> int:
        return self._count(STATUS_SKIPPED_UNKNOWN)

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            "dry_run": self.dry_run,
            "summary": {
                "total_files": len(self.files),
                "migrated": self.migrated,
                "already_canonical": self.already_canonical,
                "skipped_unknown": self.skipped_unknown,
            },
            "files": [f.to_dict() for f in self.files],
        }


def migrate_metadata(
    directory: str,
    dry_run: bool = False,
    recursive: bool = True,
) -> MigrationReport:
    """Bring every recognized legacy artifact under ``directory`` onto
    canonical frontmatter identity.

    Raises :class:`~rac.services.create.MissingRepositoryConfig` when no
    repository key is established and
    :class:`~rac.services.create.IdGenerationExhausted` on persistent ID
    collisions.
    """
    config = load_repository_config(directory)
    if config is None:
        raise MissingRepositoryConfig(directory)

    repository_root = str(Path(config.config_path).parent.parent)
    issued = {entry.id.upper() for entry in build_repository_index(repository_root).artifacts}

    def _next_id() -> str:
        for _ in range(_MAX_ID_ATTEMPTS):
            candidate = _DEFAULT_ID_GENERATOR(config.repository_key)
            if candidate.upper() not in issued:
                issued.add(candidate.upper())
                return candidate
        raise IdGenerationExhausted(_MAX_ID_ATTEMPTS)

    files: list[FileMigration] = []
    for entry in walk_corpus(directory, recursive=recursive):
        path, product = entry.path, entry.product
        if product.metadata is not None or product.metadata_issues:
            # Any frontmatter presence — valid, malformed, or unterminated —
            # means migration keeps its hands off (Initiative 4: never modify
            # an existing envelope). Validation owns reporting broken ones.
            files.append(FileMigration(path=str(path), status=STATUS_ALREADY_CANONICAL))
            continue
        artifact_type = entry.artifact_type
        if spec_for(artifact_type) is None:
            files.append(FileMigration(path=str(path), status=STATUS_SKIPPED_UNKNOWN))
            continue
        artifact_id = _next_id()
        if not dry_run:
            # Prepend the envelope only; the body bytes are untouched.
            original = path.read_bytes()
            envelope = render_frontmatter(artifact_id, artifact_type)
            path.write_bytes(envelope.encode("utf-8") + original)
        files.append(
            FileMigration(
                path=str(path),
                status=STATUS_MIGRATED,
                id=artifact_id,
                type=artifact_type,
            )
        )
    return MigrationReport(directory=directory, recursive=recursive, dry_run=dry_run, files=files)
