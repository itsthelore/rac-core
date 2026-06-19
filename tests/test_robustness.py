"""Parser and bounded-traversal robustness battery (v0.23.0, WS4).

Adversarial input must never crash, hang, or exhaust memory: oversize files and
fields, alias-bombed / deeply nested front matter, non-UTF-8 bytes, ReDoS-style
strings, and high-fan-out / cyclic relationship graphs are all reported as
structured data and bounded. Determinism is load-bearing — the fuzz pass runs
from a fixed seed with a pinned iteration count and no network (REQ-009).
"""

from __future__ import annotations

import asyncio
import json
import random
import time

from rac.core import markdown as md_mod
from rac.core.frontmatter import parse_frontmatter
from rac.core.markdown import _BRACKET_RE, _CANONICAL_ID_RE, parse, parse_file
from rac.core.metadata import ID_RE
from rac.core.validation import (
    _AMBIGUOUS_RE,
    _EARS_IF_RE,
    _NORMATIVE_RE,
    _QUARTER_RE,
    _THEN_RE,
)
from rac.mcp.server import build_server
from rac.services import relationships as rel_mod
from rac.services.resolve import find_artifacts

DECISION = (
    "---\nschema_version: 1\nid: {id}\ntype: decision\n---\n# {title}\n\n"
    "## Status\n\nAccepted\n\n## Context\n\n{context}\n\n## Decision\n\nDo it.\n\n"
    "## Consequences\n\nFine.\n{supersedes}"
)
REQUIREMENT = (
    "---\nschema_version: 1\nid: {id}\ntype: requirement\n---\n# {title}\n\n"
    "## Problem\n\nx\n\n## Requirements\n\n- [REQ-001] The system MUST do it.\n{related}"
)


def _decision(root, name, aid, *, context="Background.", supersedes=None):
    body = DECISION.format(
        id=aid,
        title=name,
        context=context,
        supersedes=f"\n## Supersedes\n\n- {supersedes}\n" if supersedes else "",
    )
    (root / f"{name}.md").write_text(body, encoding="utf-8")


def _requirement(root, name, aid, *, related=None):
    rel = (
        "\n## Related Decisions\n\n" + "\n".join(f"- {r}" for r in related) + "\n"
        if related
        else ""
    )
    (root / f"{name}.md").write_text(
        REQUIREMENT.format(id=aid, title=name, related=rel), encoding="utf-8"
    )


def _suffix(i: int) -> str:
    # A valid 12-char Crockford suffix (no I/L/O/U) from an index.
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    out = ""
    n = i
    for _ in range(12):
        out = alphabet[n % 32] + out
        n //= 32
    return out


def _get_related(root, artifact_id, budget=1_000_000_000):
    server = build_server(str(root), budget=budget)
    contents, _ = asyncio.run(server.call_tool("get_related", {"id": artifact_id}))
    return json.loads(contents[0].text)


# --- REQ-001: per-file / per-parse byte cap ----------------------------------


def test_oversize_file_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("RAC_MAX_FILE_BYTES", "512")
    big = tmp_path / "big.md"
    big.write_text("# T\n\n" + ("x " * 1000), encoding="utf-8")
    product = parse_file(str(big))  # must not raise
    assert [i.code for i in product.parse_issues] == ["artifact-oversize"]
    assert product.parse_issues[0].severity == "error"


def test_in_memory_parse_rejects_oversize(monkeypatch):
    monkeypatch.setattr(md_mod, "max_file_bytes", lambda: 256)
    product = parse("# T\n\n" + ("word " * 500))
    assert any(i.code == "artifact-oversize" for i in product.parse_issues)


def test_normal_file_has_no_parse_issues(tmp_path):
    _decision(tmp_path, "ok", "RAC-AAAAAAAAAAAA")
    assert parse_file(str(tmp_path / "ok.md")).parse_issues == []


# --- REQ-002: front-matter caps (size, depth, alias bomb) --------------------


def test_alias_bomb_is_reported_not_raised():
    bomb = "a: &x [1, 1, 1, 1]\nb: *x\nc: *x\n"
    metadata, issues = parse_frontmatter(bomb)
    assert metadata is None
    assert [i.code for i in issues] == ["malformed-frontmatter"]


def test_billion_laughs_terminates_quickly():
    # Classic alias-expansion bomb; aliases are forbidden, so it is rejected
    # immediately instead of expanding.
    lol = "a: &a [x,x,x,x,x,x,x,x,x]\n" + "".join(
        f"{c}: [&{c} *{chr(ord(c) - 1)}]\n" for c in "bcdefgh"
    )
    start = time.monotonic()
    metadata, issues = parse_frontmatter(lol)
    assert time.monotonic() - start < 1.0
    assert metadata is None and issues


def test_deep_nesting_is_reported_not_raised():
    deep = "k: " + ("[" * 500) + "1" + ("]" * 500) + "\n"
    metadata, issues = parse_frontmatter(deep)
    assert metadata is None
    assert [i.code for i in issues] == ["malformed-frontmatter"]


def test_oversize_frontmatter_is_reported():
    raw = "schema_version: 1\nblob: " + ("a" * (70 << 10)) + "\n"
    metadata, issues = parse_frontmatter(raw)
    assert metadata is None
    assert [i.code for i in issues] == ["malformed-frontmatter"]


def test_duplicate_key_rejection_still_works():
    metadata, issues = parse_frontmatter("schema_version: 1\nschema_version: 2\n")
    assert metadata is None
    assert issues[0].code == "duplicate-frontmatter-key"


# --- REQ-003: body field caps ------------------------------------------------


def test_oversized_field_is_truncated_not_failed(monkeypatch):
    monkeypatch.setattr(md_mod, "MAX_FIELD_CHARS", 100)
    text = "# T\n\n## Context\n\n" + "\n".join(f"line {i} " * 5 for i in range(50))
    product = parse(text)
    assert any(i.code == "field-truncated" for i in product.parse_issues)


def test_total_line_cap_truncates_body(monkeypatch):
    monkeypatch.setattr(md_mod, "MAX_CAPTURED_LINES", 10)
    text = "# T\n\n## Context\n\n" + "\n".join(f"x{i}" for i in range(100))
    product = parse(text)
    assert any(i.code == "body-truncated" for i in product.parse_issues)


# --- REQ-004: regex linearity + query input is never a regex -----------------

_CONTENT_REGEXES = {
    "_BRACKET_RE": _BRACKET_RE,
    "_CANONICAL_ID_RE": _CANONICAL_ID_RE,
    "ID_RE": ID_RE,
    "_AMBIGUOUS_RE": _AMBIGUOUS_RE,
    "_NORMATIVE_RE": _NORMATIVE_RE,
    "_EARS_IF_RE": _EARS_IF_RE,
    "_THEN_RE": _THEN_RE,
    "_QUARTER_RE": _QUARTER_RE,
}


def test_content_regexes_are_linear_time():
    # A pathological string against each content-applied regex must terminate
    # fast — none uses nested quantifiers or overlapping alternation (REQ-004).
    adversarial = ("a" * 50_000) + " shall if then Q1 " + ("!" * 50_000)
    for name, pattern in _CONTENT_REGEXES.items():
        start = time.monotonic()
        pattern.search(adversarial)
        pattern.match(adversarial)
        assert time.monotonic() - start < 0.5, name


def test_query_input_is_matched_literally_not_compiled(tmp_path):
    # A regex-bomb query must be tokenized and compared literally, never compiled
    # — so it cannot hang the matcher or raise re.error (REQ-004).
    _decision(tmp_path, "alpha", "RAC-AAAAAAAAAAAA")
    start = time.monotonic()
    result = find_artifacts(str(tmp_path), "(a+)+$" + ("a" * 1000))
    assert time.monotonic() - start < 1.0
    assert result.match_count == 0  # no artifact contains those tokens


# --- REQ-005: graceful degradation; the walk continues -----------------------


def test_walk_continues_past_malformed_and_binary(tmp_path, monkeypatch):
    from rac.core.corpus import walk_corpus

    monkeypatch.setenv("RAC_MAX_FILE_BYTES", "2048")
    _decision(tmp_path, "good", "RAC-AAAAAAAAAAAA")
    (tmp_path / "binary.md").write_bytes(b"\xff\xfe\x00\x01 not utf8 \x80\x81")
    (tmp_path / "huge.md").write_text("# H\n\n" + ("z " * 4000), encoding="utf-8")
    entries = list(walk_corpus(str(tmp_path)))  # must not raise
    assert len(entries) == 3
    # The good artifact parsed cleanly; the bad ones carry structured issues.
    by_name = {e.path.name: e for e in entries}
    assert by_name["good.md"].product.parse_issues == []
    assert any(i.code == "non-utf8-content" for i in by_name["binary.md"].product.parse_issues)
    assert any(i.code == "artifact-oversize" for i in by_name["huge.md"].product.parse_issues)


def test_get_related_does_not_crash_on_corpus_with_malformed(tmp_path):
    _decision(tmp_path, "good", "RAC-AAAAAAAAAAAA")
    (tmp_path / "binary.md").write_bytes(b"\xff\xfe rubbish \x80")
    payload = _get_related(tmp_path, "RAC-AAAAAAAAAAAA")  # must not raise
    assert payload["id"] == "RAC-AAAAAAAAAAAA"
    assert payload["incoming"] == []


# --- REQ-006/007/008: bounded, ordered get_related ---------------------------


def test_high_fan_out_hub_is_capped_and_marked(tmp_path, monkeypatch):
    monkeypatch.setattr(rel_mod, "MAX_RELATED_EDGES", 3)
    _decision(tmp_path, "hub", "RAC-AAAAAAAAAAAA")
    referrers = 8
    for i in range(referrers):
        _requirement(tmp_path, f"ref{i}", f"RAC-{_suffix(i + 1)}", related=["RAC-AAAAAAAAAAAA"])
    payload = _get_related(tmp_path, "RAC-AAAAAAAAAAAA")
    assert len(payload["incoming"]) == 3  # capped
    assert payload["truncated"] is True
    assert payload["omitted"] == referrers - 3
    # Ordered by relationship type then ascending id (REQ-006), byte-stable.
    ids = [e["id"] for e in payload["incoming"]]
    assert ids == sorted(ids)


def test_get_related_byte_identical_on_adversarial_corpus(tmp_path):
    # A cycle (mutual supersedes), a self-reference attempt, and a small hub.
    _decision(tmp_path, "one", "RAC-AAAAAAAAAAAA", supersedes="RAC-BBBBBBBBBBBB")
    _decision(tmp_path, "two", "RAC-BBBBBBBBBBBB", supersedes="RAC-AAAAAAAAAAAA")
    for i in range(5):
        _requirement(tmp_path, f"r{i}", f"RAC-{_suffix(i + 1)}", related=["RAC-AAAAAAAAAAAA"])
    first = _get_related(tmp_path, "RAC-AAAAAAAAAAAA")
    second = _get_related(tmp_path, "RAC-AAAAAAAAAAAA")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# --- REQ-009: deterministic fuzz, no network ---------------------------------


def test_parser_fuzz_never_raises():
    rng = random.Random(1337)  # fixed seed -> reproducible from the recorded value
    alphabet = "abcXYZ-_:[]{}&*#\n \t01é中"
    for _ in range(300):
        n = rng.randint(0, 4000)
        text = "".join(rng.choice(alphabet) for _ in range(n))
        # Half the cases get a frontmatter-ish leading block.
        if rng.random() < 0.5:
            text = (
                "---\n"
                + "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 200)))
                + "\n---\n"
                + text
            )
        product = parse(text)  # must never raise
        assert product is not None
        # And the raw frontmatter parser tolerates arbitrary bytes-as-text.
        parse_frontmatter(text[:2000])


def test_parser_fuzz_handles_binary_decoded_text():
    rng = random.Random(7)
    for _ in range(100):
        blob = bytes(rng.randint(0, 255) for _ in range(rng.randint(0, 2000)))
        parse(blob.decode("utf-8", errors="replace"))  # must never raise
