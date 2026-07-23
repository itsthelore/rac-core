"""Validation severity overrides — warnings-first onboarding (ADR-053).

A team adopting RAC on a legacy repository should not have CI fail on hundreds of
pre-existing findings. A repository may declare an optional ``validation`` section
in the committed ``.decided/config.yaml`` to downgrade or silence specific findings —
per rule code and per artifact type — so the gate can be tightened over time
rather than all at once. The loader lives in :mod:`asdecided.services.init` (which owns
``.decided/config.yaml``); this module is the pure model and application logic.

Determinism (ADR-002) is preserved: the overrides live in a committed, versioned
file, so the same repository state yields the same findings and exit code. This
is *not* a JSON-Schema dialect or a custom-type registry (ADR-052 defers those);
it is a flat, hand-managed severity map applied as a pure post-processing pass.

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

# Severities a rule may be mapped to; ``off`` suppresses the finding.
RULE_VALUES = ("error", "warning", "off")
# A whole type may be capped to error/warning, but not silenced wholesale.
TYPE_VALUES = ("error", "warning")


@dataclass(frozen=True)
class SeverityOverrides:
    """Per-rule and per-type severity overrides from ``.decided/config.yaml``."""

    rules: dict[str, str] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.rules and not self.types


EMPTY = SeverityOverrides()


def resolve_severity(base: str, code: str, artifact_type: str, overrides: SeverityOverrides) -> str:
    """The effective severity of a finding after overrides: error|warning|off.

    Pure. ``base`` is the finding's intrinsic severity; the per-type ceiling is
    applied first, then the more specific per-rule-code entry wins.
    """
    sev = base
    if overrides.types.get(artifact_type) == "warning" and sev == "error":
        sev = "warning"
    rule = overrides.rules.get(code)
    if rule is not None:
        sev = rule
    return sev


def apply_overrides(
    issues: list[Issue], artifact_type: str, overrides: SeverityOverrides
) -> list[Issue]:
    """Return ``issues`` with overridden severities; ``off`` findings dropped.

    A no-op when ``overrides`` is empty, so the default path is unchanged.
    """
    if overrides.is_empty:
        return issues
    out: list[Issue] = []
    for issue in issues:
        sev = resolve_severity(issue.severity, issue.code, artifact_type, overrides)
        if sev == "off":
            continue
        out.append(issue if sev == issue.severity else replace(issue, severity=cast(Severity, sev)))
    return out
