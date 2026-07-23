#!/usr/bin/env python3
"""Generate frontmatter conformance vectors from the oracle.

Drives `asdecided.core.frontmatter.split_frontmatter`, `_load_frontmatter_mapping`,
`parse_frontmatter`, and `asdecided.core.markdown.parse_file` over the full
PORT-CONTRACT.d/02 case matrix and dumps:

- split:   delimiter-rule cases (text -> raw/body/offset/unterminated)
- parse:   raw YAML -> tagged value model + metadata + issues, or the
           oracle's crash string (the Rust port maps those to its
           internal-oracle-divergence issue — PORT-CONTRACT decision 3)
- files:   byte-level parse_file cases (oversize/unreadable/lossy decode);
           temp paths are substituted with {PATH}
- env_cap: DECIDED_MAX_FILE_BYTES parsing table
- ids:     normalize_id / is_valid_id edge cases

Deterministic: fixed case lists; set encodings sorted by canonical JSON.

Run with the oracle venv:
    .venv-oracle/bin/python rust/spec/gen_vectors_frontmatter.py
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import tempfile
from pathlib import Path

from asdecided.core.frontmatter import (
    _load_frontmatter_mapping,
    parse_frontmatter,
    split_frontmatter,
)
from asdecided.core.limits import max_file_bytes
from asdecided.core.markdown import parse_file
from asdecided.core.metadata import is_valid_id, normalize_id

OUT = Path(__file__).resolve().parents[1] / "rac-engine/tests/vectors/frontmatter.json"


def canon(e) -> str:
    return json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def enc(v):
    if v is None:
        return {"t": "none"}
    if isinstance(v, bool):
        return {"t": "bool", "v": v}
    if isinstance(v, int):
        return {"t": "int", "v": str(v)}
    if isinstance(v, float):
        return {"t": "float", "v": repr(v)}
    if isinstance(v, str):
        return {"t": "str", "v": v}
    if isinstance(v, bytes):
        return {"t": "bytes", "v": list(v)}
    if isinstance(v, datetime.datetime):
        off = v.utcoffset()
        tz = None if off is None else int(off.total_seconds())
        return {
            "t": "datetime",
            "v": [v.year, v.month, v.day, v.hour, v.minute, v.second, v.microsecond],
            "tz": tz,
        }
    if isinstance(v, datetime.date):
        return {"t": "date", "v": [v.year, v.month, v.day]}
    if isinstance(v, tuple):
        return {"t": "tuple", "v": [enc(x) for x in v]}
    if isinstance(v, list):
        return {"t": "list", "v": [enc(x) for x in v]}
    if isinstance(v, dict):
        return {"t": "map", "v": [[enc(k), enc(val)] for k, val in v.items()]}
    if isinstance(v, set):
        return {"t": "set", "v": sorted((enc(x) for x in v), key=canon)}
    raise TypeError(f"unencodable {type(v)}")


def enc_issue(i):
    return [i.severity, i.code, i.message, i.line]


def enc_meta(m):
    if m is None:
        return None
    return {
        # str: schema_version can be a Python bignum beyond i64/JSON numbers.
        "schema_version": str(m.schema_version),
        "id": m.id,
        "type": m.type,
        "relationships": [[k, list(v)] for k, v in m.relationships.items()],
        "tags": list(m.tags),
        "provenance": m.provenance,
    }


# ---------------------------------------------------------------------------
# split cases
# ---------------------------------------------------------------------------

SPLIT_TEXTS = [
    "---\na: 1\n---\nbody",
    "---\na: 1\n...\nbody",
    "---\n---",
    "---",
    "---\na: 1\nbody",
    "",
    "﻿---\na: 1\n---\nbody",
    "​---\na: 1\n---\nbody",
    "---\r\na: 1\r\n---\r\nbody\r\n",
    " ---\na: 1\n ... \nbody",
    "\t---\t\na: 1\n\t---\nbody",
    "\xa0---\xa0\na: 1\n\xa0...\nbody",
    "\x0b---\na: 1\n\x1c---\x1f\nbody",
    "\x85---\na: 1\n---\nbody",
    "----\na: 1\n---\nbody",
    "--- yaml\na: 1\n---\nbody",
    "\n---\na: 1\n---\nbody",
    "body only\nno frontmatter",
    "---\n---\nbody\n---\nmore",
    "---\n...\n",
    "---\na: 1\n----\n---\nbody",
    "---\n\n---\n",
    "---\na: 1\n --- \nbody line 1\nbody line 2",
    "--\na: 1\n---",
    "...\na: 1\n---",
    "---\na: 1",
    "---\n",
    "---\r\n---\r",
    "--- \na: 1\n---",  # U+2028 is str.strip() whitespace
    "---\na: |\n  ---\n...\nbody",
]

# ---------------------------------------------------------------------------
# parse cases (raw frontmatter YAML)
# ---------------------------------------------------------------------------


def scalar_cases():
    scalars = [
        # bools (and near-bools)
        "yes", "Yes", "YES", "no", "No", "NO", "true", "True", "TRUE",
        "false", "False", "FALSE", "on", "On", "ON", "off", "Off", "OFF",
        "y", "n", "Y", "N", "yEs", "tRue", "oN", "yes ", " yes",
        # null spellings
        "~", "null", "Null", "NULL", "", "none", "NoNe", "nul",
        # ints
        "0", "-0", "+5", "-7", "123", "1_000", "010", "0o10", "0x1F", "0X1F",
        "0x_", "0b101", "0b_1_0", "0_", "00", "09", "1:30", "1:30:30", "-1:30",
        "+1:2", "1:60", "1:5_9", "190:20", "0x", "0b", "1__0", "_1", "1_",
        # floats
        ".inf", "-.Inf", "+.INF", ".nan", ".NaN", ".NAN", "-.nan", "6.", "6.0",
        "-0.0", "0.", ".5", "1_0.5", "1:30.0", "1:30.5", "-1:30.", "3.14159",
        "1.5e+3", "1.5E-3", "1e5", "1e+5", "1.e+5", ".5e+3", "1.5e3", "6.02e+23",
        "9999999999999999999999.0", "1.5e+310", "inf", "nan", "Infinity",
        "0.0.0", "1.2.3",
        # timestamps
        "2026-07-11", "2026-7-1", "2026-07-11T10:00:00Z", "2026-07-11t10:00:00z",
        "2026-07-11 10:00:00", "2026-07-11 10:00:00.5", "2026-07-11 10:00:00.123456789",
        "2026-07-11 10:00:00 +05:30", "2026-07-11 10:00:00-05:00",
        "2026-07-11T10:00:00+0:00", "2026-07-11 \t 10:00:00 \t Z",
        "2026-07-11T1:02:03", "0001-01-01", "9999-12-31", "2024-02-29",
        "2026-07-11T10:00:00.5Z", "2026-07-1110:00:00", "2026-07-11 10:00",
        "2026:07:11", "20260711",
        # strings and unicode
        "hello", "hello world", "héllo", "ß", "日本語", "�repl",
        "it's", 'say "hi"', "back\\slash", "a#b", "x@y", "e`f",
        "-", "?", ":", "-x", "?x", ":x", "a:b", "a: b#c", "<x>", "<<x", "=x", "=",
        "<<",
    ]
    return [f"k: {s}" if s else "k:" for s in scalars]


def key_cases():
    keys = [
        "0x1F", "010", "1:30", ".inf", ".nan", "6.", "1e5", "2026-07-11",
        "2026-07-11 10:00:00Z", "2026-07-11 10:00:00 +05:30",
        "2026-07-11 10:00:00-05:00", "2026-07-11 10:00:00.25",
        "yes", "Off", "~", "null", "y", "n", "9", "-3", "+4", "1_2",
        "true", "wörd", "it's", 'quo"te', "space key", "ß",
    ]
    return [f"{k}: 1" for k in keys] + ["? explicit\n: 1", ": novalue", "?" ]


PARSE_CASES = (
    scalar_cases()
    + key_cases()
    + [
        # structure
        "schema_version: 1",
        "schema_version: 1\nid: rac-ktq63dpsmf19\ntype: decision\nrelationships:\n  implements:\n    - RAC-KTQ63DPSMF19\ntags:\n  - alpha\n  - ' Beta '",
        "schema_version: 0x1",
        "schema_version: 01",
        "schema_version: +1",
        "schema_version: 1_0",
        "schema_version: 1:30",
        "schema_version: 2",
        "schema_version: 90",
        "schema_version: -1",
        "schema_version: 1.0",
        "schema_version: '1'",
        "schema_version: yes",
        "schema_version: true",
        "schema_version: null",
        "schema_version:",
        "schema_version: [1]",
        "schema_version: {v: 1}",
        "id: RAC-KTQ63DPSMF19\nschema_version: 1",
        "id: rac-ktq63dpsmf19\nschema_version: 1",
        "id: '  rac-ktq63dpsmf19  '\nschema_version: 1",
        "id: RAC-KTQ63DPSMFI9\nschema_version: 1",
        "id: RAC-KTQ63DPSMF1\nschema_version: 1",
        "id: RAC-KTQ63DPSMF199\nschema_version: 1",
        "id: R-KTQ63DPSMF19\nschema_version: 1",
        "id: RABCDEFGHIJ-KTQ63DPSMF19\nschema_version: 1",
        "id: 9AC-KTQ63DPSMF19\nschema_version: 1",
        "id: rac_KTQ63DPSMF19\nschema_version: 1",
        "id: 5\nschema_version: 1",
        "id: null\nschema_version: 1",
        "id: 2026-07-11\nschema_version: 1",
        "id: [x]\nschema_version: 1",
        "id: \"RAC-KTQ63DPSMF19\\n\"\nschema_version: 1",
        "id: \"rac-ktq63dpsmf19\\u00a0\"\nschema_version: 1",
        "id: \"ßAC-KTQ63DPSMF19\"\nschema_version: 1",
        "type: decision\nschema_version: 1",
        "type: requirement\nschema_version: 1",
        "type: roadmap\nschema_version: 1",
        "type: prompt\nschema_version: 1",
        "type: design\nschema_version: 1",
        "type: Decision\nschema_version: 1",
        "type: banana\nschema_version: 1",
        "type: 5\nschema_version: 1",
        "type: null\nschema_version: 1",
        "type: [decision]\nschema_version: 1",
        "type: 2026-07-11\nschema_version: 1",
        "relationships: {}\nschema_version: 1",
        "relationships: null\nschema_version: 1",
        "relationships:\nschema_version: 1",
        "relationships: []\nschema_version: 1",
        "relationships: flat\nschema_version: 1",
        "relationships:\n  implements: RAC-KTQ63DPSMF19\nschema_version: 1",
        "relationships:\n  implements:\n    - RAC-KTQ63DPSMF19\n    - '  not an id '\nschema_version: 1",
        "relationships:\n  implements:\n    - 2026-07-11\nschema_version: 1",
        "relationships:\n  implements:\n    - 5\nschema_version: 1",
        "relationships:\n  5:\n    - RAC-KTQ63DPSMF19\nschema_version: 1",
        "relationships:\n  implements: []\n  depends_on:\n    - a\n    - a\nschema_version: 1",
        "tags: []\nschema_version: 1",
        "tags: null\nschema_version: 1",
        "tags:\nschema_version: 1",
        "tags: [' Alpha ', beta]\nschema_version: 1",
        "tags: ['']\nschema_version: 1",
        "tags: [' ']\nschema_version: 1",
        "tags: [\"\\u00a0\"]\nschema_version: 1",
        "tags: [5]\nschema_version: 1",
        "tags: [2026-07-11]\nschema_version: 1",
        "tags: {a: 1}\nschema_version: 1",
        "tags: tag\nschema_version: 1",
        # unknown fields / ordering
        "zzz: 1\naaa: 2\nschema_version: 1",
        "zzz: 1",
        "2: x\ntrue: y\nnull: z\n2026-07-11: w",
        "we're: 1",
        'has"quote: 1',
        "Schema_Version: 1",
        "schema_version : 1",
        " schema_version: 1",
        # duplicates (Python-equality classes)
        "a: 1\na: 2",
        "'a': 1\na: 2",
        "\"a\": 1\na: 2",
        "1: a\ntrue: b",
        "1: a\n1.0: b",
        "yes: a\non: b",
        "0: a\nfalse: b",
        "0: a\n-0.0: b",
        "a: 1\nA: 2",
        ".nan: 1\n.nan: 2",
        ".nan: 1\n.NaN: 2",
        "it's: 1\nit's: 2",
        "a:\n  b: 1\n  b: 2",
        "x: {a: 1, a: 2}",
        "[{a: 1, a: 2}]",
        "2026-07-11: 1\n2026-07-11: 2",
        "~: 1\nnull: 2",
        "1_0: a\n10: b",
        "0x10: a\n16: b",
        "a: 1\nb: 2\na: 3",
        # anchors and aliases
        "a: &x 1\nb: *x",
        "a: &x 1\nb: 2",
        "a: &x 1\nb: &x 2",
        "a: &x 1\nb: &y 2",
        "*x: 1",
        "a: *nowhere",
        "&m\na: 1",
        # merge / value keys
        "<<: {a: 1}",
        "base: &b {x: 1}\nmerged:\n  <<: *b",
        "a:\n  <<: {x: 1}\n  y: 2",
        "=: 1",
        "a: =",
        "a: <<",
        # explicit tags
        "a: !!str 2026-07-11",
        "a: !!str 1",
        "a: !!int 010",
        "a: !!int '1:30'",
        "a: !!float '1.5'",
        "a: !!float inf",
        "a: !!bool 'yes'",
        "a: !!null ''",
        "a: !!timestamp 2026-7-1",
        "a: !!timestamp '2026-07-11 10:00:00'",
        "a: !!binary aGk=",
        "a: !!binary 'aGVsbG8gd29ybGQ='",
        "a: !!binary aGk",
        "a: !!binary 'a'",
        "a: !!binary ''",
        "a: !!seq [1, 2]",
        "a: !!map {b: 1}",
        "a: !!set {x, y}",
        "a: !!set {x: 1, y: 2}",
        "a: !!omap [{k: v}, {k2: v2}]",
        "a: !!pairs [{k: v}, {k: v2}]",
        "a: !!omap [x]",
        "a: !!omap [{k: v, k2: v2}]",
        "a: !!omap x",
        "a: !!python/object {}",
        "a: !foo bar",
        "a: !<x> y",
        "a: ! 123",
        "a: !!str",
        "!!str k: 1",
        "a: !!str [1]",
        "a: !!seq {x: 1}",
        # flow collections
        "a: [1, 2, 3]",
        "a: {b: 1, c: 2}",
        "a: [1, [2, [3]]]",
        "a: {b: {c: {d: 1}}}",
        "a: [1, 2",
        "a: {b: 1",
        "a: [1,, 2]",
        "a: [1 2]",
        "a: {b 1}",
        "a: ]",
        "a: [,]",
        "a: {,}",
        "[1, 2]: x",
        "{b: 1}: x",
        "a: [x, {y: [z]}, ~]",
        "a: {? k}",
        "a: [? k]",
        # block structure and errors
        "a:\n  b: 1\n  c: 2",
        "a:\n- 1\n- 2",
        "a:\n  - 1\n  - 2",
        "- a\n- b",
        "just a scalar",
        "'quoted scalar'",
        "# only a comment",
        "  \n \n",
        "a: b:\n c",
        "a:\n\tb: 1",
        "\ta: 1",
        "a: 1\n b: 2",
        "a: 1\nb",
        "a: 1\n- b",
        "? complex\n: value\nsimple: 2",
        "a: |\n  line1\n  line2",
        "a: |+\n  line1\n\n",
        "a: |-\n  line1\n",
        "a: |2\n    indented",
        "a: |0\n  x",
        "a: |x\n  x",
        "a: >\n  fold1\n  fold2\n\n  para2",
        "a: >-\n  fold1\n  fold2",
        "a: 'single''quote'",
        "a: 'unterminated",
        'a: "double\\nescape"',
        'a: "\\x41\\u00e9\\U0001F600"',
        'a: "\\q"',
        'a: "\\x4"',
        'a: "\\u12"',
        'a: "unterminated',
        'a: "trail\\',
        "a: \"tab\\there\"",
        "multi: line\n  plain\n  scalar",
        "multi: line\n\n  with blank",
        "%YAML 1.2\na: 1",
        "%YAML 1.2\nfoo",
        "%YAML 1.1\n---\na: 1",
        "%YAML 2.0\n---\na: 1",
        "%YAML 1.2\n%YAML 1.1\n---\na: 1",
        "%TAG !e! tag:example.com,2000:\n---\ne: 1",
        "%TAG !e! tag:example.com,2000:\n%TAG !e! tag:other.com,2000:\n---\ne: 1",
        "%FOO bar\n---\na: 1",
        "%YAML\na: 1",
        "%YAML 1\na: 1",
        "%YAML x\na: 1",
        "a: 1\n--- foo",
        "a: 1\n...",
        "a: 1\n...\nb: 2",
        "--- {a: 1}",
        "a: 1\n%FOO",
        # depth cap geometry (root map d1)
        "a: " + "[" * 30 + "1" + "]" * 30,
        "a: " + "[" * 31 + "1" + "]" * 31,
        "a: " + "[" * 29 + "1" + "]" * 29,
        "a:\n" + "\n".join("  " * (i + 1) + "k:" for i in range(30)) + " 1",
        "a:\n" + "\n".join("  " * (i + 1) + "k:" for i in range(31)) + " 1",
        # wide but shallow never trips the cap
        "\n".join(f"k{i}: {i}" for i in range(60)),
        # NUL and control characters (ReaderError, full multi-line str)
        "a: \x00",
        "a: \x07",
        "a: \x1b",
        "\x7fa: 1",
        "a: ﻿x",
        "key�: �",
        # CRLF inside raw (split keeps \r; PyYAML treats CR as a break)
        "a: 1\r\nb: 2\r",
        "a: 1 b: 2",
        "a: 1 b: 2",
        "a: 1\x85b: 2",
        # oversize raw
        "k: " + "x" * 65531 + "\n",  # 65536 bytes -> passes cap
        "k: " + "x" * 65532 + "\n",  # 65537 bytes -> oversize
        "k: " + "é" * 32766,         # 65536 bytes (2-byte chars) -> passes
        "k: " + "é" * 32767,         # 65538 bytes -> oversize
        # beyond-i64 integers (fuzz finding 003: Python bignums, no overflow)
        "n: 9223372036854775806",
        "n: 9223372036854775807",   # i64::MAX
        "n: 9223372036854775808",   # i64::MAX + 1
        "n: -9223372036854775807",
        "n: -9223372036854775808",  # i64::MIN
        "n: -9223372036854775809",  # i64::MIN - 1
        "n: 18446744073709551615",  # u64::MAX
        "n: 18446744073709551616",  # u64::MAX + 1
        "n: " + "9" * 100,          # 100-digit
        "n: -" + "9" * 100,         # negative huge
        "n: 0xFFFFFFFFFFFFFFFFFF",  # hex huge
        "n: -0xFFFFFFFFFFFFFFFFFF",
        "n: 0777777777777777777777777",  # octal huge
        "n: 0b" + "1" * 70,         # binary huge
        "n: 99999999999999999999:30",  # sexagesimal huge
        "n: 1_000_000_000_000_000_000_0",
        "n: !!int '0xFF_FF_FFFFFFFFFFFFFF'",
        "n: !!int '9223372036854775808'",
        "schema_version: 99999999999999999999",
        "schema_version: -99999999999999999999",
        "schema_version: 9223372036854775808",
        # huge-int keys: Python-equality duplicate classes incl. vs float
        "10000000000000000000: a\n1e19: b",  # 1e19 resolves as str, no dup
        "99999999999999999999: a\n99999999999999999999: b",
        "10000000000000000000: a\n10000000000000000000.0: b",  # bigint == 1e19 float
        "10000000000000000000: a\n1.0e+19: b",                 # same, exp spelling
        "10000000000000000001: a\n10000000000000000000.0: b",  # off by one: no dup
        "9999999999999999999: a\n1e19: b",  # i64-range int vs str key
        # CPython 4300-digit int<->str conversion limit (oracle crashes)
        "n: " + "9" * 4300,
        "n: " + "9" * 4301,
        "n: -" + "9" * 4300,
        "a: !!int '" + "9" * 4301 + "'",
        "? 0x" + "F" * 3568 + "\n: x",  # 4295 decimal digits: repr fits
        "? 0x" + "F" * 3600 + "\n: x",  # repr over the limit: validate crash
        "schema_version: 0x" + "F" * 3600,
        "type: [0x" + "F" * 3600 + "]\nschema_version: 1",
        "? 0x" + "F" * 3600 + "\n: x\n? 0x" + "F" * 3600 + "\n: y",  # dup: load crash
        # !!map on non-mapping nodes (fuzz finding 002: `_no_duplicates`
        # iterates node.value with no type check — non-empty scalars and
        # sequences crash the oracle; empty ones reach the caught
        # ConstructorError)
        "!!map a",
        "k: !!map a",
        "k: !!map ''",
        "k: !!map []",
        "k: !!map [x]",
        "k: !!map [[x]]",
        "k: !!map [{a: 1}]",
        "? !!map xy\n: 1",
        "k: !!map |\n  text",
        "k: !!timestamp {=: 2026-07-11}",
        # oracle-crash catalog (recorded as crash strings)
        "? [1, 2]\n: x",
        "? {a: 1}\n: x",
        "? !!set {a}\n: x",
        "[a]: 1",
        "a: !!int ''",
        "a: !!int zz",
        "a: !!int '0x'",
        "a: !!bool xyz",
        "a: !!float zz",
        "a: !!float ''",
        "a: !!timestamp not-a-date",
        "a: 2026-13-01",
        "a: 2026-02-30",
        "a: 2024-02-30",
        "a: 0000-01-01",
        "a: 2026-07-11 25:00:00",
        "a: 2026-07-11 10:60:00",
        "a: 2026-07-11 10:00:61",
        "a: 2026-07-11 10:00:00 +99:00",
        "a: 2026-07-11 10:00:00 -25",
        # adversarial extras promoted from the differential fuzz batches
        "a: 1\rb: 2",
        "a: x\r  y\r  z",
        "a: |\r  x\r  y",
        "a: >\x85  x\x85\x85  y",
        "k: - 1 - 2",
        "a: 'q\r\n  w'",
        'a: "q    w"',
        "k" * 1025 + ": 1",
        "k" * 1024 + ": 1",
        "'" + "k" * 1100 + "': 1",
        "[" + "a" * 1100 + ": 1]",
        "a:\n- 1\n- - 2\n  - 3",
        "? |\n  bk\n: v",
        "?\n: v",
        "? a\n? b",
        "a: &x\nb: 2",
        "a: &x !!str y",
        "&a1 x: 1",
        "x: &a1\ny: *a1",
        'a: "\\\n   folded"',
        "a: 'x''y'''",
        "a: # comment\n  1",
        "a: x\n # deep comment\nb: 2",
        " a: 1\n b: 2",
        "  a: 1\n b: 2",
        "a\t: 1",
        "a:\t1",
        "%TAG ! !x-\n---\n!yy 1",
        "%TAG !! tag:z:\n---\n!!m {}",
        "! 1",
        "!<t> {a: 1}",
        "a: !<tag:yaml.org,2002:int> 5",
        "a: !!merge b",
        "<<: [{a: 1}, {b: 2}]",
        "k: !!set {<<: {a: 1}}",
        "k: !!set {=: 1}",
        "k: !!set {'x': 1, x: 2}",
        "k: >1\n x",
        "k: |\n\tx",
        "k: |9\n         x",
        "a: 'x' y",
        "a: [1: 2]",
        "a: [? 1]",
        "a: {1: 2: 3}",
        "- ? k\n  : v",
    ]
)

# ---------------------------------------------------------------------------
# parse_file cases (byte-level)
# ---------------------------------------------------------------------------

GOOD = b"---\nschema_version: 1\nid: rac-ktq63dpsmf19\n---\n# Title\n"

FILE_CASES = [
    {"name": "plain_ok", "bytes": GOOD, "env": None},
    {"name": "bom_defeats_frontmatter", "bytes": b"\xef\xbb\xbf" + GOOD, "env": None},
    {
        "name": "lossy_stray_bytes",
        "bytes": b"---\nschema_version: 1\nid: rac-ktq63dpsm\xff19\n---\nbody a\xff\xfe\xf0\x9f b\n",
        "env": None,
    },
    {
        "name": "lossy_truncated_multibyte",
        "bytes": b"---\nschema_version: 1\n---\na\xff\xfe\xf0\x9f b\n",
        "env": None,
    },
    {"name": "oversize_default_cap", "repeat": ["x", 1048576 + 1], "env": None},
    {"name": "at_default_cap", "repeat": ["x", 1048576], "env": None},
    {"name": "oversize_small_cap", "bytes": GOOD, "env": "16"},
    {"name": "at_small_cap", "bytes": b"0123456789abcdef", "env": "16"},
    {"name": "env_bad_falls_back", "bytes": GOOD, "env": "abc"},
    {"name": "env_negative_falls_back", "bytes": GOOD, "env": "-5"},
    {"name": "env_zero_falls_back", "bytes": GOOD, "env": "0"},
    {"name": "unterminated_block", "bytes": b"---\nschema_version: 1\nno close\n", "env": None},
    {"name": "crlf_file", "bytes": b"---\r\nschema_version: 1\r\n---\r\nbody\r\n", "env": None},
    {"name": "empty_file", "bytes": b"", "env": None},
    {"name": "missing_file", "bytes": None, "env": None},
    {"name": "directory", "bytes": b"", "env": None, "dir": True},
]

READ_CODES = ("artifact-oversize", "unreadable-artifact", "non-utf8-content")

# ---------------------------------------------------------------------------
# env cap and id tables
# ---------------------------------------------------------------------------

ENV_CAP_VALUES = [
    None, "abc", "", " ", "0", "-1", "1", "16", "65536", " 123 ", "1_0",
    "+9", "0x10", "12.5", "1e3", "\t2048\n", "999999999999",
    # CPython int() accepts non-ASCII Nd digits and Unicode whitespace
    # (fuzz campaign 2, finding 004 hardening).
    "٣٢", " ١٢٣ ", "1_000_000", "1__0", "_1", "1_",
    # just below the oracle read-crash zone: still a real cap
    "9223372036854775773",
]

ID_VALUES = [
    "RAC-KTQ63DPSMF19", "rac-ktq63dpsmf19", "  rac-ktq63dpsmf19  ",
    "RAC-KTQ63DPSMFI9", "RAC-KTQ63DPSMFL9", "RAC-KTQ63DPSMFO9", "RAC-KTQ63DPSMFU9",
    "R-KTQ63DPSMF19", "RA-KTQ63DPSMF19", "RABCDEFGHI-KTQ63DPSMF19",
    "RABCDEFGHIJ-KTQ63DPSMF19", "R2D2-KTQ63DPSMF19", "9AC-KTQ63DPSMF19",
    "RAC-KTQ63DPSMF1", "RAC-KTQ63DPSMF199", "RAC_KTQ63DPSMF19", "RAC-ktq63dpsmf19",
    "ßac-ktq63dpsmf19", "ﬁx-ktq63dpsmf19", "rac -ktq63dpsmf19",
    " rac-ktq63dpsmf19 ", "RAC-KTQ63DPSMF19\n", "RAC-KTQ63DPSMF19\nX",
    "RAC--KTQ63DPSMF19", "RAC-KTQ63DPSMF19-KTQ63DPSMF19", "AB-CD-KTQ63DPSMF19",
    "", "-KTQ63DPSMF19", "RAC-", "RAC-KTQ63DPSMF1️9",
]


def rle(text: str):
    """Run-length encode long single-char runs so committed vectors stay small.

    Returns [[chunk, count], ...]; decoding is concat(chunk * count).
    """
    out = []
    lit = []
    i = 0
    while i < len(text):
        j = i
        while j < len(text) and text[j] == text[i]:
            j += 1
        if j - i >= 100:
            if lit:
                out.append(["".join(lit), 1])
                lit = []
            out.append([text[i], j - i])
        else:
            lit.append(text[i:j])
        i = j
    if lit:
        out.append(["".join(lit), 1])
    return out


def gen_parse_case(raw: str):
    entry = {}
    if len(raw) > 2000:
        entry["raw_rle"] = rle(raw)
    else:
        entry["raw"] = raw
    try:
        data, load_issues = _load_frontmatter_mapping(raw)
    except Exception as e:  # noqa: BLE001 — oracle crash catalog
        entry["crash"] = f"{type(e).__name__}: {e}"
        return entry
    try:
        meta, issues = parse_frontmatter(raw)
    except Exception as e:  # noqa: BLE001 — validator-stage crash (the load
        # succeeded; e.g. the 4300-digit int->str limit while formatting a
        # field-issue message). The Rust port surfaces the marker from
        # parse_frontmatter only.
        entry["crash"] = f"{type(e).__name__}: {e}"
        entry["crash_stage"] = "validate"
        return entry
    if data is not None and len(raw) > 2000:
        # Skip the (huge) data echo for cap-boundary cases; issues/metadata
        # still pin the behavior.
        entry["data"] = {"t": "omitted"}
    else:
        entry["data"] = None if data is None else enc(data)
    entry["load_issues"] = [enc_issue(i) for i in load_issues]
    entry["metadata"] = enc_meta(meta)
    entry["issues"] = [enc_issue(i) for i in issues]
    return entry


def gen_file_case(case):
    old = os.environ.pop("DECIDED_MAX_FILE_BYTES", None)
    try:
        if case["env"] is not None:
            os.environ["DECIDED_MAX_FILE_BYTES"] = case["env"]
        data = case.get("bytes")
        if "repeat" in case:
            ch, n = case["repeat"]
            data = ch.encode("ascii") * n
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "artifact.md")
            if case.get("dir"):
                os.mkdir(path)
            elif data is not None:
                with open(path, "wb") as fh:
                    fh.write(data)
            product = parse_file(path)
            read_issues = [
                enc_issue(i) for i in product.parse_issues if i.code in READ_CODES
            ]
            out = {
                "name": case["name"],
                "bytes": None
                if data is None or "repeat" in case
                else base64.b64encode(data).decode("ascii"),
                "repeat": case.get("repeat"),
                "dir": bool(case.get("dir")),
                "env": case["env"],
                "read_issues": [
                    [s, c, m.replace(path, "{PATH}"), ln] for s, c, m, ln in read_issues
                ],
                "metadata": enc_meta(product.metadata),
                "metadata_issues": [enc_issue(i) for i in product.metadata_issues],
            }
            return out
    finally:
        os.environ.pop("DECIDED_MAX_FILE_BYTES", None)
        if old is not None:
            os.environ["DECIDED_MAX_FILE_BYTES"] = old


def gen_env_cap(value):
    old = os.environ.pop("DECIDED_MAX_FILE_BYTES", None)
    try:
        if value is not None:
            os.environ["DECIDED_MAX_FILE_BYTES"] = value
        return {"value": value, "expected": max_file_bytes()}
    finally:
        os.environ.pop("DECIDED_MAX_FILE_BYTES", None)
        if old is not None:
            os.environ["DECIDED_MAX_FILE_BYTES"] = old


def main() -> None:
    split_cases = []
    for text in SPLIT_TEXTS:
        s = split_frontmatter(text)
        split_cases.append(
            {
                "text": text,
                "raw": s.raw,
                "body": s.body,
                "line_offset": s.line_offset,
                "unterminated": s.unterminated,
            }
        )

    parse_cases = [gen_parse_case(raw) for raw in PARSE_CASES]
    file_cases = [gen_file_case(c) for c in FILE_CASES]
    env_cases = [gen_env_cap(v) for v in ENV_CAP_VALUES]
    id_cases = [
        {"value": v, "valid": is_valid_id(v), "normalized": normalize_id(v)}
        for v in ID_VALUES
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "split": split_cases,
                "parse": parse_cases,
                "files": file_cases,
                "env_cap": env_cases,
                "ids": id_cases,
            },
            indent=1,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    ncrash = sum(1 for c in parse_cases if "crash" in c)
    print(
        f"wrote {OUT}: split={len(split_cases)} parse={len(parse_cases)} "
        f"(crash={ncrash}) files={len(file_cases)} env={len(env_cases)} ids={len(id_cases)}"
    )


if __name__ == "__main__":
    main()
