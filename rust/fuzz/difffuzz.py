#!/usr/bin/env python3
"""difffuzz — differential fuzzer for the RAC native-engine divergence hunt.

Campaign 2 of the native-engine spike: generate/mutate Markdown artifacts
aimed at the parity landmine classes recorded in rust/PORT-CONTRACT.d/02
(YAML 1.1 frontmatter), 03 (markdown extraction), 04 (classification/
validation), 05 (relationships), 06 (resolve/find ranking) and 09 (walk/
stats/export/review/schema), run BOTH engines (Python oracle + Rust port)
over a command matrix under the parity-harness environment, and compare
stdout bytes + exit codes.

Campaign-2 matrix additions over campaign 1:
  - resolve QUERY corpus [--json] / find QUERY corpus [--json] with queries
    derived from the mutated corpus content (id fragments, unicode words,
    duplicated tokens, title words),
  - schema [NAME [--template]] [--json] / schema --list [--json],
  - export corpus [--json] and export corpus --documents,
  - review corpus [--json|--sarif],
  - relationships corpus [--json] (inspection arm, no --validate),
  - validate - (stdin) [--json] [--corpus corpus],
  - RAC_MAX_FILE_BYTES env variation on validate,
  - path-argument edge forms (trailing slash, ./ prefix, doubled slash,
    .markdown extension as a direct file argument),
  - multi-file corpora (auxiliary artifacts next to the mutated primary).

Every input runs a CORE command set plus a deterministic sample of the
EXTENDED pool. On divergence the input is greedily minimized (line-level
ddmin, then byte-level) while the divergence AND its triage class persist,
and a repro bundle is written under <findings>/<NNN>-<slug>/.

Oracle-crash triage: inputs that crash the oracle uncaught (Python
traceback on stderr) while the Rust engine emits the documented
`internal-oracle-divergence` marker are the campaign-1 finding-001 class —
divergence by design (PORT-CONTRACT decision 3). They are filed at most
once per command with an `-oracle-crash` suffix and DO NOT count against a
round's dry verdict.

stdlib only. Generation is fully deterministic given --seed; with
--jobs > 1 execution order (and hence finding numbering) may vary, but the
set of divergence signatures found is order-independent.

Usage:
  python3 rust/fuzz/difffuzz.py --seed 201 --rounds 1 --batch 800 --jobs 8

Journal: one line per batch appended to rust/fuzz/campaign.log.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading

# ---------------------------------------------------------------------------
# Locations / constants
# ---------------------------------------------------------------------------

FUZZ_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(FUZZ_DIR))

DEFAULT_ORACLE = os.path.join(REPO_ROOT, ".venv-oracle", "bin", "rac")
DEFAULT_ENGINE = os.path.join(REPO_ROOT, "rust", "target", "release", "rac")
DEFAULT_FINDINGS = os.path.join(FUZZ_DIR, "findings2")
CAMPAIGN_LOG = os.path.join(FUZZ_DIR, "campaign.log")

# The version seam: makes the Rust binary report the oracle's setuptools-scm
# version so --version / SARIF driver.version compare raw (see parity-cases).
RAC_RS_VERSION = "0.1.dev50+g21c8be403"

RUN_TIMEOUT_S = 30
TIMEOUT_EXIT = -9999  # sentinel exit code for a timed-out engine
MAX_FILE_BYTES = 1 << 20  # 1 MiB cap on generated inputs
MAX_MINIMIZE_EVALS = 350  # predicate-evaluation budget per finding
BYTE_MIN_LIMIT = 4096  # only byte-minimize inputs at or under this size

ORACLE_CRASH_MARK = b"Traceback (most recent call last)"
RUST_MARKER = b"internal-oracle-divergence"

# ---------------------------------------------------------------------------
# Parity environment (mirrors rust/parity-harness/src/main.rs base_env)
# ---------------------------------------------------------------------------


def parity_env(xdg_root: str) -> dict:
    env = {}
    for inherited in ("PATH", "HOME"):
        if inherited in os.environ:
            env[inherited] = os.environ[inherited]
    env["XDG_CONFIG_HOME"] = os.path.join(xdg_root, "config")
    env["XDG_STATE_HOME"] = os.path.join(xdg_root, "state")
    env["XDG_CACHE_HOME"] = os.path.join(xdg_root, "cache")
    env["RAC_NO_CACHE"] = "1"
    env["LC_ALL"] = "C"
    env["TZ"] = "UTC"
    env["COLUMNS"] = "80"
    env["PYTHONHASHSEED"] = "0"
    env["RAC_RS_VERSION"] = RAC_RS_VERSION
    for leaf in ("config", "state", "cache"):
        os.makedirs(os.path.join(xdg_root, leaf), exist_ok=True)
    return env


def run_engine(engine: str, argv: list, cwd: str, env: dict, stdin_data=None):
    """Run one engine; return (exit_code, stdout_bytes). Piped stdio."""
    code, out, _ = run_engine_full(engine, argv, cwd, env, stdin_data)
    return code, out


def run_engine_full(engine: str, argv: list, cwd: str, env: dict, stdin_data=None):
    """Run one engine; return (exit_code, stdout_bytes, stderr_bytes)."""
    kwargs = dict(
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=RUN_TIMEOUT_S,
    )
    if stdin_data is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = stdin_data
    try:
        p = subprocess.run([engine] + argv, **kwargs)
    except subprocess.TimeoutExpired:
        return TIMEOUT_EXIT, b"", b""
    code = p.returncode
    if code < 0:  # killed by signal: match the harness's 128+sig convention
        code = 128 + (-code)
    return code, p.stdout, p.stderr

# ---------------------------------------------------------------------------
# Seed corpus
# ---------------------------------------------------------------------------


def load_seed_corpus(rng: random.Random) -> list:
    """Fixture corpora + a deterministic sample of the live rac/ corpus +
    synthetic templates. Returns a list of bytes objects."""
    seeds = []

    fixture_root = os.path.join(REPO_ROOT, "tests", "fixtures")
    fixture_files = sorted(
        os.path.join(dp, f)
        for dp, _, fs in os.walk(fixture_root)
        for f in fs
        if f.endswith(".md")
    )
    for path in fixture_files:
        seeds.append(read_file(path))

    rac_root = os.path.join(REPO_ROOT, "rac")
    rac_files = sorted(
        os.path.join(dp, f)
        for dp, _, fs in os.walk(rac_root)
        for f in fs
        if f.endswith(".md")
    )
    sample_n = min(60, len(rac_files))
    for path in rng.sample(rac_files, sample_n):
        seeds.append(read_file(path))

    seeds.extend(s.encode("utf-8") for s in SYNTHETIC_TEMPLATES)
    return [s[:MAX_FILE_BYTES] for s in seeds if s]


def read_file(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


SYNTHETIC_TEMPLATES = [
    # requirement, no frontmatter (legacy shape)
    "# Search Filters\n\n## Problem\n\nUsers cannot narrow results.\n\n"
    "## Requirements\n\n[REQ-001] The system SHALL filter by category.\n"
    "[REQ-002] The system SHALL combine filters.\n",
    # requirement with frontmatter
    "---\nschema_version: 1\nid: RAC-KTQ63DPSMF19\ntype: requirement\n---\n"
    "# Requirement: Fuzz Target\n\n## Problem\n\nA problem.\n\n"
    "## Requirements\n\n- The system SHALL exist.\n",
    # decision
    "---\nschema_version: 1\nid: RAC-KTQ63DPT6008\ntype: decision\n"
    "tags: [architecture, fuzz]\n---\n# ADR-999 Fuzz Decision\n\n## Status\n\n"
    "Accepted\n\n## Context\n\nContext text.\n\n## Decision\n\nDecide.\n\n"
    "## Consequences\n\n- One.\n",
    # roadmap
    "---\nschema_version: 1\nid: RAC-KVA46RJE43ZJ\ntype: roadmap\n---\n"
    "# RAC v9.9.9 Fuzz Roadmap\n\n## Status\n\nPlanned\n\n## Goal\n\nGoal.\n\n"
    "## Scope\n\n- Item.\n",
    # prompt
    "---\nschema_version: 1\nid: RAC-KTW0M8104880\ntype: prompt\n---\n"
    "# Fuzz Prompt\n\n## Objective\n\nDo the thing.\n\n## Input\n\n- A file.\n\n"
    "## Instructions\n\nFollow them.\n\n## Output\n\nA result.\n",
    # design
    "---\nschema_version: 1\nid: RAC-KTY0D0DFTCJA\ntype: design\n---\n"
    "# Fuzz Design\n\n## Context\n\nContext.\n\n## User Need\n\nNeed.\n\n"
    "## Design\n\nShape.\n\n## Constraints\n\nNone.\n",
    # empty-ish / degenerate shapes
    "",
    "---\n---\n",
    "# \n",
    "---\nid: RAC-KTQ63DPSMF19\n",
]

# ---------------------------------------------------------------------------
# Mutation machinery
#
# Operators take (rng, data: bytes, ctx) -> bytes. Text-level operators
# round-trip through surrogateescape so pre-existing invalid UTF-8 survives.
# ---------------------------------------------------------------------------


def to_text(data: bytes) -> str:
    return data.decode("utf-8", errors="surrogateescape")


def to_bytes(text: str) -> bytes:
    return text.encode("utf-8", errors="surrogateescape")


def split_fm(lines: list):
    """Locate a leading frontmatter block. Returns (open_idx, close_idx) of
    the delimiter lines, or None."""
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return (0, i)
    return None


def ensure_fm(rng: random.Random, lines: list) -> tuple:
    """Return (lines, (open, close)) synthesizing a frontmatter block if absent."""
    fm = split_fm(lines)
    if fm:
        return lines, fm
    block = ["---", "schema_version: 1", "id: RAC-KTQ63DPSMF19",
             "type: " + rng.choice(["requirement", "decision", "roadmap", "prompt", "design"]),
             "---"]
    return block + lines, (0, 4)


def fm_kv_lines(lines: list, fm: tuple) -> list:
    """Indices of top-level 'key: value' lines inside the fm block."""
    out = []
    for i in range(fm[0] + 1, fm[1]):
        if re.match(r"^[A-Za-z_][\w-]*:(\s|$)", lines[i]):
            out.append(i)
    return out


# --- YAML 1.1 landmine scalars (PORT-CONTRACT.d/02 §4, SafeLoader resolvers)
TRICKY_SCALARS = [
    # bool forms (YAML 1.1: y/n/yes/no/on/off + casings)
    "y", "Y", "n", "N", "yes", "Yes", "YES", "no", "No", "NO",
    "true", "True", "TRUE", "false", "False", "FALSE",
    "on", "On", "ON", "off", "Off", "OFF",
    # int forms: octal (both spellings), hex, binary, underscores
    "017", "0o17", "0x1F", "0xdeadBEEF", "0b1010_1010", "1_000", "-017", "+0x10",
    # sexagesimal
    "1:30:00", "190:20:30", "-1:2:3", "12:00",
    # dates / timestamps
    "2026-07-11", "2001-12-14t21:59:43.10-05:00", "2001-12-14 21:59:43.10 -5",
    "2002-12-14T21:59:43Z", "1969-12-31",
    # floats
    ".inf", "-.Inf", ".NAN", ".nan", "6.8523015e+5", "685_230.15", "+12e03",
    "190:20:30.15", "-0.0", "1e2",
    # null forms
    "~", "null", "Null", "NULL", "",
    # misc resolver bait
    "=", "-", "e10", "0x", "0o", ".", "*", "&", "!", "'y'", '"no"',
]


def op_fm_scalar_swap(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    kvs = fm_kv_lines(lines, fm)
    if not kvs:
        return to_bytes("\n".join(lines) + "\n")
    i = rng.choice(kvs)
    key = lines[i].split(":", 1)[0]
    lines[i] = f"{key}: {rng.choice(TRICKY_SCALARS)}"
    return to_bytes("\n".join(lines) + "\n")


def op_fm_quote(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    kvs = fm_kv_lines(lines, fm)
    if not kvs:
        return data
    i = rng.choice(kvs)
    key, _, val = lines[i].partition(":")
    val = val.strip() or "x"
    style = rng.randrange(4)
    if style == 0:
        lines[i] = f"{key}: '{val}'"
    elif style == 1:
        lines[i] = f'{key}: "{val}"'
    elif style == 2:
        lines[i] = f'{key}: "\\x41\\u0041\\U00000041"'
    else:
        lines[i] = f"{key}: '' ''"  # single-quote escape bait
    return to_bytes("\n".join(lines) + "\n")


def op_fm_anchor_alias(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    kvs = fm_kv_lines(lines, fm)
    if not kvs:
        return data
    i = rng.choice(kvs)
    key, _, val = lines[i].partition(":")
    val = val.strip() or "draft"
    lines[i] = f"{key}: &a{rng.randrange(9)} {val}"
    anchor = lines[i].split("&", 1)[1].split()[0]
    lines.insert(fm[1], f"x_alias: *{anchor}" if rng.random() < 0.8 else f"x_alias: *nosuch{rng.randrange(9)}")
    return to_bytes("\n".join(lines) + "\n")


def op_fm_merge_key(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    insert = fm[0] + 1
    lines.insert(insert, "x_base: &base {status: draft, extra: 1}")
    lines.insert(fm[1] + 1, "<<: *base")
    return to_bytes("\n".join(lines) + "\n")


def op_fm_dup_key(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    kvs = fm_kv_lines(lines, fm)
    if not kvs:
        return data
    i = rng.choice(kvs)
    key = lines[i].split(":", 1)[0]
    lines.insert(fm[1], f"{key}: {rng.choice(TRICKY_SCALARS)}")
    return to_bytes("\n".join(lines) + "\n")


def op_fm_dup_key_cross_type(rng, data, ctx):
    """Duplicate a key with a different node TYPE (scalar vs seq vs map)."""
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    kvs = fm_kv_lines(lines, fm)
    if not kvs:
        return data
    i = rng.choice(kvs)
    key = lines[i].split(":", 1)[0]
    form = rng.randrange(3)
    if form == 0:
        lines[fm[1]:fm[1]] = [f"{key}:", "  - a", "  - b"]
    elif form == 1:
        lines[fm[1]:fm[1]] = [f"{key}:", "  nested: yes"]
    else:
        lines[fm[1]:fm[1]] = [f"{key}: [a, {rng.choice(TRICKY_SCALARS) or '~'}]"]
    return to_bytes("\n".join(lines) + "\n")


def op_fm_deep_nesting(rng, data, ctx):
    """Nesting depth around 30-32 (flow or block)."""
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    depth = rng.randrange(28, 35)
    if rng.random() < 0.5:
        val = "[" * depth + "x" + "]" * depth
        lines.insert(fm[1], f"x_deep: {val}")
    else:
        block = ["x_deep:"]
        for d in range(depth):
            block.append("  " * (d + 1) + f"k{d}:")
        block.append("  " * (depth + 1) + "leaf: 1")
        lines[fm[1]:fm[1]] = block
    return to_bytes("\n".join(lines) + "\n")


def op_fm_oversize(rng, data, ctx):
    """Oversize payloads: giant scalar or thousands of keys/list items."""
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    form = rng.randrange(3)
    if form == 0:
        lines.insert(fm[1], "x_big: " + "A" * rng.choice([1 << 14, 1 << 16, 1 << 18]))
    elif form == 1:
        n = rng.choice([500, 3000])
        lines[fm[1]:fm[1]] = [f"x_k{j}: {j}" for j in range(n)]
    else:
        n = rng.choice([500, 3000])
        lines[fm[1]:fm[1]] = ["tags:"] + [f"  - t{j}" for j in range(n)]
    return to_bytes("\n".join(lines) + "\n")[:MAX_FILE_BYTES]


def op_fm_tags_mutate(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    forms = [
        "tags: [on, off, 017, 1:30]",
        "tags: not-a-list",
        "tags:\n  - yes\n  - 2026-07-11\n  - .inf",
        "tags: [[nested]]",
        "tags: {a: b}",
        "tags: [é, \U0001f600, '']",
    ]
    lines[fm[1]:fm[1]] = rng.choice(forms).split("\n")
    return to_bytes("\n".join(lines) + "\n")


def op_fm_relationships(rng, data, ctx):
    """Relationship blocks aimed at the resolution/validation arm (05)."""
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    ids = ctx.get("known_ids") or ["RAC-KTQ63DPT6008"]
    tgt = rng.choice(ids + ["RAC-KTQ63DQZZZZZ", "ADR-007", "adr-007",
                            "  spaced id  ", "", "RAC-KTQ63DPSMF19"])
    kind = rng.choice(["implements", "supersedes", "depends_on", "verified_by",
                       "frobnicates", "references"])
    forms = [
        f"relationships:\n  {kind}: [{tgt}]" if tgt.strip() else f"relationships:\n  {kind}: ['{tgt}']",
        f"relationships:\n  {kind}:\n    - '{tgt}'\n    - '{tgt}'",
        f"relationships:\n  {kind}: {tgt or '~'}",
        "relationships: not-a-map",
        f"relationships:\n  {kind}: [{rng.choice(TRICKY_SCALARS) or '~'}]",
    ]
    lines[fm[1]:fm[1]] = rng.choice(forms).split("\n")
    return to_bytes("\n".join(lines) + "\n")


def op_fm_complex_key(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    choice = rng.randrange(3)
    if choice == 0:
        lines[fm[1]:fm[1]] = ["? [a, b]", ": v"]
    elif choice == 1:
        lines.insert(fm[1], "{a: 1}: mapping-key")
    else:
        lines.insert(fm[1], "123: int-key")
    return to_bytes("\n".join(lines) + "\n")


def op_fm_tab(rng, data, ctx):
    lines = to_text(data).splitlines()
    lines, fm = ensure_fm(rng, lines)
    i = rng.randrange(fm[0] + 1, fm[1]) if fm[1] > fm[0] + 1 else fm[0] + 1
    if i < len(lines):
        lines[i] = "\t" + lines[i] if rng.random() < 0.5 else lines[i].replace(": ", ":\t", 1)
    return to_bytes("\n".join(lines) + "\n")


# --- delimiter games (PORT-CONTRACT.d/02 §1)

def op_bom(rng, data, ctx):
    bom = b"\xef\xbb\xbf"
    choice = rng.randrange(3)
    if choice == 0:
        return bom + data
    if choice == 1:
        return bom + bom + data
    return data[: len(data) // 2] + bom + data[len(data) // 2:]


def op_crlf(rng, data, ctx):
    if rng.random() < 0.6:
        return data.replace(b"\n", b"\r\n")
    # only some lines: CR before a random subset of newlines
    out = bytearray()
    for chunk in data.split(b"\n"):
        out += chunk + (b"\r\n" if rng.random() < 0.5 else b"\n")
    return bytes(out[:-1]) if out else data


def op_nbsp_delim(rng, data, ctx):
    text = to_text(data)
    lines = text.splitlines()
    targets = [i for i, l in enumerate(lines) if l.strip() in ("---", "...")]
    if not targets:
        lines.insert(0, "---")
        targets = [0]
    i = rng.choice(targets)
    nb = " "
    lines[i] = rng.choice([nb + lines[i], lines[i] + nb, lines[i].replace("---", "-" + nb + "--")])
    return to_bytes("\n".join(lines) + "\n")


def op_delim_games(rng, data, ctx):
    lines = to_text(data).splitlines()
    game = rng.randrange(7)
    if game == 0:  # trailing spaces after ---
        lines, fm = ensure_fm(rng, lines)
        lines[fm[0]] = "---" + " " * rng.randrange(1, 4)
    elif game == 1:  # four dashes
        lines, fm = ensure_fm(rng, lines)
        lines[rng.choice(fm)] = "----"
    elif game == 2:  # close with ...
        lines, fm = ensure_fm(rng, lines)
        lines[fm[1]] = "..."
    elif game == 3:  # blank line before opening ---
        lines.insert(0, "")
    elif game == 4:  # indent the opening delimiter
        lines, fm = ensure_fm(rng, lines)
        lines[fm[0]] = " " * rng.randrange(1, 4) + "---"
    elif game == 5:  # remove the closing delimiter (unterminated block)
        fm = split_fm(lines)
        if fm:
            del lines[fm[1]]
        else:
            lines.insert(0, "---")
    else:  # duplicate a --- mid-document
        pos = rng.randrange(len(lines) + 1) if lines else 0
        lines.insert(pos, "---")
    return to_bytes("\n".join(lines) + "\n")


# --- markdown structure (PORT-CONTRACT.d/03)

def _random_line(rng, lines):
    return rng.randrange(len(lines) + 1) if lines else 0


def op_setext(rng, data, ctx):
    lines = to_text(data).splitlines()
    pos = _random_line(rng, lines)
    title = rng.choice(["Setext Trap", "Requirements", "Status", "Problem"])
    under = rng.choice(["====", "----", "-", "=", "--- ---"])
    lines[pos:pos] = [title, under]
    return to_bytes("\n".join(lines) + "\n")


def op_heading_in_container(rng, data, ctx):
    lines = to_text(data).splitlines()
    heads = [i for i, l in enumerate(lines) if l.lstrip().startswith("#")]
    prefix = rng.choice(["> ", "- ", "1. ", ">> ", "* "])
    if heads:
        i = rng.choice(heads)
        lines[i] = prefix + lines[i]
    else:
        lines.insert(_random_line(rng, lines), prefix + "# Contained Heading")
    return to_bytes("\n".join(lines) + "\n")


def op_fences(rng, data, ctx):
    lines = to_text(data).splitlines()
    pos = _random_line(rng, lines)
    game = rng.randrange(4)
    if game == 0:  # unclosed fence swallowing the rest
        lines.insert(pos, rng.choice(["```", "~~~", "````yaml"]))
    elif game == 1:  # fence containing headings and ---
        lines[pos:pos] = ["```", "# Fenced Heading", "---", "## Also fenced", "```"]
    elif game == 2:  # fence with info string and mismatched close
        lines[pos:pos] = ["````md", "## inside", "```"]
    else:  # tilde fence closed by backticks (must NOT close)
        lines[pos:pos] = ["~~~", "## inside", "```", "## still inside?"]
    return to_bytes("\n".join(lines) + "\n")


def op_indented_code(rng, data, ctx):
    lines = to_text(data).splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith("#")]
    if heads:
        i = rng.choice(heads)
        lines[i] = " " * rng.choice([4, 5, 8]) + lines[i]
    else:
        lines.insert(_random_line(rng, lines), "    # Indented Heading")
    return to_bytes("\n".join(lines) + "\n")


def op_html_block(rng, data, ctx):
    lines = to_text(data).splitlines()
    pos = _random_line(rng, lines)
    block = rng.choice([
        ["<div>", "# HTML-swallowed heading", "</div>"],
        ["<!-- # commented heading", "## still comment -->"],
        ["<table><tr><td>", "## Requirements", "</td></tr></table>"],
        ["<Div Unclosed>"],
        ["<script>", "let x = '# nope';", "</script>"],
    ])
    lines[pos:pos] = block
    return to_bytes("\n".join(lines) + "\n")


def op_tabs(rng, data, ctx):
    lines = to_text(data).splitlines()
    if not lines:
        return b"#\tTabbed\n"
    i = rng.randrange(len(lines))
    game = rng.randrange(3)
    if game == 0:
        lines[i] = lines[i].replace("# ", "#\t", 1)
    elif game == 1:
        lines[i] = "\t" + lines[i]
    else:
        lines[i] = lines[i].replace(" ", "\t")
    return to_bytes("\n".join(lines) + "\n")


def op_hash_games(rng, data, ctx):
    lines = to_text(data).splitlines()
    pos = _random_line(rng, lines)
    lines.insert(pos, rng.choice([
        "#NoSpaceHeading",
        "# Closing Hashes ###",
        "# Closing Hashes ### ",
        "\\# Escaped Heading",
        "####### Seven Hashes",
        "#",
        "# ",
        "  ## Two-space heading",
    ]))
    return to_bytes("\n".join(lines) + "\n")


def op_unicode_heading(rng, data, ctx):
    lines = to_text(data).splitlines()
    pos = _random_line(rng, lines)
    lines.insert(pos, rng.choice([
        "# Requireḿents",              # combining acute
        "# שלום Status",  # RTL
        "# Zero​Width‍Joined",
        "# ＃ Fullwidth Hash",
        "＃ Fullwidth Number Sign",
        "# Título Über",
    ]))
    return to_bytes("\n".join(lines) + "\n")


def op_control_chars(rng, data, ctx):
    """U+001C-U+001F (Python str.splitlines() splits on these; most parsers
    do not), plus VT/FF."""
    ch = rng.choice([b"\x1c", b"\x1d", b"\x1e", b"\x1f", b"\x0b", b"\x0c"])
    pos = rng.randrange(len(data) + 1) if data else 0
    return data[:pos] + ch + data[pos:]


def op_astral(rng, data, ctx):
    lines = to_text(data).splitlines()
    pos = _random_line(rng, lines)
    lines.insert(pos, rng.choice([
        "# Emoji \U0001f600\U0001f680 heading",
        "# Replacement � char",
        "\U0001f600 [REQ-001] The system SHALL \U0001f4a5.",
        "# \U00010348 Gothic",
    ]))
    return to_bytes("\n".join(lines) + "\n")


def op_invalid_utf8(rng, data, ctx):
    """Raw invalid byte injection at the file level."""
    junk = rng.choice([
        b"\xff", b"\xfe", b"\x80", b"\xc3", b"\xc3\x28",
        b"\xed\xa0\x80",          # UTF-8-encoded surrogate
        b"\xf0\x9f\x98",          # truncated 4-byte sequence
        b"\xc0\xaf",              # overlong
    ])
    pos = rng.randrange(len(data) + 1) if data else 0
    return data[:pos] + junk + data[pos:]


# --- file-level

def op_truncate(rng, data, ctx):
    if not data:
        return data
    if rng.random() < 0.5:
        return data[: rng.randrange(len(data))]
    lines = data.split(b"\n")
    return b"\n".join(lines[: rng.randrange(len(lines))])


def op_concat(rng, data, ctx):
    other = rng.choice(ctx["corpus"])
    sep = rng.choice([b"", b"\n", b"\n---\n"])
    return (data + sep + other)[:MAX_FILE_BYTES]


def op_splice(rng, data, ctx):
    other = rng.choice(ctx["corpus"]).split(b"\n")
    lines = data.split(b"\n")
    if not lines or not other:
        return data
    a = rng.randrange(len(lines))
    b = rng.randrange(a, min(len(lines), a + 10) + 1)
    oa = rng.randrange(len(other))
    ob = rng.randrange(oa, min(len(other), oa + 10) + 1)
    return b"\n".join(lines[:a] + other[oa:ob] + lines[b:])[:MAX_FILE_BYTES]


def op_dup_block(rng, data, ctx):
    lines = data.split(b"\n")
    if len(lines) < 2:
        return data + data
    a = rng.randrange(len(lines))
    b = rng.randrange(a, min(len(lines), a + 8) + 1)
    return b"\n".join(lines[:b] + lines[a:b] + lines[b:])[:MAX_FILE_BYTES]


def op_remove_block(rng, data, ctx):
    lines = data.split(b"\n")
    if len(lines) < 2:
        return data
    a = rng.randrange(len(lines))
    b = rng.randrange(a, min(len(lines), a + 6) + 1)
    return b"\n".join(lines[:a] + lines[b:])


def op_byte_edit(rng, data, ctx):
    if not data:
        return bytes([rng.randrange(256)])
    pos = rng.randrange(len(data))
    if rng.random() < 0.5:
        return data[:pos] + bytes([rng.randrange(256)]) + data[pos + 1:]
    return data[:pos] + bytes([rng.randrange(256)]) + data[pos:]


OPERATORS = [
    op_fm_scalar_swap, op_fm_quote, op_fm_anchor_alias, op_fm_merge_key,
    op_fm_dup_key, op_fm_dup_key_cross_type, op_fm_deep_nesting,
    op_fm_oversize, op_fm_tags_mutate, op_fm_relationships, op_fm_complex_key,
    op_fm_tab,
    op_bom, op_crlf, op_nbsp_delim, op_delim_games,
    op_setext, op_heading_in_container, op_fences, op_indented_code,
    op_html_block, op_tabs, op_hash_games, op_unicode_heading,
    op_control_chars, op_astral, op_invalid_utf8,
    op_truncate, op_concat, op_splice, op_dup_block, op_remove_block,
    op_byte_edit,
]

# Weight the frontmatter-scalar op up: it targets landmine class #1.
WEIGHTS = [3 if op is op_fm_scalar_swap else 1 for op in OPERATORS]

KNOWN_IDS = ["RAC-KTQ63DPSMF19", "RAC-KTQ63DPT6008", "RAC-KTQ63DPVVB37",
             "RAC-KVA46RJE43ZJ", "RAC-KTW0M8104880", "RAC-KTY0D0DFTCJA"]

AUX_TEMPLATE = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n"
    "{rel}---\n# ADR-{n} Aux {name}\n\n## Status\n\nAccepted\n\n"
    "## Context\n\nC.\n\n## Decision\n\nD.\n\n## Consequences\n\n- One.\n"
)


def generate(rng: random.Random, corpus: list) -> tuple:
    """One fuzz input: base pick + 1..4 mutations, plus optional auxiliary
    corpus files (multi-file mode). Returns (bytes, op_names, aux) where aux
    is a list of (relpath, bytes) written next to corpus/case.md."""
    data = rng.choice(corpus)
    ctx = {"corpus": corpus, "known_ids": KNOWN_IDS}
    names = []
    for _ in range(rng.randrange(1, 5)):
        op = rng.choices(OPERATORS, weights=WEIGHTS, k=1)[0]
        data = op(rng, data, ctx)[:MAX_FILE_BYTES]
        names.append(op.__name__)

    aux = []
    if rng.random() < 0.35:  # multi-file corpus mode
        n_aux = rng.randrange(1, 4)
        primary_ids = re.findall(r"RAC-[A-Za-z0-9]{6,16}", to_text(data))
        for j in range(n_aux):
            form = rng.randrange(10)
            if form < 5:  # plain corpus pick
                blob = rng.choice(corpus)
            elif form < 8:  # corpus pick with one mutation
                op = rng.choices(OPERATORS, weights=WEIGHTS, k=1)[0]
                blob = op(rng, rng.choice(corpus), ctx)[:MAX_FILE_BYTES]
                names.append("aux:" + op.__name__)
            else:  # synthetic decision referencing an id from the primary
                tgt = rng.choice(primary_ids) if primary_ids else rng.choice(KNOWN_IDS)
                rel = f"relationships:\n  supersedes: [{tgt}]\n"
                blob = to_bytes(AUX_TEMPLATE.format(
                    id=rng.choice(KNOWN_IDS), rel=rel, n=900 + j, name=f"A{j}"))
            ext = ".markdown" if rng.random() < 0.1 else ".md"
            sub = "sub/" if rng.random() < 0.25 else ""
            aux.append((f"{sub}aux{j}{ext}", blob))
    return data, names, aux

# ---------------------------------------------------------------------------
# Command matrix
#
# A command spec is a dict:
#   name       stable coarse name (feeds the dedup signature)
#   argv       argv after the engine binary; cwd = case dir
#   env        extra env vars merged over the parity env
#   stdin      "primary" to feed the (current) primary bytes on stdin
#   copy_as    also write the primary bytes at this relpath before running
# ---------------------------------------------------------------------------


def cmd(name, argv, env=None, stdin=None, copy_as=None):
    return {"name": name, "argv": argv, "env": env or {}, "stdin": stdin,
            "copy_as": copy_as}


# Always run: broad, cheap detectors for the parse/validate pipeline.
CORE_COMMANDS = [
    cmd("validate-file", ["validate", "corpus/case.md"]),
    cmd("validate-file-json", ["validate", "corpus/case.md", "--json"]),
    cmd("validate-dir-sarif", ["validate", "corpus", "--sarif"]),
    cmd("relationships-validate-json", ["relationships", "corpus", "--validate", "--json"]),
    cmd("stats-dir-json", ["stats", "corpus", "--json"]),
]

# RAC_MAX_FILE_BYTES probe values (plus data-length-derived boundary values
# added at build time). Mixes valid, boundary, non-positive, unparseable,
# underscore/sign/whitespace forms, huge (beyond i64/u64) and non-ASCII
# decimal digits (CPython int() accepts them).
MAXBYTES_VALUES = [
    "16", "64", "100", "1024", "0", "-1", "abc", "", " 4096 ", "1_024",
    "+512", "99999999999999999999", "٣٢",  # Arabic-Indic "32"
    "0x400", "1e6", "  ", " 128", "18446744073709551617",
]

SCHEMA_NAMES = ["requirement", "decision", "roadmap", "prompt", "design"]

EXTENDED_SAMPLE = 5  # extended commands sampled per input


def derive_queries(rng: random.Random, data: bytes) -> list:
    """Deterministic query candidates from the mutated content: full ids,
    id fragments, unicode words, duplicated tokens, title words."""
    text = to_text(data)[:20000]
    cands = []
    ids = re.findall(r"RAC-[A-Za-z0-9]{4,20}", text)
    for i in ids[:4]:
        cands.append(i)
        if len(i) > 8:
            cands.append(i[: rng.randrange(6, len(i))])  # fragment
        cands.append(i.lower())
    adrs = re.findall(r"ADR-\d+", text)
    cands.extend(adrs[:2])
    words = re.findall(r"\w{2,24}", text, re.UNICODE)
    non_ascii = [w for w in words if any(ord(c) > 127 for c in w)]
    if words:
        w = rng.choice(words)
        cands.append(w)
        cands.append(f"{w} {w}")  # duplicate token
        if len(words) >= 2:
            cands.append(" ".join(rng.sample(words, 2)))
    if non_ascii:
        cands.append(rng.choice(non_ascii))
    for line in text.splitlines():
        if line.startswith("# "):
            cands.append(line[2:].strip()[:60])
            break
    cands.extend(["", "the system SHALL", "RAC"])
    cands = [c for c in cands if len(c) <= 80]
    return cands or ["RAC"]


def build_commands(rng: random.Random, data: bytes) -> list:
    """CORE + a deterministic sample of the extended pool for this input."""
    qs = derive_queries(rng, data)
    q_resolve = rng.choice(qs)
    q_find = rng.choice(qs)
    mb_pool = MAXBYTES_VALUES + [str(len(data)), str(max(1, len(data) - 1)),
                                 str(len(data) + 1)]
    mb = rng.choice(mb_pool)
    schema_name = rng.choice(SCHEMA_NAMES + [q_find[:30] or "requirement", "Requirement", "REQUIREMENT"])
    schema_variant = rng.choice([
        cmd("schema-list", ["schema", "--list"]),
        cmd("schema-list-json", ["schema", "--list", "--json"]),
        cmd("schema-name", ["schema", schema_name]),
        cmd("schema-name-json", ["schema", schema_name, "--json"]),
        cmd("schema-name-template", ["schema", schema_name, "--template"]),
    ])

    pool = [
        # plain dir arms not in CORE
        cmd("validate-dir", ["validate", "corpus"]),
        cmd("validate-dir-json", ["validate", "corpus", "--json"]),
        cmd("relationships-validate", ["relationships", "corpus", "--validate"]),
        cmd("stats-dir", ["stats", "corpus"]),
        # inspection arm
        cmd("relationships-inspect", ["relationships", "corpus"]),
        cmd("relationships-inspect-json", ["relationships", "corpus", "--json"]),
        # review
        cmd("review-dir", ["review", "corpus"]),
        cmd("review-dir-json", ["review", "corpus", "--json"]),
        cmd("review-dir-sarif", ["review", "corpus", "--sarif"]),
        # export
        cmd("export-dir", ["export", "corpus"]),
        cmd("export-dir-json", ["export", "corpus", "--json"]),
        cmd("export-dir-documents", ["export", "corpus", "--documents"]),
        # resolve / find (content-derived queries)
        cmd("resolve-query", ["resolve", q_resolve, "corpus"]),
        cmd("resolve-query-json", ["resolve", q_resolve, "corpus", "--json"]),
        cmd("find-query", ["find", q_find, "corpus"]),
        cmd("find-query-json", ["find", q_find, "corpus", "--json"]),
        # schema (one sampled variant)
        schema_variant,
        # stdin
        cmd("validate-stdin", ["validate", "-"], stdin="primary"),
        cmd("validate-stdin-json", ["validate", "-", "--json"], stdin="primary"),
        cmd("validate-stdin-corpus-json",
            ["validate", "-", "--corpus", "corpus", "--json"], stdin="primary"),
        # RAC_MAX_FILE_BYTES env variation
        cmd("validate-file-maxbytes", ["validate", "corpus/case.md", "--json"],
            env={"RAC_MAX_FILE_BYTES": mb}),
        cmd("validate-dir-maxbytes", ["validate", "corpus"],
            env={"RAC_MAX_FILE_BYTES": mb}),
        # path-argument edge forms
        cmd("validate-dir-slash", ["validate", "corpus/"]),
        cmd("validate-dir-dot", ["validate", "./corpus", "--json"]),
        cmd("validate-file-doubleslash", ["validate", "corpus//case.md"]),
        cmd("stats-dir-slash", ["stats", "corpus/"]),
        cmd("validate-markdown-ext", ["validate", "corpus/case.markdown"],
            copy_as="corpus/case.markdown"),
    ]
    return CORE_COMMANDS + rng.sample(pool, EXTENDED_SAMPLE)

# ---------------------------------------------------------------------------
# Differential execution
# ---------------------------------------------------------------------------


class Worker:
    """Per-thread scratch context: its own case dir + XDG root."""

    def __init__(self, root: str, idx: int):
        self.case_dir = os.path.join(root, f"case{idx}")
        self.corpus_dir = os.path.join(self.case_dir, "corpus")
        os.makedirs(self.corpus_dir, exist_ok=True)
        self.env = parity_env(os.path.join(root, f"xdg{idx}"))
        self.aux = []

    def set_aux(self, aux):
        """Reset the corpus dir to hold exactly `aux` (primary written later)."""
        self.aux = aux
        shutil.rmtree(self.corpus_dir, ignore_errors=True)
        os.makedirs(self.corpus_dir, exist_ok=True)
        for rel, blob in aux:
            p = os.path.join(self.corpus_dir, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(blob)


class Fuzzer:
    def __init__(self, args):
        self.oracle = os.path.abspath(args.oracle)
        self.engine = os.path.abspath(args.engine)
        self.findings_dir = os.path.abspath(args.findings)
        self.workdir = os.path.abspath(args.workdir) if args.workdir else tempfile.mkdtemp(prefix="difffuzz-")
        os.makedirs(self.workdir, exist_ok=True)
        os.makedirs(self.findings_dir, exist_ok=True)
        self.lock = threading.Lock()
        self.worker0 = Worker(self.workdir, 0)
        self.seen = self._load_signatures()
        self.evals = 0

    # -- signatures persist across runs so re-runs don't re-file known finds
    def _sig_path(self):
        return os.path.join(self.findings_dir, "signatures.txt")

    def _load_signatures(self):
        try:
            with open(self._sig_path()) as fh:
                return set(l.strip() for l in fh if l.strip())
        except FileNotFoundError:
            return set()

    def _save_signature_locked(self, sig):
        self.seen.add(sig)
        with open(self._sig_path(), "a") as fh:
            fh.write(sig + "\n")

    # -- core check
    def diverges(self, worker: Worker, data: bytes, spec: dict):
        """Write data as the primary case file (aux already staged in the
        worker), run one command spec on both engines.

        Returns (diverged, detail, triage) where detail = (ea, oa, eb, ob)
        and triage = "oracle-crash" for the documented 001 class (oracle
        uncaught traceback + Rust marker) else "engine"."""
        with open(os.path.join(worker.corpus_dir, "case.md"), "wb") as fh:
            fh.write(data)
        if spec["copy_as"]:
            p = os.path.join(worker.case_dir, spec["copy_as"])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:
                fh.write(data)
        env = dict(worker.env)
        env.update(spec["env"])
        stdin_data = data if spec["stdin"] == "primary" else None
        self.evals += 1
        ea, oa, sa = run_engine_full(self.oracle, spec["argv"], worker.case_dir, env, stdin_data)
        eb, ob, sb = run_engine_full(self.engine, spec["argv"], worker.case_dir, env, stdin_data)
        if spec["copy_as"]:
            try:
                os.remove(os.path.join(worker.case_dir, spec["copy_as"]))
            except OSError:
                pass
        detail = (ea, oa, eb, ob)
        if ea == TIMEOUT_EXIT and eb == TIMEOUT_EXIT:
            return False, detail, "engine"
        div = ea != eb or oa != ob
        triage = "engine"
        # Any uncaught oracle traceback is the documented finding-001 class:
        # the oracle died, so divergence is unavoidable and by design
        # (PORT-CONTRACT decision 3). The reverse case — Rust emitting the
        # marker while the oracle exits cleanly — stays "engine" (that shape
        # was campaign-1 finding 003, a real port bug).
        if div and ORACLE_CRASH_MARK in sa:
            triage = "oracle-crash"
        _ = sb
        return div, detail, triage

    def check_all(self, worker: Worker, data: bytes, commands: list) -> list:
        """Run the full per-input matrix; return every diverging
        (spec, detail, triage)."""
        hits = []
        for spec in commands:
            div, detail, triage = self.diverges(worker, data, spec)
            if div:
                hits.append((spec, detail, triage))
        return hits

    # -- minimization
    def minimize(self, worker: Worker, data: bytes, spec: dict, triage: str) -> bytes:
        """Greedy reduction while the divergence on spec persists WITH the
        same triage class (so an engine bug never drifts into the documented
        oracle-crash class mid-shrink, or vice versa).
        Line-level ddmin first, then byte-level for small inputs."""
        self.evals = 0

        def pred(blob: bytes) -> bool:
            div, _, t = self.diverges(worker, blob, spec)
            return div and t == triage

        data = self._ddmin(data.split(b"\n"), pred, joiner=b"\n")
        if len(data) <= BYTE_MIN_LIMIT:
            data = self._ddmin([data[i:i + 1] for i in range(len(data))], pred, joiner=b"")
        return data

    def _ddmin(self, atoms: list, pred, joiner: bytes) -> bytes:
        n = 2
        while len(atoms) >= 2 and self.evals < MAX_MINIMIZE_EVALS:
            chunk = max(1, len(atoms) // n)
            reduced = False
            i = 0
            while i < len(atoms) and self.evals < MAX_MINIMIZE_EVALS:
                candidate = atoms[:i] + atoms[i + chunk:]
                if pred(joiner.join(candidate)):
                    atoms = candidate
                    reduced = True
                else:
                    i += chunk
            if not reduced:
                if chunk == 1:
                    break
                n = min(len(atoms), n * 2)
        return joiner.join(atoms)

    # -- reporting
    def _next_finding_number_locked(self):
        nums = [0]
        for name in os.listdir(self.findings_dir):
            m = re.match(r"^(\d{3})-", name)
            if m:
                nums.append(int(m.group(1)))
        return max(nums) + 1

    def file_finding(self, worker: Worker, seed_label, original: bytes, op_names,
                     spec: dict, detail, triage: str):
        """Returns (slug_or_None, triage). Dedup on the ORIGINAL divergence
        signature, before minimization (see campaign-1 dedup-masking note).
        The documented oracle-crash class dedups coarsely (one repro per
        command name) and is marked so rounds can discount it."""
        cmd_name = spec["name"]
        if triage == "oracle-crash":
            orig_sig = hashlib.sha1(f"001|{cmd_name}".encode()).hexdigest()
        else:
            orig_sig = signature(cmd_name, detail[0], detail[2], detail[1], detail[3])
        with self.lock:
            if orig_sig in self.seen:
                return None, triage
            self.seen.add(orig_sig)  # claim before the (slow) minimize
        minimized = self.minimize(worker, original, spec, triage)
        div, (ea, oa, eb, ob), t = self.diverges(worker, minimized, spec)
        if not div or t != triage:  # flaky (should not happen — deterministic)
            minimized = original
            div, (ea, oa, eb, ob), t = self.diverges(worker, minimized, spec)
            if not div:
                return None, triage
        off = first_diff(oa, ob)
        sig = signature(cmd_name, ea, eb, oa, ob)
        with self.lock:
            self._save_signature_locked(orig_sig)
            same_class = sig != orig_sig and sig in self.seen
            if not same_class and triage != "oracle-crash":
                self._save_signature_locked(sig)
            num = self._next_finding_number_locked()
            suffix = "-oracle-crash" if triage == "oracle-crash" else ""
            slug = f"{num:03d}-{cmd_name}-{sig[:8]}" + ("-sameclass" if same_class else "") + suffix
            fdir = os.path.join(self.findings_dir, slug)
            os.makedirs(fdir, exist_ok=True)
        write(os.path.join(fdir, "repro.md"), minimized)
        write(os.path.join(fdir, "original.md"), original)
        write(os.path.join(fdir, "oracle.stdout"), oa)
        write(os.path.join(fdir, "rust.stdout"), ob)
        for rel, blob in worker.aux:
            p = os.path.join(fdir, "aux", rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            write(p, blob)
        readme = self._readme(worker, slug, seed_label, op_names, spec, triage,
                              ea, eb, oa, ob, off, minimized)
        write(os.path.join(fdir, "README.md"), readme.encode("utf-8"))
        return slug, triage

    def _readme(self, worker, slug, seed_label, op_names, spec, triage,
                ea, eb, oa, ob, off, minimized):
        base_env = worker.env
        env_line = " ".join(
            f"{k}={base_env[k]}"
            for k in ("LC_ALL", "TZ", "COLUMNS", "RAC_NO_CACHE", "PYTHONHASHSEED", "RAC_RS_VERSION")
        )
        for k, v in spec["env"].items():
            env_line += f" {k}={v!r}"
        argv = spec["argv"]
        lines = [
            f"# Finding {slug}",
            "",
            f"- command: `rac {' '.join(argv)}`  (cwd = a dir containing `corpus/case.md` = `repro.md`)",
            f"- triage: {'documented oracle-crash class (001, divergence by design)' if triage == 'oracle-crash' else 'engine divergence'}",
            f"- campaign: {seed_label}; mutation chain: {', '.join(op_names)}",
            f"- exit codes: oracle={fmt_exit(ea)} rust={fmt_exit(eb)}",
            f"- stdout bytes: oracle={len(oa)} rust={len(ob)}",
            f"- first stdout diff offset: {off if off is not None else 'none (exit-code-only divergence)'}",
            f"- repro input: `repro.md` (minimized, {len(minimized)} bytes); pre-minimization input: `original.md`",
        ]
        if spec["stdin"]:
            lines.append("- stdin: the repro bytes are ALSO fed on stdin (`validate -`)")
        if spec["copy_as"]:
            lines.append(f"- the repro bytes are also written at `{spec['copy_as']}`")
        if worker.aux:
            lines.append(f"- auxiliary corpus files (under `aux/`): {', '.join(rel for rel, _ in worker.aux)}")
        lines += [
            "",
            "Reproduce:",
            "",
            "```sh",
            "mkdir -p /tmp/repro/corpus && cp repro.md /tmp/repro/corpus/case.md && cd /tmp/repro",
            f"env -i PATH=\"$PATH\" HOME=\"$HOME\" {env_line} \\",
            f"  XDG_CONFIG_HOME=/tmp/repro/xdg/config XDG_STATE_HOME=/tmp/repro/xdg/state XDG_CACHE_HOME=/tmp/repro/xdg/cache \\",
            f"  <engine> {' '.join(sh_quote(a) for a in argv)} " + ("< corpus/case.md" if spec["stdin"] else "</dev/null"),
            "```",
            "",
        ]
        if off is not None:
            lines += [
                f"Oracle stdout around byte {off}:",
                "",
                "```",
                hexdump_window(oa, off).rstrip("\n"),
                "```",
                "",
                f"Rust stdout around byte {off}:",
                "",
                "```",
                hexdump_window(ob, off).rstrip("\n"),
                "```",
                "",
            ]
        return "\n".join(lines)


def sh_quote(s: str) -> str:
    return s if re.fullmatch(r"[\w./:@=+-]+", s) else "'" + s.replace("'", "'\\''") + "'"


def fmt_exit(code):
    return "TIMEOUT" if code == TIMEOUT_EXIT else str(code)


def write(path, data: bytes):
    with open(path, "wb") as fh:
        fh.write(data)


def first_diff(a: bytes, b: bytes):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n if len(a) != len(b) else None


def signature(cmd_name, ea, eb, oa, ob) -> str:
    """Dedup key: command + exits + 64 bytes of both sides around first diff."""
    off = first_diff(oa, ob)
    h = hashlib.sha1()
    h.update(f"{cmd_name}|{ea}|{eb}|".encode())
    if off is not None:
        lo = max(0, off - 8)
        h.update(oa[lo:off + 56])
        h.update(b"|")
        h.update(ob[lo:off + 56])
    return h.hexdigest()


def hexdump_window(data: bytes, offset: int) -> str:
    """16-byte rows, hex + printable ASCII, ~4 rows around offset (mirrors the
    parity harness's failure context)."""
    start = max((offset // 16) - 1, 0) * 16
    end = min(start + 4 * 16, len(data))
    out = []
    row = start
    while row < end:
        chunk = data[row:min(row + 16, end)]
        hexes = []
        for i in range(16):
            if i == 8:
                hexes.append("")
            hexes.append(f"{chunk[i]:02x}" if i < len(chunk) else "  ")
        ascii_ = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        out.append(f"{row:08x}  {' '.join(hexes)}  |{ascii_}|")
        row += 16
    if end < len(data):
        out.append(f"... ({len(data) - end} more bytes)")
    if not out:
        out.append("(empty)")
    return "\n".join(out) + "\n"

# ---------------------------------------------------------------------------
# Campaign loop
# ---------------------------------------------------------------------------


def run_round(fz: Fuzzer, corpus: list, seed: int, rnd: int, batch: int, jobs: int):
    """Generate `batch` inputs deterministically, evaluate them across `jobs`
    threads. Returns (divergent_inputs, new_engine_findings, new_crash_findings)."""
    rng = random.Random(f"{seed}:{rnd}")
    inputs = []
    for i in range(batch):
        data, op_names, aux = generate(rng, corpus)
        cmds = build_commands(random.Random(f"{seed}:{rnd}:cmds:{i}"), data)
        inputs.append((i, data, op_names, aux, cmds))

    workers = [Worker(fz.workdir, w) for w in range(jobs)]
    results = []  # (i, n_hits, [(slug, triage)])
    res_lock = threading.Lock()
    idx_lock = threading.Lock()
    cursor = [0]

    def loop(worker: Worker):
        while True:
            with idx_lock:
                if cursor[0] >= len(inputs):
                    return
                item = inputs[cursor[0]]
                cursor[0] += 1
            i, data, op_names, aux, cmds = item
            worker.set_aux(aux)
            hits = fz.check_all(worker, data, cmds)
            filed = []
            for spec, detail, triage in hits:
                slug, t = fz.file_finding(
                    worker, f"seed={seed} round={rnd} case={i}", data, op_names,
                    spec, detail, triage)
                if slug:
                    filed.append((slug, t))
                    print(f"  DIVERGENCE [{t}] -> {os.path.basename(fz.findings_dir)}/{slug}",
                          file=sys.stderr)
            if hits:
                with res_lock:
                    results.append((i, len(hits), filed))

    threads = [threading.Thread(target=loop, args=(w,)) for w in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    n_div_inputs = len(results)
    new_engine = [s for _, _, filed in results for s, t in filed if t == "engine"]
    new_crash = [s for _, _, filed in results for s, t in filed if t == "oracle-crash"]
    return n_div_inputs, new_engine, new_crash


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, required=True, help="master PRNG seed")
    ap.add_argument("--rounds", type=int, default=1, help="number of batches")
    ap.add_argument("--batch", type=int, default=25, help="files per batch")
    ap.add_argument("--jobs", type=int, default=1, help="worker threads")
    ap.add_argument("--oracle", default=DEFAULT_ORACLE)
    ap.add_argument("--engine", default=DEFAULT_ENGINE)
    ap.add_argument("--findings", default=DEFAULT_FINDINGS)
    ap.add_argument("--workdir", default=None, help="scratch dir (default: mkdtemp)")
    ap.add_argument("--log", default=CAMPAIGN_LOG)
    args = ap.parse_args()

    for exe in (args.oracle, args.engine):
        if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
            sys.exit(f"difffuzz: engine not executable: {exe}")

    fz = Fuzzer(args)
    corpus = load_seed_corpus(random.Random(f"corpus:{args.seed}"))
    print(f"difffuzz: seed={args.seed} corpus={len(corpus)} operators={len(OPERATORS)} "
          f"core={len(CORE_COMMANDS)}+{EXTENDED_SAMPLE} jobs={args.jobs} workdir={fz.workdir}",
          file=sys.stderr)

    total_div = 0
    for rnd in range(args.rounds):
        n_div, new_engine, new_crash = run_round(fz, corpus, args.seed, rnd, args.batch, args.jobs)
        total_div += n_div
        line = (f"campaign2 seed={args.seed} round={rnd} batch={args.batch} "
                f"divergent_inputs={n_div} new_engine_findings={len(new_engine)} "
                f"new_oracle_crash_repros={len(new_crash)} "
                f"engine=[{','.join(new_engine)}] crash=[{','.join(new_crash)}]")
        with open(args.log, "a") as fh:
            fh.write(line + "\n")
        print(f"round {rnd}: {line}", file=sys.stderr)

    if args.workdir is None:
        shutil.rmtree(fz.workdir, ignore_errors=True)
    print(f"difffuzz: done — {total_div} divergent inputs "
          f"({args.rounds}x{args.batch} files)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
