"""Mentioned-but-unlinked reference detection (link suggestions, ADR-082).

For each artifact, find the references its *body* makes to other corpus
artifacts that are not declared as ``## Related`` edges, and return them as
advisory suggestions. ``rac doctor`` is the first surface for these.

The boundaries this honours:

* **Suggest, never apply (ADR-082).** The detector emits findings only — it
  writes no edge. Declared ``## Related`` sections remain the source of truth
  (ADR-074) and promotion stays a human review act (ADR-065).
* **Deterministic and offline (ADR-002, ADR-066).** A pure function of corpus
  bytes: identical bytes yield byte-identical findings. No model, no network.
* **Reuse the existing machinery.** Resolution goes through the same resolver
  validation uses (:func:`resolve_in_index`), the body text comes from the
  shared parser's sections, the declared graph from
  :func:`relationships_from_corpus`, and the relationship vocabulary from
  :data:`RELATIONSHIP_SECTIONS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rac.core.corpus import CorpusEntry, walk_corpus
from rac.services.index import index_from_corpus
from rac.services.relationships import RELATIONSHIP_SECTIONS, relationships_from_corpus
from rac.services.resolve import OUTCOME_RESOLVED, resolve_in_index

# A candidate reference is a run of alphanumerics with internal single hyphens
# kept, so ``adr-074`` and ``RAC-KW47GGS85CKG`` each survive as one token. The
# search tokenizer (ADR-037) would split on the hyphen; here the hyphen is part
# of the token and every other character is a boundary, so matching stays on
# token boundaries without substring false positives.
_CANDIDATE_RE = re.compile(r"[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*")

# The corpus-idiomatic short reference for a decision — ``<letters>-<digits>``,
# e.g. ``adr-074``. When a target has no such alias the filename stem is used
# instead (the form every non-decision type writes).
_NUMBERED_REF_RE = re.compile(r"^[A-Za-z]+-\d+$")

# Relationship-section headings, normalized. Their contents are *declared* edges,
# not body mentions, so these sections are never scanned for suggestions.
_RELATIONSHIP_HEADINGS = frozenset(RELATIONSHIP_SECTIONS)


@dataclass(frozen=True)
class UnlinkedReference:
    """One advisory suggestion: a body mention with no declared edge.

    ``source``'s body names ``target`` (by id, filename-style ref, or alias),
    ``target != source``, and ``target`` is not already a declared ``## Related``
    edge of ``source``.
    """

    source_path: str
    target_path: str
    target_id: str
    matched_token: str
    related_section: str  # display heading, e.g. "Related Decisions"
    suggested_line: str  # paste-ready, e.g. "- adr-074"


def _related_section_for(target_type: str) -> str:
    """Display heading of the ``## Related <Type>s`` section for ``target_type``."""
    return f"related {target_type}s".title()


def _preferred_ref(aliases: list[str], path: str) -> str:
    """The corpus-idiomatic short reference for the target (``adr-074`` / stem)."""
    numbered = sorted((a for a in aliases if _NUMBERED_REF_RE.fullmatch(a)), key=len)
    if numbered:
        return numbered[0]
    return Path(path).stem


def detect_unlinked_references(
    directory: str,
    entries: list[CorpusEntry] | None = None,
    recursive: bool = True,
) -> list[UnlinkedReference]:
    """References an artifact's body names but does not declare as edges.

    ``entries`` lets a caller (such as ``rac doctor``) pass an already-walked
    corpus snapshot so the corpus is parsed once; when omitted the directory is
    walked here. Findings are sorted by ``(source_path, target_id)`` so the
    output is byte-stable.
    """
    if entries is None:
        entries = list(walk_corpus(directory, recursive=recursive))
    index = index_from_corpus(directory, entries, recursive=recursive).artifacts
    by_path = {entry.path: entry for entry in index}

    # Declared edges keyed by source, using the same resolution validation uses
    # (resolved, unique targets only) so "already linked" cannot drift.
    declared: dict[str, set[str]] = {}
    for rel in relationships_from_corpus(entries):
        if rel.resolved_path is not None:
            declared.setdefault(rel.source_path, set()).add(rel.resolved_path)

    findings: list[UnlinkedReference] = []
    for source in index:
        self_aliases = {alias.casefold() for alias in source.aliases}
        already = declared.get(source.path, set())
        seen_targets: set[str] = set()
        for section in source.search_sections:
            if section.heading.strip().casefold() in _RELATIONSHIP_HEADINGS:
                continue  # declared edges, not body mentions
            for line in section.lines:
                for match in _CANDIDATE_RE.finditer(line):
                    token = match.group(0)
                    if token.casefold() in self_aliases:
                        continue  # a self-reference is not a missing link
                    result = resolve_in_index(index, token)
                    if result.outcome != OUTCOME_RESOLVED:
                        continue  # not a unique corpus artifact
                    target = result.artifact
                    assert target is not None  # a resolved outcome carries the artifact
                    if target.path == source.path or target.path in already:
                        continue
                    if target.path in seen_targets:
                        continue  # one finding per (source, target) pair
                    seen_targets.add(target.path)
                    target_entry = by_path[target.path]
                    findings.append(
                        UnlinkedReference(
                            source_path=source.path,
                            target_path=target.path,
                            target_id=target.id,
                            matched_token=token,
                            related_section=_related_section_for(target.type),
                            suggested_line=(
                                f"- {_preferred_ref(list(target_entry.aliases), target.path)}"
                            ),
                        )
                    )
    findings.sort(key=lambda f: (f.source_path, f.target_id))
    return findings
