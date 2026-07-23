#!/usr/bin/env python3
"""Generate index-store golden vectors from the frozen oracle (ADR-104 stack).

REGENERABLE: any byte change to the pinned fixture corpora shifts the
vectors — rerun with the oracle venv python:

    cd /home/user/rac-core && .venv-oracle/bin/python rust/spec/gen_vectors_index.py

Emits `rust/rac-engine/tests/vectors/index_store.json`:

- per pinned corpus: the corpus content hash, the marker JSON text, and
  every segment file's byte size + sha256 as written by the oracle's
  `write_store` over a serial `build_derived_index` (the store
  byte-identity referee's expected values);
- the raw segment bytes (hex) for both fixture corpora — the codec
  vectors the Rust reader/writer round-trip against;
- a pinned `.vseg` validation store and `.fseg` freshness manifest
  encoding (synthetic rows, byte-exact), plus a `manifest_root_key`
  probe pair;
- the scoring fingerprint string.

The LIVE `rac/` corpus is deliberately NOT pinned here (it changes every
docs commit); live-corpus byte-identity is refereed dynamically by the
batch verification (oracle store vs native store over the working tree).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from asdecided.core.corpus import corpus_content_hash
from asdecided.core.models import Issue
from asdecided.services.derived_cache import SCHEMA_VERSION, build_derived_index
from asdecided.services.freshness import FileState
from asdecided.services.index_store import (
    ValidationRow,
    _encode_validation_store,  # noqa: PLC2701 — byte-exact vector source
    manifest_root_key,
    scoring_fingerprint,
    store_dir,
    write_store,
)
from asdecided.services.index_format import Writer, encode_segment

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / "rac-engine/tests/vectors/index_store.json"

CORPORA = {
    "index-repo": "rust/fixtures/index/repo/rac",
    "mini-repo": "rust/fixtures/closure/mini-repo/rac",
}


def corpus_vectors(rel: str, *, raw: bool) -> dict:
    # The corpus directory is passed REPO-RELATIVE (cwd is pinned to the repo
    # root in main()): entry paths embed in the segment bytes, so an absolute
    # invocation would make the goldens machine-specific.
    directory = rel
    corpus_hash = corpus_content_hash(directory)
    derived = build_derived_index(directory)
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        assert write_store(cache_dir, corpus_hash, SCHEMA_VERSION, derived)
        seg_dir = store_dir(cache_dir, corpus_hash)
        segments = {}
        for path in sorted(seg_dir.iterdir()):
            data = path.read_bytes()
            entry = {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            if raw:
                entry["hex"] = data.hex()
            segments[path.name] = entry
    marker = json.dumps({"schema_version": SCHEMA_VERSION, "corpus_hash": corpus_hash})
    return {
        "directory": rel,
        "corpus_hash": corpus_hash,
        "bundle_version": SCHEMA_VERSION,
        "marker_text": marker,
        "segments": segments,
    }


def vseg_vector() -> dict:
    rows = {
        "decisions/a.md": ValidationRow(
            size=120,
            mtime_ns=1_700_000_000_123_456_789,
            content_hash="a" * 64,
            artifact_type="decision",
            status="valid",
            issues=(),
        ),
        "notes/bad.md": ValidationRow(
            size=7,
            mtime_ns=42,
            content_hash="b" * 64,
            artifact_type="decision",
            status="invalid",
            issues=(
                Issue(severity="error", code="missing-consequences", message="msg one", line=None),
                Issue(severity="warning", code="w-code", message="café ünïcode", line=17),
            ),
        ),
    }
    payload = _encode_validation_store("cfg-fingerprint-0123", rows)
    return {
        "config_hash": "cfg-fingerprint-0123",
        "rows": {
            rel: {
                "size": r.size,
                "mtime_ns": r.mtime_ns,
                "content_hash": r.content_hash,
                "artifact_type": r.artifact_type,
                "status": r.status,
                "issues": [
                    {"severity": i.severity, "code": i.code, "message": i.message, "line": i.line}
                    for i in r.issues
                ],
            }
            for rel, r in rows.items()
        },
        "hex": payload.hex(),
    }


def fseg_vector() -> dict:
    manifest = {
        "decisions/a.md": FileState(content_hash="c" * 64, size=120, mtime_ns=1_700_000_000_000_000_001),
        "z.md": FileState(content_hash="d" * 64, size=0, mtime_ns=0),
    }
    writer = Writer()
    writer.u32(1)  # _MANIFEST_FORMAT_VERSION
    writer.u32(len(manifest))
    for rel, state in manifest.items():
        writer.text(rel)
        writer.u64(state.size)
        writer.u64(state.mtime_ns)
        writer.text(state.content_hash)
    payload = encode_segment(writer.payload)
    return {
        "rows": {
            rel: {"content_hash": s.content_hash, "size": s.size, "mtime_ns": s.mtime_ns}
            for rel, s in manifest.items()
        },
        "hex": payload.hex(),
    }


def main() -> None:
    import os

    os.chdir(REPO)  # relative corpus paths are part of the golden bytes
    vectors = {
        "_comment": "GENERATED by rust/spec/gen_vectors_index.py — do not edit. Oracle store goldens over the pinned fixture corpora.",
        "scoring_fingerprint": scoring_fingerprint(),
        "bundle_version": SCHEMA_VERSION,
        "corpora": {name: corpus_vectors(rel, raw=True) for name, rel in CORPORA.items()},
        "vseg": vseg_vector(),
        "fseg": fseg_vector(),
        "manifest_root_key": {
            "note": "manifest_root_key resolves the directory then hashes '<resolved>\\0<mode>'; probe pair for a stable absolute path.",
            "directory": "/nonexistent/probe-root",
            "recursive": manifest_root_key("/nonexistent/probe-root", recursive=True),
            "top_level": manifest_root_key("/nonexistent/probe-root", recursive=False),
        },
    }
    OUT.write_text(json.dumps(vectors, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    total = sum(len(c["segments"]) for c in vectors["corpora"].values())
    print(f"wrote {OUT} ({total} segment goldens)")


if __name__ == "__main__":
    main()
