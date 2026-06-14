"""`naive_rag` arm — commodity RAG over the same markdown.

Embeddings + top-k cosine retrieval over section chunks. No typing, no
relationship traversal: it retrieves the chunks most similar to the task and
nothing else. This is the second mandatory threatening baseline. Its
characteristic failure is built in, not contrived: as the corpus grows past the
top-k budget (or conflict density rises), relevant context — including the
section that marks a decision superseded — can fall out of the retrieved set,
severing a relationship that whole-corpus or typed retrieval would preserve.

For real runs, swap the embedder for a pinned hosted/local model via the
`[real]` extra; the retrieval logic is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import (
    SCAFFOLD,
    CorpusArtifact,
    GroundingContext,
    Provider,
    Task,
    estimate_tokens,
)
from .embedding import Embedder, LocalDeterministicEmbedder, cosine
from .grounding_format import format_block


@dataclass(frozen=True)
class _Chunk:
    artifact_id: str
    artifact_type: str
    text: str
    vector: list[float]


def _split_sections(text: str) -> list[str]:
    """Split markdown into section chunks on `## ` headings (front matter kept)."""
    parts: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            parts.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        parts.append("\n".join(current).strip())
    return [p for p in parts if p]


class NaiveRagProvider(Provider):
    name = "naive_rag"

    def __init__(self, answering_model, embedder: Embedder | None = None, top_k: int = 4):
        super().__init__(answering_model)
        self.embedder = embedder or LocalDeterministicEmbedder()
        self.top_k = top_k  # pinned retrieval budget
        self._chunks: list[_Chunk] = []

    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        self._chunks = []
        for a in corpus:
            for section in _split_sections(a.text):
                self._chunks.append(
                    _Chunk(a.id, a.type, section, self.embedder.embed(section))
                )
        # Grounding is task-dependent for RAG; assembled lazily in respond().
        self._grounding = GroundingContext(text="", artifacts_supplied=(), token_estimate=0)

    def respond(self, task: Task):
        query = self.embedder.embed(f"{task.prompt}\n{task.proposed_action}")
        ranked = sorted(
            self._chunks, key=lambda c: cosine(query, c.vector), reverse=True
        )
        top = ranked[: self.top_k]
        blocks = [format_block(c.artifact_id, c.artifact_type, c.text) for c in top]
        text = "\n".join(blocks)
        self._grounding = GroundingContext(
            text=text,
            artifacts_supplied=tuple(dict.fromkeys(c.artifact_id for c in top)),
            token_estimate=estimate_tokens(text),
        )
        return self.answering_model.respond(SCAFFOLD, self._grounding, task)
