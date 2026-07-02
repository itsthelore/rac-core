"""Validation severity overrides -- warnings-first onboarding (ADR-053).

A team adopting RAC on an existing repository should not have CI fail on hundreds
of pre-existing findings at once. A repository may declare an optional
``validation`` section in its committed ``.rac/config.yaml`` that downgrades or
silences specific findings -- per rule code and per artifact type -- so the gate
can be tightened over time. The loader lives in :mod:`rac.services.init` (which
owns ``.rac/config.yaml``); this module is only the pure model and the pass that
applies it.

Determinism (ADR-002) is preserved because the overrides live in a committed,
versioned file: the same repository state yields the same findings and the same
exit code. This is deliberately *not* a JSON-Schema dialect or a custom-type
registry (ADR-052 defers those) -- just a flat severity map applied as a pure
post-processing step over an already-computed finding list.

Config shape::

    validation:
      rules:                 # rule code -> error | warning | off
        ambiguous-verb: off
        too-many-requirements: warning
      types:                 # artifact type -> error | warning  (a ceiling)
        roadmap: warning

Precedence: a per-type ``warning`` ceiling downgrades that type's ``error``
findings to ``warning``; a per-rule-code entry is more specific and wins over the
ceiling (so a downgraded type can still force one rule back to ``error``).
``off`` suppresses the finding entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

from .models import Issue, Severity

# Severities a single rule may be mapped to; ``off`` drops the finding.
RULE_VALUES = ("error", "warning", "off")
# A whole type may only be capped to error/warning -- never silenced wholesale.
TYPE_VALUES = ("error", "warning")


@dataclass(frozen=True)
class SeverityOverrides:
    """Per-rule and per-type severity overrides parsed from ``.rac/config.yaml``."""

    rules: dict[str, str] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.rules and not self.types


# Shared sentinel for "no overrides configured". Callers rely on the default
# path (below) returning the original list unchanged, identity included.
EMPTY = SeverityOverrides()


def resolve_severity(base: str, code: str, artifact_type: str, overrides: SeverityOverrides) -> str:
    """Return a finding's effective severity after overrides: error|warning|off.

    Pure. ``base`` is the finding's intrinsic severity. The per-type ceiling is
    applied first, then a more specific per-rule-code entry (if any) overrides it.
    """
    severity = base
    if overrides.types.get(artifact_type) == "warning" and severity == "error":
        severity = "warning"
    rule_override = overrides.rules.get(code)
    if rule_override is not None:
        severity = rule_override
    return severity


def apply_overrides(
    issues: list[Issue], artifact_type: str, overrides: SeverityOverrides
) -> list[Issue]:
    """Return ``issues`` re-graded by ``overrides``, with ``off`` findings dropped.

    When ``overrides`` is empty the input list is returned unchanged -- the same
    object, so the default (no-config) path allocates nothing.
    """
    if overrides.is_empty:
        return issues
    regraded: list[Issue] = []
    for issue in issues:
        severity = resolve_severity(issue.severity, issue.code, artifact_type, overrides)
        if severity == "off":
            continue  # suppressed entirely
        if severity == issue.severity:
            regraded.append(issue)  # unchanged -- preserve object identity
        else:
            regraded.append(replace(issue, severity=cast(Severity, severity)))
    return regraded
