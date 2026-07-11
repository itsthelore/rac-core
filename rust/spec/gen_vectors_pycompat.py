#!/usr/bin/env python3
"""Generate oracle test vectors for rust/rac-engine/src/pycompat.rs.

Run with the oracle venv python (.venv-oracle/bin/python). Output is
deterministic: rust/rac-engine/tests/vectors/pycompat.json.

Vector sections (all expected values computed by this CPython 3.11):
- casefold:   [input, str.casefold(input)]
- strip:      [input, [strip, lstrip, rstrip]]
- is_space:   [codepoint, bool]
- splitlines: [input, parts]
- repr:       [input, repr(input)]
- float_repr: [bits_u64, repr(float)]
- round:      [bits_u64, ndigits, result_bits_u64]
- format_1f:  [bits_u64, f"{x:.1f}"]
- percent0:   [bits_u64, f"{x:.0%}"]
- re_digit:   [codepoint, bool]
- re_word:    [codepoint, bool]

Floats travel as IEEE-754 bit patterns (u64) so transport is exact.
"""
from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "rac-engine" / "tests" / "vectors" / "pycompat.json"


def bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


# --- casefold ---------------------------------------------------------------

CASEFOLD_STRINGS = [
    "", "Hello World", "STRASSE", "Straße", "ẞ", "ﬃ", "ﬄung", "İstanbul",
    "ΣΊΣΥΦΟΣ", "Σς σ", "µ MICRO µ", "ǅungla", "Ǆ ǅ ǆ", "ᾨδή", "ᾟ",
    "ŉ apostrophe-n", "ΐ ΰ", "Ⅷ roman", "ⅷ", "ᏣᎳᎩ Cherokee", "ꭰꮳꮃꭹ",
    "café CAFÉ", "ЁЛКА ёлка", "ΑΒΓΔΕ", "İı Ii", "İİİ",
    "Haẞlo", "և ﬀ ﬗ", "MIXEDcase123", "ÅåÄäÖö",
    "ǰ Ǩǩ", "ῤῦ", "İ̇", "ß mid ß end ß",
]
# Deterministic per-codepoint coverage: every 977th codepoint plus every
# 199th entry of the casefold map itself.
CASEFOLD_CPS = list(range(0, 0x110000, 977))
_mapped = sorted(cp for cp in range(0x110000) if chr(cp).casefold() != chr(cp))
CASEFOLD_CPS += _mapped[::199]

casefold_rows = [[s, s.casefold()] for s in CASEFOLD_STRINGS]
for cp in CASEFOLD_CPS:
    if 0xD800 <= cp <= 0xDFFF:
        continue
    c = chr(cp)
    casefold_rows.append([c, c.casefold()])

# --- strip ------------------------------------------------------------------

STRIP_STRINGS = [
    "", "   ", "x", "  x  ", "\t\n x \r\n", "\x1c\x1d\x1e\x1fx\x1c",
    "\xa0nbsp\xa0", " ogham ", "  x ",
    " line ", " 　ideographic　", "\x0b\x0cx\x0b",
    "​zwsp​", "﻿bom﻿", "\x85nel\x85",
    " \t   mixed　  ", "no-ws-at-all",
    " figure-space ", "᠎ mongolian ᠎",
    "inner space kept", "\nonly-left", "only-right\n",
    "   ", "\x1c", "a\x1fb", "　", "\t\t\t", "\r", "\x0c",
    " unicode café ", " thin ", " narrow ",
]
strip_rows = [[s, [s.strip(), s.lstrip(), s.rstrip()]] for s in STRIP_STRINGS]

# --- is_space / re classes ---------------------------------------------------

CLASS_CPS = sorted(set(
    list(range(0, 0x180))
    + [0x85, 0xa0, 0x1680, 0x180e, 0x2000, 0x2007, 0x200a, 0x200b, 0x2028,
       0x2029, 0x202f, 0x205f, 0x3000, 0xfeff, 0x0660, 0x06f0, 0x0966,
       0x09e6, 0x0a66, 0x0ce6, 0x0e50, 0x0ed0, 0x0f20, 0x1040, 0x17e0,
       0x1810, 0xff10, 0xff19, 0x104a0, 0x1d7ce, 0x1d7ff, 0x2460, 0x00b2,
       0x00bd, 0x5e74, 0x4e00, 0xac00, 0x1f600, 0x0300, 0x0641, 0x05d0,
       0x203f, 0x2040, 0x2054, 0xfe33, 0xff3f, 0x00b7, 0x30fb]
    + list(range(0x2000, 0x2070, 7))
))
is_space_rows = [[cp, chr(cp).isspace()] for cp in CLASS_CPS]
d_re = re.compile(r"\d")
w_re = re.compile(r"\w")
re_digit_rows = [[cp, bool(d_re.match(chr(cp)))] for cp in CLASS_CPS]
re_word_rows = [[cp, bool(w_re.match(chr(cp)))] for cp in CLASS_CPS]

# --- splitlines ---------------------------------------------------------------

SPLITLINES_STRINGS = [
    "", "one", "a\nb", "a\rb", "a\r\nb", "a\n\rb", "a\r\r\nb", "\n",
    "\r\n", "\n\n\n", "a\n", "a\nb\n", "a\vb", "a\fb", "a\x1cb", "a\x1db",
    "a\x1eb", "a\x1fb", "a\x85b", "a b", "a b", "a  b",
    "mixed\nline\rendings\r\nhere\x85and more done",
    "\r\na", "trailing\r", "\rleading", "a\r\n\r\nb", "no newline at all",
    "tab\tis\tnot\ta\tboundary", "\x0b\x0c", "é\nü\r\nñ", "🎉\n🎊",
    "a ", " ", "cr at end\r\n",
]
splitlines_rows = [[s, s.splitlines()] for s in SPLITLINES_STRINGS]

# --- repr ---------------------------------------------------------------------

REPR_STRINGS = [
    "", "plain", "it's", 'say "hi"', "both ' and \"", "back\\slash",
    "tab\there", "new\nline", "cr\rhere", "bell\x07", "null\x00byte",
    "\x01\x02\x03", "esc\x1b[0m", "del\x7f", "\x80\x9f latin1 controls",
    "\xa0nbsp", "\xadsoft-hyphen", "café", "naïve résumé", "→ arrows ←",
    "em—dash", "↳ continuation", "✗ cross ✅ check", "⚠️ warning",
    "🎉 party 🎊", "𝔘𝔫𝔦𝔠𝔬𝔡𝔢", "\U0001F600\U0001F4A9", "​zwsp",
    " ls ps", "﻿bom", "mix'ed \"quotes\" \\ and \n ctrl\x05",
    "ütf-8 ünïcode", "汉字 kanji", "한글", "עברית", "العربية",
    "\udcff".encode("utf-8", "surrogateescape").decode("utf-8", "replace"),
    "ends with quote'", '"starts with quote', "'", '"', "'\"'",
    "\t\n\r", "\x7f\x80", "á combining", "\U0010FFFF max",
    "\U00010000 first astral",
]
repr_rows = [[s, repr(s)] for s in REPR_STRINGS]

# --- float repr ----------------------------------------------------------------

FLOATS = [
    0.0, -0.0, 1.0, -1.0, 2.0, 0.5, 100.0, 1234567.0, 123456789.0,
    0.1, 0.2, 0.3, 0.7, 3.3, 0.33, 2.675, 2.67, 0.125, 0.855,
    1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 9.999e-5, 0.0001, 0.00012345,
    1e15, 1e16, 1e17, 9999999999999998.0, 9.999999999999999e15,
    123456789012345.6, 1234567890123456.7, 12345678901234567.8,
    1e20, -1e20, 1.5e300, 1.7976931348623157e308, 2.2250738585072014e-308,
    5e-324, 1e-323, 2.5e-323, 4.9406564584124654e-324,
    0.8571428571428571, 2 / 3, 10 / 3, 1 / 3, 22 / 7, 355 / 113,
    3.141592653589793, 2.718281828459045, 6.02214076e23, 6.62607015e-34,
    -0.1, -2.675, -1e-5, -5e-324, -9999999999999998.0,
    0.30000000000000004, 0.1 + 0.2, 9007199254740992.0, 9007199254740993.0,
    4503599627370496.0, 1048576.0, 16777216.0, 1e307, 1e-307,
    1.1, 1.2, 1.3, 1.4, 1.5, 2.5, 3.5, 1e1, 1e2, 55.0, 0.9999999999999999,
    1.0000000000000002, 123.456, 999999999999999.9, 99999999999999.99,
    # dtoa tie cases: exact binary value halfway between two shortest
    # candidates — CPython (Gay dtoa) resolves to even, Rust {:e} does not.
    -101065508335255.12, 101065508335255.12, 32.03125, 0.703125,
    1.048576e6, 5960464.477539062, 0.4444580078125, 123.828125,
]
float_repr_rows = [[bits(x), repr(x)] for x in FLOATS]

# --- round ---------------------------------------------------------------------

ROUND_VALUES = [
    0.0, -0.0, 0.5, 1.5, 2.5, 3.5, -0.5, -1.5, -2.5, 0.25, 0.75,
    0.125, 0.375, 2.675, 2.665, 2.685, 0.05, 0.15, 0.25, 0.35, 0.45,
    0.55, 0.65, 0.85, 1.005, 1.015, 0.855, 2 / 3, 10 / 3, 1 / 3,
    0.1, 0.2, 0.3, 0.7, 123.456, 123.454, -123.456, 0.0001, 1e-5,
    5e-324, -5e-324, 1e15, 1e16, 9999999999999998.0, 123456789.987654321,
    0.49999999999999994, 0.5000000000000001, -0.4, 0.4, 1234.5678,
    2.5e-10, 3.14159265358979, 12345.6789, 0.30000000000000004,
    0.045, 0.055, 0.0000005, 1.25, 1.35, 1.45, 100.5, 101.5,
]
ROUND_NDIGITS = [0, 1, 2, 6, 12]
round_rows = []
for x in ROUND_VALUES:
    for nd in ROUND_NDIGITS:
        round_rows.append([bits(x), nd, bits(round(x, nd))])
# negative and large ndigits (avoid overflow-raising combos)
for x, nd in [(12345.678, -1), (12345.678, -2), (12345.678, -3), (15.0, -1),
              (25.0, -1), (250.0, -2), (350.0, -2), (-15.0, -1), (0.5, -1),
              (1e15, -14), (123456789.0, -5), (0.1, 20), (0.1, 30),
              (2.675, 3), (5e-324, 323), (5e-324, 324), (5e-324, 400),
              (1.5, 100), (-2.5, 0), (1e16, -17), (4.5, -1), (5.5, -1)]:
    round_rows.append([bits(x), nd, bits(round(x, nd))])

# --- format helpers ---------------------------------------------------------------

FORMAT_VALUES = [
    0.0, -0.0, 0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95,
    1.05, 1.15, 2.5, -0.04, -0.05, -0.06, 0.04, 2 / 3, 10 / 3, 1 / 3,
    2.675, 0.855, 0.005, 0.0049, 123.456, 99.99, 99.94, 99.95, 99.96,
    -99.95, 1e-5, 5e-324, 0.1, 0.9999999999999999, 1234567.891,
    0.849999999999, 0.005000000001, 1.0, 100.0, 3.14159,
]
format_1f_rows = [[bits(x), f"{x:.1f}"] for x in FORMAT_VALUES]
percent0_rows = [[bits(x), f"{x:.0%}"] for x in FORMAT_VALUES]

payload = {
    "generated_by": "rust/spec/gen_vectors_pycompat.py",
    "python": sys.version.split()[0],
    "casefold": casefold_rows,
    "strip": strip_rows,
    "is_space": is_space_rows,
    "splitlines": splitlines_rows,
    "repr": repr_rows,
    "float_repr": float_repr_rows,
    "round": round_rows,
    "format_1f": format_1f_rows,
    "percent0": percent0_rows,
    "re_digit": re_digit_rows,
    "re_word": re_word_rows,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, ensure_ascii=True, indent=1) + "\n")
total = sum(len(v) for v in payload.values() if isinstance(v, list))
print(f"wrote {OUT}: {total} rows "
      f"({', '.join(f'{k}={len(v)}' for k, v in payload.items() if isinstance(v, list))})")
