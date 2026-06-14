"""Embedding backends for the retrieval arms.

The default `LocalDeterministicEmbedder` is a real but dependency-free
bag-of-words hashing embedder: it produces a fixed-width, L2-normalised vector
with no network and no model download, so the spine runs offline and
reproducibly. It is a faithful stand-in for "commodity RAG" — exactly the
threatening baseline the benchmark needs — and its recall genuinely degrades as
the corpus grows past top-k.

For real benchmark runs, swap in a pinned hosted/local embedding model via the
`[real]` extra (see TODO below). Arms depend only on the `Embedder` interface.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class Embedder(ABC):
    """Maps text to a fixed-width vector. Implementations must be deterministic."""

    name: str = "base"
    dim: int = 0

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...


class LocalDeterministicEmbedder(Embedder):
    """Hashing bag-of-words embedder. Offline, deterministic, dependency-free."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.name = f"local-hash-bow-{dim}"

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h, "big") % self.dim
            # Signed contribution keeps the space from collapsing to one orthant.
            sign = 1.0 if h[0] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (assumed roughly unit norm)."""
    return sum(x * y for x, y in zip(a, b))


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return vec if norm == 0.0 else [v / norm for v in vec]


class VoyageEmbedder(Embedder):
    """Pinned Voyage AI embeddings (Anthropic's recommended embedding provider).

    Real, reproducible retrieval for benchmark runs. Pin the model id; results
    are deterministic for a fixed model + input. Requires the `[real]` extra
    (`voyageai`) and a VOYAGE_API_KEY. Lazily imported so the offline spine
    keeps importing without the dependency.
    """

    def __init__(self, model: str = "voyage-3") -> None:
        self.model = model
        self.name = f"voyage:{model}"
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import voyageai  # type: ignore  # provided by the [real] extra

            self._client = voyageai.Client()
            # Probe dimensionality once so cosine() comparisons are well-defined.
            probe = self._client.embed(["."], model=self.model).embeddings[0]
            self.dim = len(probe)
        return self._client

    def embed(self, text: str) -> list[float]:
        client = self._ensure_client()
        vec = client.embed([text], model=self.model).embeddings[0]
        return _l2_normalize(list(vec))


class SentenceTransformerEmbedder(Embedder):
    """Pinned local sentence-transformers model. Offline-capable once downloaded.

    A reproducible alternative to a hosted embedder. Requires the
    `[local-embeddings]` extra (`sentence-transformers`). Lazily imported.
    """

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self.model = model
        self.name = f"st:{model}"
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model)
            self.dim = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._ensure_model()
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]


def make_embedder(spec: str) -> Embedder:
    """Build an embedder from a spec string.

    `local-hash` (offline default) | `voyage[:model]` | `st[:model]`.
    Real benchmark runs pin a real backend; the offline demo uses `local-hash`.
    """
    if spec in ("", "local-hash"):
        return LocalDeterministicEmbedder()
    if spec.startswith("voyage"):
        _, _, model = spec.partition(":")
        return VoyageEmbedder(model or "voyage-3")
    if spec.startswith("st"):
        _, _, model = spec.partition(":")
        return SentenceTransformerEmbedder(model or "all-MiniLM-L6-v2")
    raise ValueError(f"unknown embedder spec: {spec!r}")
