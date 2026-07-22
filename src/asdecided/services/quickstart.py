"""Guided first run — `decided quickstart` (v0.13.0).

``quickstart`` collapses the cold start from three commands (`decided init`,
`decided new`, `decided validate`) to one by composing the existing identity and
creation capabilities: it establishes the repository key (reusing
``init_repository``) and scaffolds a single starter artifact (reusing
``create_artifact``) under the conventional ``rac/<family>/`` path. The CLI
stays a thin adapter, and any future consumer (Explorer, an IDE action)
shares one onboarding path.

The scaffold is a deliberately narrow exception to "RAC is not a content
store" (ADR-024), recorded in ADR-044: it writes exactly one artifact, only
when the corpus is empty, as the unmodified canonical template body plus a
system-assigned opaque id. A corpus that already holds any recognised
artifact is refused before anything is written.

Failure contract:

- unsupported type            → :class:`~asdecided.core.templates.TemplateNotFound`
  (usage error; validated before any write)
- corpus already has artifacts → :class:`CorpusNotEmpty` (refused; exit 1)
- established key conflicts    → :class:`~asdecided.services.init.RepositoryKeyConflict`
  (refused; exit 1)
- bad key syntax              → :class:`~asdecided.services.init.InvalidRepositoryKey`
  (usage error)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from asdecided.core.idgen import generate_id
from asdecided.core.templates import load_template
from asdecided.errors import RACError
from asdecided.services.create import CreatedArtifact, create_artifact
from asdecided.services.index import build_repository_index
from asdecided.services.init import DEFAULT_KEY, init_repository

DEFAULT_TYPE = "requirement"


class CorpusNotEmpty(RACError):
    """The corpus already holds a recognised artifact; quickstart refuses.

    Onboarding writes a starter artifact only into an empty corpus (ADR-044);
    an existing corpus is never scaffolded over.
    """

    def __init__(self, directory: str, sample_path: str) -> None:
        self.directory = directory
        self.sample_path = sample_path
        super().__init__(
            f"corpus already has artifacts (e.g. {sample_path}); "
            "rac quickstart only scaffolds an empty corpus — "
            "use `decided new` to add more"
        )


@dataclass
class QuickstartResult:
    """Outcome of one `decided quickstart` run (stable JSON contract, ADR-007)."""

    repository_key: str
    config_path: str
    created: bool  # False when the key was already established (idempotent init)
    artifact: CreatedArtifact

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "repository_key": self.repository_key,
            "config_path": self.config_path,
            "created": self.created,
            "artifact": {
                "type": self.artifact.artifact_type,
                "path": self.artifact.path,
                "id": self.artifact.id,
            },
        }


def _family(artifact_type: str) -> str:
    """The conventional plural directory for ``artifact_type`` (e.g. decisions)."""
    return f"{artifact_type}s"


def quickstart(
    directory: str,
    *,
    key: str = DEFAULT_KEY,
    artifact_type: str = DEFAULT_TYPE,
    id_generator: Callable[[str], str] = generate_id,
) -> QuickstartResult:
    """Establish identity and scaffold one starter artifact in ``directory``.

    Validates the artifact type first (cheap), refuses a non-empty corpus
    before writing anything, then establishes the key and creates the starter
    artifact at ``<directory>/decisions/<family>/first-<type>.md``. ``id_generator``
    is injectable for deterministic tests.

    Raises :class:`~asdecided.core.templates.TemplateNotFound` for an unknown type,
    :class:`CorpusNotEmpty` when the corpus already holds a recognised
    artifact, and the :mod:`~asdecided.services.init` errors for key problems — in
    every refusal case nothing is written.
    """
    load_template(artifact_type)  # validate the type before any side effect

    # Refuse a non-empty corpus before establishing identity or writing — an
    # existing corpus is never scaffolded over (ADR-044).
    index = build_repository_index(directory, recursive=True)
    existing = next((e for e in index.artifacts if e.type != "unknown"), None)
    if existing is not None:
        raise CorpusNotEmpty(directory, existing.path)

    init_result = init_repository(directory, key=key)

    art_dir = Path(directory) / "decisions" / _family(artifact_type)
    art_dir.mkdir(parents=True, exist_ok=True)
    out_path = art_dir / f"first-{artifact_type}.md"
    created_artifact = create_artifact(artifact_type, str(out_path), id_generator=id_generator)

    return QuickstartResult(
        repository_key=init_result.repository_key,
        config_path=init_result.config_path,
        created=init_result.created,
        artifact=created_artifact,
    )
