"""Repository health diagnostic — ``rac doctor`` (v0.23.0, WS3).

One front door for corpus health. RAC already *detects* most defects, but the
signals are spread across three commands a new adopter has to know to chain.
``doctor`` runs them in a single pass and returns one verdict, each finding
carrying a paste-ready fix. It reuses the services that already own each defect
class rather than re-deriving them (ADR-049, ADR-055, ADR-060):

- structural validity — :func:`rac.services.validate.validate_directory`;
- relationship integrity (broken / ambiguous / self / type-mismatch / retired /
  duplicate-id / cyclic) — :func:`rac.services.relationships.validate_relationships`.

On top of the reused signals ``doctor`` adds only what no command already
provides (REQ-002): **high-fan-out hubs** (a node whose inbound-plus-outbound
resolved-edge degree exceeds a configurable threshold) and a heuristic
**injection-style content** flag for human review (REQ-005). Orphans fall out of
the same one-hop degree pass and are counted from the shared inbound signal
(ADR-078), so ``doctor``'s orphan count equals the portfolio's exactly — a test
pins the no-drift.

Everything is deterministic and offline (ADR-002, ADR-034, ADR-066): no AI, no
network, byte-identical output across runs on an unchanged corpus. ``doctor``
never edits content — the injection flag is a reviewable WARNING, never a
hard-fail or an auto-edit, and asserts nothing about safety; the trust boundary
stays human PR review (ADR-065). The run exits non-zero only on a validation or
relationship-integrity *error*; every warning (orphan, hub, injection, unlinked
reference) still exits zero (REQ-007).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rac.core.artifacts import spec_for
from rac.core.corpus import CorpusCache, CorpusEntry
from rac.services.links import detect_unlinked_references
from rac.services.relationships import (
    ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_RELATIONSHIP_CYCLE,
    RELATIONSHIP_SEVERITY,
    RelationshipIssue,
    inbound_counts_from_corpus,
    relationships_from_corpus,
    validate_relationships,
)
from rac.services.validate import STATUS_INVALID, validate_directory

# A node with more than this many resolved relationship edges is a high-fan-out
# hub. The default is deliberately generous; a run can tighten it per invocation
# so authors fix the data while doctor only names it (REQ-004).
DEFAULT_HUB_THRESHOLD = 20

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# Errors sort before warnings; the rest of the key (path, code, problem) breaks
# ties deterministically (ADR-002).
_SEVERITY_RANK = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1}

# Stable finding codes — part of the JSON contract (ADR-007). Validation and
# relationship findings keep their upstream codes; these five originate here.
CODE_INVALID_ARTIFACT = "invalid-artifact"
CODE_ORPHANED_ARTIFACT = "orphaned-artifact"
CODE_HIGH_FAN_OUT_HUB = "high-fan-out-hub"
CODE_INJECTION_CONTENT = "injection-style-content"
CODE_UNLINKED_REFERENCE = "unlinked-reference"

# Heuristic injection-style idioms (REQ-005): instruction overrides, role/system
# impersonation, concealment from the user, and steering away from recorded
# decisions. Each `.` is intentionally line-bounded (no DOTALL) so a match is a
# contained idiom, not two distant paragraphs colliding. A review aid only, never
# a safety verdict (ADR-065). The pattern text is behaviour, not structure — it
# is preserved verbatim so what does and does not flag never shifts.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction-override",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b"
            r"(previous|prior|above|earlier|preceding|all|the system|your)\b.{0,20}"
            r"(instruction|instructions|prompt|directive|directives|rule|rules|context)",
            re.IGNORECASE,
        ),
    ),
    (
        "role-reassignment",
        re.compile(
            r"\byou are now\b|\bfrom now on,?\s+you\s+(are|will|must|should|shall)\b|"
            r"\bpretend to be\b|\bact as if you\s+(are|were)\b",
            re.IGNORECASE,
        ),
    ),
    ("ai-impersonation", re.compile(r"\bas an ai(\s+language)?\s+model\b", re.IGNORECASE)),
    (
        "chat-role-injection",
        re.compile(r"^\s*(system|assistant|developer|tool)\s*:", re.IGNORECASE | re.MULTILINE),
    ),
    (
        "conceal-from-user",
        re.compile(
            r"\b(do not|don't|never|without)\b.{0,30}"
            r"(tell|telling|inform|informing|mention|mentioning|reveal|revealing|notify)\b.{0,20}"
            r"\b(the user|them|anyone)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "decision-steering",
        re.compile(
            r"\b(ignore|disregard|override|bypass|violate)\b.{0,40}"
            r"\b(recorded\s+)?(decision|decisions|adr|requirement|policy)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class DoctorFinding:
    """One health finding: where, what, how severe, and the paste-ready fix."""

    path: str
    code: str
    severity: str  # SEVERITY_ERROR | SEVERITY_WARNING
    problem: str
    fix: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "code": self.code,
            "severity": self.severity,
            "problem": self.problem,
            "fix": self.fix,
        }


@dataclass
class DoctorReport:
    """Aggregated repository health — the stable JSON contract (ADR-007)."""

    directory: str
    hub_threshold: int
    findings: list[DoctorFinding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == SEVERITY_WARNING)

    @property
    def ok(self) -> bool:
        """A run passes when no error-severity finding is present (REQ-007)."""
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "directory": self.directory,
            "hub_threshold": self.hub_threshold,
            "ok": self.ok,
            "summary": {"errors": self.error_count, "warnings": self.warning_count},
            "findings": [f.to_dict() for f in self.findings],
        }


def diagnose(
    directory: str, recursive: bool = True, hub_threshold: int = DEFAULT_HUB_THRESHOLD
) -> DoctorReport:
    """Run every health phase over one shared corpus snapshot and sort the result.

    A single per-invocation :class:`CorpusCache` (WS8) is threaded through the
    validation, relationship, degree, injection, and unlinked-reference phases so
    each artifact is parsed once for the whole run. The cache is a performance
    path only — the report is byte-identical to reprocessing each phase from a
    fresh walk (REQ-003), which ``test_idempotent`` pins.
    """
    cache = CorpusCache()
    entries = cache.collect(directory, recursive=recursive)

    findings: list[DoctorFinding] = []
    findings.extend(_validation_findings(directory, recursive, cache))
    findings.extend(_relationship_findings(directory, recursive, cache))
    findings.extend(_degree_findings(entries, hub_threshold))
    findings.extend(_injection_findings(entries))
    findings.extend(_unlinked_reference_findings(directory, entries, recursive))

    # Errors first, then a stable (path, code, problem) tiebreak so the ordering
    # is independent of the phase that produced each finding (ADR-002).
    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.path, f.code, f.problem))
    return DoctorReport(directory=directory, hub_threshold=hub_threshold, findings=findings)


def _validation_findings(
    directory: str, recursive: bool, cache: CorpusCache
) -> list[DoctorFinding]:
    """One error finding per structurally invalid artifact, reusing the validator.

    The validator owns the defect detail; doctor surfaces only the verdict and
    points at ``rac validate <path>`` for the full report (REQ-001, REQ-003).
    """
    result = validate_directory(directory, recursive=recursive, cache=cache)
    findings: list[DoctorFinding] = []
    for file in result.files:
        if file.status != STATUS_INVALID:
            continue
        error_codes = sorted(
            {issue.code for issue in file.issues if issue.severity == SEVERITY_ERROR}
        )
        findings.append(
            DoctorFinding(
                path=file.path,
                code=CODE_INVALID_ARTIFACT,
                severity=SEVERITY_ERROR,
                problem="structural validation failed: " + ", ".join(error_codes),
                fix=f"Run: rac validate {file.path}",
            )
        )
    return findings


def _relationship_findings(
    directory: str, recursive: bool, cache: CorpusCache
) -> list[DoctorFinding]:
    """One finding per relationship-integrity issue, reusing the engine.

    Broken / ambiguous / type-mismatch / retired / self references, cycles, and
    duplicate ids all come from ``relationships --validate`` (REQ-002, REQ-004).
    Intrinsic severity is the recorded source of truth (``RELATIONSHIP_SEVERITY``);
    an unmapped code defaults to error so a new integrity defect fails loud.
    """
    result = validate_relationships(directory, recursive=recursive, cache=cache)
    return [
        DoctorFinding(
            path=_issue_path(issue),
            code=issue.code,
            severity=RELATIONSHIP_SEVERITY.get(issue.code, SEVERITY_ERROR),
            problem=_issue_problem(issue),
            fix=f"Run: rac relationships {directory} --validate",
        )
        for issue in result.issues
    ]


def _issue_path(issue: RelationshipIssue) -> str:
    """The best anchor path for a relationship issue: source, else first involved."""
    if issue.source_path:
        return issue.source_path
    if issue.paths:
        return issue.paths[0]
    return ""


def _issue_problem(issue: RelationshipIssue) -> str:
    """A human-readable one-liner per issue kind (duplicate / cycle / reference)."""
    if issue.code == ISSUE_DUPLICATE_IDENTIFIER:
        joined = ", ".join(issue.paths or [])
        return f"duplicate artifact identifier {issue.identifier!r} in: {joined}"
    if issue.code == ISSUE_RELATIONSHIP_CYCLE:
        chain = " -> ".join(issue.paths or [])
        return f"relationship cycle in {issue.relationship!r}: {chain}"
    return f"{issue.code} via {issue.relationship!r} -> {issue.target!r}"


def _degree_findings(entries: list[CorpusEntry], hub_threshold: int) -> list[DoctorFinding]:
    """Orphans (inbound degree 0) and high-fan-out hubs from one degree pass.

    Only typed artifacts (``spec_for`` resolves) participate. Inbound comes from
    the shared canonical signal (also the search graph boost, ADR-078) so the
    orphan count cannot drift from the portfolio's; outbound is counted here over
    resolved edges. Degree is their sum.
    """
    known_paths = [str(e.path) for e in entries if spec_for(e.artifact_type) is not None]
    inbound = inbound_counts_from_corpus(entries)
    outbound = _outbound_resolved_degrees(entries, set(known_paths))

    findings: list[DoctorFinding] = []
    for path in known_paths:
        inbound_degree = inbound.get(path, 0)
        degree = inbound_degree + outbound[path]
        if inbound_degree == 0:
            findings.append(
                DoctorFinding(
                    path=path,
                    code=CODE_ORPHANED_ARTIFACT,
                    severity=SEVERITY_WARNING,
                    problem="no other artifact references this one (orphaned)",
                    fix=(
                        "Reference it from a related artifact (a `## Related ...` "
                        "section), or confirm it is intentionally standalone."
                    ),
                )
            )
        if degree > hub_threshold:
            findings.append(
                DoctorFinding(
                    path=path,
                    code=CODE_HIGH_FAN_OUT_HUB,
                    severity=SEVERITY_WARNING,
                    problem=(
                        f"high-fan-out hub: {degree} resolved relationship edges "
                        f"(threshold {hub_threshold})"
                    ),
                    fix=(
                        "Consider splitting this artifact or narrowing its "
                        "relationships so a single node is not a traversal bottleneck."
                    ),
                )
            )
    return findings


def _outbound_resolved_degrees(entries: list[CorpusEntry], known_paths: set[str]) -> dict[str, int]:
    """Resolved outbound edge count per known artifact (unresolved edges ignored)."""
    degrees = dict.fromkeys(known_paths, 0)
    for rel in relationships_from_corpus(entries):
        if rel.resolved_path is None:
            continue  # only unique, non-self, resolved edges count toward degree
        if rel.source_path in degrees:
            degrees[rel.source_path] += 1
    return degrees


def _unlinked_reference_findings(
    directory: str, entries: list[CorpusEntry], recursive: bool
) -> list[DoctorFinding]:
    """Body references to other artifacts with no declared edge (ADR-082).

    Advisory WARNINGs suggesting a ``## Related`` link the prose already implies.
    The detector reuses the shared snapshot (no second walk) and writes nothing —
    it suggests, it never applies (ADR-082).
    """
    return [
        DoctorFinding(
            path=ref.source_path,
            code=CODE_UNLINKED_REFERENCE,
            severity=SEVERITY_WARNING,
            problem=(
                f"body references {ref.matched_token} but declares no "
                f"{ref.related_section} link to it"
            ),
            fix=(
                f"Add `{ref.suggested_line}` under `## {ref.related_section}` "
                "if the link is intended — a suggestion to review; RAC writes "
                "no edge (ADR-082)."
            ),
        )
        for ref in detect_unlinked_references(directory, entries=entries, recursive=recursive)
    ]


def _injection_findings(entries: list[CorpusEntry]) -> list[DoctorFinding]:
    """Heuristic injection-style content flag for human review (REQ-005).

    A reviewable WARNING only — never an auto-edit, a hard-fail, or a safety
    claim (ADR-065). Each artifact's stored text is scanned for the narrow idioms
    in :data:`_INJECTION_PATTERNS`; every matching label is named, sorted, in the
    finding so the message is stable.
    """
    findings: list[DoctorFinding] = []
    for entry in entries:
        text = _scan_text(str(entry.path))
        if text is None:
            continue
        matched = sorted(label for label, pattern in _INJECTION_PATTERNS if pattern.search(text))
        if not matched:
            continue
        findings.append(
            DoctorFinding(
                path=str(entry.path),
                code=CODE_INJECTION_CONTENT,
                severity=SEVERITY_WARNING,
                problem=(
                    f"instruction-like / injection-style content for review ({', '.join(matched)})"
                ),
                fix=(
                    "Review this content; artifact content is untrusted and the "
                    "trust boundary is human PR review (ADR-065). Remove or quote "
                    "the flagged phrasing if it was not intended as literal guidance."
                ),
            )
        )
    return findings


def _scan_text(path: str) -> str | None:
    """The artifact's stored text, or None when it cannot be read as UTF-8."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):  # pragma: no cover — walked files are readable
        return None


# --- Rendering ---------------------------------------------------------------
# doctor owns its own human/JSON rendering (the established per-service pattern);
# both are byte-pinned by the golden fixtures. JSON uses ``ensure_ascii=False`` so
# the em-dash and backticks in fix text survive verbatim.


def render_doctor_json(report: DoctorReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def render_doctor_human(report: DoctorReport) -> str:
    lines = [f"Repository health: {report.directory}", ""]
    if not report.findings:
        lines.append("✓ No issues found.")
        return "\n".join(lines)

    lines.append(f"{report.error_count} error(s), {report.warning_count} warning(s)")
    lines.append("")
    for finding in report.findings:
        label = "ERROR  " if finding.severity == SEVERITY_ERROR else "WARNING"
        lines.append(f"{label}  {finding.path}")
        lines.append(f"  [{finding.code}] {finding.problem}")
        lines.append(f"  fix: {finding.fix}")
        lines.append("")
    lines.append("✓ No errors (warnings are advisory)." if report.ok else "✗ Errors present.")
    return "\n".join(lines)
