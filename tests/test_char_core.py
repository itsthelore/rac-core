"""Characterization tests for the cross-cutting core cluster.

These tests were added before the rebuild-scale examiner freeze. They pin the
*current* observable behavior of the classification / frontmatter / identity /
filesystem / limits seams so that a reimplementation cannot change any of these
behaviors silently: a divergence becomes a failing test — a decision to record,
not an accident to discover in production.

They are characterization, not endorsement. Where the current behavior is a
sharp edge (a BOM defeating frontmatter, a symlinked directory not being
descended), the test freezes exactly what the code does today; it does not
assert what the code *should* do. A rebuild that deliberately changes one of
these behaviors should update the corresponding test as a recorded decision.
"""

from __future__ import annotations

import hashlib
import os

from rac.core.classification import CONFIDENCE_THRESHOLD, classify, score_artifacts
from rac.core.corpus import content_hash
from rac.core.fs import find_markdown_files
from rac.core.identity import artifact_identifier, artifact_identifiers
from rac.core.limits import DEFAULT_MAX_FILE_BYTES, max_file_bytes
from rac.core.markdown import parse, parse_file

# --- BOM before frontmatter (finding #1, HIGH) -------------------------------
#
# CHARACTERIZATION OF CURRENT BEHAVIOR — NOT AN ENDORSEMENT.
#
# `parse_file` decodes bytes with plain "utf-8", which (unlike "utf-8-sig")
# retains a leading UTF-8 BOM. `split_frontmatter` only treats a block as
# frontmatter when `lines[0].strip() == "---"`, and str.strip() does NOT treat
# the BOM (U+FEFF) as whitespace. So a BOM-prefixed document has first line
# "﻿---", the frontmatter branch is skipped, and the ENTIRE file (BOM,
# frontmatter, and all) is treated as Markdown body. Net effect: the id, type,
# schema_version, and relationships in a BOM-saved artifact are silently
# ignored; identity falls back to the filename and classification comes from the
# body headings only.
#
# A rebuild that decodes with "utf-8-sig" or strips a BOM (a very natural
# choice) MUST fail this test — that change alters identity, type, and
# validation outcome for the same bytes and has to be a recorded decision, not a
# quiet flip. If BOM tolerance is intended, invert these assertions.

_BOM = b"\xef\xbb\xbf"
_FRONTMATTER_DECISION_BODY_REQUIREMENT = (
    b"---\n"
    b"schema_version: 1\n"
    b"id: RAC-01JY4M8X2QZ7\n"
    b"type: decision\n"
    b"---\n"
    b"# T\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
)


def test_bom_prefixed_frontmatter_is_silently_ignored(tmp_path):
    p = tmp_path / "note.md"
    p.write_bytes(_BOM + _FRONTMATTER_DECISION_BODY_REQUIREMENT)
    product = parse_file(str(p))

    # BOM defeats frontmatter: no metadata is parsed at all.
    assert product.metadata is None
    assert product.metadata_issues == []
    # Identity falls back to the filename stem (the frontmatter id is unseen).
    assert artifact_identifier(product, None, str(p)) == "note"
    # Classification comes from the BODY headings (Problem + Requirements), NOT
    # the frontmatter `type: decision`, which was never parsed.
    assert classify(product).type == "requirement"


def test_same_bytes_without_bom_do_parse_frontmatter(tmp_path):
    # The contrast: identical bytes WITHOUT the BOM parse the frontmatter, so
    # the id is honored. This is what makes the BOM behavior above a silent flip.
    p = tmp_path / "note2.md"
    p.write_bytes(_FRONTMATTER_DECISION_BODY_REQUIREMENT)
    product = parse_file(str(p))

    assert product.metadata is not None
    assert product.metadata.id == "RAC-01JY4M8X2QZ7"


# --- find_markdown_files semantics (finding #2, HIGH) ------------------------


def test_find_markdown_skips_dotted_dirs_and_non_md(tmp_path):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "b.md").write_text("# B\n", encoding="utf-8")

    # Only the top-level `.md` survives: `.txt` is not matched and `.git/` is a
    # dotted directory whose files are skipped.
    assert [p.name for p in find_markdown_files(str(tmp_path))] == ["a.md"]


def test_find_markdown_recurses_nested_dirs_in_sorted_order(tmp_path):
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.md").write_text("# C\n", encoding="utf-8")

    found = find_markdown_files(str(tmp_path))
    # Sorted by full path: top-level "a.md" and "b.md" sort before "sub/c.md".
    assert [str(p.relative_to(tmp_path)) for p in found] == [
        "a.md",
        "b.md",
        os.path.join("sub", "c.md"),
    ]

    # recursive=False looks only at files directly inside the directory.
    top = find_markdown_files(str(tmp_path), recursive=False)
    assert [p.name for p in top] == ["a.md", "b.md"]


def test_find_markdown_dotted_root_does_not_self_skip(tmp_path):
    # The dotted-component check runs on `p.relative_to(root).parts` only, so a
    # root that is itself dotted (e.g. a ".rac" directory) does NOT skip its own
    # direct files — but a dotted subdirectory inside it still is skipped.
    root = tmp_path / ".rac"
    root.mkdir()
    (root / "x.md").write_text("# X\n", encoding="utf-8")
    inner = root / ".hidden"
    inner.mkdir()
    (inner / "y.md").write_text("# Y\n", encoding="utf-8")

    assert [str(p.relative_to(root)) for p in find_markdown_files(str(root))] == ["x.md"]


def test_find_markdown_symlink_handling(tmp_path):
    # CHARACTERIZATION of the current symlink behavior (Path.rglob under this
    # interpreter): a symlinked `.md` FILE is discovered like any other file, but
    # a symlinked DIRECTORY is NOT descended into. A rebuild that follows
    # directory symlinks (e.g. rglob(recurse_symlinks=True)) would change corpus
    # membership and must fail this test.
    real = tmp_path / "real"
    real.mkdir()
    (real / "r.md").write_text("# R\n", encoding="utf-8")

    # A symlink to a directory: its contents must not appear under the link name.
    link_dir = tmp_path / "linkdir"
    os.symlink(real, link_dir)
    # A symlink to a `.md` file: it must appear.
    link_file = tmp_path / "linkfile.md"
    os.symlink(real / "r.md", link_file)

    rel = {str(p.relative_to(tmp_path)) for p in find_markdown_files(str(tmp_path))}
    assert os.path.join("real", "r.md") in rel  # the real directory is walked
    assert os.path.join("linkdir", "r.md") not in rel  # symlinked dir NOT descended
    assert "linkfile.md" in rel  # symlinked file IS discovered


# --- classification tie-break ordering (finding #3, HIGH) --------------------


def test_classify_full_tie_breaks_to_earlier_spec_order():
    # A document whose sections give `requirement` and `roadmap` the EXACT same
    # fit AND the same matched-required count: problem + requirements are the two
    # required sections of `requirement`; outcomes + initiatives are the two
    # required sections of `roadmap`; risks + assumptions are recommended for
    # both. Each type scores points = 2 + 0.5*2 = 3.0 over a ceiling of 3.5, so
    # fit ties at 3/3.5 with matched_required == 2 on both.
    text = (
        "# T\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
        "\n## Outcomes\n\no\n\n## Initiatives\n\ni\n"
        "\n## Risks\n\nr\n\n## Assumptions\n\na\n"
    )
    product = parse(text)
    scores = score_artifacts(product)
    top_two = {s.name: s for s in scores[:2]}
    assert set(top_two) == {"requirement", "roadmap"}
    assert top_two["requirement"].fit == top_two["roadmap"].fit
    assert len(top_two["requirement"].matched_required) == len(top_two["roadmap"].matched_required)
    # A full tie falls back to ARTIFACT_SPECS declaration order (stable sort):
    # `requirement` is declared before `roadmap`, so it wins.
    assert classify(product).type == "requirement"


def test_classify_tie_break_prefers_more_matched_required():
    # A document that fully matches BOTH `requirement` and `decision` (all their
    # required and recommended sections). Both reach fit == 1.0, but `decision`
    # has 3 matched-required sections to `requirement`'s 2. The sort key is
    # (fit, len(matched_required)) descending, so the more-required-matches type
    # wins even though `requirement` is declared FIRST in ARTIFACT_SPECS — this
    # pins that the second sort key overrides declaration order.
    text = (
        "# T\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
        "\n## Success Metrics\n\nm\n\n## Risks\n\nr\n\n## Assumptions\n\na\n"
        "\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n"
        "\n## Status\n\ns\n\n## Category\n\ncat\n\n## Alternatives Considered\n\nalt\n"
    )
    product = parse(text)
    scores = score_artifacts(product)
    by_name = {s.name: s for s in scores}
    assert by_name["requirement"].fit == 1.0
    assert by_name["decision"].fit == 1.0
    assert len(by_name["requirement"].matched_required) == 2
    assert len(by_name["decision"].matched_required) == 3
    assert classify(product).type == "decision"


# --- confidence exact rounded value (finding #4, MEDIUM) ---------------------


def test_classify_confidence_is_rounded_to_two_places():
    # A requirement with both required sections plus 2 of 3 recommended:
    # points = 2 + 0.5*2 = 3.0 over ceiling 3.5 -> fit = 0.857..., rounded to
    # 2 decimal places -> 0.86. Pins both the fit formula and the 2dp rounding
    # that inspect/stats JSON expose (ADR-007).
    text = (
        "# T\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
        "\n## Success Metrics\n\nm\n\n## Risks\n\nr\n"
    )
    classification = classify(parse(text))
    assert classification.type == "requirement"
    assert classification.confidence == 0.86
    assert classification.confidence >= CONFIDENCE_THRESHOLD


# --- oversize error message text and parse-vs-file split (finding #5, MED) ----


def test_oversize_parse_and_file_messages_differ(tmp_path, monkeypatch):
    monkeypatch.setenv("RAC_MAX_FILE_BYTES", "64")
    oversize = "x" * 200  # well over the 64-byte cap

    # In-memory parse path: "parse cap".
    in_memory = parse(oversize)
    assert [i.code for i in in_memory.parse_issues] == ["artifact-oversize"]
    assert "parse cap" in in_memory.parse_issues[0].message
    assert "RAC_MAX_FILE_BYTES" in in_memory.parse_issues[0].message

    # File path: the same code but a DIFFERENT message, "file cap".
    p = tmp_path / "big.md"
    p.write_text(oversize, encoding="utf-8")
    from_file = parse_file(str(p))
    assert [i.code for i in from_file.parse_issues] == ["artifact-oversize"]
    assert "file cap" in from_file.parse_issues[0].message


# --- artifact_identifiers alias list (finding #6, MEDIUM) --------------------


def test_artifact_identifiers_order_and_casefold_dedup():
    # Canonical frontmatter id first, then the legacy "## ID" value, then the
    # filename prefix, then the whole stem — with case-insensitive dedup that
    # preserves first-seen order and casing. Here the filename prefix "adr-004"
    # collides case-insensitively with the "## ID" value and is dropped.
    text = "---\nschema_version: 1\nid: RAC-01JY4M8X2QZ7\n---\n# T\n\n## ID\n\nadr-004\n"
    product = parse(text)
    assert artifact_identifiers(product, None, "adr-004-x.md") == [
        "RAC-01JY4M8X2QZ7",
        "adr-004",
        "adr-004-x",
    ]


def test_artifact_identifiers_dedup_preserves_first_seen_casing():
    # "## ID" is "ADR-004"; the filename prefix "adr-004" is deduped against it
    # case-insensitively, and the first-seen casing ("ADR-004") is kept.
    text = "---\nschema_version: 1\nid: RAC-01JY4M8X2QZ7\n---\n# T\n\n## ID\n\nADR-004\n"
    product = parse(text)
    assert artifact_identifiers(product, None, "adr-004-x.md") == [
        "RAC-01JY4M8X2QZ7",
        "ADR-004",
        "adr-004-x",
    ]


# --- max_file_bytes env fallback (finding #7, MEDIUM) ------------------------


def test_max_file_bytes_falls_back_for_non_positive_and_unparseable(monkeypatch):
    # A non-positive or unparseable RAC_MAX_FILE_BYTES falls back to the default
    # (the guard is never disabled); a positive value is honored.
    for bad in ("0", "-1", "abc", ""):
        monkeypatch.setenv("RAC_MAX_FILE_BYTES", bad)
        assert max_file_bytes() == DEFAULT_MAX_FILE_BYTES

    monkeypatch.setenv("RAC_MAX_FILE_BYTES", "2048")
    assert max_file_bytes() == 2048

    monkeypatch.delenv("RAC_MAX_FILE_BYTES", raising=False)
    assert max_file_bytes() == DEFAULT_MAX_FILE_BYTES


# --- CRLF handling in split/body (finding #8, MEDIUM) ------------------------


def test_crlf_frontmatter_parses_and_body_strips_carriage_returns():
    # A CRLF document: the "---\r" delimiter is still recognized (each line is
    # stripped before the delimiter comparison), so the frontmatter parses and
    # the id is read. Captured section bodies are per-line stripped, so interior
    # carriage returns do NOT survive into product.sections.
    text = (
        "---\r\nschema_version: 1\r\nid: RAC-01JY4M8X2QZ7\r\ntype: decision\r\n---\r\n"
        "# T\r\n\r\n## Context\r\n\r\nhello world\r\n"
    )
    product = parse(text)
    assert product.metadata is not None
    assert product.metadata.id == "RAC-01JY4M8X2QZ7"
    assert product.sections.get("context") == "hello world"
    assert "\r" not in product.sections["context"]


# --- content_hash unreadable-path sentinel (finding #9, LOW) -----------------


def test_content_hash_unreadable_path_is_a_stable_sentinel(tmp_path):
    # An unreadable / missing path hashes to a fixed sentinel rather than
    # raising, and that sentinel differs from any real file's content hash (so a
    # missing file cannot collide with real content in the derived-index cache).
    missing = tmp_path / "nope.md"
    expected = hashlib.sha256(b"\x00rac-unreadable-artifact").hexdigest()
    assert content_hash(missing) == expected

    empty = tmp_path / "empty.md"
    empty.write_bytes(b"")
    assert content_hash(missing) != content_hash(empty)
