"""Prompt routing — `rac route` (ADR-068).

Scores a prompt's structural complexity and recommends a ``local`` or ``cloud``
model, reading the decision boundary (threshold and feature weights) from the
nearest ``.rac/config.yaml`` so a team calibrates it without a RAC release. The
scoring itself is the pure, AI-optional function in :mod:`rac.core.complexity`;
this service only resolves config and reads the input. RAC stops at the
recommendation — it never selects a provider, reads a credential, or invokes a
model (ADR-034, ADR-035). The caller takes the recommendation and runs inference.
"""

from __future__ import annotations

from pathlib import Path

from rac.core.complexity import ComplexityScore, score_complexity

from .init import load_routing_config


def route_text(
    text: str, *, start_dir: str = ".", threshold: float | None = None
) -> ComplexityScore:
    """Score ``text`` and recommend a model, using config from ``start_dir``.

    A ``threshold`` argument (e.g. ``--threshold`` on the CLI) overrides the
    configured one for this call without touching ``.rac/config.yaml``.
    """
    config = load_routing_config(start_dir)
    if threshold is not None:
        config = type(config)(threshold=threshold, weights=config.weights)
    return score_complexity(text, config=config)


def route_file(path: str, *, threshold: float | None = None) -> ComplexityScore:
    """Score the prompt in ``path``; routing config is resolved from its directory."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    return route_text(text, start_dir=str(file_path.parent), threshold=threshold)
