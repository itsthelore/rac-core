#!/usr/bin/env python3
"""Generate walk-order test vectors from the oracle (`asdecided.core.fs`).

Builds several tricky temp trees (nested dirs, dash-vs-slash sort traps, hidden
dirs/files, symlinks, uppercase .MD vs .md), runs the SAME code path the CLI
uses (`find_markdown_files`), and dumps the walk order as paths RELATIVE to each
tree root. The tree structure is recorded alongside so the Rust test recreates
an identical tree in its own tempdir and replays.

Deterministic: tree structures are fixed; only relative expected order is
committed (portable across machines / temp locations).

Run with the oracle venv:
    .venv-oracle/bin/python rust/spec/gen_vectors_walk.py
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from asdecided.core.fs import find_markdown_files

OUT = Path(__file__).resolve().parents[1] / "rac-engine/tests/vectors/walk.json"


# Each case: dirs to create, files to create (empty), symlinks (target is
# relative to the link's parent dir), and whether the walk is recursive.
CASES = [
    {
        "name": "mixed_sort_and_exclusions",
        "recursive": True,
        "dirs": ["realdir", "sub", ".hidden"],
        "files": [
            "Z.md",            # uppercase sorts before lowercase
            "a.md",
            "b.md",
            "space file.md",   # space in name
            "sub-x.md",        # dash-vs-slash trap vs sub/c.md
            "sub.md",
            "sub0.md",
            "realdir/r.md",
            "sub/c.md",
            ".dotfile.md",     # hidden file -> excluded
            ".hidden/h.md",    # under hidden dir -> excluded
            "upper.MD",        # case-sensitive: excluded
            "x.Md",            # excluded
            "x.markdown",      # excluded (not .md)
            "plain.txt",       # excluded (not markdown)
        ],
        "symlinks": [
            {"link": "alink.md", "target": "a.md"},       # symlinked file: INCLUDED
            {"link": "linkdir", "target": "realdir"},      # symlinked dir: NOT descended
        ],
    },
    {
        "name": "component_wise_sort_trap",
        "recursive": True,
        # a/b.md vs a-b.md vs a.md — component-wise puts a/b.md first.
        "dirs": ["a", "a/deep"],
        "files": [
            "a-b.md",
            "a.md",
            "a/b.md",
            "a/deep/z.md",
            "a/deep/a.md",
            "a0.md",           # '0'(0x30) > '.'(0x2E) and > '-'(0x2D)
        ],
        "symlinks": [],
    },
    {
        "name": "nested_hidden_and_symlink_dir",
        "recursive": True,
        "dirs": ["docs", "docs/.git", "docs/sub", "target_dir"],
        "files": [
            "docs/one.md",
            "docs/.git/config.md",   # hidden dir component -> excluded
            "docs/sub/two.md",
            "target_dir/deep.md",
        ],
        "symlinks": [
            {"link": "docs/link_to_target", "target": "../target_dir"},  # not descended
            {"link": "docs/broken.md", "target": "nonexistent_file"},    # broken symlink FILE: included
        ],
    },
    {
        "name": "top_level_only",
        "recursive": False,
        "dirs": ["nested"],
        "files": [
            "top.md",
            "nested/inner.md",   # NOT reached: non-recursive
        ],
        "symlinks": [],
    },
]


def build_tree(root: Path, case: dict) -> None:
    for d in case["dirs"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    for f in case["files"]:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    for link in case["symlinks"]:
        linkpath = root / link["link"]
        linkpath.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(link["target"], linkpath)


# Root-arg normalization (`str(Path(arg))`, PORT-CONTRACT.d/09 §1.6). The
# per-artifact `path` prefix downstream is `str(root / rel)`, so the root arg is
# normalized first. These pin the documented cases and a few extras.
NORMALIZE_ARGS = [
    "rac/",
    "./rac/",
    "rac//",
    "rac/./x",
    "rac",
    ".",
    "",
    "/abs/path/",
    "//double/leading",
    "///triple",
    "a/../b",
    "a/b/../c",
    "./",
    "x/y/z",
]


def main() -> None:
    out_cases = []
    for case in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_tree(root, case)
            found = find_markdown_files(str(root), recursive=case["recursive"])
            expected = [str(p.relative_to(root)) for p in found]
        out_cases.append(
            {
                "name": case["name"],
                "recursive": case["recursive"],
                "dirs": case["dirs"],
                "files": case["files"],
                "symlinks": case["symlinks"],
                "expected": expected,
            }
        )

    normalize = [{"arg": a, "expected": str(Path(a))} for a in NORMALIZE_ARGS]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"cases": out_cases, "normalize": normalize}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({len(out_cases)} cases, {len(normalize)} normalize)")


if __name__ == "__main__":
    main()
