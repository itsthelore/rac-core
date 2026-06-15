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
from .embedding import (
    Embedder,
    LocalDeterministicEmbedder,
    SentenceTransformerEmbedder,
    VoyageEmbedder,
    make_embedder,
)
from .memory_provider import MemoryProviderArm
from .naive_rag import NaiveRagProvider
from .no_grounding import NoGroundingProvider
from .rac import RacProvider, resolve_supersedes

# Real, runnable arms this pass: context_dump, naive_rag, no_grounding (offline);
# rac (needs the external rac CLI). memory_provider is a typed stub.
ARMS: dict[str, type[Provider]] = {
    "context_dump": ContextDumpProvider,
    "naive_rag": NaiveRagProvider,
    "no_grounding": NoGroundingProvider,
    "rac": RacProvider,
    "memory_provider": MemoryProviderArm,
}

REAL_ARMS = ("context_dump", "naive_rag", "no_grounding")


def make_answering_model(name: str, seed: int) -> AnsweringModel:
    """Build the held-constant answering model from a name.

    `offline-stub` -> ScriptedAnsweringModel (deterministic, no network);
    `claude` -> ClaudeAnsweringModel (pinned Opus 4.8, needs the [real] extra +
    ANTHROPIC_API_KEY). Lives here so both the CLI and the crossover can build
    backends without importing each other.
    """
    if name == "offline-stub":
        return ScriptedAnsweringModel(seed=seed)
    if name == "claude":
        return ClaudeAnsweringModel(seed=seed)
    raise ValueError(f"unknown answering model {name!r}; use 'offline-stub' or 'claude'.")


def build_provider(arm: str, answering_model, embedder_spec: str = "local-hash") -> Provider:
    """Instantiate an arm, wiring a real embedder into naive_rag when asked."""
    if arm == "naive_rag":
        return NaiveRagProvider(answering_model, embedder=make_embedder(embedder_spec))
    return ARMS[arm](answering_model)


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
    "make_answering_model",
    "build_provider",
    "Embedder",
    "LocalDeterministicEmbedder",
    "VoyageEmbedder",
    "SentenceTransformerEmbedder",
    "make_embedder",
    "ContextDumpProvider",
    "NaiveRagProvider",
    "NoGroundingProvider",
    "RacProvider",
    "resolve_supersedes",
    "MemoryProviderArm",
]
