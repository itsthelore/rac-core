"""Movement-B bundle B4 — incremental directory validation (ADR-103).

B4 makes ``rac validate DIR --cache`` changeset-bound: a stat-manifest scan
detects the changed / added / removed set, and only changed files are re-parsed
and re-validated while unchanged files reuse their cached ``FileValidation``.
Directory validation is a pure per-file computation — every ``FileValidation`` is
a pure function of ``(file bytes, resolved config)`` and OKF conformance is
per-file — so there is no cross-file layer in ``rac validate DIR`` (duplicate-id /
relationship-resolution / cycle checks live in the relationships subsystem, not
here). These tests pin what the incremental mode must guarantee:

(a) **Byte-parity** — ``--cache`` output equals the uncached run (human AND
    ``--json`` AND exit code) across no-change, edit, add, remove, rename, and the
    file-mutation scenarios the performance lens frames as cross-file transition
    classes T1–T5/T7 (a dangling reference's target added, a duplicate id
    appearing, a referenced file removed, a supersedes cycle created by an edit, a
    target's status flipped). ``rac validate DIR`` emits no relationship findings,
    so both paths agree on every scenario — the assertion is that the per-file
    cache correctly reuses / invalidates across each mutation without ever
    inventing or dropping a finding.
(b) **The config-fingerprint key** — editing an *ancestor* ``.rac/config.yaml``
    (the audit-mandated trap) invalidates every cached result, so the next run
    reflects the new severity policy exactly as a fresh run does.
(c) **Cached-result reuse** — a counting seam on ``validate()`` proves unchanged
    files are not re-validated on the second run.
(d) **Accepted staleness (S5)** — an in-place rewrite preserving both size and
    mtime_ns is reused stale by the stat rung until a content confirm; ``verify``
    catches it. The test *is* the record of the accepted trade.
(e) **Corruption resilience** — a corrupt results store is a miss that recomputes
    fresh, never a wrong answer.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import rac.services.validate as validate_service
from rac.cli import main
from rac.services.index_store import open_validation_store, validate_store_root
from rac.services.validate import (
    _config_fingerprint,
    _root_key,
    validate_directory,
    validate_directory_incremental,
)

# Crockford-base32-clean ids (no I/L/O/U) so Core never falls back to the stem.
_D1 = "RAC-B4AAAA000001"
_D2 = "RAC-B4BBBB000001"
_D3 = "RAC-B4CCCC000001"


def _decision(ident: str, title: str, *, status: str = "Accepted", related=()) -> str:
    text = (
        f"---\nschema_version: 1\nid: {ident}\ntype: decision\n---\n"
        f"# {title}\n\n## Status\n\n{status}\n\n## Category\n\nArchitecture\n\n"
        f"## Context\n\nalpha beta gamma\n\n## Decision\n\nD.\n\n## Consequences\n\nE.\n"
    )
    if related:
        text += "\n## Related Decisions\n\n" + "".join(f"- {t}\n" for t in related)
    return text


def _corpus(tmp_path: Path, files: dict[str, str], *, key: str = "RAC") -> Path:
    corpus = tmp_path / "corpus"
    (corpus / ".rac").mkdir(parents=True)
    (corpus / ".rac" / "config.yaml").write_text(f"repository_key: {key}\n", encoding="utf-8")
    for name, text in files.items():
        path = corpus / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return corpus


def _bump(path: Path) -> None:
    """Advance a file's mtime well past 'now' so the stat rung always detects it.

    Guards the same-size in-place edit scenarios (e.g. a status flip) against a
    coarse-mtime filesystem — normal wall-clock advance already changes mtime_ns,
    this just makes the parity tests deterministic regardless of resolution.
    """
    future = time.time() + 5
    os.utime(path, (future, future))


def _run(capsys, argv: list[str]) -> tuple[int, str]:
    rc = main(argv)
    return rc, capsys.readouterr().out


def _assert_parity(capsys, cache_dir: Path, monkeypatch, corpus: Path) -> None:
    """Full run == cold-cache run == warm-cache run, for human, JSON, and exit code."""
    monkeypatch.setenv("RAC_CACHE_DIR", str(cache_dir))
    for fmt in ([], ["--json"], ["--sarif"]):
        full = _run(capsys, ["validate", str(corpus), *fmt])
        cold = _run(capsys, ["validate", str(corpus), "--cache", *fmt])
        warm = _run(capsys, ["validate", str(corpus), "--cache", *fmt])
        assert full == cold == warm, fmt


def _warm(capsys, cache_dir: Path, monkeypatch, corpus: Path) -> None:
    monkeypatch.setenv("RAC_CACHE_DIR", str(cache_dir))
    _run(capsys, ["validate", str(corpus), "--cache"])


# --- (a) byte-parity across every mutation class -----------------------------


def test_parity_no_change(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A"), "b.md": "# broken\n\nnope\n"})
    _assert_parity(capsys, tmp_path / "cache", monkeypatch, corpus)


def test_parity_edit(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A"), "b.md": _decision(_D2, "B")})
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "a.md").write_text(_decision(_D1, "A", status="Nonsense"), encoding="utf-8")
    _bump(corpus / "a.md")
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_add(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A")})
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "b.md").write_text("# broken\n\nnope\n", encoding="utf-8")
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_remove(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A"), "b.md": _decision(_D2, "B")})
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "b.md").unlink()
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_rename(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A"), "b.md": _decision(_D2, "B")})
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "b.md").rename(corpus / "c.md")  # same bytes, new path
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_t1_not_found_reference_resolved_by_added_file(tmp_path, capsys, monkeypatch):
    # T1: a source references _D2 which does not yet exist; adding _D2 would flip a
    # relationship resolution *in the graph subsystem* — invisible to validate DIR.
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A", related=[_D2])})
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "b.md").write_text(_decision(_D2, "B"), encoding="utf-8")
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_t3_duplicate_identifier_appears(tmp_path, capsys, monkeypatch):
    # T3: a second file declaring _D1 makes the id ambiguous cross-file — again a
    # relationship-subsystem finding, not a validate-DIR one; per-file cache holds.
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A")})
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "dup.md").write_text(_decision(_D1, "A duplicate"), encoding="utf-8")
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_t2_removed_file_breaks_reference(tmp_path, capsys, monkeypatch):
    # T2: removing the only file with _D2 breaks a reference from _D1.
    corpus = _corpus(
        tmp_path, {"a.md": _decision(_D1, "A", related=[_D2]), "b.md": _decision(_D2, "B")}
    )
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "b.md").unlink()
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_t7_supersedes_cycle_created_by_edit(tmp_path, capsys, monkeypatch):
    # T7: editing files into a supersedes cycle is a graph cycle finding, not a
    # validate-DIR finding; the per-file structural results are unaffected.
    corpus = _corpus(
        tmp_path,
        {
            "a.md": _decision(_D1, "A") + f"\n## Supersedes\n\n- {_D2}\n",
            "b.md": _decision(_D2, "B"),
        },
    )
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "b.md").write_text(
        _decision(_D2, "B") + f"\n## Supersedes\n\n- {_D1}\n", encoding="utf-8"
    )
    _bump(corpus / "b.md")
    _assert_parity(capsys, cache, monkeypatch, corpus)


def test_parity_t5_target_status_flip(tmp_path, capsys, monkeypatch):
    # T5: flipping a referenced target's status changes a graph status-consistency
    # finding, but is only a per-file metadata change to validate DIR.
    corpus = _corpus(
        tmp_path,
        {"a.md": _decision(_D1, "A", related=[_D2]), "b.md": _decision(_D2, "B")},
    )
    cache = tmp_path / "cache"
    _warm(capsys, cache, monkeypatch, corpus)
    (corpus / "b.md").write_text(_decision(_D2, "B", status="Deprecated"), encoding="utf-8")
    _bump(corpus / "b.md")
    _assert_parity(capsys, cache, monkeypatch, corpus)


# --- (b) the config-fingerprint key: ancestor-config edit invalidates ---------


def test_ancestor_config_edit_invalidates_cache(tmp_path, capsys, monkeypatch):
    # A typed decision missing its Consequences section: an error under the default
    # policy, clean once the rule is turned off. The corpus is nested one level
    # down so the config edit is genuinely an *ancestor* edit relative to the
    # validated directory (the audit's ancestor-walk trap, v2 §3.1).
    corpus = tmp_path / "corpus"
    (corpus / ".rac").mkdir(parents=True)
    config = corpus / ".rac" / "config.yaml"
    config.write_text("repository_key: RAC\n", encoding="utf-8")
    sub = corpus / "adr"
    sub.mkdir()
    (sub / "broken.md").write_text(
        "---\nschema_version: 1\nid: " + _D1 + "\ntype: decision\n---\n"
        "# D\n\n## Status\n\nAccepted\n\n## Context\n\nc\n\n## Decision\n\nd\n",
        encoding="utf-8",
    )

    cache = tmp_path / "cache"
    monkeypatch.setenv("RAC_CACHE_DIR", str(cache))
    warm_rc, _ = _run(capsys, ["validate", str(sub), "--cache"])  # warm: fails on missing section
    assert warm_rc == 1

    # The fingerprint must change when the ancestor config changes.
    before = _config_fingerprint(str(sub))
    config.write_text(
        "repository_key: RAC\nvalidation:\n  rules:\n    missing-consequences: off\n",
        encoding="utf-8",
    )
    assert _config_fingerprint(str(sub)) != before

    # After the ancestor edit the cache must be invalidated: cache and full agree on
    # the new policy, and the run now passes — a stale (pre-edit) cache would fail.
    for fmt in ([], ["--json"]):
        full = _run(capsys, ["validate", str(sub), *fmt])
        cache_run = _run(capsys, ["validate", str(sub), "--cache", *fmt])
        assert full == cache_run, fmt
        assert full[0] == 0, fmt  # missing-consequences downgraded off → passes


# --- (c) cached-result reuse proof (a counting seam on validate()) -----------


def test_unchanged_files_are_not_revalidated(tmp_path, capsys, monkeypatch):
    corpus = _corpus(
        tmp_path,
        {"a.md": _decision(_D1, "A"), "b.md": _decision(_D2, "B"), "c.md": _decision(_D3, "C")},
    )
    cache = tmp_path / "cache"

    calls: list[int] = [0]
    real = validate_service.validate

    def counting(*args, **kwargs):
        calls[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(validate_service, "validate", counting)

    validate_directory_incremental(str(corpus), cache_dir=cache)
    assert calls[0] == 3  # cold: every file validated

    calls[0] = 0
    validate_directory_incremental(str(corpus), cache_dir=cache)
    assert calls[0] == 0  # warm, no change: nothing re-validated

    calls[0] = 0
    (corpus / "a.md").write_text(_decision(_D1, "A", status="Bogus"), encoding="utf-8")
    _bump(corpus / "a.md")
    validate_directory_incremental(str(corpus), cache_dir=cache)
    assert calls[0] == 1  # only the edited file is re-validated


# --- (d) accepted staleness (S5): size+mtime-preserving in-place rewrite -------


def test_size_and_mtime_preserving_rewrite_is_the_accepted_stat_miss(tmp_path, capsys, monkeypatch):
    # "Accepted" and "Rejected" are both 8 characters, so swapping them is a
    # same-size rewrite; restoring mtime makes it invisible to the stat proxy.
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A", status="Accepted")})
    cache = tmp_path / "cache"
    path = corpus / "a.md"
    before = path.stat()

    validate_directory_incremental(str(corpus), cache_dir=cache)  # warm: status valid

    path.write_text(_decision(_D1, "A", status="Rejected"), encoding="utf-8")  # now invalid
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))  # preserve the proxy
    assert path.stat().st_size == before.st_size

    stale = validate_directory_incremental(str(corpus), cache_dir=cache)
    fresh = validate_directory(str(corpus))
    # The stat rung reuses the stale (valid) result — the accepted S5 miss.
    assert stale.to_dict() != fresh.to_dict()
    assert stale.ok and not fresh.ok

    # The verify floor re-reads bytes and catches it, matching a fresh run.
    verified = validate_directory_incremental(str(corpus), cache_dir=cache, verify=True)
    assert verified.to_dict() == fresh.to_dict()


# --- (e) corrupt store → full recompute, never a wrong answer -----------------


def test_corrupt_results_store_recomputes_fresh(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A"), "b.md": "# broken\n\nnope\n"})
    cache = tmp_path / "cache"

    validate_directory_incremental(str(corpus), cache_dir=cache)  # warm: writes the store

    store = validate_store_root(cache) / f"{_root_key(str(corpus))}.vseg"
    assert store.is_file()
    store.write_bytes(b"not a valid segment \x00\x01\x02 pickle-looking garbage")

    # A corrupt store opens as a miss → full recompute, output still correct.
    assert (
        open_validation_store(cache, _root_key(str(corpus)), _config_fingerprint(str(corpus)))
        is None
    )
    recovered = validate_directory_incremental(str(corpus), cache_dir=cache)
    assert recovered.to_dict() == validate_directory(str(corpus)).to_dict()
    # The run rewrote a valid store, so the cache is restored for next time.
    assert (
        open_validation_store(cache, _root_key(str(corpus)), _config_fingerprint(str(corpus)))
        is not None
    )


def test_truncated_store_is_a_miss(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A")})
    cache = tmp_path / "cache"
    validate_directory_incremental(str(corpus), cache_dir=cache)
    store = validate_store_root(cache) / f"{_root_key(str(corpus))}.vseg"
    store.write_bytes(store.read_bytes()[:12])  # header only, payload gone
    assert (
        open_validation_store(cache, _root_key(str(corpus)), _config_fingerprint(str(corpus)))
        is None
    )
    assert (
        validate_directory_incremental(str(corpus), cache_dir=cache).to_dict()
        == validate_directory(str(corpus)).to_dict()
    )


# --- timing scorecard split (stderr-only, opt-in) ----------------------------


def test_timing_line_is_stderr_only_and_opt_in(tmp_path, capsys, monkeypatch):
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A")})
    cache = tmp_path / "cache"
    monkeypatch.setenv("RAC_CACHE_DIR", str(cache))

    # Absent by default: no rac-timing line on either stream.
    main(["validate", str(corpus), "--cache"])
    quiet = capsys.readouterr()
    assert "rac-timing" not in quiet.err
    assert "rac-timing" not in quiet.out

    monkeypatch.setenv("RAC_TIMING", "1")
    rc = main(["validate", str(corpus), "--cache", "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "rac-timing" not in captured.out  # frozen stdout untouched
    assert "rac-timing: detect_ms=" in captured.err
    assert "recompute_ms=" in captured.err
    assert "files_changed=" in captured.err


def test_store_segment_is_not_a_pickle(tmp_path):
    # The no-code-bearing-format proof: the store opens with the segment magic,
    # never a pickle/JSON opcode (ADR-101 discipline carried to the results store).
    corpus = _corpus(tmp_path, {"a.md": _decision(_D1, "A")})
    cache = tmp_path / "cache"
    validate_directory_incremental(str(corpus), cache_dir=cache)
    store = validate_store_root(cache) / f"{_root_key(str(corpus))}.vseg"
    assert store.read_bytes()[:8] == b"RACIDX01"
