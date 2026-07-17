#!/usr/bin/env python3
"""Differential proof for the batched git-recency join (COUNCIL-REVIEW B1 step 2).

The native engine, on a *linear* history, answers the ADR-045 recency join from a
single `git log --name-only` pass instead of one `git log -1 -- <path>` spawn per
path (rac-engine `gitinfo::batched_recency`). This tool proves that swap is
byte-identical to the per-path oracle semantics for BOTH fields, over every
tracked file in the repo:

  last_committed  == `git log -1 --format=%cI -- <path>`         (newest touch)
  first_committed == `git log --reverse --format=%cI -- <path>`  (oldest touch)

It exits non-zero on any divergence. On a history that contains a merge commit
the batched pass is not used (an evil merge can make a whole-history walk
disagree with per-path simplification), so this tool asserts the linear-history
invariant and skips the batched comparison with a notice when merges are present
— matching the engine's own gate.

Usage:  python3 rust/tools/recency_batch_diff.py [REPO_ROOT]
        (REPO_ROOT defaults to this checkout's root)
"""
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]


def git(args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def per_path_last(paths):
    out = {}
    for p in paths:
        r = git(["log", "-1", "--format=%cI", "--", p])
        out[p] = r.stdout.strip() or None
    return out


def per_path_first(paths):
    out = {}
    for p in paths:
        r = git(["log", "--reverse", "--format=%cI", "--", p])
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        out[p] = lines[0] if lines else None
    return out


def batched():
    """One newest-first pass: last = first-seen date, first = last-seen (oldest).
    \x01 marks a %cI record; -z NUL-separates records and file names (no quoting);
    the first file after a commit carries a leading \\n to strip."""
    r = git(["-c", "core.quotePath=false", "log", "-z", "--format=\x01%cI", "--name-only"])
    last, first = {}, {}
    cur = None
    for tok in r.stdout.split("\x00"):
        if tok.startswith("\x01"):
            cur = tok[1:].strip()
        else:
            path = tok.lstrip("\n")
            if path:
                if path not in last:
                    last[path] = cur
                first[path] = cur
    return last, first


def main():
    if git(["rev-parse", "--show-toplevel"]).returncode != 0:
        sys.exit(f"{REPO} is not a git work tree")
    merges = git(["rev-list", "--merges", "--max-count=1", "HEAD"]).stdout.strip()
    if merges:
        print(f"NOTE: history has merge commit(s) (e.g. {merges[:12]}); the engine "
              "uses per-path here, batched comparison skipped.")
        return

    # -z + core.quotePath=false yields RAW, unquoted names — the same key space
    # batched() uses. With default quoting a non-ASCII name would be octal-quoted
    # here but raw in the batched map, so both lookups miss and the file is
    # compared None==None (a vacuous pass that masks a real divergence).
    paths = [p for p in git(["-c", "core.quotePath=false", "ls-files", "-z"]).stdout.split("\x00") if p]
    print(f"linear history; tracked files: {len(paths)}")

    t0 = time.time(); base_last = per_path_last(paths); t_pp = time.time() - t0
    base_first = per_path_first(paths)
    t0 = time.time(); b_last, b_first = batched(); t_b = time.time() - t0

    mism = []
    for p in paths:
        if base_last[p] != b_last.get(p):
            mism.append(("last", p, base_last[p], b_last.get(p)))
        if base_first[p] != b_first.get(p):
            mism.append(("first", p, base_first[p], b_first.get(p)))

    print(f"per-path:  {t_pp:.2f}s ({len(paths)} spawns)")
    print(f"batched:   {t_b:.3f}s (1 spawn)  ->  {t_pp / max(t_b, 1e-6):.0f}x")
    print(f"mismatches (last+first over {len(paths)} files): {len(mism)}")
    for kind, p, want, got in mism[:25]:
        print(f"  DIVERGE[{kind}] {p!r}: per-path={want!r} batched={got!r}")
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
