"""Tests for the v0.11.0 `rac export` command (roadmap v0.11.0, Initiatives 1+3).

The export payload and the Portal HTML are public contracts (ADR-007, viewer
contract v1): the JSON golden pins the payload byte-for-byte, the HTML test
proves the file is exactly the vendored shell with the payload in its data
seam, and the drift guard fails when the lore-web viewer source changes
without re-vendoring (Initiative 2's mitigation).

The golden lives here rather than in tests/test_golden.py because it needs a
case-specific `rac.__version__` monkeypatch (the one environment-derived
payload field). Same mechanism otherwise — refresh after an intentional
change with:

    RAC_UPDATE_GOLDEN=1 python -m pytest tests/test_export_cmd.py
"""

from __future__ import annotations

import hashlib
import json
import os
from importlib import resources
from pathlib import Path

import pytest
from conftest import fixture_path

import rac
from rac.cli import main
from rac.output.portal import PortalSeamMissing, render_export_html
from rac.services.export import build_corpus_export

REPO_ROOT = Path(__file__).parent.parent
GOLDEN = Path(__file__).parent / "golden" / "export_json.txt"
LORE_WEB = REPO_ROOT / "lore-web"

# The empty data seam exactly as the shell-only viewer build emits it.
SEAM = '<script type="application/json" id="lore-export"></script>'


def _shell() -> str:
    return (
        resources.files("rac.templates")
        .joinpath("portal/lore-portal-shell.html")
        .read_text(encoding="utf-8")
    )


# --- service layer -----------------------------------------------------------


def test_build_corpus_export_skips_unknown_and_orders_by_path():
    export = build_corpus_export(fixture_path("export"))
    # Four Markdown files, one unclassifiable: only classified artifacts export.
    assert export.artifact_count == 3
    assert [a.path for a in export.artifacts] == sorted(a.path for a in export.artifacts)
    assert "random-notes" not in {a.id for a in export.artifacts}


def test_aliases_canonical_first():
    export = build_corpus_export(fixture_path("export"))
    decision = export.artifacts[0]
    assert decision.id == "RAC-00000000EXP1"
    assert decision.aliases[0] == decision.id
    assert "adr-001" in decision.aliases  # legacy filename-prefix alias


def test_status_canonicalized_and_absent_falls_back(tmp_path):
    export = build_corpus_export(fixture_path("export"))
    by_id = {a.id: a for a in export.artifacts}
    # Authored "proposed" exports in inspect's canonical spelling.
    assert by_id["notes-raw-html"].status == "Proposed"
    assert by_id["v0-portal-roadmap"].status == "Planned"
    # No ## Status section at all -> the pinned "unknown".
    (tmp_path / "bare.md").write_text(
        "# Bare\n\n## Context\n\nWhy.\n\n## Decision\n\nDo.\n\n## Consequences\n\nDone.\n",
        encoding="utf-8",
    )
    bare = build_corpus_export(str(tmp_path))
    assert bare.artifacts[0].status == "unknown"


def test_title_falls_back_to_canonical_id(tmp_path):
    (tmp_path / "untitled.md").write_text(
        "## Context\n\nWhy.\n\n## Decision\n\nDo.\n\n## Consequences\n\nDone.\n",
        encoding="utf-8",
    )
    export = build_corpus_export(str(tmp_path))
    assert export.artifacts[0].title == export.artifacts[0].id == "untitled"


def test_body_html_escapes_raw_html_and_renders_markdown():
    export = build_corpus_export(fixture_path("export"))
    body = next(a for a in export.artifacts if a.id == "notes-raw-html").body_html
    assert "&lt;script&gt;" in body
    assert "<script>" not in body
    assert "<img" not in body  # external loads arrive as text
    assert "<strong>bold text</strong>" in body
    assert "<li>item one</li>" in body


def test_unresolved_reference_preserved_verbatim():
    export = build_corpus_export(fixture_path("export"))
    targets = {edge.to for edge in export.relationships}
    assert "REQ-DOES-NOT-EXIST" in targets


def test_relationships_resolve_via_aliases_and_sort_by_from_to():
    export = build_corpus_export(fixture_path("export"))
    edges = [(e.from_, e.to) for e in export.relationships]
    assert edges == sorted(edges)
    # "ADR-001" (a legacy alias) resolves to the decision's canonical id.
    assert ("v0-portal-roadmap", "RAC-00000000EXP1") in edges
    assert all(e.type == "relates-to" for e in export.relationships)


def test_corpus_name_ignores_trailing_separator():
    with_slash = build_corpus_export(fixture_path("export") + "/")
    without = build_corpus_export(fixture_path("export"))
    assert with_slash.corpus_name == without.corpus_name == "export"


def test_service_deterministic():
    first = build_corpus_export(fixture_path("export"))
    second = build_corpus_export(fixture_path("export"))
    assert first.to_dict() == second.to_dict()


def test_empty_corpus_exports_valid_payload(tmp_path):
    export = build_corpus_export(str(tmp_path))
    payload = export.to_dict()
    assert payload["corpus"]["artifact_count"] == 0
    assert payload["artifacts"] == []
    assert payload["relationships"] == []


# --- golden JSON contract (ADR-007) -------------------------------------------


def test_golden_export_json(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    # Pin the one environment-derived field for byte-stability.
    monkeypatch.setattr(rac, "__version__", "0.0.0-test")

    rc = main(["export", "tests/fixtures/export"])
    out = capsys.readouterr().out

    if os.environ.get("RAC_UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(out, encoding="utf-8")

    assert rc == 0
    assert out == GOLDEN.read_text(encoding="utf-8"), (
        f"Output of `rac export tests/fixtures/export` drifted from {GOLDEN}.\n"
        "If the change is intentional, refresh with: "
        "RAC_UPDATE_GOLDEN=1 python -m pytest tests/test_export_cmd.py"
    )


# --- CLI surface ---------------------------------------------------------------


def test_json_flag_is_explicit_no_op(capsys):
    assert main(["export", fixture_path("export")]) == 0
    default_out = capsys.readouterr().out
    assert main(["export", fixture_path("export"), "--json"]) == 0
    assert capsys.readouterr().out == default_out


def test_cli_deterministic(capsys):
    assert main(["export", fixture_path("export")]) == 0
    first = capsys.readouterr().out
    assert main(["export", fixture_path("export")]) == 0
    assert capsys.readouterr().out == first


def test_missing_directory_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["export", "no/such/dir"])
    assert exc.value.code == 2
    assert "not a directory" in capsys.readouterr().err


def test_out_without_html_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["export", fixture_path("export"), "--out", "x.html"])
    assert exc.value.code == 2
    assert "--out requires --html" in capsys.readouterr().err


def test_unwritable_out_exits_2(tmp_path, capsys):
    target = tmp_path / "missing" / "portal.html"
    with pytest.raises(SystemExit) as exc:
        main(["export", fixture_path("export"), "--html", "--out", str(target)])
    assert exc.value.code == 2
    assert "cannot write" in capsys.readouterr().err


def test_empty_corpus_cli_exits_0(tmp_path, capsys):
    assert main(["export", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifacts"] == []


def test_html_overwrites_existing_file(tmp_path, capsys):
    out = tmp_path / "portal.html"
    out.write_text("stale build artifact", encoding="utf-8")
    assert main(["export", fixture_path("export"), "--html", "--out", str(out)]) == 0
    capsys.readouterr()
    assert "stale build artifact" not in out.read_text(encoding="utf-8")


# --- HTML round-trip (viewer contract: data injection) -------------------------


def test_html_round_trip(tmp_path, capsys):
    out = tmp_path / "portal.html"
    rc = main(["export", fixture_path("export"), "--html", "--out", str(out)])
    assert rc == 0
    assert capsys.readouterr().out == f"wrote {out} — 3 artifact(s), 3 relationship(s)\n"

    html = out.read_text(encoding="utf-8")
    shell = _shell()
    prefix, suffix = shell.split(SEAM)  # exactly one empty seam in the shell

    # Byte-identity around the seam: nothing but the seam changed.
    assert html.startswith(prefix)
    assert html.endswith(suffix)
    assert SEAM not in html  # the empty seam is gone, none re-introduced

    populated = html[len(prefix) : len(html) - len(suffix)]
    open_tag = '<script type="application/json" id="lore-export">'
    assert populated.startswith(open_tag)
    assert populated.endswith("</script>")
    embedded = json.loads(populated[len(open_tag) : -len("</script>")])

    assert main(["export", fixture_path("export")]) == 0
    assert embedded == json.loads(capsys.readouterr().out)


def test_payload_is_script_safe():
    export = build_corpus_export(fixture_path("export"))
    html = render_export_html(export)
    prefix, suffix = _shell().split(SEAM)
    populated = html[len(prefix) : len(html) - len(suffix)]
    open_tag = '<script type="application/json" id="lore-export">'
    body = populated[len(open_tag) : -len("</script>")]
    # The escapes the viewer contract pins: bodies are full of </p> etc., so
    # without them the element would close early; both are valid JSON escapes.
    assert "</" not in body
    assert "<!--" not in body
    assert json.loads(body) == export.to_dict()


def test_seam_missing_raises_and_cli_exits_2(monkeypatch, capsys):
    export = build_corpus_export(fixture_path("export"))
    monkeypatch.setattr("rac.output.portal._load_shell", lambda: "<html></html>")
    with pytest.raises(PortalSeamMissing):
        render_export_html(export)
    with pytest.raises(SystemExit) as exc:
        main(["export", fixture_path("export"), "--html", "--out", "unused.html"])
    assert exc.value.code == 2
    assert "data seam" in capsys.readouterr().err


# --- vendoring drift guard (roadmap v0.11.0, Initiative 2 mitigation) ----------


def test_viewer_source_drift_guard():
    """Re-implements the normative hash from lore-web/scripts/vendor-portal-shell.mjs."""
    if not LORE_WEB.is_dir():
        pytest.skip("lore-web/ not present (installed-package context)")

    provenance = json.loads(
        (REPO_ROOT / "src/rac/templates/portal/provenance.json").read_text(encoding="utf-8")
    )

    def collect(base: Path, exclude: tuple[str, ...] = ()) -> list[str]:
        out = []
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(LORE_WEB).as_posix()
            if any(rel == ex or rel.startswith(ex + "/") for ex in exclude):
                continue
            out.append(rel)
        return out

    files = sorted(
        collect(LORE_WEB / "src/viewer", exclude=("src/viewer/sample",))
        + collect(LORE_WEB / "src/components")
        + collect(LORE_WEB / "src/styles")
        + ["vite.config.viewer.ts", "scripts/build-viewer-artifact.mjs"]
    )

    digest = hashlib.sha256()
    for rel in files:
        content = (LORE_WEB / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")

    assert digest.hexdigest() == provenance["viewer_source_sha256"], (
        "viewer source changed — run `cd lore-web && npm run vendor:shell` and commit the result"
    )
