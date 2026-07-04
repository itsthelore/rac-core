"""Artifact drift detection — the git-native "suspect link" (phase 1).

A referenced target can change in git while the artifact that references it stays
untouched. The corpus already holds both the validated relationship graph
(ADR-074) and every artifact's last-committed time (ADR-045), but emits no signal
— the failure mode PR review alone is proven not to catch (the 27,772-PR evidence
in the `freshness-and-drift-detection` roadmap). Enterprise requirements tools
call this a "suspect link"; this is Lore's deterministic, git-native equivalent.

A finding requires two conditions, both deterministic and offline (ADR-002,
ADR-066), with no wall-clock input:

1. **Touch** — a validated, resolvable reference points at a target whose last
   commit is newer than the referring artifact's own last commit.
2. **Substance** — the target's *meaning-bearing prose* actually changed since the
   referrer was last touched. A link-only or metadata-only edit (adding a
   ``## Related`` or ``## Applies To`` section, a rename, reformatting) is not
   drift: the decision the referrer relies on still says the same thing. This is
   the meaningful-change scoping the roadmap folds into phase 1 with real findings
   in hand — the last-committed comparison alone over-flags on batch commits and
   metadata touches.

It is advisory and never a verdict (ADR-034) — "review recommended," not "wrong" —
and never an auto-fix (a recorded non-goal). Only declared, resolvable artifact
references are considered; external-reference sections (related tickets, verified
by) carry ``resolved_path is None`` and are excluded — never dated. Every value
degrades to silence outside git, for untracked files, or in a shallow clone
missing the revisions (ADR-045): where substance cannot be determined the finding
falls back conservatively to the touch signal rather than being wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.markdown import parse
from rac.services.recency import (
    artifact_recency,
    file_at_revision,
    first_change_sha,
    last_change_sha,
    repository_root,
)
from rac.services.relationships import RELATIONSHIP_SECTIONS, relationships_from_corpus

# Section headings whose change is not substantive drift: relationship and scope
# sections (declared links, ``## Applies To``), supersedes, external references,
# and the ID. ``product.sections`` keys are casefolded, so the exclusion set is too.
_NON_SUBSTANTIVE_SECTIONS = {s.casefold() for s in RELATIONSHIP_SECTIONS} | {"id"}


@dataclass(frozen=True)
class DriftFinding:
    """One suspect link: a resolvable reference whose target's prose changed after its referrer.

    ``source_committed`` / ``target_committed`` are the evidencing commit times —
    reported facts, with ``target_committed > source_committed`` the touch condition
    and a substantive prose change the second (REQ-004).
    """

    source_path: str
    target_path: str
    relationship: str  # snake_case section name ("related_decisions", ...)
    source_committed: datetime
    target_committed: datetime


def _substantive(content: str) -> str:
    """The target's meaning-bearing prose: parsed section bodies minus frontmatter,
    relationship / scope sections, and the ID, so a link-only or metadata-only edit
    compares equal. Deterministic and offline (ADR-066)."""
    product = parse(content)
    return "\n\n".join(
        f"{heading}\n{body}"
        for heading, body in sorted(product.sections.items())
        if heading not in _NON_SUBSTANTIVE_SECTIONS
    )


def detect_drift(
    directory: str,
    recursive: bool = True,
    *,
    entries: list[CorpusEntry] | None = None,
) -> list[DriftFinding]:
    """Every suspect link in ``directory``, deterministically ordered.

    Computed from the git-derived recency service (ADR-045) and the validated
    relationship graph (ADR-074) — resolved, unique, non-self, in-corpus edges
    only, so external references are excluded by construction (ADR-087). A pre-walked
    ``entries`` snapshot is reused when given (the doctor pass supplies one). Outside
    git every last-committed time is ``None`` and the result is empty (REQ-005).
    """
    if entries is None:
        entries = list(walk_corpus(directory, recursive=recursive))
    last_by_path = {
        a.path: a.last_committed for a in artifact_recency(directory, recursive=recursive).artifacts
    }
    repo_root = repository_root(directory)

    sha_cache: dict[str, str | None] = {}
    current_prose_cache: dict[str, str | None] = {}

    def _source_sha(path: str) -> str | None:
        if path not in sha_cache:
            sha_cache[path] = last_change_sha(repo_root, path) if repo_root is not None else None
        return sha_cache[path]

    def _current_prose(path: str) -> str | None:
        if path not in current_prose_cache:
            try:
                current_prose_cache[path] = _substantive(Path(path).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                current_prose_cache[path] = None
        return current_prose_cache[path]

    def _prose_changed(source_path: str, target_path: str) -> bool:
        """Did the target's prose change since the source was last committed?

        Conservative: any inability to read the historical revision (no git, shallow
        clone, unreadable file) falls back to ``True`` — the touch signal stands
        rather than a real change being silently dropped.
        """
        if repo_root is None:
            return True
        source_sha = _source_sha(source_path)
        if source_sha is None:
            return True
        baseline = file_at_revision(repo_root, source_sha, target_path)
        if baseline is None:
            # The target did not exist at the source's last commit; compare against
            # its earliest revision so a target that never changed its prose is not
            # flagged merely for being authored after the reference.
            first_sha = first_change_sha(repo_root, target_path)
            baseline = file_at_revision(repo_root, first_sha, target_path) if first_sha else None
        current = _current_prose(target_path)
        if baseline is None or current is None:
            return True
        return _substantive(baseline) != current

    findings: list[DriftFinding] = []
    seen: set[tuple[str, str]] = set()
    for rel in relationships_from_corpus(entries):
        if rel.resolved_path is None:  # unresolved / external / self — excluded
            continue
        source = last_by_path.get(rel.source_path)
        target = last_by_path.get(rel.resolved_path)
        if source is None or target is None:  # git cannot date one side — silent
            continue
        if target <= source:  # referrer is at least as fresh — not suspect
            continue
        key = (rel.source_path, rel.resolved_path)
        if key in seen:  # decide each edge once
            continue
        seen.add(key)
        if not _prose_changed(rel.source_path, rel.resolved_path):  # touch, not substance
            continue
        findings.append(
            DriftFinding(
                source_path=rel.source_path,
                target_path=rel.resolved_path,
                relationship=rel.relationship,
                source_committed=source,
                target_committed=target,
            )
        )
    findings.sort(key=lambda f: (f.source_path, f.target_path))
    return findings
