"""Policy-aware unified enforcement — `rac gate` (v0.21.14, ADR-049 / ADR-063).

``rac gate`` is the single enforcement entry point: it runs validation,
relationship integrity, and review over a corpus, then classifies every finding
as *blocking* or *advisory* under the corpus enforcement policy (ADR-049 —
enforcement is the product). One command, one exit code, one SARIF document, so
the PR gate carries the whole RAC contract as a single required check instead of
three separate uploads.

The classification is governed, not hardcoded (ADR-063: the thin client renders;
the engine decides). A corpus declares an optional ``enforcement:`` section in
its committed ``.rac/config.yaml`` (loaded by :mod:`rac.services.init`, which
owns the file) mapping finding codes to ``blocking``/``advisory``/``off``. The
*default* enforcement classes are chosen so that, with no policy, a gate run is
``ok`` exactly when validate, relationships, and review all pass — preserving the
v0.21.13 behaviour the policy refines.

Determinism and offline (ADR-002): the gate composes the same deterministic
services, applies a pure policy pass, and sorts findings by a stable key, so the
same corpus state yields a byte-identical report, JSON, and SARIF.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.services.init import load_enforcement_policy
from rac.services.relationships import (
    RELATIONSHIP_SEVERITY,
    RelationshipIssue,
    validate_relationships,
)
from rac.services.review import (
    PRIORITY_BROKEN_RELATIONSHIP,
    ReviewIssue,
    build_review,
)
from rac.services.validate import DirectoryValidation, validate_directory

# The two enforcement classes a finding can carry, plus the suppressed marker
# (``off`` drops the finding entirely). Sources name where a finding originated.
ENFORCEMENT_BLOCKING = "blocking"
ENFORCEMENT_ADVISORY = "advisory"
ENFORCEMENT_OFF = "off"

SOURCE_VALIDATE = "validate"
SOURCE_RELATIONSHIPS = "relationships"
SOURCE_REVIEW = "review"


@dataclass(frozen=True)
class EnforcementPolicy:
    """A corpus enforcement policy: finding codes mapped to a class (ADR-049).

    Three disjoint *intent* sets of finding codes. ``classify`` resolves a
    finding's effective class with a fixed precedence — ``off`` (suppress) wins,
    then ``blocking``, then ``advisory``, else the caller's default. A code in
    more than one set is therefore harmless: precedence makes the result
    deterministic regardless of declaration order.
    """

    blocking: frozenset[str] = frozenset()
    advisory: frozenset[str] = frozenset()
    off: frozenset[str] = frozenset()

    def classify(self, code: str, default: str) -> str | None:
        """The effective enforcement class for ``code``, or ``None`` if suppressed.

        Precedence: ``off`` -> ``blocking`` -> ``advisory`` -> ``default``. A
        ``None`` result means the finding is dropped (the policy turned it off).
        """
        if code in self.off:
            return None
        if code in self.blocking:
            return ENFORCEMENT_BLOCKING
        if code in self.advisory:
            return ENFORCEMENT_ADVISORY
        return default


# The neutral policy: every finding keeps its default class (ADR-049). Used when
# a corpus declares no ``enforcement:`` section, so the no-policy path is a no-op.
EMPTY_POLICY = EnforcementPolicy()


@dataclass(frozen=True)
class GateFinding:
    """One enforced finding, normalised across the three underlying services.

    ``source`` records which service produced it; ``severity`` is the intrinsic
    severity (drives the SARIF level); ``enforcement`` is the policy-resolved
    class that drives the exit code. ``to_dict`` is the stable JSON contract
    (ADR-007); fields are additive and ordered for deterministic output.
    """

    source: str  # SOURCE_VALIDATE | SOURCE_RELATIONSHIPS | SOURCE_REVIEW
    code: str
    severity: str  # "error" | "warning" | "info"
    enforcement: str  # ENFORCEMENT_BLOCKING | ENFORCEMENT_ADVISORY
    path: str
    line: int | None
    message: str

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "code": self.code,
            "severity": self.severity,
            "enforcement": self.enforcement,
            "path": self.path,
            "line": self.line,
            "message": self.message,
        }


@dataclass
class GateReport:
    """The unified enforcement result over a corpus (v0.21.14).

    ``ok`` is False when any finding is blocking — the single exit-code signal
    the PR gate consumes. ``to_dict`` is the stable JSON contract (ADR-007).
    """

    directory: str
    recursive: bool
    findings: list[GateFinding] = field(default_factory=list)

    @property
    def blocking(self) -> list[GateFinding]:
        return [f for f in self.findings if f.enforcement == ENFORCEMENT_BLOCKING]

    @property
    def advisory(self) -> list[GateFinding]:
        return [f for f in self.findings if f.enforcement == ENFORCEMENT_ADVISORY]

    @property
    def ok(self) -> bool:
        """True when nothing is blocking — advisory findings never fail the gate."""
        return not self.blocking

    def to_dict(self) -> dict:
        return {
            "schema_version": "1",
            "directory": self.directory,
            "recursive": self.recursive,
            "ok": self.ok,
            "blocking_count": len(self.blocking),
            "advisory_count": len(self.advisory),
            "findings": [f.to_dict() for f in self.findings],
        }


# Default enforcement classes per source. These are chosen so that, under the
# EMPTY_POLICY, a gate run is ``ok`` exactly when validate.ok AND
# relationships.ok AND review.ok — the v0.21.13 behaviour the policy refines.

# Validate: an "error" fails validation (it sets the invalid status), so it is
# blocking by default; warnings and OKF info findings are advisory.
_VALIDATE_DEFAULT = {"error": ENFORCEMENT_BLOCKING}

# Relationships: today *any* relationship issue fails `--validate` (exit 1), so
# every relationship finding is blocking by default. The intrinsic severity used
# for the SARIF level is the canonical mapping owned by the relationships
# service (RELATIONSHIP_SEVERITY), so SARIF and the gate never disagree.


def _validate_findings(result: DirectoryValidation) -> list[tuple[str, str, str, int | None, str]]:
    """``(code, severity, path, line, message)`` for every validate finding.

    Core validation findings carry a line anchor when present; OKF conformance
    findings are file-level (no line). Mirrors ``render_validate_sarif``.
    """
    out: list[tuple[str, str, str, int | None, str]] = []
    for file in result.files:
        for issue in file.issues:
            out.append((issue.code, issue.severity, file.path, issue.line, issue.message))
    if result.okf is not None:
        for finding in result.okf.findings:
            out.append((finding.code, finding.severity, finding.path, None, finding.message))
    return out


def _relationship_finding(issue: RelationshipIssue) -> tuple[str, str, str, int | None, str]:
    """``(code, severity, path, line, message)`` for one relationship finding.

    The message and anchor mirror ``render_relationships_sarif``: repository-level
    findings (duplicate identifier, cycle) anchor on the first involved path and
    name every file; reference findings anchor on the source. Line is always None
    (relationship findings are file-level).
    """
    from rac.output.sarif import _relationship_result

    # Reuse the SARIF result builder so the message and URI never drift from the
    # standalone `rac relationships --sarif` output (one formatting source).
    result = _relationship_result(issue)
    uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    severity = RELATIONSHIP_SEVERITY.get(issue.code, "warning")
    return (issue.code, severity, uri, None, result["message"]["text"])


def _review_finding(issue: ReviewIssue) -> tuple[str, str, str, int | None, str]:
    """``(code, severity, path, line, message)`` for one review finding.

    The message carries the suggested action so the fix is visible inline, exactly
    as ``render_review_sarif`` formats it.
    """
    message = f"{issue.message} — {issue.action}" if issue.action else issue.message
    return (issue.code, issue.severity, issue.path, None, message)


def build_gate(
    directory: str,
    recursive: bool = True,
    policy: EnforcementPolicy | None = None,
) -> GateReport:
    """Run validation, relationships, and review and enforce the corpus policy.

    When ``policy`` is None it is loaded from the directory's ``.rac/config.yaml``
    (:func:`load_enforcement_policy`). Each underlying finding is mapped to a
    :class:`GateFinding` with a default enforcement class, then the policy is
    applied — findings the policy turns ``off`` are dropped. Findings are sorted
    deterministically by ``(path, line, source, code, message)`` so the report,
    JSON, and SARIF are byte-stable (ADR-002).
    """
    if policy is None:
        policy = load_enforcement_policy(directory)

    validation = validate_directory(directory, recursive=recursive)
    relationships = validate_relationships(directory, recursive=recursive)
    review = build_review(directory, recursive=recursive)

    findings: list[GateFinding] = []

    def add(
        source: str,
        code: str,
        severity: str,
        path: str,
        line: int | None,
        message: str,
        default: str,
    ) -> None:
        enforcement = policy.classify(code, default)
        if enforcement is None:
            return  # suppressed by an ``off`` policy entry
        findings.append(
            GateFinding(
                source=source,
                code=code,
                severity=severity,
                enforcement=enforcement,
                path=path,
                line=line,
                message=message,
            )
        )

    for code, severity, path, line, message in _validate_findings(validation):
        add(
            SOURCE_VALIDATE,
            code,
            severity,
            path,
            line,
            message,
            _VALIDATE_DEFAULT.get(severity, ENFORCEMENT_ADVISORY),
        )

    for rel_issue in relationships.issues:
        code, severity, path, line, message = _relationship_finding(rel_issue)
        # Every relationship issue fails `--validate` today, so the default is
        # blocking; a policy may downgrade a specific code (e.g. superseded).
        add(SOURCE_RELATIONSHIPS, code, severity, path, line, message, ENFORCEMENT_BLOCKING)

    for review_issue in review.issues:
        code, severity, path, line, message = _review_finding(review_issue)
        # Priority 1-2 findings fail review today (ReviewReport.ok), so they are
        # blocking by default; advisory priorities (3+) are advisory.
        default = (
            ENFORCEMENT_BLOCKING
            if review_issue.priority <= PRIORITY_BROKEN_RELATIONSHIP
            else ENFORCEMENT_ADVISORY
        )
        add(SOURCE_REVIEW, code, severity, path, line, message, default)

    findings.sort(key=lambda f: (f.path, f.line or 0, f.source, f.code, f.message))
    return GateReport(directory=directory, recursive=recursive, findings=findings)
