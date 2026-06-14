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


# TODO(real-embeddings): add a pinned hosted/local embedder behind the `[real]`
# extra, e.g. an Anthropic/OpenAI embedding endpoint or a pinned
# sentence-transformers model. Pin model id + revision in runner config so runs
# reproduce. Keep the `Embedder` interface; do not let arms import a concrete
# backend directly.
