"""Scenario loading and the frozen worked examples.

Three discriminating worked scenarios plus a negative control ship here. Per
CONTRIBUTING.md, production scenarios must be derived from real/public ADR sets
or a design partner's real incident — never hand-authored to favour an arm —
and gold labels must be written blind to which arm produced which output.
"""

from .loader import (
    GoldLabel,
    Relationship,
    Scenario,
    load_scenario,
    load_scenarios,
)

__all__ = [
    "GoldLabel",
    "Relationship",
    "Scenario",
    "load_scenario",
    "load_scenarios",
]
