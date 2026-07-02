"""Policy-aware unified enforcement — ``rac gate`` (v0.21.14, ADR-049 / ADR-063).

``rac gate`` is the single enforcement entry point. It runs validation,
relationship integrity, and review over one corpus, normalises every finding to
a :class:`GateFinding`, then classifies each as *blocking* or *advisory* under
the corpus enforcement policy (ADR-049 — enforcement is the product). The result
is one exit code, one JSON envelope, and one SARIF document, so a PR gate carries
the whole RAC contract as a single required check instead of three uploads.

Classification is governed, not hardcoded (ADR-063: the thin client renders, the
engine decides). A corpus declares an optional ``enforcement:`` section in its
committed ``.rac/config.yaml`` (owned and loaded by :mod:`rac.services.init`)
mapping finding codes to ``blocking`` / ``advisory`` / ``off``. The *default*
enforcement classes are chosen so that, with no policy, a gate run is ``ok``
exactly when validate, relationships, and review all pass — the v0.21.13
behaviour the policy refines.

Deterministic and offline (ADR-002): the gate composes the same deterministic
services, applies a pure policy pass, and sorts findings by a stable key, so an
unchanged corpus yields byte-identical report, JSON, and SARIF.

Single corpus walk (v0.21.19): the three analyses share one pre-walked snapshot
via the engine's ``*_from_corpus`` seams instead of each re-walking the tree — one
walk, not three — with output byte-identical to the prior multi-walk composition
(ADR-023). ``test_gate_perf`` pins that equivalence, and imports the private
finding helpers below to reconstruct the report the multi-walk way; their names,
signatures, and ``(code, severity, path, line, message)`` tuple shape are a hard
contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rac.core.corpus import walk_corpus
from rac.services.init import load_enforcement_policy, load_overrides
from rac.services.portfolio import portfolio_from_corpus
from rac.services.relationships import (
    RELATIONSHIP_SEVERITY,
    RelationshipIssue,
    validation_from_corpus,
)
from rac.services.review import (
    PRIORITY_BROKEN_RELATIONSHIP,
    ReviewIssue,
    review_from_portfolio,
)
from rac.services.validate import DirectoryValidation, validate_corpus

# The two enforcement classes a finding can carry, plus the suppressed marker
# (``off`` drops a finding entirely). Sources name where a finding originated.
ENFORCEMENT_BLOCKING = "blocking"
ENFORCEMENT_ADVISORY = "advisory"
ENFORCEMENT_OFF = "off"

SOURCE_VALIDATE = "validate"
SOURCE_RELATIONSHIPS = "relationships"
SOURCE_REVIEW = "review"


@dataclass(frozen=True)
class EnforcementPolicy:
    """A corpus enforcement policy: finding codes mapped to a class (ADR-049).

    Three disjoint *intent* sets. :meth:`classify` resolves a finding's effective
    class with a fixed precedence — ``off`` (suppress) wins, then ``blocking``,
    then ``advisory``, else the caller's default. A code declared in more than one
    set is therefore harmless: precedence makes the result independent of
    declaration order.
    """

    blocking: frozenset[str] = frozenset()
    advisory: frozenset[str] = frozenset()
    off: frozenset[str] = frozenset()

    def classify(self, code: str, default: str) -> str | None:
        """Effective enforcement class for ``code``, or ``None`` when suppressed.

        Precedence ``off`` -> ``blocking`` -> ``advisory`` -> ``default``. A
        ``None`` result means the policy turned this finding off and it is dropped.
        """
        if code in self.off:
            return None
        if code in self.blocking:
            return ENFORCEMENT_BLOCKING
        if code in self.advisory:
            return ENFORCEMENT_ADVISORY
        return default


# The neutral policy: every finding keeps its default class. Used when a corpus
# declares no ``enforcement:`` section, making the no-policy path a pure no-op.
EMPTY_POLICY = EnforcementPolicy()

# Default enforcement for a validate finding, keyed by intrinsic severity. Only an
# ``error`` (which sets the invalid status) is blocking; warnings and OKF info
# findings fall through to advisory. Imported by ``test_gate_perf``.
_VALIDATE_DEFAULT = {"error": ENFORCEMENT_BLOCKING}


@dataclass(frozen=True)
class GateFinding:
    """One enforced finding, normalised across the three underlying services.

    ``source`` records which service produced it; ``severity`` is the intrinsic
    severity (drives the SARIF level); ``enforcement`` is the policy-resolved class
    that drives the exit code. ``to_dict`` is the stable JSON contract (ADR-007),
    ordered for deterministic output.
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

    ``ok`` is False when any finding is blocking — the single exit-code signal the
    PR gate consumes. ``to_dict`` is the stable JSON contract (ADR-007).
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


# --- Per-source finding normalisers ------------------------------------------
# Each collapses a service's finding into the gate's common
# ``(code, severity, path, line, message)`` tuple. The tuple shape and these three
# names are imported by ``test_gate_perf`` — a hard contract.


def _validate_findings(result: DirectoryValidation) -> list[tuple[str, str, str, int | None, str]]:
    """``(code, severity, path, line, message)`` for every validate finding.

    Core validation issues carry a line anchor when present; OKF conformance
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

    Message and anchor are borrowed from the SARIF result builder so ``rac gate``
    and ``rac relationships --sarif`` share one formatting source and can never
    drift. Line is always None (relationship findings are file-level).
    """
    # Imported lazily: rac.output.sarif imports GateReport from this module, so a
    # module-level import here would close a cycle.
    from rac.output.sarif import _relationship_result

    result = _relationship_result(issue)
    uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    severity = RELATIONSHIP_SEVERITY.get(issue.code, "warning")
    return (issue.code, severity, uri, None, result["message"]["text"])


def _review_finding(issue: ReviewIssue) -> tuple[str, str, str, int | None, str]:
    """``(code, severity, path, line, message)`` for one review finding.

    The suggested action is appended so the fix is visible inline, exactly as
    ``render_review_sarif`` formats it. Line is always None.
    """
    message = f"{issue.message} — {issue.action}" if issue.action else issue.message
    return (issue.code, issue.severity, issue.path, None, message)


def build_gate(
    directory: str,
    recursive: bool = True,
    policy: EnforcementPolicy | None = None,
) -> GateReport:
    """Run validation, relationships, and review and enforce the corpus policy.

    When ``policy`` is None it is loaded from ``.rac/config.yaml``
    (:func:`load_enforcement_policy`). Each underlying finding is normalised, given
    a default enforcement class, then run through the policy — findings the policy
    turns ``off`` are dropped. Findings are sorted by
    ``(path, line, source, code, message)`` so report, JSON, and SARIF are
    byte-stable (ADR-002).

    One walk feeds every analysis (v0.21.19): the ``*_from_corpus`` snapshot seams
    produce results identical to their directory entry points
    (``validate_directory`` / ``validate_relationships`` / ``build_review``), which
    each walk once. Severity overrides (ADR-053) are loaded once and applied
    identically by every snapshot path.
    """
    if policy is None:
        policy = load_enforcement_policy(directory)

    entries = list(walk_corpus(directory, recursive=recursive))
    overrides = load_overrides(directory)

    validation = validate_corpus(directory, entries, recursive=recursive, overrides=overrides)
    relationships = validation_from_corpus(directory, entries, recursive=recursive)
    portfolio = portfolio_from_corpus(directory, entries, recursive=recursive)
    review = review_from_portfolio(directory, portfolio, recursive=recursive)

    findings: list[GateFinding] = []

    def enforce(
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

    # Validate: only an intrinsic error is blocking by default (it is what sets the
    # invalid status); warnings and OKF info findings default to advisory.
    for code, severity, path, line, message in _validate_findings(validation):
        enforce(
            SOURCE_VALIDATE,
            code,
            severity,
            path,
            line,
            message,
            _VALIDATE_DEFAULT.get(severity, ENFORCEMENT_ADVISORY),
        )

    # Relationships: every issue fails ``--validate`` today, so each defaults to
    # blocking; a policy may downgrade a specific code (e.g. superseded).
    for rel_issue in relationships.issues:
        code, severity, path, line, message = _relationship_finding(rel_issue)
        enforce(SOURCE_RELATIONSHIPS, code, severity, path, line, message, ENFORCEMENT_BLOCKING)

    # Review: priority 1-2 findings fail review today (ReviewReport.ok), so they
    # default to blocking; advisory priorities (3+) default to advisory.
    for review_issue in review.issues:
        code, severity, path, line, message = _review_finding(review_issue)
        default = (
            ENFORCEMENT_BLOCKING
            if review_issue.priority <= PRIORITY_BROKEN_RELATIONSHIP
            else ENFORCEMENT_ADVISORY
        )
        enforce(SOURCE_REVIEW, code, severity, path, line, message, default)

    findings.sort(key=lambda f: (f.path, f.line or 0, f.source, f.code, f.message))
    return GateReport(directory=directory, recursive=recursive, findings=findings)
