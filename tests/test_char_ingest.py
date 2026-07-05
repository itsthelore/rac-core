"""Characterization tests for the `rac ingest` cluster.

Characterization tests added before the rebuild-scale examiner freeze: they pin
the *current* observable behavior of document ingest, note-tool ingest, and the
vault-ingest renderers exactly as it stands today, so a reimplementation that
changes any of it fails here. They assert what the code does, not what it should
do — nothing here is a correctness judgement.

Focus areas (behaviors the existing suite left unpinned):

- ``render_vault_ingest_human`` — the full multi-line stdout/summary a user sees
  for ``rac ingest <dir>`` (preview and write/skip shapes).
- Case-insensitive file-extension dispatch (``FILE.DOCX``, ``notes.Md``,
  ``graph.JSON``).
- Roam page-title to draft-filename sanitization bytes.
- Per-note-tool draft assembly (Logseq/Notion/Roam each emit the same
  ``## Related`` candidate block), so a per-converter fork in the rebuild is
  caught even though only the Obsidian path has a golden fixture today.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fixture_path

from rac import cli
from rac.cli import main
from rac.output.human import render_vault_ingest_human
from rac.services.ingest import (
    MarkdownConverter,
    MarkItDownConverter,
    UnsupportedDocument,
    _missing_extra_message,
    converter_for,
    ingest,
)
from rac.services.note_ingest import (
    LogseqConverter,
    NotionConverter,
    ObsidianConverter,
    _roam_filename,
    _split_frontmatter,
    roam_result_for_file,
)

# The candidate-relationship comment prepended before every ``## Related`` block.
# Shared by all note-tool converters via ``_assemble_draft``; pinned here so a
# per-converter fork of the assembly is caught for Logseq/Notion/Roam too (today
# only the Obsidian golden fixture pins it).
_CANDIDATE_NOTE = (
    "<!-- Candidate relationships imported from wikilinks (ADR-079): review and "
    "promote to real references before this becomes an artifact; not asserted. -->"
)


def _obsidian_vault(tmp_path: Path) -> Path:
    """A small Obsidian vault exercising resolved, ambiguous, unresolved links."""
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    (root / "Decisions").mkdir()
    (root / "Auth.md").write_text(
        "---\ntitle: Auth Policy\ntags: [security, auth]\n---\n\n"
        "See [[Login Policy]] and [[Decisions/ADR One|the ADR]].\n"
        "Unknown [[Ghost Note]], self [[Auth]], ambiguous [[Dup]], embed ![[diagram.png]].\n"
        "A plain sentence with unmapped_key: value preserved.\n",
        encoding="utf-8",
    )
    (root / "Login Policy.md").write_text("# Login Policy\n\nBack to [[Auth]].\n", encoding="utf-8")
    (root / "Decisions" / "ADR One.md").write_text("# ADR One\n\nBody.\n", encoding="utf-8")
    (root / "Dup.md").write_text("root dup\n", encoding="utf-8")
    (root / "Decisions" / "Dup.md").write_text("nested dup\n", encoding="utf-8")
    (root / ".obsidian" / "workspace.md").write_text("not a note\n", encoding="utf-8")
    return root


# --- Case-insensitive extension dispatch (finding #2, HIGH) ------------------


def test_converter_selection_is_case_insensitive():
    # `converter_for` lower-cases the suffix, so an upper/mixed-case extension
    # still routes to the right converter.
    assert isinstance(converter_for(Path("a.DOCX")), MarkItDownConverter)
    assert isinstance(converter_for(Path("SPEC.Docx")), MarkItDownConverter)
    assert isinstance(converter_for(Path("a.MD")), MarkdownConverter)
    assert isinstance(converter_for(Path("notes.Md")), MarkdownConverter)
    assert isinstance(converter_for(Path("a.MARKDOWN")), MarkdownConverter)
    assert isinstance(converter_for(Path("page.HTML")), MarkItDownConverter)


def test_missing_extra_message_folds_case():
    # `_missing_extra_message` also lower-cases before the extra lookup, but keeps
    # the original suffix verbatim in the message text.
    assert "[ingest-office]" in _missing_extra_message(".XLSX")
    assert "converting '.XLSX' needs" in _missing_extra_message(".XLSX")


def test_cli_uppercase_json_extension_routes_to_roam(tmp_path, capsys):
    # The CLI `.json` fast-path uses `path.suffix.lower() == ".json"`, so a bare
    # Roam export with an upper-case extension still ingests directly.
    graph = [{"title": "Auth", "children": [{"string": "x"}]}]
    path = tmp_path / "graph.JSON"
    path.write_text(json.dumps(graph), encoding="utf-8")
    out = tmp_path / "drafts"
    assert cli.main(["ingest", str(path), "-o", str(out)]) == cli.EXIT_OK
    written = {p.relative_to(out).as_posix() for p in out.rglob("*.md")}
    assert written == {"Auth.md"}
    assert "via roam" in capsys.readouterr().out


# --- Roam title -> filename sanitization (finding #3, HIGH) ------------------


def test_roam_filename_sanitizes_separators_and_whitespace():
    # `/` and `\` become `-`, surrounding whitespace is stripped, `.md` appended.
    assert _roam_filename("A/B Page") == "A-B Page.md"
    assert _roam_filename(" A/B Nested ") == "A-B Nested.md"
    assert _roam_filename("A\\B") == "A-B.md"
    assert _roam_filename("Plain Title") == "Plain Title.md"


def test_roam_title_with_slash_flattens_to_filename(tmp_path):
    # The emitted `suggested_filename` (the byte path drafts are written to) is
    # the flattened title; the H1 in the body keeps the raw, untrimmed title.
    graph = [
        {"title": " A/B Nested ", "children": [{"string": "See [[Login Policy]]"}]},
        {"title": "Login Policy", "children": [{"string": "body"}]},
    ]
    path = tmp_path / "g.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    result = roam_result_for_file(path)
    nested = next(d for d in result.drafts if d.source_path == " A/B Nested ")
    assert nested.suggested_filename == "A-B Nested.md"
    # source_path keeps the raw title; the body H1 is the raw title verbatim.
    assert nested.markdown.startswith("#  A/B Nested \n")
    # The slash-linked page resolves to the flattened target filename.
    assert nested.related == ["Login Policy.md"]


# --- Human summary rendering (finding #1, HIGH) ------------------------------


def test_cli_human_preview_summary_exact(tmp_path, capsys):
    # The full multi-line preview summary (no -o) a user sees, byte-for-byte.
    root = _obsidian_vault(tmp_path)
    assert cli.main(["ingest", str(root)]) == cli.EXIT_OK
    out = capsys.readouterr().out
    expected = (
        f"Ingested 5 note(s) from {root} via obsidian.\n"
        "  3 wikilink(s) resolved to candidate ## Related references.\n"
        "  2 link(s) need review (ambiguous or unresolved) — left inline, never guessed.\n"
        "\n"
        "Preview only — pass -o <dir> to write the drafts for review.\n"
        "\n"
        "Links to review:\n"
        "  Auth.md: unresolved wikilink [[Ghost Note]]\n"
        "  Auth.md: ambiguous wikilink [[Dup]]\n"
    )
    assert out == expected


def test_render_vault_ingest_human_write_and_skip_block():
    # The write path of the renderer: the "Wrote N draft(s)" line, the "Skipped"
    # block with the per-path bullets, and the trailing review list. Called
    # directly so the written/skipped lists are deterministic.
    result = ObsidianConverter().convert_vault(_render_vault())
    rendered = render_vault_ingest_human(
        result,
        written=["OUT/Auth.md", "OUT/Login Policy.md"],
        skipped=["OUT/Dup.md"],
        output_dir="OUT",
    )
    expected = (
        f"Ingested 5 note(s) from {result.root} via obsidian.\n"
        "  3 wikilink(s) resolved to candidate ## Related references.\n"
        "  2 link(s) need review (ambiguous or unresolved) — left inline, never guessed.\n"
        "\n"
        "Wrote 2 draft(s) to OUT.\n"
        "Skipped 1 draft(s) — an artifact already exists (pass --force to overwrite):\n"
        "  - OUT/Dup.md\n"
        "\n"
        "Links to review:\n"
        "  Auth.md: unresolved wikilink [[Ghost Note]]\n"
        "  Auth.md: ambiguous wikilink [[Dup]]"
    )
    assert rendered == expected


def test_render_vault_ingest_human_notion_csv_line(tmp_path):
    # The "N database CSV(s) skipped" line only fires when skipped_sources is set;
    # the Notion export path is the one that populates it.
    result = NotionConverter().convert_vault(_notion_export(tmp_path))
    rendered = render_vault_ingest_human(result, written=[], skipped=[], output_dir=None)
    assert (
        "  1 database CSV(s) skipped — Notion exports each row as its own page; "
        "the CSV is a redundant index." in rendered
    )


# A vault helper that does not depend on a per-test tmp_path fixture, for the
# direct-renderer test above.
def _render_vault() -> Path:
    import tempfile

    return _obsidian_vault(Path(tempfile.mkdtemp()))


# --- Per-note-tool draft assembly (fork guard) -------------------------------


def test_logseq_draft_assembly_bytes(tmp_path):
    # Logseq reuses the shared `_assemble_draft`; pin its emitted bytes so a
    # per-converter fork is caught (only Obsidian has a golden fixture).
    root = tmp_path / "graph"
    (root / "logseq").mkdir(parents=True)
    (root / "logseq" / "config.edn").write_text("{}\n", encoding="utf-8")
    (root / "pages").mkdir()
    (root / "pages" / "Auth.md").write_text(
        "type:: decision\n- Depends on [[Login Policy]]\n", encoding="utf-8"
    )
    (root / "pages" / "Login Policy.md").write_text("- body\n", encoding="utf-8")
    result = LogseqConverter().convert_vault(root)
    auth = next(d for d in result.drafts if d.source_path == "pages/Auth.md")
    assert auth.markdown == (
        "type:: decision\n"
        "- Depends on [Login Policy](<pages/Login Policy.md>)\n"
        "\n"
        f"{_CANDIDATE_NOTE}\n"
        "\n"
        "## Related\n"
        "\n"
        "- pages/Login Policy.md\n"
    )


def test_notion_draft_assembly_bytes(tmp_path):
    result = NotionConverter().convert_vault(_notion_export(tmp_path))
    auth = next(d for d in result.drafts if d.source_path.startswith("Auth "))
    h2 = "b" * 32
    assert auth.markdown == (
        "# Auth\n"
        "\n"
        f"Depends on [Login](Login%20{h2}.md).\n"
        "\n"
        f"{_CANDIDATE_NOTE}\n"
        "\n"
        "## Related\n"
        "\n"
        f"- Login {h2}.md\n"
    )


def test_roam_draft_assembly_bytes(tmp_path):
    graph = [
        {"title": "Auth", "children": [{"string": "See [[Login Policy]]"}]},
        {"title": "Login Policy", "children": [{"string": "body"}]},
    ]
    path = tmp_path / "g.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    result = roam_result_for_file(path)
    auth = next(d for d in result.drafts if d.source_path == "Auth")
    assert auth.markdown == (
        "# Auth\n"
        "\n"
        "- See [Login Policy](<Login Policy.md>)\n"
        "\n"
        f"{_CANDIDATE_NOTE}\n"
        "\n"
        "## Related\n"
        "\n"
        "- Login Policy.md\n"
    )


def _notion_export(tmp_path: Path) -> Path:
    """A minimal Notion export: two hashed pages plus a database CSV."""
    h1, h2, h3 = "a" * 32, "b" * 32, "c" * 32
    root = tmp_path / "export"
    root.mkdir()
    (root / f"Auth {h1}.md").write_text(
        f"# Auth\n\nDepends on [Login](Login%20{h2}.md).\n", encoding="utf-8"
    )
    (root / f"Login {h2}.md").write_text("# Login\n\nbody\n", encoding="utf-8")
    (root / f"Tasks {h3}.csv").write_text("Name,Status\nTask A,Done\n", encoding="utf-8")
    return root


# --- Single-file JSON with -o reports the written path (finding #4, MEDIUM) ---


def test_cli_json_shape_reports_output_path(tmp_path, capsys):
    out = tmp_path / "o.md"
    rc = main(["ingest", fixture_path("ingest", "sample.md"), "-o", str(out), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(out)
    assert payload["converter"] == "markdown"
    assert out.exists()


# --- Single-file write success message on stderr (finding #5, MEDIUM) --------


def test_cli_write_reports_chars_and_converter_on_stderr(tmp_path, capsys):
    out = tmp_path / "o.md"
    assert main(["ingest", fixture_path("ingest", "sample.md"), "-o", str(out)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""  # nothing on stdout for a non-JSON write
    assert f"Wrote {out}" in captured.err
    assert "chars, via markdown)." in captured.err


# --- _SKIP_DIRS beyond .obsidian/logseq (finding #6, MEDIUM) -----------------


def test_trash_git_bak_recycle_dirs_are_skipped(tmp_path):
    root = _obsidian_vault(tmp_path)
    for skip in (".trash", ".git", "bak", ".recycle"):
        (root / skip).mkdir()
        (root / skip / "Old.md").write_text("x\n", encoding="utf-8")
    sources = [d.source_path for d in ObsidianConverter().convert_vault(root).drafts]
    assert not any(s.startswith((".trash/", ".git/", "bak/", ".recycle/")) for s in sources)


def test_skip_dirs_apply_to_parents_not_leaf(tmp_path):
    # The skip is checked on rel_parts[:-1], so a *file* literally named like a
    # skip dir at the root is still ingested.
    root = _obsidian_vault(tmp_path)
    (root / "bak.md").write_text("a real note\n", encoding="utf-8")
    sources = [d.source_path for d in ObsidianConverter().convert_vault(root).drafts]
    assert "bak.md" in sources


# --- _split_frontmatter boundary shapes (finding #7, MEDIUM) -----------------


def test_split_frontmatter_boundaries():
    # Unterminated frontmatter -> whole text is body, nothing extracted.
    assert _split_frontmatter("---\ntitle: x\n\nbody\n") == (
        "",
        "---\ntitle: x\n\nbody\n",
    )
    # Text that does not open with exactly `---\n` -> all body.
    assert _split_frontmatter("no fence\n") == ("", "no fence\n")
    # Only-frontmatter (closing fence, nothing after) -> all frontmatter, empty body.
    assert _split_frontmatter("---\ntitle: x\n---\n") == ("---\ntitle: x\n---\n", "")
    # Well-formed block -> partitioned, both fences kept on the frontmatter side.
    assert _split_frontmatter("---\ntitle: x\n---\nbody\n") == (
        "---\ntitle: x\n---\n",
        "body\n",
    )


# --- Unsupported-type message text + extensionless fallback (finding #8) ------


def test_unsupported_message_lists_supported_and_uses_name_when_no_extension(tmp_path):
    bad = tmp_path / "Makefile"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedDocument) as exc:
        ingest(str(bad))
    message = str(exc.value)
    # `p.suffix or p.name`: with no extension the full name is reported.
    assert message.startswith("unsupported file type 'Makefile'.")
    assert "Supported: " in message
    assert ".docx" in message and ".md" in message


def test_unsupported_message_reports_suffix_when_present(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedDocument) as exc:
        ingest(str(bad))
    assert "unsupported file type '.txt'." in str(exc.value)


# --- Vault-ingest JSON written/skipped fields (finding #9, MEDIUM) -----------


def test_cli_json_written_and_skipped(tmp_path, capsys):
    root = _obsidian_vault(tmp_path)
    out = tmp_path / "drafts"
    # First run writes all five drafts.
    assert cli.main(["ingest", str(root), "-o", str(out), "--json"]) == cli.EXIT_OK
    first = json.loads(capsys.readouterr().out)
    assert first["output_dir"] == str(out)
    assert len(first["written"]) == 5
    assert first["skipped"] == []
    # Second run against the same dir skips them all — none written, five skipped.
    assert cli.main(["ingest", str(root), "-o", str(out), "--json"]) == cli.EXIT_OK
    second = json.loads(capsys.readouterr().out)
    assert second["written"] == []
    assert len(second["skipped"]) == 5


# --- Notion link-filtering rules (finding #10, LOW) --------------------------


def test_notion_skips_mailto_anchor_protocol_and_non_md_links(tmp_path):
    h1 = "a" * 32
    root = tmp_path / "export"
    root.mkdir()
    (root / f"Page {h1}.md").write_text(
        f"# Page\n\n[mail](mailto:x@y.com) [anchor](#section) [proto](//cdn/x.md) "
        f"[asset](image%20name.png) [ext](https://e.com) [self](Page%20{h1}.md)\n",
        encoding="utf-8",
    )
    draft = NotionConverter().convert_vault(root).drafts[0]
    # None of the filtered link kinds become candidates or warnings; the only
    # `.md` link points at the page itself, so it is not a candidate either.
    assert draft.related == []
    assert draft.warnings == []


# --- _missing_extra_message for .xls and .htm (finding #11, LOW) -------------


def test_missing_extra_message_xls_and_htm():
    assert "[ingest-office]" in _missing_extra_message(".xls")
    assert "[ingest]" in _missing_extra_message(".htm")  # htm -> base markitdown
