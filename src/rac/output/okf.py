"""OKF bundle export — `rac export --okf` (v0.13.6).

A derived view of the corpus as a conformant Open Knowledge Format (OKF v0.1
Draft) bundle (ADR-048: OKF is an informative carrier profile and a derived
export target, never a source format). The bundle is a tree of Markdown files —
one per typed artifact, plus a generated ``index.md`` and ``log.md`` — returned
as a ``{relative path: file contents}`` mapping the CLI writes to disk.

Bundle paths are relative to the exported corpus root, so the bundle mirrors the
corpus layout without leaking the caller's directory. The RAC ``type`` stays
authoritative; each artifact file projects it to the OKF ``type`` per the
ADR-048 mapping. Every relationship that resolves (``rac relationships
--validate``) is rendered as a body link in a derived ``# Citations`` section, so
links survive for permissive OKF consumers while the typed front matter and
``## Related <Type>`` sections remain the source of truth.

Determinism (ADR-002, matching ``render_export_json``): artifacts in
sorted-path order, citations and index entries ordered explicitly, ``log.md``
grouped by commit date (newest first) then path — the same corpus state yields a
byte-identical bundle. Recency is derived from git (ADR-045); when git cannot
answer, ``log.md`` degrades to a placeholder rather than failing.
"""

from __future__ import annotations

import os

from rac.core.frontmatter import split_frontmatter
from rac.core.okf import OKF_TYPE
from rac.services.export import CorpusExport, ExportArtifact
from rac.services.recency import RecencyReport

# RAC ``type`` → OKF ``type`` is defined once in ``rac.core.okf`` (ADR-048) and
# re-exported here for the bundle renderer and its existing importers. Unknown-
# type files are excluded from the export, so every ``art.type`` resolves.
__all__ = ["OKF_TYPE", "render_okf_bundle"]

# Human plural headings for the index, in a fixed disclosure order.
_INDEX_SECTIONS: tuple[tuple[str, str], ...] = (
    ("requirement", "Requirements"),
    ("decision", "Decisions"),
    ("design", "Designs"),
    ("roadmap", "Roadmaps"),
    ("prompt", "Prompts"),
)

_INDEX_PATH = "index.md"
_LOG_PATH = "log.md"


def _body(path: str) -> str:
    """The Markdown body after the frontmatter envelope, trailing space trimmed."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return split_frontmatter(text).body.strip()


def _artifact_file(
    art: ExportArtifact,
    citations: list[tuple[str, str]],
    created: str | None,
    updated: str | None,
) -> str:
    """One OKF artifact file: projected front matter, body, derived citations.

    OKF-reserved descriptive fields (ADR-050), projected present-only so the
    bundle stays minimal and deterministic: ``tags`` from the source frontmatter,
    ``created``/``updated`` derived from git (never stored in source, ADR-045).
    """
    front = ["---", f"type: {OKF_TYPE[art.type]}", f"id: {art.id}"]
    if created is not None:
        front.append(f"created: {created}")
    if updated is not None:
        front.append(f"updated: {updated}")
    if art.tags:
        front.append(f"tags: [{', '.join(art.tags)}]")
    lines = [*front, "---", "", _body(art.path)]
    if citations:
        lines += ["", "# Citations", ""]
        lines += [f"- [{title}]({path})" for title, path in citations]
    return "\n".join(lines) + "\n"


def _citations(
    art: ExportArtifact,
    export: CorpusExport,
    by_id: dict[str, ExportArtifact],
    rel: dict[str, str],
) -> list[tuple[str, str]]:
    """Resolved outgoing relationships as ``(title, bundle path)`` link pairs.

    A relationship resolves exactly when its ``to`` is a canonical id present in
    the corpus; unresolved references (literal text) carry no link target and are
    left to the authoritative ``## Related`` sections in the body.
    """
    pairs: list[tuple[str, str]] = []
    for edge in export.relationships:
        if edge.from_ != art.id:
            continue
        target = by_id.get(edge.to)
        if target is not None:
            pairs.append((target.title, rel[target.path]))
    return pairs


def _index(export: CorpusExport, rel: dict[str, str]) -> str:
    """``index.md`` — progressive disclosure: overview, then artifacts by type."""
    count = export.artifact_count
    noun = "artifact" if count == 1 else "artifacts"
    lines = [
        f"# {export.corpus_name} — Knowledge Index",
        "",
        f"A derived OKF bundle of {count} {noun}. The RAC corpus is authoritative;"
        " this index is a generated entry point.",
    ]
    by_type: dict[str, list[ExportArtifact]] = {}
    for art in export.artifacts:
        by_type.setdefault(art.type, []).append(art)
    for type_name, heading in _INDEX_SECTIONS:
        members = by_type.get(type_name)
        if not members:
            continue
        lines += ["", f"## {heading}", ""]
        lines += [f"- [{art.title}]({rel[art.path]})" for art in members]
    return "\n".join(lines) + "\n"


def _log(export: CorpusExport, recency: RecencyReport, rel: dict[str, str]) -> str:
    """``log.md`` — corpus history grouped by commit date, newest first."""
    last_by_path = {a.path: a.last_committed for a in recency.artifacts}
    title_by_path = {art.path: art.title for art in export.artifacts}

    dated: dict[str, list[str]] = {}
    for path, committed in last_by_path.items():
        if committed is None or path not in title_by_path:
            continue
        dated.setdefault(committed.date().isoformat(), []).append(path)

    if not dated:
        return "# Log\n\n_No commit history available._\n"

    lines = ["# Log"]
    for day in sorted(dated, reverse=True):
        lines += ["", f"## {day}", ""]
        for path in sorted(dated[day]):
            lines.append(f"- [{title_by_path[path]}]({rel[path]})")
    return "\n".join(lines) + "\n"


def render_okf_bundle(export: CorpusExport, recency: RecencyReport, root: str) -> dict[str, str]:
    """Project a corpus export as an OKF bundle (``{relative path: contents}``).

    One file per typed artifact at its path relative to ``root`` (the exported
    corpus directory), plus ``index.md`` and ``log.md`` at the bundle root. Pure
    and deterministic given the same ``export`` and ``recency``.
    """
    rel = {art.path: os.path.relpath(art.path, root) for art in export.artifacts}
    by_id = {art.id: art for art in export.artifacts}
    recency_by_path = {a.path: a for a in recency.artifacts}
    files: dict[str, str] = {}
    for art in export.artifacts:
        key = rel[art.path]
        if key in (_INDEX_PATH, _LOG_PATH):
            raise ValueError(f"artifact path {key!r} collides with a generated bundle file")
        record = recency_by_path.get(art.path)
        created = record.first_committed.isoformat() if record and record.first_committed else None
        updated = record.last_committed.isoformat() if record and record.last_committed else None
        files[key] = _artifact_file(art, _citations(art, export, by_id, rel), created, updated)
    files[_INDEX_PATH] = _index(export, rel)
    files[_LOG_PATH] = _log(export, recency, rel)
    return files
