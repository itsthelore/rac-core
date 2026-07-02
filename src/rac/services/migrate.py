"""Bring legacy artifacts onto canonical frontmatter identity (`rac migrate metadata`).

The repeatable step onto canonical identity (ADR-025, staged migration): a
recognized artifact that carries no frontmatter has the canonical envelope —
``schema_version``, a freshly minted opaque ID, and its classified ``type`` —
prepended, while its Markdown body is preserved byte-for-byte.

The operation is idempotent and conservative by construction. A file that
already has any frontmatter (valid, malformed, or unterminated) is reported
untouched — validation, not migration, owns broken envelopes. A document that
does not classify is reported rather than guessed at (ADR-010), and once a user
repairs it the next run picks it up. ``dry_run`` produces the identical report
without writing a byte, so a bulk rewrite can be previewed first. Minted IDs are
deduplicated within the run and against the existing repository index — the same
contract as ``rac new``.
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

# Per-file outcomes; part of the stable JSON contract (ADR-007).
STATUS_MIGRATED = "migrated"
STATUS_ALREADY_CANONICAL = "already-canonical"
STATUS_SKIPPED_UNKNOWN = "skipped-unknown"

# Bounded ID regeneration per file, matching ``rac new``.
_MAX_ID_ATTEMPTS = 5

# Module-level generator seam: golden tests monkeypatch this name for
# deterministic IDs, so ``_next_id`` must resolve it as a module global at call
# time rather than binding the default at import.
_DEFAULT_ID_GENERATOR = generate_id


@dataclass
class FileMigration:
    """Migration outcome for one Markdown file in the walk."""

    path: str
    status: str  # one of the STATUS_* constants
    id: str | None = None  # minted ID; None unless migrated
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
        return sum(1 for file in self.files if file.status == status)

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
            "files": [file.to_dict() for file in self.files],
        }


def migrate_metadata(
    directory: str,
    dry_run: bool = False,
    recursive: bool = True,
) -> MigrationReport:
    """Migrate every recognized frontmatter-less artifact under ``directory``.

    Raises :class:`~rac.services.create.MissingRepositoryConfig` when no
    repository key is established, and
    :class:`~rac.services.create.IdGenerationExhausted` on persistent ID
    collisions.
    """
    config = load_repository_config(directory)
    if config is None:
        raise MissingRepositoryConfig(directory)

    # Seed the dedup set from every ID already issued across the repository, so
    # a freshly minted ID never collides with an existing artifact.
    repository_root = str(Path(config.config_path).parent.parent)
    issued = {entry.id.upper() for entry in build_repository_index(repository_root).artifacts}

    def _next_id() -> str:
        for _ in range(_MAX_ID_ATTEMPTS):
            # ``_DEFAULT_ID_GENERATOR`` is looked up as a module global here so
            # the golden-test monkeypatch takes effect.
            candidate = _DEFAULT_ID_GENERATOR(config.repository_key)
            if candidate.upper() not in issued:
                issued.add(candidate.upper())
                return candidate
        raise IdGenerationExhausted(_MAX_ID_ATTEMPTS)

    files: list[FileMigration] = []
    for entry in walk_corpus(directory, recursive=recursive):
        path, product = entry.path, entry.product

        # Any frontmatter presence — valid or broken — is left strictly alone.
        if product.metadata is not None or product.metadata_issues:
            files.append(FileMigration(path=str(path), status=STATUS_ALREADY_CANONICAL))
            continue

        artifact_type = entry.artifact_type
        if spec_for(artifact_type) is None:
            files.append(FileMigration(path=str(path), status=STATUS_SKIPPED_UNKNOWN))
            continue

        artifact_id = _next_id()
        if not dry_run:
            # Prepend the envelope; the original body bytes are untouched.
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
