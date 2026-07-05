"""Persistent corpus index — byte-parity, changeset refresh, recency (ADR-100/101).

The Movement-B index directory (``src/rac/services/persistent_index.py``) must be
an invisible optimisation: index-served output is byte-identical to the fresh
walk-and-parse path for any corpus state, incremental work is bound by the
changeset, mtime is a hint but the byte hash is the authority, corruption degrades
to a clean rebuild, the bytes are deterministic, the graph column matches the live
relationship build, and the recency column matches the live git answer.

These tests pin exactly those invariants.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from conftest import fixture_path

from rac.core.corpus import walk_corpus
from rac.services.index import build_repository_index
from rac.services.persistent_index import (
    PersistentIndexError,
    build_index,
    load_index,
    open_index,
)
from rac.services.recency import _last_committed, _repository_root
from rac.services.relationships import (
    inbound_counts_from_corpus,
    incoming_references,
    neighborhood,
    outgoing_references,
    relationships_from_corpus,
)
from rac.services.resolve import resolve_in_index, search_index

RESOLVE_FIXTURE = fixture_path("resolve")


# --- edge-case corpus builder ------------------------------------------------


def _edge_case_corpus(root: Path) -> None:
    """A small corpus exercising prefix, camelCase, AND-semantics, and a real edge.

    ``adr-001`` references ``adr-002`` by filename stem (a stem always resolves),
    so the resolved-edge graph is non-trivial for the inbound/neighbourhood pins.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "adr-001.md").write_text(
        "# ADR-1 camelCaseWord softDelete\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nThe relationships subsystem handles softDelete semantics.\n\n"
        "## Decision\n\nUse camelCaseWord tokens.\n\n"
        "## Consequences\n\nGood.\n\n"
        "## Related Decisions\n\n- adr-002\n",
        encoding="utf-8",
    )
    (root / "adr-002.md").write_text(
        "# ADR-2 Relationships format\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nc\n\n"
        "## Decision\n\nd\n\n"
        "## Consequences\n\nk\n",
        encoding="utf-8",
    )
    (root / "req-001.md").write_text(
        "# Requirement One relationships\n\n"
        "## Problem\n\np\n\n"
        "## Requirements\n\n[REQ-001] The system supports softDelete of relationships.\n",
        encoding="utf-8",
    )


_EDGE_CASE_QUERIES: tuple[tuple[str, str | None], ...] = (
    ("relationships", None),  # exact token, multiple docs
    ("relationship", None),  # prefix of "relationships"
    ("camel", None),  # prefix into a camelCase seam
    ("camelcase", None),  # casefolded camelCase token
    ("camelCaseWord", None),  # mixed-case query
    ("softdelete", None),  # camelCase seam split
    ("soft delete", None),  # AND across two terms
    ("relationships format", None),  # AND, spanning title + body
    ("relationships", "decision"),  # type filter
    ("relationships", "requirement"),  # type filter to the other type
    ("zzznomatch", None),  # no match — a valid empty result
    ("", None),  # empty query — a valid empty result
    ("...", None),  # all-punctuation — tokenises to nothing
    ("adr", None),  # id/path prefix
)


def _index_dir(tmp_path: Path, name: str = "idx") -> str:
    return str(tmp_path / name)


# --- 1. byte-parity: index search == fresh walk search -----------------------


def test_search_parity_over_resolve_fixture(tmp_path):
    idx = _index_dir(tmp_path)
    build_index(RESOLVE_FIXTURE, idx, workers=1)
    fresh = build_repository_index(RESOLVE_FIXTURE).artifacts
    with load_index(idx) as index:
        # entries() reproduce the fresh repository index rows exactly.
        assert [e.to_dict() for e in index.entries()] == [e.to_dict() for e in fresh]
        for query in ("markdown", "mark", "format", "canonical format", "zzz"):
            expected = search_index(fresh, query).to_dict(include_evidence=True)
            got = index.search_entries(query).to_dict(include_evidence=True)
            assert got == expected, f"drift for {query!r}"


def test_search_parity_over_edge_case_corpus(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    fresh = build_repository_index(str(root)).artifacts
    with load_index(idx) as index:
        for query, artifact_type in _EDGE_CASE_QUERIES:
            expected = search_index(fresh, query, artifact_type=artifact_type).to_dict(
                include_evidence=True
            )
            got = index.search_entries(query, artifact_type=artifact_type).to_dict(
                include_evidence=True
            )
            assert got == expected, f"drift for {query!r} type={artifact_type}"


def test_explain_evidence_matches_frozen_scorer(tmp_path):
    # The candidate scorer must reproduce the BM25F/RRF evidence bit-for-bit — the
    # full {field, terms, tier, score, components} block, floats included.
    idx = _index_dir(tmp_path)
    build_index(RESOLVE_FIXTURE, idx, workers=1)
    fresh = build_repository_index(RESOLVE_FIXTURE).artifacts
    with load_index(idx) as index:
        expected = search_index(fresh, "markdown").to_dict(include_evidence=True)
        got = index.search_entries("markdown").to_dict(include_evidence=True)
        assert got == expected
        # The evidence block is present and carries the score components verbatim.
        evidence = got["matches"][0]["evidence"]
        assert set(evidence) == {"field", "terms", "tier", "score", "components"}
        assert set(evidence["components"]) == {"bm25", "lexical_rank", "graph_rank", "inbound"}


# --- 2. refresh splices only the changeset -----------------------------------


def _assert_full_search_parity(index, root: str) -> None:
    fresh = build_repository_index(root).artifacts
    assert [e.to_dict() for e in index.entries()] == [e.to_dict() for e in fresh]
    for query in ("relationships", "softdelete", "camel", "quantum", "photosynthesis", "adr"):
        expected = search_index(fresh, query).to_dict(include_evidence=True)
        got = index.search_entries(query).to_dict(include_evidence=True)
        assert got == expected, f"post-refresh drift for {query!r}"


def test_refresh_edit_add_remove_rename_keeps_parity(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    index = load_index(idx)

    # Edit one artifact's title.
    (root / "adr-002.md").write_text(
        (root / "adr-002.md")
        .read_text(encoding="utf-8")
        .replace("# ADR-2 Relationships format", "# ADR-2 Edited photosynthesis"),
        encoding="utf-8",
    )
    assert index.refresh(str(root)) == 1  # exactly one file re-indexed
    _assert_full_search_parity(index, str(root))

    # Add a new artifact, remove one, rename another — one refresh.
    (root / "adr-004.md").write_text(
        "# ADR-4 Newly added quantum\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n",
        encoding="utf-8",
    )
    (root / "req-001.md").unlink()
    os.rename(root / "adr-001.md", root / "adr-001-renamed.md")
    # Re-indexed count is the added + renamed-in file (2); the removed and the
    # rename's old path are dropped, not re-parsed.
    assert index.refresh(str(root)) == 2
    _assert_full_search_parity(index, str(root))

    # A refresh with no filesystem change touches nothing.
    assert index.refresh(str(root)) == 0
    index.close()


def test_zero_change_refresh_reindexes_nothing(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    with load_index(idx) as index:
        assert index.refresh(str(root)) == 0
        assert index.refresh(str(root)) == 0


# --- 2b. candidate fast path: splice only the named changeset -----------------


def test_candidates_fast_path_matches_full_and_skips_untouched(tmp_path, monkeypatch):
    # The watcher already knows the dirty paths, so refresh(candidates=...) must
    # splice exactly those — an edit, an add (in a new subdirectory), and a delete —
    # WITHOUT ever enumerating the corpus or touching any unnamed file, yet produce
    # an index byte-identical to a fresh full build over the final corpus.
    import rac.services.persistent_index as pi

    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    index = load_index(idx)

    # Edit adr-002, add sub/adr-009 (a new subdirectory file), delete req-001.
    (root / "adr-002.md").write_text(
        (root / "adr-002.md")
        .read_text(encoding="utf-8")
        .replace("# ADR-2 Relationships format", "# ADR-2 Edited photosynthesis"),
        encoding="utf-8",
    )
    (root / "sub").mkdir()
    (root / "sub" / "adr-009.md").write_text(
        "# ADR-9 Added quantum\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n",
        encoding="utf-8",
    )
    (root / "req-001.md").unlink()
    candidates = ["adr-002.md", "sub/adr-009.md", "req-001.md"]

    # Isolation: the fast path must never call the full enumerate, and must only
    # hash / parse the named files — the untouched adr-001 is never read.
    def _no_enumerate(*_a, **_k):
        raise AssertionError("candidate fast path must not enumerate the corpus")

    hashed: list[str] = []
    parsed: list[str] = []
    real_sha, real_parse = pi._sha256, pi._parse_one
    monkeypatch.setattr(pi, "find_markdown_files", _no_enumerate)
    monkeypatch.setattr(pi, "_sha256", lambda p: (hashed.append(str(p)), real_sha(p))[1])
    monkeypatch.setattr(
        pi, "_parse_one", lambda r, d, p: (parsed.append(str(p)), real_parse(r, d, p))[1]
    )

    # Edit + add re-index (2); the delete drops without a reparse.
    assert index.refresh(str(root), candidates=candidates) == 2

    # The untouched survivor was never hashed nor parsed.
    assert not any("adr-001" in p for p in hashed), hashed
    assert not any("adr-001" in p for p in parsed), parsed
    # Only the named files were hashed/parsed.
    assert all(("adr-002" in p or "adr-009" in p or "req-001" in p) for p in hashed), hashed
    assert all(("adr-002" in p or "adr-009" in p) for p in parsed), parsed

    # Parity: byte-identical to a fresh full build over the final corpus. (The
    # monkeypatch only rebinds persistent_index's names; build_repository_index
    # walks via its own import, so the comparison is unaffected.)
    _assert_full_search_parity(index, str(root))
    index.close()


def test_candidates_unchanged_named_path_is_a_noop(tmp_path):
    # A named candidate whose bytes still match the manifest (an event with no real
    # change) splices nothing and rewrites nothing.
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    with load_index(idx) as index:
        assert index.refresh(str(root), candidates=["adr-002.md"]) == 0
        # An empty candidate set is likewise a no-op.
        assert index.refresh(str(root), candidates=[]) == 0


def test_candidates_hash_authority_over_stat_hint(tmp_path):
    # Bytes stay the authority for a NAMED path: a size+mtime-preserving edit that
    # the full-scan stat hint would miss is still caught when the path is named,
    # because a named candidate is always hashed.
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    index = load_index(idx)

    target = root / "adr-002.md"
    before = target.read_text(encoding="utf-8")
    stat = target.stat()
    edited = before.replace("format", "forms.")  # same byte length as "format"
    assert len(edited) == len(before) and edited != before
    target.write_text(edited, encoding="utf-8")
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    # Naming the path forces the hash — the edit is spliced without verify mode.
    assert index.refresh(str(root), candidates=["adr-002.md"]) == 1
    _assert_full_search_parity(index, str(root))
    index.close()


def test_directory_candidate_falls_back_to_full_enumerate(tmp_path, monkeypatch):
    # A directory-level dirty path can hide an arbitrary changeset, so refresh must
    # abandon the fast path and run the full stat scan, which still finds the file
    # created inside the new subdirectory.
    import rac.services.persistent_index as pi

    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    index = load_index(idx)

    (root / "sub").mkdir()
    (root / "sub" / "adr-009.md").write_text(
        "# ADR-9 Added quantum\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n",
        encoding="utf-8",
    )

    enumerated: list[int] = []
    real = pi.find_markdown_files
    monkeypatch.setattr(
        pi, "find_markdown_files", lambda *a, **k: (enumerated.append(1), real(*a, **k))[1]
    )

    # The candidate is the new directory itself; refresh must fall back.
    assert index.refresh(str(root), candidates=["sub"]) == 1
    assert enumerated, "a directory candidate must fall back to the full enumerate"
    _assert_full_search_parity(index, str(root))
    index.close()


# --- 3. mtime-hint safety: verify catches a size+mtime-preserving edit --------


def test_size_and_mtime_preserving_edit_needs_verify(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    index = load_index(idx)

    target = root / "adr-002.md"
    before = target.read_text(encoding="utf-8")
    stat = target.stat()
    # A same-length edit, mtime restored: the stat hint cannot see it (ADR-100
    # records exactly this as a missed refresh outside verify mode).
    edited = before.replace("format", "forms.")  # "forms." is byte-length 6, as "format"
    assert len(edited) == len(before) and edited != before
    target.write_text(edited, encoding="utf-8")
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    # Non-verify refresh: the mtime hint is authority-free, so it misses the edit.
    assert index.refresh(str(root)) == 0

    # verify=True re-hashes everything and catches it — the strict byte guarantee.
    assert index.refresh(str(root), verify=True) == 1
    _assert_full_search_parity(index, str(root))
    index.close()


# --- 4. corruption / schema mismatch -> clean rebuild ------------------------


def test_corrupt_index_is_a_miss_and_open_rebuilds(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)

    (Path(idx) / "header.json").write_text("{ not valid json", encoding="utf-8")
    try:
        load_index(idx)
        raise AssertionError("corrupt header must raise PersistentIndexError")
    except PersistentIndexError:
        pass

    # open_index degrades to a clean rebuild — a latency cost, never an answer change.
    with open_index(str(root), idx) as index:
        fresh = build_repository_index(str(root)).artifacts
        assert [e.to_dict() for e in index.entries()] == [e.to_dict() for e in fresh]


def test_schema_mismatch_is_a_miss(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)

    header_path = Path(idx) / "header.json"
    import json

    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["schema_version"] = "999"
    header_path.write_text(json.dumps(header), encoding="utf-8")
    try:
        load_index(idx)
        raise AssertionError("schema mismatch must raise PersistentIndexError")
    except PersistentIndexError:
        pass


# --- 5. determinism: identical bytes -> identical index files ----------------


def _dir_digest(index_dir: str) -> str:
    hasher = hashlib.sha256()
    for path in sorted(Path(index_dir).iterdir()):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def test_build_is_byte_deterministic(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    a = _index_dir(tmp_path, "a")
    b = _index_dir(tmp_path, "b")
    build_index(str(root), a, workers=1)
    build_index(str(root), b, workers=1)
    assert _dir_digest(a) == _dir_digest(b)


# --- 6. graph parity: inbound counts + neighborhood --------------------------


def test_graph_parity_with_relationships_from_corpus(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)

    entries = list(walk_corpus(str(root)))
    fresh = build_repository_index(str(root)).artifacts
    from rac.services.relationships import relationships_from_corpus

    rels = relationships_from_corpus(entries)
    identity = {e.path: (e.id, e.type, e.title) for e in fresh}

    with load_index(idx) as index:
        assert index.inbound_counts() == inbound_counts_from_corpus(entries)
        # A real resolved edge exists (adr-001 -> adr-002 by stem).
        assert index.inbound_counts() == {str(root / "adr-002.md"): 1}
        for origin in (e.path for e in fresh):
            for depth in (1, 2, 5):
                expected = neighborhood(rels, identity, origin, depth=depth)
                assert index.neighborhood(origin, depth=depth) == expected


# --- 6b. per-generation memoised lookups: parity + no stale memo -------------


def _assert_memo_parity(index, root: str) -> None:
    """The memoised seams (resolve / outgoing / incoming / neighborhood) are
    byte-identical to the frozen fresh-path functions for the current corpus."""
    entries = build_repository_index(root).artifacts
    rels = relationships_from_corpus(list(walk_corpus(root)))
    identity = {e.path: (e.id, e.type, e.title) for e in entries}
    # A present id, an absent id, and a duplicate-safe casefold all route the same.
    for entry in entries:
        assert index.resolve(entry.id) == resolve_in_index(entries, entry.id)
        assert index.resolve(entry.id.lower()) == resolve_in_index(entries, entry.id.lower())
        assert index.outgoing(entry.path) == outgoing_references(rels, entry.path)
        assert index.incoming(entry.path) == incoming_references(rels, identity, entry.path)
        for depth in (1, 2, 5):
            assert index.neighborhood(entry.path, depth=depth) == neighborhood(
                rels, identity, entry.path, depth=depth
            )
    assert index.resolve("RAC-DOES-NOT-EXIST") == resolve_in_index(entries, "RAC-DOES-NOT-EXIST")


def test_memoised_seams_match_frozen_path_and_survive_refresh(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    index = load_index(idx)

    # Warm every memo (resolution map, identity map, edge groupings, adjacency),
    # then assert each seam matches the fresh path over the initial corpus.
    _assert_memo_parity(index, str(root))

    # A refresh that changes the graph shape and identities: add a back-edge, edit a
    # title, add a new artifact, remove one. If any memo were stale the seams would
    # answer for the pre-edit corpus.
    (root / "adr-002.md").write_text(
        (root / "adr-002.md")
        .read_text(encoding="utf-8")
        .replace("# ADR-2 Relationships format", "# ADR-2 Relationships format quantum")
        + "\n## Related Decisions\n\n- adr-001\n",
        encoding="utf-8",
    )
    (root / "adr-005.md").write_text(
        "# ADR-5 Added photosynthesis\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nk\n\n"
        "## Related Decisions\n\n- adr-002\n",
        encoding="utf-8",
    )
    (root / "req-001.md").unlink()
    assert index.refresh(str(root)) >= 1

    # Same assertion, post-refresh: the memos were dropped in _adopt and rebuilt
    # against the new mapped state, so every seam reflects the edited corpus.
    _assert_memo_parity(index, str(root))
    index.close()


# --- 7. recency column == live git answer for the same head ------------------


def _git(repo: Path, *args: str, when: str | None = None) -> None:
    env = dict(os.environ)
    if when is not None:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def test_recency_column_matches_live_git(tmp_path):
    repo = tmp_path / "corpus"
    repo.mkdir()
    _git(repo, "init")
    (repo / "a.md").write_text(
        "# A\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "one", when="2024-01-01T12:00:00+00:00")
    (repo / "b.md").write_text(
        "# B\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-002] y\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "two", when="2024-06-15T09:30:00+00:00")

    idx = _index_dir(tmp_path)
    build_index(str(repo), idx, workers=1)
    repo_root = _repository_root(str(repo))
    with load_index(idx) as index:
        assert index.git_head is not None
        stored = index.recency()
        assert stored  # both files carry a committed date
        for path, value in stored.items():
            live = _last_committed(repo_root, path)
            live_iso = live.isoformat() if live is not None else None
            assert value == live_iso, f"recency drift for {path}"


def test_recency_is_none_without_git(tmp_path):
    root = tmp_path / "corpus"
    _edge_case_corpus(root)
    idx = _index_dir(tmp_path)
    build_index(str(root), idx, workers=1)
    with load_index(idx) as index:
        assert index.git_head is None
        assert set(index.recency().values()) == {None}
