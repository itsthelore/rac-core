"""Note-tool ingest — Obsidian normalisation, determinism, losslessness (ADR-079).

Initiative 1 of the `ingest-sources` roadmap (itsthelore/rac-core#227): the
Obsidian converter and the shared wikilink machinery the other note tools reuse.
These tests hold the requirement's contract (`rac-note-tool-ingest-sources`):

- **Wikilinks → candidates (REQ-003):** resolved links become candidate
  ``## Related`` references and inline Markdown links; ambiguous/unresolved links
  are left inline and reported, never guessed, never asserted.
- **Directory in, set out (REQ-002):** a vault yields one draft per note.
- **Deterministic + offline (REQ-006):** re-ingesting a vault is byte-identical;
  drafts never overwrite existing files.
- **Lossless (REQ-007):** frontmatter and unmapped content are preserved verbatim.
- **Registry, not core (REQ-005):** converters register beside markitdown.
"""

from __future__ import annotations

import json

from rac import cli
from rac.services.note_ingest import (
    ObsidianConverter,
    converter_by_name,
    converter_names,
    detect_converter,
    parse_wikilinks,
    vault_converters,
)


def _vault(tmp_path):
    """A small Obsidian vault exercising every link and content shape."""
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
    # A config-dir file that must never be walked as a note.
    (root / ".obsidian" / "workspace.md").write_text("not a note\n", encoding="utf-8")
    return root


def _ingest(tmp_path):
    return ObsidianConverter().convert_vault(_vault(tmp_path))


# --- parsing (unit) ----------------------------------------------------------


def test_parse_wikilinks_shapes():
    links = parse_wikilinks("[[Plain]] [[Note|alias]] [[Note#heading]] ![[embed.png]] [[a^block]]")
    assert [(link.target, link.alias, link.fragment, link.embed) for link in links] == [
        ("Plain", None, None, False),
        ("Note", "alias", None, False),
        ("Note", None, "heading", False),
        ("embed.png", None, None, True),
        ("a", None, "block", False),
    ]


# --- detection + registry ----------------------------------------------------


def test_detects_obsidian_vault(tmp_path):
    assert detect_converter(_vault(tmp_path)).name == "obsidian"


def test_detect_returns_none_without_marker(tmp_path):
    (tmp_path / "a.md").write_text("x\n", encoding="utf-8")
    assert detect_converter(tmp_path) is None


def test_registry_lookup():
    assert converter_names() == ["obsidian"]
    assert converter_by_name("obsidian").name == "obsidian"
    assert converter_by_name("logseq") is None
    assert [c.name for c in vault_converters()] == ["obsidian"]


# --- normalisation -----------------------------------------------------------


def test_one_draft_per_note_skipping_config(tmp_path):
    result = _ingest(tmp_path)
    sources = [d.source_path for d in result.drafts]
    assert sources == [
        "Auth.md",
        "Decisions/ADR One.md",
        "Decisions/Dup.md",
        "Dup.md",
        "Login Policy.md",
    ]
    assert ".obsidian/workspace.md" not in sources


def test_resolved_links_become_candidates_and_inline(tmp_path):
    auth = next(d for d in _ingest(tmp_path).drafts if d.source_path == "Auth.md")
    # Bare unique + qualified-with-alias resolve; self is excluded from candidates.
    assert auth.related == ["Login Policy.md", "Decisions/ADR One.md"]
    assert "[Login Policy](<Login Policy.md>)" in auth.markdown
    assert "[the ADR](<Decisions/ADR One.md>)" in auth.markdown
    assert "## Related" in auth.markdown


def test_unresolved_and_ambiguous_left_inline_and_warned(tmp_path):
    auth = next(d for d in _ingest(tmp_path).drafts if d.source_path == "Auth.md")
    assert "[[Ghost Note]]" in auth.markdown  # unresolved: verbatim
    assert "[[Dup]]" in auth.markdown  # ambiguous: verbatim, not guessed
    assert any("unresolved" in w and "Ghost Note" in w for w in auth.warnings)
    assert any("ambiguous" in w and "Dup" in w for w in auth.warnings)
    # An ambiguous name never becomes a candidate relationship.
    assert not any("Dup" in r for r in auth.related)


def test_self_link_inline_but_not_a_candidate(tmp_path):
    auth = next(d for d in _ingest(tmp_path).drafts if d.source_path == "Auth.md")
    assert "[Auth](Auth.md)" in auth.markdown
    assert "Auth.md" not in auth.related


def test_embed_left_verbatim(tmp_path):
    auth = next(d for d in _ingest(tmp_path).drafts if d.source_path == "Auth.md")
    assert "![[diagram.png]]" in auth.markdown


def test_frontmatter_and_unmapped_content_preserved(tmp_path):
    auth = next(d for d in _ingest(tmp_path).drafts if d.source_path == "Auth.md")
    assert "title: Auth Policy" in auth.markdown
    assert "tags: [security, auth]" in auth.markdown
    assert "unmapped_key: value preserved." in auth.markdown  # nothing dropped


def test_lossless_every_source_word_survives(tmp_path):
    # Every non-wikilink word in a source note appears in its draft (REQ-007).
    root = _vault(tmp_path)
    result = ObsidianConverter().convert_vault(root)
    import re as _re

    for draft in result.drafts:
        source = (root / draft.source_path).read_text(encoding="utf-8")
        source_no_links = _re.sub(r"!?\[\[[^\]]+\]\]", " ", source)
        for word in source_no_links.split():
            assert word in draft.markdown, f"{word!r} dropped from {draft.source_path}"


def test_reingest_is_byte_identical(tmp_path):
    root = _vault(tmp_path)
    first = ObsidianConverter().convert_vault(root)
    second = ObsidianConverter().convert_vault(root)
    assert [d.markdown for d in first.drafts] == [d.markdown for d in second.drafts]


# --- CLI ---------------------------------------------------------------------


def test_cli_writes_drafts_and_never_overwrites(tmp_path, capsys):
    root = _vault(tmp_path)
    out = tmp_path / "drafts"
    assert cli.main(["ingest", str(root), "-o", str(out)]) == cli.EXIT_OK
    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.md"))
    assert written == [
        "Auth.md",
        "Decisions/ADR One.md",
        "Decisions/Dup.md",
        "Dup.md",
        "Login Policy.md",
    ]
    # Mutate a written draft, re-ingest: it must be skipped, not overwritten.
    (out / "Auth.md").write_text("EDITED BY HUMAN\n", encoding="utf-8")
    assert cli.main(["ingest", str(root), "-o", str(out)]) == cli.EXIT_OK
    assert (out / "Auth.md").read_text(encoding="utf-8") == "EDITED BY HUMAN\n"
    assert "Skipped" in capsys.readouterr().out


def test_cli_force_overwrites(tmp_path):
    root = _vault(tmp_path)
    out = tmp_path / "drafts"
    cli.main(["ingest", str(root), "-o", str(out)])
    (out / "Auth.md").write_text("EDITED\n", encoding="utf-8")
    cli.main(["ingest", str(root), "-o", str(out), "--force"])
    assert "EDITED" not in (out / "Auth.md").read_text(encoding="utf-8")


def test_cli_json_shape(tmp_path, capsys):
    root = _vault(tmp_path)
    assert cli.main(["ingest", str(root), "--json"]) == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["converter"] == "obsidian"
    assert payload["note_count"] == 5
    assert payload["resolved_link_count"] >= 1
    assert {d["source"] for d in payload["drafts"]} >= {"Auth.md", "Login Policy.md"}


def test_cli_directory_without_marker_errors(tmp_path, capsys):
    (tmp_path / "a.md").write_text("x\n", encoding="utf-8")
    try:
        cli.main(["ingest", str(tmp_path)])
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == cli.EXIT_USAGE
    assert "could not detect" in capsys.readouterr().err


def test_cli_from_on_a_file_errors(tmp_path, capsys):
    doc = tmp_path / "doc.md"
    doc.write_text("hi\n", encoding="utf-8")
    try:
        cli.main(["ingest", str(doc), "--from", "obsidian"])
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == cli.EXIT_USAGE
    assert "--from applies to" in capsys.readouterr().err


def test_cli_stdout_on_directory_errors(tmp_path, capsys):
    root = _vault(tmp_path)
    try:
        cli.main(["ingest", str(root), "--stdout"])
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == cli.EXIT_USAGE
    assert "--stdout is not supported" in capsys.readouterr().err


def test_cli_single_file_ingest_unchanged(tmp_path, capsys):
    # A Markdown file still routes to the existing single-file path, byte-unchanged.
    doc = tmp_path / "note.md"
    doc.write_text("# Hi\n\nbody\n", encoding="utf-8")
    assert cli.main(["ingest", str(doc)]) == cli.EXIT_OK
    assert capsys.readouterr().out == "# Hi\n\nbody\n\n"


def test_cli_from_choices_match_registry(capsys):
    # The parser hardcodes --from choices to stay import-light; pin them to the
    # converter registry so a new tool can't be added to one and forgotten in the
    # other. Every registry name parses; a non-registry name is rejected.
    parser = cli.build_parser()
    for name in converter_names():
        assert parser.parse_args(["ingest", "x", "--from", name]).from_tool == name
    try:
        parser.parse_args(["ingest", "x", "--from", "not-a-tool"])
        raise AssertionError("expected a parse error for an unknown --from value")
    except SystemExit:
        pass
