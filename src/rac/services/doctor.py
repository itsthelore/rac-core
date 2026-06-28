"""Repository health diagnostic — `rac doctor` (v0.23.0, WS3).

One front door for corpus health. RAC already *detects* most defects, but across
three commands a new adopter must know to chain. `doctor` runs them in one pass
and returns a single verdict with a paste-ready fix per finding, reusing the
existing services rather than re-deriving any defect class they already own
(ADR-049, ADR-055, ADR-060):

- structural validity, from :func:`rac.services.validate.validate_directory`;
- relationship integrity (broken / ambiguous / self / type-mismatch / retired /
  duplicate-id / cyclic), from
  :func:`rac.services.relationships.validate_relationships`.

It adds only the two diagnostics no command provides (REQ-002): **high-fan-out
hubs** (a node whose inbound-plus-outbound resolved-edge degree exceeds a
configurable threshold) and a heuristic **injection-style content** flag for
human review (REQ-005). Orphans are derived from the same one-hop degree pass
and match the portfolio's "never a resolved target" count exactly (a test pins
this), so the signal cannot drift from the service that owns it.

Everything is deterministic and offline (ADR-002, ADR-034, ADR-066): no AI, no
network, byte-identical output across runs on an unchanged corpus. `doctor`
never edits content — the injection flag is a reviewable WARNING, never a
hard-fail or an auto-edit, and makes no safety claim; the trust boundary stays
human PR review (ADR-065). It exits non-zero only on a validation or
relationship-integrity *error*; warnings (orphans, hubs, injection) exit zero
(REQ-007).
"""

from __future__ import annotations

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

# Fixed default hub threshold, configurable per run (decision: ~20). A node with
# more than this many resolved relationship edges is a high-fan-out hub WS4 must
# bound at runtime; authors fix the data, doctor names it (REQ-004).
DEFAULT_HUB_THRESHOLD = 20

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
_SEVERITY_RANK = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1}

# Stable doctor finding codes (part of the JSON contract, ADR-007). Validation
# and relationship findings reuse the upstream codes; these three are doctor's.
CODE_INVALID_ARTIFACT = "invalid-artifact"
CODE_ORPHANED_ARTIFACT = "orphaned-artifact"
CODE_HIGH_FAN_OUT_HUB = "high-fan-out-hub"
CODE_INJECTION_CONTENT = "injection-style-content"
CODE_UNLINKED_REFERENCE = "unlinked-reference"

# Heuristic injection-style idioms (REQ-005): instruction overrides, role/system
# impersonation, concealment from the user, and steering away from recorded
# decisions. Deterministic and narrow — each `.` stays within a line (no DOTALL),
# so a match is a contained idiom, not an accident of two distant paragraphs.
# This is a review aid, never a safety verdict (ADR-065).
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
    """Aggregated repository health (stable JSON contract, ADR-007)."""

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
    """Run validation, relationship integrity, and the two new checks in one pass.

    All four phases share one per-invocation :class:`CorpusCache` (WS8), so each
    artifact is parsed once for the whole run rather than re-parsed by the
    validation, relationship, and degree/injection phases independently. The
    short-circuit is a performance path only — the report is byte-identical to a
    full reprocess (REQ-003).
    """
    cache = CorpusCache()
    entries = cache.collect(directory, recursive=recursive)
    findings: list[DoctorFinding] = []
    findings.extend(_validation_findings(directory, recursive, cache))
    findings.extend(_relationship_findings(directory, recursive, cache))
    findings.extend(_degree_findings(entries, hub_threshold))
    findings.extend(_injection_findings(entries))
    findings.extend(_unlinked_reference_findings(directory, entries, recursive))
    # Deterministic order: errors before warnings, then path, code, problem.
    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.path, f.code, f.problem))
    return DoctorReport(directory=directory, hub_threshold=hub_threshold, findings=findings)


def _validation_findings(
    directory: str, recursive: bool, cache: CorpusCache | None = None
) -> list[DoctorFinding]:
    """One finding per structurally invalid artifact, reusing the validator.

    The validator owns the defect detail; doctor surfaces the verdict and points
    at `rac validate <path>` for the full report (REQ-001, REQ-003).
    """
    result = validate_directory(directory, recursive=recursive, cache=cache)
    findings: list[DoctorFinding] = []
    for file in result.files:
        if file.status != STATUS_INVALID:
            continue
        codes = sorted({issue.code for issue in file.issues if issue.severity == SEVERITY_ERROR})
        problem = "structural validation failed: " + ", ".join(codes)
        findings.append(
            DoctorFinding(
                path=file.path,
                code=CODE_INVALID_ARTIFACT,
                severity=SEVERITY_ERROR,
                problem=problem,
                fix=f"Run: rac validate {file.path}",
            )
        )
    return findings


def _relationship_findings(
    directory: str, recursive: bool, cache: CorpusCache | None = None
) -> list[DoctorFinding]:
    """One finding per relationship-integrity issue, reusing the engine.

    Cycles, duplicate ids, broken / ambiguous / type-mismatch / retired / self
    references all come from `relationships --validate` (REQ-002, REQ-004);
    intrinsic severity is the recorded source of truth (`RELATIONSHIP_SEVERITY`).
    """
    result = validate_relationships(directory, recursive=recursive, cache=cache)
    findings: list[DoctorFinding] = []
    for issue in result.issues:
        findings.append(
            DoctorFinding(
                path=_issue_path(issue),
                code=issue.code,
                severity=RELATIONSHIP_SEVERITY.get(issue.code, SEVERITY_ERROR),
                problem=_issue_problem(issue),
                fix=f"Run: rac relationships {directory} --validate",
            )
        )
    return findings


def _issue_path(issue: RelationshipIssue) -> str:
    if issue.source_path:
        return issue.source_path
    if issue.paths:
        return issue.paths[0]
    return ""


def _issue_problem(issue: RelationshipIssue) -> str:
    if issue.code == ISSUE_DUPLICATE_IDENTIFIER:
        return (
            f"duplicate artifact identifier {issue.identifier!r} in: {', '.join(issue.paths or [])}"
        )
    if issue.code == ISSUE_RELATIONSHIP_CYCLE:
        return f"relationship cycle in {issue.relationship!r}: {' -> '.join(issue.paths or [])}"
    return f"{issue.code} via {issue.relationship!r} -> {issue.target!r}"


def _degree_findings(entries: list[CorpusEntry], hub_threshold: int) -> list[DoctorFinding]:
    """Orphans (inbound degree 0) and high-fan-out hubs, from one degree pass.

    Doctor's own one-hop degree computation (REQ-002): resolved edges only,
    counted per node. The orphan definition matches the portfolio's exactly —
    a known artifact that is never a resolved target — so it cannot drift.
    """
    known_paths = {str(e.path) for e in entries if spec_for(e.artifact_type) is not None}
    # Inbound is the shared canonical signal (also the search graph boost, ADR-078)
    # so the orphan count cannot drift from it; outbound is doctor's own one pass.
    counts = inbound_counts_from_corpus(entries)
    inbound: dict[str, int] = {p: counts.get(p, 0) for p in known_paths}
    outbound: dict[str, int] = {p: 0 for p in known_paths}
    for rel in relationships_from_corpus(entries):
        if rel.resolved_path is None:  # only resolved (unique, non-self) edges
            continue
        if rel.source_path in outbound:
            outbound[rel.source_path] += 1

    findings: list[DoctorFinding] = []
    for path in known_paths:
        degree = inbound[path] + outbound[path]
        if inbound[path] == 0:
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


def _unlinked_reference_findings(
    directory: str, entries: list[CorpusEntry], recursive: bool
) -> list[DoctorFinding]:
    """Body references to other artifacts with no declared edge (ADR-082).

    Advisory WARNINGs that suggest a `## Related` link the prose already implies;
    the detector writes nothing (suggest, never apply). Reuses the shared corpus
    snapshot so no second walk happens.
    """
    findings: list[DoctorFinding] = []
    for ref in detect_unlinked_references(directory, entries=entries, recursive=recursive):
        findings.append(
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
        )
    return findings


def _injection_findings(entries: list[CorpusEntry]) -> list[DoctorFinding]:
    """Heuristic injection-style content flag for human review (REQ-005).

    A reviewable WARNING only — never an auto-edit, a hard-fail, or a safety
    claim (ADR-065). Each artifact's stored text is scanned for the narrow
    idioms in :data:`_INJECTION_PATTERNS`; the first match names the finding.
    """
    findings: list[DoctorFinding] = []
    for entry in entries:
        text = _scan_text(str(entry.path))
        if text is None:
            continue
        matched = [label for label, pattern in _INJECTION_PATTERNS if pattern.search(text)]
        if matched:
            findings.append(
                DoctorFinding(
                    path=str(entry.path),
                    code=CODE_INJECTION_CONTENT,
                    severity=SEVERITY_WARNING,
                    problem=(
                        "instruction-like / injection-style content for review "
                        f"({', '.join(sorted(matched))})"
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
    """The artifact's stored text, or None if it cannot be read as UTF-8."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):  # pragma: no cover — walked files are readable
        return None


# --- Rendering ---------------------------------------------------------------


def render_doctor_json(report: DoctorReport) -> str:
    import json

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
    verdict = "✓ No errors (warnings are advisory)." if report.ok else "✗ Errors present."
    lines.append(verdict)
    return "\n".join(lines)
