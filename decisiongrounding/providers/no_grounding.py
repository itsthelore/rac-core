"""`no_grounding` arm — control. STUB.

Supplies the answering model with NO decision grounding at all (empty context).
It measures the floor: how often the answering model adheres to prior decisions
from parametric knowledge alone. Every grounded arm must beat this.
"""

from __future__ import annotations

from .base import CorpusArtifact, GroundingContext, Provider


class NoGroundingProvider(Provider):
    name = "no_grounding"

    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        # TODO(no-grounding): supply an empty (or scaffold-only) grounding so the
        # arm reflects parametric adherence with zero retrieved context. Trivial
        # to finish, but left as a stub this pass to keep the spine to the two
        # threatening real arms.
        raise NotImplementedError("no_grounding arm is a stub this pass")
