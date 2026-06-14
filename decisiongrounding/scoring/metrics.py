"""Metric aggregation over scored runs.

Headline metric: decision-adherence rate. Also: stale-decision rate,
false-permit rate, false-prohibit rate, and per-arm run-to-run variance. No
MemScore-style composite — the headline stays a single, legible rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import pvariance


def _rate(flags: list[bool]) -> float:
    return sum(1 for f in flags if f) / len(flags) if flags else 0.0


@dataclass(frozen=True)
class ArmMetrics:
    arm: str
    n_runs: int
    adherence_rate: float
    stale_decision_rate: float
    false_permit_rate: float
    false_prohibit_rate: float

    def as_dict(self) -> dict:
        return {
            "arm": self.arm,
            "n_runs": self.n_runs,
            "adherence_rate": self.adherence_rate,
            "stale_decision_rate": self.stale_decision_rate,
            "false_permit_rate": self.false_permit_rate,
            "false_prohibit_rate": self.false_prohibit_rate,
        }


def aggregate(arm: str, scores: list) -> ArmMetrics:
    """Aggregate a list of Score objects for one arm."""
    return ArmMetrics(
        arm=arm,
        n_runs=len(scores),
        adherence_rate=_rate([s.adherent for s in scores]),
        stale_decision_rate=_rate([s.stale_decision_followed for s in scores]),
        false_permit_rate=_rate([s.false_permit for s in scores]),
        false_prohibit_rate=_rate([s.false_prohibit for s in scores]),
    )


def adherence_variance(per_seed_rates: list[float]) -> float:
    """Population variance of an arm's adherence rate across repeated seeds.

    Run-to-run variance is itself a result: a grounding layer that is correct
    but unstable is reported as such, not smoothed over.
    """
    if len(per_seed_rates) < 2:
        return 0.0
    return pvariance(per_seed_rates)
