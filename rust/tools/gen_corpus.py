#!/usr/bin/env python3
"""Deterministic synthetic RAC corpus generator (stdlib only).

Generates N artifacts across the five RAC types (requirement, decision,
roadmap, prompt, design) with realistic per-type sections and real
cross-references (by filename stem, so relationships/resolve have work to do).
Fully deterministic: a fixed seed drives every choice; no wall-clock content.

Usage:
    python3 gen_corpus.py --n 1000 --out <dir> [--seed 1234]

The layout is one subdirectory per type. References target earlier artifacts
of the matching type so they resolve to exactly one path.
"""

import argparse
import os
import random
import shutil
import sys

# Crockford base32, uppercase, excluding I, L, O, U (matches metadata.ID_RE
# suffix class [0-9A-HJKMNP-TV-Z]).
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

TYPES = ["requirement", "decision", "roadmap", "prompt", "design"]

# Filename prefix per type (`<letters>-<digits>` so the prefix is an alias).
PREFIX = {
    "requirement": "req",
    "decision": "adr",
    "roadmap": "rm",
    "prompt": "prm",
    "design": "dz",
}

# Sections written per type: (heading, kind). kind drives body generation.
# Required + a couple recommended, then relationship sections are added
# separately. Values chosen to validate cleanly (valid status/category enums).
SECTIONS = {
    "requirement": [
        ("Problem", "para"),
        ("Requirements", "reqs"),
        ("Success Metrics", "para"),
        ("Risks", "bullets"),
        ("Assumptions", "bullets"),
        ("Status", "status:requirement"),
    ],
    "decision": [
        ("Context", "para"),
        ("Decision", "para"),
        ("Consequences", "para"),
        ("Status", "status:decision"),
        ("Category", "category:decision"),
        ("Alternatives Considered", "bullets"),
    ],
    "roadmap": [
        ("Outcomes", "bullets"),
        ("Initiatives", "bullets"),
        ("Success Measures", "para"),
        ("Assumptions", "bullets"),
        ("Risks", "bullets"),
        ("Status", "status:roadmap"),
    ],
    "prompt": [
        ("Objective", "para"),
        ("Input", "para"),
        ("Instructions", "bullets"),
        ("Output", "para"),
        ("Constraints", "bullets"),
        ("Evaluation", "para"),
        ("Status", "status:prompt"),
    ],
    "design": [
        ("Context", "para"),
        ("User Need", "para"),
        ("Design", "para"),
        ("Constraints", "bullets"),
        ("Rationale", "para"),
        ("Accessibility", "para"),
        ("Status", "status:design"),
    ],
}

# Non-retired status values (keep the corpus mostly clean / non-superseded).
STATUS = {
    "requirement": "Accepted",
    "decision": "Accepted",
    "roadmap": "Planned",
    "prompt": "Active",
    "design": "Accepted",
}
CATEGORY = ["Architecture", "Product", "Process", "Technical", "Other"]

# Relationship section name -> target type, per source type. Kept type-correct
# so references never trip relationship-target-type-mismatch.
REL_SECTIONS = {
    "requirement": [("Related Decisions", "decision"), ("Related Roadmaps", "roadmap")],
    "decision": [("Related Requirements", "requirement"), ("Related Roadmaps", "roadmap")],
    "roadmap": [("Related Requirements", "requirement"), ("Related Decisions", "decision")],
    "prompt": [("Related Requirements", "requirement"), ("Related Decisions", "decision")],
    "design": [("Related Requirements", "requirement"), ("Related Decisions", "decision")],
}

WORDS = [
    "corpus", "artifact", "validation", "classifier", "pipeline", "roadmap",
    "decision", "requirement", "prompt", "design", "engine", "parser",
    "relationship", "resolver", "schema", "export", "review", "cache",
    "walk", "identity", "frontmatter", "markdown", "throughput", "latency",
    "boundary", "deterministic", "contract", "gate", "ingest", "recency",
]
# A little Unicode to exercise casefold / utf-8 paths (kept out of filenames).
UNICODE_BITS = [
    "café", "naïve", "Straße", "résumé", "façade", "ÿ", "Ω-tuning",
    "日本語", "über", "mañana", "—em-dash—", "middle·dot",
]


def crockford_id(rng, index):
    """12-char Crockford suffix; last 3 chars encode index → globally unique."""
    prefix = "".join(rng.choice(CROCKFORD) for _ in range(9))
    n = index
    tail = ""
    for _ in range(3):
        tail = CROCKFORD[n % 32] + tail
        n //= 32
    return "RAC-" + prefix + tail


def slug(rng):
    return "-".join(rng.choice(WORDS) for _ in range(rng.randint(2, 4)))


def sentence(rng, unicode_ok=True):
    n = rng.randint(6, 16)
    parts = [rng.choice(WORDS) for _ in range(n)]
    if unicode_ok and rng.random() < 0.35:
        parts.insert(rng.randint(0, len(parts)), rng.choice(UNICODE_BITS))
    s = " ".join(parts)
    return s[0].upper() + s[1:] + "."


def paragraph(rng):
    return " ".join(sentence(rng) for _ in range(rng.randint(2, 4)))


def bullets(rng):
    return "\n".join("- " + sentence(rng) for _ in range(rng.randint(2, 5)))


def reqs_body(rng):
    lines = []
    for i in range(1, rng.randint(3, 6)):
        lines.append(f"- [REQ-{i:03d}] The system must {sentence(rng).lower()}")
    return "\n".join(lines)


def render_body(rng, artifact_type, kind):
    if kind == "para":
        return paragraph(rng)
    if kind == "bullets":
        return bullets(rng)
    if kind == "reqs":
        return reqs_body(rng)
    if kind.startswith("status:"):
        return STATUS[artifact_type]
    if kind.startswith("category:"):
        return rng.choice(CATEGORY)
    return paragraph(rng)


def build_artifact(rng, artifact_type, index, by_type):
    aid = crockford_id(rng, index)
    tags = sorted({rng.choice(WORDS) for _ in range(rng.randint(1, 3))})
    title_kind = artifact_type.capitalize()
    title = f"{title_kind} {index}: {slug(rng).replace('-', ' ').title()}"
    if rng.random() < 0.2:
        title += f" ({rng.choice(UNICODE_BITS)})"

    lines = [
        "---",
        "schema_version: 1",
        f"id: {aid}",
        f"type: {artifact_type}",
        "tags: [" + ", ".join(tags) + "]",
        "---",
        "",
        f"# {title}",
        "",
    ]
    for heading, kind in SECTIONS[artifact_type]:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(render_body(rng, artifact_type, kind))
        lines.append("")

    # Relationship sections referencing earlier artifacts of the target type.
    for heading, target_type in REL_SECTIONS[artifact_type]:
        pool = by_type.get(target_type, [])
        if not pool:
            continue
        k = min(len(pool), rng.randint(1, 3))
        picks = rng.sample(pool, k)
        if not picks:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        for target_stem in picks:
            lines.append(f"- {target_stem}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate a synthetic RAC corpus.")
    ap.add_argument("--n", type=int, required=True, help="number of artifacts")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--seed", type=int, default=20260711)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    dirmap = {
        "requirement": "requirements",
        "decision": "decisions",
        "roadmap": "roadmaps",
        "prompt": "prompts",
        "design": "designs",
    }
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    for sub in dirmap.values():
        os.makedirs(os.path.join(out, sub))

    # Weighted mix: more requirements/decisions than the rest.
    weights = {"requirement": 3, "decision": 3, "roadmap": 1, "prompt": 2, "design": 2}
    bag = []
    for t, w in weights.items():
        bag += [t] * w
    plan = [bag[i % len(bag)] for i in range(args.n)]
    # Deterministic shuffle so types interleave.
    rng.shuffle(plan)

    by_type = {t: [] for t in TYPES}
    counters = {t: 0 for t in TYPES}
    written = 0
    for index in range(args.n):
        atype = plan[index]
        counters[atype] += 1
        stem = f"{PREFIX[atype]}-{counters[atype]:05d}-{slug(rng)}"
        content = build_artifact(rng, atype, index, by_type)
        path = os.path.join(out, dirmap[atype], stem + ".md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        by_type[atype].append(stem)
        written += 1

    print(f"wrote {written} artifacts to {out}", file=sys.stderr)
    for t in TYPES:
        print(f"  {t:12s} {len(by_type[t])}", file=sys.stderr)


if __name__ == "__main__":
    main()
