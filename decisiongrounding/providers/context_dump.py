"""`context_dump` arm — paste every artifact into the answering model's context.

This is a mandatory threatening baseline: it is exactly the skeptic's position
("frontier models + long context just absorb the decisions"). It supplies the
whole corpus verbatim, so every stated relationship (including supersession) is
present. Any grounding layer must beat this to justify its existence.
"""

from __future__ import annotations

from .base import CorpusArtifact, GroundingContext, Provider, estimate_tokens
from .grounding_format import format_block


class ContextDumpProvider(Provider):
    name = "context_dump"

    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        blocks = [format_block(a.id, a.type, a.text) for a in corpus]
        text = "\n".join(blocks)
        self._grounding = GroundingContext(
            text=text,
            artifacts_supplied=tuple(a.id for a in corpus),
            token_estimate=estimate_tokens(text),
        )
