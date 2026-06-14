"""`memory_provider` arm — general-purpose memory layer. STUB.

A MemoryBench-style adapter slot for a commodity memory layer (Mem0 / Zep /
Supermemory). Per ADR-0001 we borrow MemoryBench's provider-adapter convention
without adopting its conversational-QA evaluation contract, so this arm can
reuse those upstream adapters while still being scored by our deterministic
structural scorer.
"""

from __future__ import annotations

from .base import CorpusArtifact, GroundingContext, Provider, Task


class MemoryProviderArm(Provider):
    name = "memory_provider"

    def __init__(self, answering_model, backend: str = "TODO-pin-backend"):
        super().__init__(answering_model)
        self.backend = backend  # e.g. "mem0", "zep", "supermemory" (pin version)

    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        # TODO(memory-arm): ingest each artifact into the pinned memory backend
        # via its MemoryBench adapter (add/write). Pin the backend + version so
        # runs reproduce. Respect the single symmetric grounding opportunity:
        # ingestion happens once here.
        raise NotImplementedError("memory_provider arm is a stub this pass")

    def respond(self, task: Task):
        # TODO(memory-arm): query the backend (search/recall) for the task, wrap
        # the recalled items as GroundingContext, and feed the held-constant
        # answering model. Do not let the backend call the answering model itself
        # — keep the answering model fixed across arms.
        raise NotImplementedError("memory_provider arm is a stub this pass")
