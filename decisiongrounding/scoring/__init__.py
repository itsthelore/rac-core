"""Deterministic scoring, metric aggregation, and the crossover artifact."""

from .metrics import ArmMetrics, adherence_variance, aggregate, recall_rate
from .scorer import Score, score

__all__ = [
    "Score",
    "score",
    "ArmMetrics",
    "aggregate",
    "adherence_variance",
    "recall_rate",
]
