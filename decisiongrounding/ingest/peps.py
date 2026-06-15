"""Deterministic ingest of real Python PEPs into corpus artifacts.

Real/public-derived corpus material (CONTRIBUTING.md rule 2). PEP sources are
pinned to one immutable commit of `python/peps`, so the corpus is byte-for-byte
reproducible and auditable — nothing here is hand-written PEP prose.

    python -m ingest.peps build  --out scenarios_real/peps_version_supersession
    python -m ingest.peps verify --out scenarios_real/peps_version_supersession

`build` fetches each pinned PEP and writes:

* `corpus/PEP-XXXX.md` — a short provenance preamble plus the verbatim upstream
  reStructuredText, and
* `provenance.json` — per-PEP source URL, sha256 of the upstream `.rst`, the
  parsed RFC-2822 headers, and the supersedes edges *derived from those headers*
  (`Superseded-By` / `Replaces`).

`verify` re-fetches at the same pin and fails if any committed corpus file no
longer reproduces from the recorded upstream bytes — catching both upstream
drift and local tampering.

The task and gold label in `scenario.json` are authored by hand, blind to arm
outputs (rule 1). This tool never writes them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

# One immutable commit of python/peps. Bumping this is a deliberate, reviewable
# act (it changes the corpus); never float it to a branch name.
PINNED_COMMIT = "f866e77409305866038471574f075cd8d83eee9e"
SOURCE_REPO = "python/peps"
_RAW = "https://raw.githubusercontent.com/{repo}/{sha}/peps/pep-{num:04d}.rst"

# The pilot corpus: the real PEP supersession pair. PEP 440 (Final) Replaces
# PEP 386 (Superseded); both edges are stated in the artifacts' own headers.
PILOT_PEPS = (386, 440)


def pep_id(num: int) -> str:
    """Stable corpus artifact id for a PEP number (e.g. 386 -> 'PEP-0386')."""
    return f"PEP-{num:04d}"


def source_url(num: int, sha: str = PINNED_COMMIT) -> str:
    return _RAW.format(repo=SOURCE_REPO, sha=sha, num=num)


def fetch_pep(num: int, sha: str = PINNED_COMMIT, timeout: float = 20.0) -> str:
    """Fetch one PEP's reStructuredText at the pinned commit."""
    url = source_url(num, sha)
    req = urllib.request.Request(url, headers={"User-Agent": "decisiongrounding-ingest"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - pinned host
        return resp.read().decode("utf-8")


def parse_headers(rst: str) -> dict[str, str]:
    """Parse the RFC-2822-style PEP header block (everything before the first
    blank line). Continuation lines (leading whitespace) fold into the prior
    field, matching how PEP tooling reads multi-line Author/Post-History values.
    """
    headers: dict[str, str] = {}
    last_key: str | None = None
    for line in rst.splitlines():
        if line.strip() == "":
            break
        if line[:1].isspace() and last_key is not None:
            headers[last_key] = f"{headers[last_key]} {line.strip()}".strip()
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        last_key = key.strip()
        headers[last_key] = value.strip()
    return headers


def _header_numbers(headers: dict[str, str], key: str) -> list[int]:
    """PEP numbers from a comma-separated header value (e.g. 'Replaces: 386')."""
    raw = headers.get(key, "")
    return [int(tok) for tok in raw.replace(",", " ").split() if tok.isdigit()]


def supersedes_targets(headers: dict[str, str]) -> list[int]:
    """PEP numbers this PEP supersedes, per its own headers.

    A `Replaces:` header on the newer PEP and a `Superseded-By:` header on the
    older PEP both encode the same edge; we read `Replaces` as the authoritative
    forward edge (newer -> older).
    """
    return _header_numbers(headers, "Replaces")


def corpus_markdown(num: int, rst: str, sha: str = PINNED_COMMIT) -> str:
    """A corpus artifact: provenance preamble + verbatim upstream PEP text."""
    title = parse_headers(rst).get("Title", "").strip()
    heading = f"# {pep_id(num)} — {title}" if title else f"# {pep_id(num)}"
    preamble = (
        f"{heading}\n\n"
        f"> Source: {SOURCE_REPO} @ {sha}\n"
        f"> Path: peps/pep-{num:04d}.rst · {source_url(num, sha)}\n"
        f"> Verbatim public artifact, pinned and unedited. Not authored for this\n"
        f"> benchmark; see provenance.json for the upstream sha256.\n\n"
        f"---\n\n"
    )
    return preamble + rst


def build_provenance(peps: tuple[int, ...], texts: dict[int, str], sha: str) -> dict:
    """The auditable record: per-PEP hashes, headers, and derived edges."""
    entries = []
    edges = []
    for num in peps:
        rst = texts[num]
        headers = parse_headers(rst)
        replaces = supersedes_targets(headers)
        entries.append(
            {
                "id": pep_id(num),
                "number": num,
                "file": f"corpus/{pep_id(num)}.md",
                "url": source_url(num, sha),
                "source_sha256": hashlib.sha256(rst.encode("utf-8")).hexdigest(),
                "status": headers.get("Status", ""),
                "title": headers.get("Title", ""),
                "replaces": [pep_id(n) for n in replaces],
                "superseded_by": [pep_id(n) for n in _header_numbers(headers, "Superseded-By")],
            }
        )
        for target in replaces:
            if target in peps:
                edges.append({"source": pep_id(num), "type": "supersedes", "target": pep_id(target)})
    return {
        "source_repo": SOURCE_REPO,
        "pinned_commit": sha,
        "peps": entries,
        "supersedes_edges": edges,
    }


def build(out_dir: Path, peps: tuple[int, ...] = PILOT_PEPS, sha: str = PINNED_COMMIT) -> dict:
    """Fetch the pinned PEPs and write corpus files + provenance.json."""
    corpus_dir = out_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    texts = {num: fetch_pep(num, sha) for num in peps}
    for num in peps:
        (corpus_dir / f"{pep_id(num)}.md").write_text(
            corpus_markdown(num, texts[num], sha), encoding="utf-8"
        )
    provenance = build_provenance(peps, texts, sha)
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def verify(out_dir: Path) -> list[str]:
    """Re-fetch at the recorded pin; return a list of integrity problems (empty
    means the committed corpus reproduces exactly from the upstream bytes)."""
    provenance = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))
    sha = provenance["pinned_commit"]
    problems: list[str] = []
    for entry in provenance["peps"]:
        num = entry["number"]
        try:
            rst = fetch_pep(num, sha)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            problems.append(f"{entry['id']}: fetch failed: {exc}")
            continue
        got = hashlib.sha256(rst.encode("utf-8")).hexdigest()
        if got != entry["source_sha256"]:
            problems.append(
                f"{entry['id']}: upstream sha256 changed ({got} != {entry['source_sha256']})"
            )
        expected_md = corpus_markdown(num, rst, sha)
        actual_md = (out_dir / entry["file"]).read_text(encoding="utf-8")
        if expected_md != actual_md:
            problems.append(f"{entry['id']}: committed {entry['file']} does not match upstream bytes")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest.peps", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("build", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("--out", required=True, help="scenario directory to write/verify")
        if name == "build":
            sp.add_argument(
                "--peps",
                default=",".join(str(n) for n in PILOT_PEPS),
                help="comma-separated PEP numbers (default: the pilot pair 386,440)",
            )
    args = parser.parse_args(argv)
    out_dir = Path(args.out)

    if args.cmd == "build":
        peps = tuple(int(x) for x in args.peps.split(",") if x.strip())
        provenance = build(out_dir, peps)
        print(f"wrote {len(peps)} PEP corpus file(s) + provenance.json to {out_dir}")
        for edge in provenance["supersedes_edges"]:
            print(f"  edge: {edge['source']} supersedes {edge['target']}")
        return 0

    problems = verify(out_dir)
    if problems:
        print("verify FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"verify OK: corpus in {out_dir} reproduces from {SOURCE_REPO}@{PINNED_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
