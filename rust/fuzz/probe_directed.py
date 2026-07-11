#!/usr/bin/env python3
"""Directed differential probes for landmine classes the random operators
do not generate: explicit YAML tags, out-of-range timestamps, beyond-i64
integers, float-overflow spellings, NUL/escape edges.

Reuses difffuzz's engine-pair machinery and findings filing. Each probe is a
named full-file input run through the same 9-command matrix.

Usage: python3 rust/fuzz/probe_directed.py [--findings DIR]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import difffuzz  # noqa: E402

FM = "---\nschema_version: 1\nid: RAC-KTQ63DPSMF19\ntype: decision\n{extra}---\n"
BODY = "# ADR-999 Probe\n\n## Status\n\nAccepted\n\n## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\n- One.\n"


def fm(extra):
    return (FM.format(extra=extra) + BODY).encode()


PROBES = [
    # explicit tags (SafeConstructor set + mismatches that crash the oracle)
    ("tag-int-empty", fm("x: !!int ''\n")),
    ("tag-int-bad", fm("x: !!int banana\n")),
    ("tag-float-bad", fm("x: !!float banana\n")),
    ("tag-bool-bad", fm("x: !!bool banana\n")),
    ("tag-binary", fm("x: !!binary aGk=\n")),
    ("tag-binary-bad", fm("x: !!binary '@@@'\n")),
    ("tag-timestamp-oob", fm("x: !!timestamp 2026-13-01\n")),
    ("tag-set", fm("x: !!set {a, b}\n")),
    ("tag-omap", fm("x: !!omap [{a: 1}]\n")),
    ("tag-pairs", fm("x: !!pairs [{a: 1}]\n")),
    ("tag-str-date", fm("x: !!str 2026-07-11\n")),
    ("tag-seq-on-scalar", fm("x: !!seq a\n")),
    ("tag-map-on-scalar", fm("x: !!map a\n")),
    # out-of-range plain timestamps (resolver matches, constructor raises)
    ("date-month-13", fm("x: 2026-13-01\n")),
    ("date-feb-30", fm("x: 2026-02-30\n")),
    ("date-day-00", fm("x: 2026-01-00\n")),
    ("date-year-0000", fm("x: 0000-01-01\n")),
    ("ts-hour-25", fm("x: 2026-01-01T25:00:00Z\n")),
    ("ts-tz-99", fm("x: 2026-01-01T10:00:00+99:00\n")),
    # beyond-i64 integers (Rust Int(i64) seam; Python is bignum)
    ("bigint-schema-version", fm("schema_version: 99999999999999999999\n").replace(b"schema_version: 1\n", b"")),
    ("bigint-unknown-field", fm("x: 99999999999999999999\n")),
    ("bigint-i64-max", fm("x: 9223372036854775807\n")),
    ("bigint-i64-max-plus-1", fm("x: 9223372036854775808\n")),
    ("bigint-i64-min", fm("x: -9223372036854775808\n")),
    ("bigint-i64-min-minus-1", fm("x: -9223372036854775809\n")),
    ("bigint-hex-over", fm("x: 0xFFFFFFFFFFFFFFFFFF\n")),
    ("bigint-sexagesimal-over", fm("x: 99999999999999999:30\n")),
    ("bigint-tags", fm("tags: [99999999999999999999]\n").replace(b"tags: 1\n", b"")),
    ("bigint-id", fm("").replace(b"id: RAC-KTQ63DPSMF19", b"id: 99999999999999999999")),
    # float edges
    ("float-overflow", fm("x: 1.0e+400\n")),
    ("float-tiny", fm("x: 1.0e-400\n")),
    ("float-neg-zero", fm("x: -0.0\n")),
    ("float-sexagesimal", fm("x: 190:20:30.15\n")),
    ("float-underscores", fm("x: 685_230.15\n")),
    # unhashable-key variants (oracle crash class)
    ("key-flow-map", fm("{a: 1}: v\n")),
    ("key-explicit-empty-seq", fm("? []\n: v\n")),
    ("key-explicit-map", fm("? {}\n: v\n")),
    ("key-set-tag", fm("!!set {a}: v\n")),
    # reader / escape edges
    ("nul-byte", fm("x: a\x00b\n")),
    ("del-char", fm("x: a\x7fb\n")),
    ("c1-control", fm("x: a\x85b\n")),
    ("dq-escapes", fm('x: "\\x41\\u0041\\U00000041\\e\\0\\N{}\\_"\n'.replace("{}", ""))),
    ("dq-bad-escape", fm('x: "\\q"\n')),
    ("sq-doubled", fm("x: 'it''s'\n")),
    # schema_version spellings of 1
    ("sv-hex-1", fm("").replace(b"schema_version: 1", b"schema_version: 0x1")),
    ("sv-octal-1", fm("").replace(b"schema_version: 1", b"schema_version: 01")),
    ("sv-sexagesimal", fm("").replace(b"schema_version: 1", b"schema_version: 1:30")),
    ("sv-bool", fm("").replace(b"schema_version: 1", b"schema_version: yes")),
    ("sv-float", fm("").replace(b"schema_version: 1", b"schema_version: 1.0")),
    ("sv-neg", fm("").replace(b"schema_version: 1", b"schema_version: -1")),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", default=difffuzz.DEFAULT_FINDINGS)
    ap.add_argument("--oracle", default=difffuzz.DEFAULT_ORACLE)
    ap.add_argument("--engine", default=difffuzz.DEFAULT_ENGINE)
    ap.add_argument("--workdir", default=None)
    args = ap.parse_args()
    args.log = os.path.join(os.path.dirname(args.findings), "probe.log")
    fz = difffuzz.Fuzzer(args)
    worker = fz.worker0
    n_div = 0
    for name, data in PROBES:
        worker.set_aux([])
        hits = fz.check_all(worker, data, difffuzz.CORE_COMMANDS)
        if hits:
            n_div += 1
            for spec, detail, triage in hits:
                slug, t = fz.file_finding(f"probe={name}", data, [name], spec, detail, triage)
                print(f"DIVERGE {name}: cmd={spec['name']} [{t}] -> {slug or 'duplicate-signature'}")
        else:
            print(f"ok      {name}")
    print(f"{n_div}/{len(PROBES)} probes diverged")


if __name__ == "__main__":
    main()
