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
from rac.core.fs import find_markdown_files
from rac.core.markdown import parse_file
from rac.core.models import Issue
from rac.core.validation import has_errors, validate

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
        return self.invalid == 0

    def to_dict(self) -> dict:
        return {
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


def validate_directory(directory: str, recursive: bool = True) -> DirectoryValidation:
    """Validate every recognized artifact under ``directory``.

    Files are processed in sorted path order (``find_markdown_files``), so the
    result — and everything rendered from it — is deterministic.
    """
    files: list[FileValidation] = []
    for path in find_markdown_files(directory, recursive=recursive):
        product = parse_file(str(path))
        artifact_type = classify(product).type
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
        issues = validate(product)
        files.append(
            FileValidation(
                path=str(path),
                artifact_type=artifact_type,
                status=STATUS_INVALID if has_errors(issues) else STATUS_VALID,
                issues=issues,
            )
        )
    return DirectoryValidation(directory=directory, recursive=recursive, files=files)
