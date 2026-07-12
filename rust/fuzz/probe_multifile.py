#!/usr/bin/env python3
"""Directed multi-file corpus probes — exercises cross-file relationship
resolution, ambiguity, walk order, and dot-dir skipping, which the
single-file random campaign cannot reach.

Each case is a dict of relpath -> content; the whole 6-command dir matrix
runs on both engines and stdout bytes + exit codes are compared.

Usage: python3 rust/fuzz/probe_multifile.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import difffuzz  # noqa: E402

ID_A = "RAC-KTQ63DPSMF19"
ID_B = "RAC-KTQ63DPT6008"
ID_C = "RAC-KTQ63DPVVB37"

REQ = """---
schema_version: 1
id: {id}
type: requirement
{rel}---
# Req {name}

## Problem

P.

## Requirements

- The system SHALL work.
"""

DEC = """---
schema_version: 1
id: {id}
type: decision
{rel}---
# ADR-{n} Dec {name}

## Status

Accepted

## Context

C.

## Decision

D.

## Consequences

- One.
"""


def req(id_, name, rel=""):
    return REQ.format(id=id_, name=name, rel=rel)


def dec(id_, name, n="001", rel=""):
    return DEC.format(id=id_, name=name, n=n, rel=rel)


CASES = [
    ("resolves", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B}]\n"),
        "b.md": dec(ID_B, "B"),
    }),
    ("dangling", {
        "a.md": req(ID_A, "A", "relationships:\n  implements: [RAC-KTQ63DQZZZZZ]\n"),
    }),
    ("ambiguous-id", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B}]\n"),
        "b1.md": dec(ID_B, "B1"),
        "b2.md": dec(ID_B, "B2", n="002"),
    }),
    ("case-normalized-target", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B.lower()}]\n"),
        "b.md": dec(ID_B, "B"),
    }),
    ("unknown-kind", {
        "a.md": req(ID_A, "A", f"relationships:\n  frobnicates: [{ID_B}]\n"),
        "b.md": dec(ID_B, "B"),
    }),
    ("dup-targets", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B}, {ID_B}]\n"),
        "b.md": dec(ID_B, "B"),
    }),
    ("self-reference", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_A}]\n"),
    }),
    ("chain-and-fanout", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B}]\n  supersedes: [{ID_C}]\n"),
        "b.md": dec(ID_B, "B"),
        "c.md": dec(ID_C, "C", n="003"),
    }),
    ("dot-dir-skipped", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B}]\n"),
        ".hidden/b.md": dec(ID_B, "B"),
    }),
    ("markdown-ext-ignored", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B}]\n"),
        "b.markdown": dec(ID_B, "B"),
    }),
    ("subdir-order", {
        "z.md": req(ID_A, "Z"),
        "sub/a.md": dec(ID_B, "SA"),
        "sub2/b.md": dec(ID_C, "SB", n="004"),
    }),
    ("unicode-filenames", {
        "é.md": req(ID_A, "E-acute"),
        "é.md": dec(ID_B, "E-combining"),
        "Zü.md": dec(ID_C, "Zu", n="005"),
    }),
    ("non-id-target-passthrough", {
        "a.md": req(ID_A, "A", "relationships:\n  implements: ['  not an id ']\n"),
    }),
    ("invalid-artifact-still-indexed", {
        "a.md": req(ID_A, "A", f"relationships:\n  implements: [{ID_B}]\n"),
        "b.md": "---\nschema_version: 1\nid: " + ID_B + "\ntype: decision\n---\n# ADR-x B\n",
    }),
    ("empty-dir-nested", {
        "sub/.keep.md": "",
        "a.md": req(ID_A, "A"),
    }),
    ("duplicate-legacy-titles", {
        "a.md": "# ADR-007 First\n\n## Status\n\nAccepted\n\n## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\n- x.\n",
        "b.md": "# ADR-007 Second\n\n## Status\n\nAccepted\n\n## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\n- x.\n",
        "c.md": req(ID_A, "C", "relationships:\n  implements: [ADR-007]\n"),
    }),
]

DIR_COMMANDS = [
    ("validate-dir", ["validate", "corpus"]),
    ("validate-dir-json", ["validate", "corpus", "--json"]),
    ("validate-dir-sarif", ["validate", "corpus", "--sarif"]),
    ("relationships", ["relationships", "corpus"]),
    ("relationships-json", ["relationships", "corpus", "--json"]),
    ("relationships-validate", ["relationships", "corpus", "--validate"]),
    ("relationships-validate-json", ["relationships", "corpus", "--validate", "--json"]),
    ("relationships-validate-sarif", ["relationships", "corpus", "--validate", "--sarif"]),
    ("stats-dir", ["stats", "corpus"]),
    ("stats-dir-json", ["stats", "corpus", "--json"]),
]


def main():
    oracle = difffuzz.DEFAULT_ORACLE
    engine = difffuzz.DEFAULT_ENGINE
    workdir = tempfile.mkdtemp(prefix="mfprobe-")
    env = difffuzz.parity_env(os.path.join(workdir, "xdg"))
    outdir = os.path.join(difffuzz.FUZZ_DIR, "findings", "multifile-probe")
    n_div = 0
    for name, files in CASES:
        case_dir = os.path.join(workdir, "case")
        shutil.rmtree(case_dir, ignore_errors=True)
        os.makedirs(os.path.join(case_dir, "corpus"))
        for rel, content in files.items():
            p = os.path.join(case_dir, "corpus", rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(content.encode("utf-8"))
        bad = []
        for cmd_name, argv in DIR_COMMANDS:
            ea, oa = difffuzz.run_engine(oracle, argv, case_dir, env)
            eb, ob = difffuzz.run_engine(engine, argv, case_dir, env)
            if ea != eb or oa != ob:
                bad.append((cmd_name, argv, ea, eb, oa, ob))
        if bad:
            n_div += 1
            fdir = os.path.join(outdir, name)
            os.makedirs(fdir, exist_ok=True)
            for rel, content in files.items():
                p = os.path.join(fdir, "corpus", rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as fh:
                    fh.write(content.encode("utf-8"))
            with open(os.path.join(fdir, "DIVERGENCE.md"), "w") as fh:
                fh.write(f"# multifile probe: {name}\n\n")
                for cmd_name, argv, ea, eb, oa, ob in bad:
                    off = difffuzz.first_diff(oa, ob)
                    fh.write(f"## {cmd_name} (`rac {' '.join(argv)}`)\n\n"
                             f"- exit: oracle={ea} rust={eb}\n"
                             f"- stdout bytes: oracle={len(oa)} rust={len(ob)}\n"
                             f"- first diff offset: {off}\n\n")
                    difffuzz.write(os.path.join(fdir, f"{cmd_name}.oracle.stdout"), oa)
                    difffuzz.write(os.path.join(fdir, f"{cmd_name}.rust.stdout"), ob)
            print(f"DIVERGE {name}: {[b[0] for b in bad]}")
        else:
            print(f"ok      {name}")
    shutil.rmtree(workdir, ignore_errors=True)
    print(f"{n_div}/{len(CASES)} multi-file cases diverged")


if __name__ == "__main__":
    main()
