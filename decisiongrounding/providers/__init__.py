"""Benchmark arms and the shared provider-adapter contract.

Every arm implements `prepare(corpus)` / `respond(task) -> ProposedChange` and
feeds a held-constant answering model behind a held-constant scaffold. Arms
differ ONLY in how they assemble grounding.
"""

from __future__ import annotations

from .answering import (
    AnsweringModel,
    ClaudeAnsweringModel,
    ScriptedAnsweringModel,
)
from .base import (
    Action,
    CorpusArtifact,
    GroundingContext,
    ProposedChange,
    Provider,
    Task,
)
from .context_dump import ContextDumpProvider
from .embedding import Embedder, LocalDeterministicEmbedder
from .memory_provider import MemoryProviderArm
from .naive_rag import NaiveRagProvider
from .no_grounding import NoGroundingProvider
from .rac import RacProvider

# Arm registry. Real, runnable arms this pass: context_dump, naive_rag.
# The rest are typed stubs (raise NotImplementedError on use).
ARMS: dict[str, type[Provider]] = {
    "context_dump": ContextDumpProvider,
    "naive_rag": NaiveRagProvider,
    "no_grounding": NoGroundingProvider,
    "rac": RacProvider,
    "memory_provider": MemoryProviderArm,
}

REAL_ARMS = ("context_dump", "naive_rag")

__all__ = [
    "ARMS",
    "REAL_ARMS",
    "Provider",
    "CorpusArtifact",
    "Task",
    "GroundingContext",
    "ProposedChange",
    "Action",
    "AnsweringModel",
    "ScriptedAnsweringModel",
    "ClaudeAnsweringModel",
    "Embedder",
    "LocalDeterministicEmbedder",
    "ContextDumpProvider",
    "NaiveRagProvider",
    "NoGroundingProvider",
    "RacProvider",
    "MemoryProviderArm",
]
