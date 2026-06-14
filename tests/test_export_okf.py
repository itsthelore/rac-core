"""Tests for the v0.13.6 `rac export --okf` OKF bundle view (ADR-048).

The bundle is a derived OKF v0.1 view of the corpus: one Markdown file per typed
artifact (front matter projecting the RAC ``type`` to its OKF ``type``), plus a
generated ``index.md`` and ``log.md``. The renderer is pure and deterministic;
``log.md`` is fed a synthetic recency here so the tests never depend on git.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.core.artifacts import ARTIFACT_SPECS
from rac.output.okf import OKF_TYPE, render_okf_bundle
from rac.services.export import build_corpus_export
from rac.services.recency import ArtifactRecency, RecencyReport

_DAY = datetime(2026, 6, 14, 9, 0, tzinfo=UTC)
_ROOT = fixture_path("export")


def _export():
    return build_corpus_export(_ROOT)


def _bundle(export, recency):
    return render_okf_bundle(export, recency, _ROOT)


def _key(art) -> str:
    """The artifact's bundle key — its path relative to the corpus root."""
    return os.path.relpath(art.path, _ROOT)


def _recency(export, when=_DAY) -> RecencyReport:
    """A synthetic recency report giving every exported artifact one date."""
    return RecencyReport(
        directory="export",
        recursive=True,
        artifacts=[
            ArtifactRecency(path=a.path, artifact_type=a.type, last_committed=when)
            for a in export.artifacts
        ],
    )


# --- renderer ----------------------------------------------------------------


def test_bundle_has_index_log_and_one_file_per_artifact():
    export = _export()
    bundle = _bundle(export, _recency(export))
    assert "index.md" in bundle
    assert "log.md" in bundle
    artifact_files = [p for p in bundle if p not in ("index.md", "log.md")]
    assert len(artifact_files) == export.artifact_count
    assert set(artifact_files) == {_key(a) for a in export.artifacts}


def test_bundle_paths_are_relative_to_the_corpus_root():
    export = _export()
    bundle = _bundle(export, _recency(export))
    # No key escapes the bundle root (no absolute paths, no parent traversal).
    assert all(not os.path.isabs(p) and not p.startswith("..") for p in bundle)


def test_okf_type_mapping_covers_every_artifact_type():
    # If a new RAC type is added without an OKF projection, this fails loudly.
    assert set(OKF_TYPE) == {spec.name for spec in ARTIFACT_SPECS}


def test_artifact_file_projects_okf_front_matter():
    export = _export()
    bundle = _bundle(export, _recency(export))
    for art in export.artifacts:
        head = bundle[_key(art)].splitlines()[:4]
        assert head == ["---", f"type: {OKF_TYPE[art.type]}", f"id: {art.id}", "---"]


def test_resolved_relationship_renders_as_citation_link():
    export = _export()
    bundle = _bundle(export, _recency(export))
    by_id = {a.id: a for a in export.artifacts}
    # Derive topology rather than assume it: a source with a resolved out-edge.
    src_id = next(e.from_ for e in export.relationships if e.to in by_id)
    src = by_id[src_id]
    target = next(by_id[e.to] for e in export.relationships if e.from_ == src_id and e.to in by_id)
    citations = bundle[_key(src)].split("# Citations", 1)[1]
    assert f"- [{target.title}]({_key(target)})" in citations
    # Unresolved references never become citation links.
    unresolved = {e.to for e in export.relationships if e.to not in by_id}
    assert all(ref not in citations for ref in unresolved)


def test_artifact_without_resolved_links_has_no_citations():
    export = _export()
    bundle = _bundle(export, _recency(export))
    by_id = {a.id: a for a in export.artifacts}
    sources_with_links = {e.from_ for e in export.relationships if e.to in by_id}
    bare = next((a for a in export.artifacts if a.id not in sources_with_links), None)
    if bare is None:
        pytest.skip("fixture has no artifact without resolved outgoing links")
    assert "# Citations" not in bundle[_key(bare)]


def test_unknown_type_files_are_excluded():
    export = _export()
    bundle = _bundle(export, _recency(export))
    assert not any("random-notes" in path for path in bundle)


def test_render_is_deterministic():
    export = _export()
    recency = _recency(export)
    assert _bundle(export, recency) == _bundle(export, recency)


def test_index_groups_artifacts_by_type():
    export = _export()
    index = _bundle(export, _recency(export))["index.md"]
    assert index.startswith("# export — Knowledge Index")
    assert "## Decisions" in index
    assert "## Roadmaps" in index
    roadmap = next(a for a in export.artifacts if a.type == "roadmap")
    assert f"- [{roadmap.title}]({_key(roadmap)})" in index


def test_log_groups_by_date_newest_first():
    export = _export()
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 6, 14, tzinfo=UTC)
    paths = [a.path for a in export.artifacts]
    recency = RecencyReport(
        directory="export",
        recursive=True,
        artifacts=[
            ArtifactRecency(path=paths[0], artifact_type="decision", last_committed=newer),
            *[
                ArtifactRecency(path=p, artifact_type="decision", last_committed=older)
                for p in paths[1:]
            ],
        ],
    )
    log = _bundle(export, recency)["log.md"]
    assert log.startswith("# Log")
    assert log.index("## 2026-06-14") < log.index("## 2026-01-01")


def test_log_degrades_to_placeholder_without_recency():
    export = _export()
    blank = RecencyReport(
        directory="export",
        recursive=True,
        artifacts=[
            ArtifactRecency(path=a.path, artifact_type=a.type, last_committed=None)
            for a in export.artifacts
        ],
    )
    assert _bundle(export, blank)["log.md"] == "# Log\n\n_No commit history available._\n"


def test_empty_corpus_yields_only_index_and_log(tmp_path):
    export = build_corpus_export(str(tmp_path))
    bundle = render_okf_bundle(export, _recency(export), str(tmp_path))
    assert set(bundle) == {"index.md", "log.md"}
    assert "0 artifacts" in bundle["index.md"]


# --- CLI ---------------------------------------------------------------------


def test_export_okf_writes_bundle_to_disk(tmp_path, capsys):
    out = tmp_path / "bundle"
    rc = main(["export", fixture_path("export"), "--okf", "--out", str(out)])
    assert rc == 0
    assert (out / "index.md").is_file()
    assert (out / "log.md").is_file()
    written = capsys.readouterr().out
    assert "artifact(s)" in written


def test_export_okf_and_html_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc:
        main(["export", fixture_path("export"), "--okf", "--html"])
    assert exc.value.code == 2


def test_export_out_requires_a_file_mode():
    with pytest.raises(SystemExit) as exc:
        main(["export", fixture_path("export"), "--out", "x"])
    assert exc.value.code == 2
