"""Per-mutation-class byte-parity for the ADR-108 parallel merge.

ADR-107 flagged the fan-out of the *derive* (not just the parse) as the highest
byte-parity risk in the system: workers emit compact per-document fragments and
the parent reproduces the derived read-model from them, so any per-document
derivation that the fragment projects incompletely — or that the merge
reassembles in the wrong order — would silently diverge from the serial build.

These tests are the risk gate. Each targets one fragile derivation with a corpus
crafted to exercise it non-trivially, then asserts that the fragment-merge path is
byte-identical to the serial derive two ways:

- ``reproduce([fragment_from_entry(e) for e in walk])`` equals
  ``build_derived_index`` — the whole merge, in-process, no worker needed; and
- an end-to-end ``build_derived_index_parallel`` writes a store whose segment
  bytes equal a single-process build's, so the fan-out is proven across a real
  process boundary and a real chunk split (cross-chunk edges, uneven partitions).

The equality is field-for-field (``DerivedIndex`` dataclass equality) and over the
lossless serialisation, so a divergence in any derived structure — resolution
outcomes, inbound counts, tokens, the portfolio gate, scope/live rows — fails here.

Identifiers are numeric (``RAC-<12 digits>``) so every fixture artifact is
schema-valid — the id syntax is Crockford base32, which excludes I/L/O/U — and the
portfolio gate reflects the relationship finding under test, not an id-syntax error.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from rac.core.corpus import corpus_content_hash, walk_corpus
from rac.services.derived_cache import build_derived_index, to_json_obj
from rac.services.index_store import store_dir, write_store
from rac.services.parallel_build import build_derived_index_parallel
from rac.services.parallel_merge import fragment_from_entry, reproduce

_BUNDLE_VERSION = "3"


def _id(n: int) -> str:
    return f"RAC-{n:012d}"


# --- fixtures ----------------------------------------------------------------


def _decision(
    ident: str,
    *,
    title: str = "Decision",
    body: str = "alpha beta gamma",
    status: str = "Accepted",
    tags: str | None = None,
    related_decisions: list[str] | None = None,
    related_requirements: list[str] | None = None,
    related_tickets: list[str] | None = None,
    supersedes: list[str] | None = None,
    applies_to: list[str] | None = None,
) -> str:
    tag_line = f"tags: [{', '.join(tags)}]\n" if tags else ""
    doc = (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n{tag_line}---\n"
        f"# {title}\n\n## Status\n\n{status}\n\n## Category\n\nArchitecture\n\n"
        f"## Context\n\n{body}\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )
    for heading, refs in (
        ("Related Decisions", related_decisions),
        ("Related Requirements", related_requirements),
        ("Related Tickets", related_tickets),
        ("Supersedes", supersedes),
        ("Applies To", applies_to),
    ):
        if refs:
            body_lines = "".join(f"- {ref}\n" for ref in refs)
            doc += f"\n## {heading}\n\n{body_lines}"
    return doc


def _requirement(ident: str, *, title: str = "Requirement", body: str = "need") -> str:
    return (
        f"---\nschema_version: 1\nid: {ident}\ntype: requirement\n---\n"
        f"# {title}\n\n## Problem\n\n{body}\n\n## Requirements\n\n- R.\n"
    )


def _write(directory: Path, name: str, content: str) -> None:
    (directory / name).write_text(content, encoding="utf-8")


def _assert_merge_parity(directory: Path):
    """The whole fragment-merge equals the serial derive, field-for-field + serialised."""
    entries = list(walk_corpus(str(directory), recursive=True))
    serial = build_derived_index(str(directory))
    merged = reproduce([fragment_from_entry(e) for e in entries], str(directory))
    assert merged == serial, "reproduce() diverged from build_derived_index()"
    assert to_json_obj(merged) == to_json_obj(serial), "serialised merge diverged"
    return serial, merged


def _segment_hashes(cache_dir: Path, corpus_hash: str) -> dict[str, str]:
    directory = store_dir(cache_dir, corpus_hash)
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.iterdir())
        if p.is_file()
    }


def _assert_store_parity(directory: Path, cache_root: Path, *, workers: int) -> int:
    """workers=N store bytes equal workers=1 store bytes; returns the workers actually used."""
    corpus_hash = corpus_content_hash(str(directory))

    serial, serial_stats = build_derived_index_parallel(str(directory), workers=1)
    assert write_store(cache_root / "s1", corpus_hash, _BUNDLE_VERSION, serial)
    serial_hashes = _segment_hashes(cache_root / "s1", corpus_hash)

    parallel, parallel_stats = build_derived_index_parallel(str(directory), workers=workers)
    assert write_store(cache_root / "sN", corpus_hash, _BUNDLE_VERSION, parallel)
    parallel_hashes = _segment_hashes(cache_root / "sN", corpus_hash)

    assert serial_stats.workers == 1
    assert parallel_hashes == serial_hashes, "fan-out store diverged from the serial store"
    return parallel_stats.workers


# --- resolution outcomes -----------------------------------------------------


def test_resolution_outcomes_parity(tmp_path):
    # resolved / not-found / ambiguous / self / external — all five outcomes in one
    # corpus so the resolved graph, inbound counts, and portfolio gate all diverge
    # if any outcome is reproduced wrongly.
    a, b, dup = _id(101), _id(102), _id(103)
    d = tmp_path
    _write(d, "a.md", _decision(a, title="A resolves to B", related_decisions=[b]))
    _write(d, "b.md", _decision(b, title="B", related_decisions=[_id(999999)]))  # not-found
    _write(d, "c.md", _decision(_id(104), related_decisions=[dup]))  # ambiguous
    _write(d, "dup1.md", _decision(dup, title="Dup one"))
    _write(d, "dup2.md", _decision(dup, title="Dup two"))
    _write(d, "self.md", _decision(_id(105), related_decisions=[_id(105)]))  # self
    _write(d, "ext.md", _decision(_id(106), related_tickets=["JIRA-123"]))  # external

    _serial, merged = _assert_merge_parity(d)
    # Sanity: the corpus is non-trivial — resolved, broken, and external edges exist.
    issues = {r.issue for r in merged.relationships}
    assert None in issues  # resolved and external edges carry no issue
    assert any(r.resolved_path for r in merged.relationships)
    assert any(r.issue for r in merged.relationships)
    # The duplicate + broken references make the portfolio relationship gate fail.
    assert merged.portfolio_summary["validation_status"]["relationships_ok"] is False


def test_duplicate_identity_parity(tmp_path):
    dup = _id(200)
    _write(tmp_path, "one.md", _decision(dup, title="First"))
    _write(tmp_path, "two.md", _decision(dup, title="Second"))
    _write(tmp_path, "solo.md", _decision(_id(201)))
    _serial, merged = _assert_merge_parity(tmp_path)
    # A duplicate canonical identifier is a relationship-validation finding.
    assert merged.portfolio_summary["validation_status"]["relationships_ok"] is False


def test_alias_and_legacy_id_parity(tmp_path):
    # A legacy-style filename gives the artifact extra aliases beyond its canonical
    # frontmatter id; the merge must build the resolution index over every alias.
    _write(tmp_path, "ADR-042-legacy.md", _decision(_id(300), title="Legacy"))
    _write(tmp_path, "ref.md", _decision(_id(301), related_decisions=["ADR-042"]))
    _assert_merge_parity(tmp_path)


def test_unknown_type_parity(tmp_path):
    _write(tmp_path, "d.md", _decision(_id(400)))
    (tmp_path / "notes.md").write_text("# Just a note\n\nNo frontmatter, no type.\n", "utf-8")
    _serial, merged = _assert_merge_parity(tmp_path)
    assert merged.portfolio_summary["artifacts"]["by_type"]["unknown"] == 1
    assert merged.portfolio_summary["artifacts"]["unknown_paths"]


def test_range_and_status_consistency_parity(tmp_path):
    # A decision whose ``## Related Decisions`` resolves to a requirement is a range
    # violation; a live decision referencing a superseded decision is a status
    # violation. Both live only in the ``_validate`` gate the portfolio reproduces.
    req, retired = _id(500), _id(501)
    _write(tmp_path, "req.md", _requirement(req))
    _write(tmp_path, "range.md", _decision(_id(502), related_decisions=[req]))
    _write(tmp_path, "old.md", _decision(retired, title="Retired", status="Superseded"))
    _write(tmp_path, "live.md", _decision(_id(503), related_decisions=[retired]))
    _serial, merged = _assert_merge_parity(tmp_path)
    assert merged.portfolio_summary["validation_status"]["relationships_ok"] is False


def test_tag_only_document_parity(tmp_path):
    # A term present only in a document's tags must tokenise into the tags field
    # vector exactly as the serial build does (ADR-109).
    _write(tmp_path, "tagged.md", _decision(_id(600), tags=["observability", "data-model"]))
    _write(tmp_path, "plain.md", _decision(_id(601)))
    _serial, merged = _assert_merge_parity(tmp_path)
    tokens = merged.field_tokens_by_path[str(tmp_path / "tagged.md")]["tags"]
    assert "observability" in tokens and "data" in tokens and "model" in tokens


def test_scope_and_live_decision_parity(tmp_path):
    # A live decision with declared ``## Applies To`` scope yields a scope row and a
    # live path; a superseded decision yields neither.
    _write(
        tmp_path,
        "live.md",
        _decision(_id(700), title="Live", applies_to=["src/rac/services/"]),
    )
    _write(tmp_path, "dead.md", _decision(_id(701), status="Deprecated"))
    _serial, merged = _assert_merge_parity(tmp_path)
    assert [r.path for r in merged.scope_rows] == [str(tmp_path / "live.md")]
    assert merged.live_decision_paths == [str(tmp_path / "live.md")]


# --- partition shape ---------------------------------------------------------


def test_empty_corpus_parity(tmp_path):
    _serial, merged = _assert_merge_parity(tmp_path)
    assert merged.index_entries == []
    assert merged.relationships == []


def test_single_document_parity(tmp_path):
    _write(tmp_path, "only.md", _decision(_id(800)))
    _assert_merge_parity(tmp_path)


def test_cross_chunk_edge_store_parity(tmp_path):
    # Source and target land in different worker chunks (sorted paths split in two),
    # so the merge must resolve an edge whose endpoints came from different workers.
    src, dst = _id(900), _id(901)
    _write(tmp_path, "aaa.md", _decision(src, title="Source", related_decisions=[dst]))
    _write(tmp_path, "mmm.md", _decision(_id(902)))
    _write(tmp_path, "yyy.md", _decision(_id(903)))
    _write(tmp_path, "zzz.md", _decision(dst, title="Target"))
    # In-process reproduce parity, then a real two-worker store parity across the split.
    _serial, merged = _assert_merge_parity(tmp_path)
    assert merged.index_entries[0].path == str(tmp_path / "aaa.md")
    # The target is referenced once — the inbound count must survive the cross-chunk merge.
    target_entry = next(e for e in merged.index_entries if e.path == str(tmp_path / "zzz.md"))
    assert target_entry.inbound_count == 1
    used = _assert_store_parity(tmp_path, tmp_path / "cache", workers=2)
    assert used >= 2, "the cross-chunk build must actually fan out"


def test_uneven_partition_store_parity(tmp_path):
    # A file count not divisible by the worker count exercises the last, shorter
    # chunk (contiguous-chunk offset arithmetic) end to end.
    for i in range(10):
        _write(tmp_path, f"d{i:02d}.md", _decision(_id(1000 + i), body=f"term{i} shared"))
    used = _assert_store_parity(tmp_path, tmp_path / "cache", workers=4)
    assert used >= 2
