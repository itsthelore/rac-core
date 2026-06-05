"""Command-line interface for RAC.

Commands:
    rac validate <file.md> [--json]
    rac diff <old.md> <new.md> [--json]
    rac stats <directory> [--json]
    rac ingest <file> [-o OUT | --stdout] [--force] [--json]
    rac inspect <file.md | -> [--json]
    rac improve <file.md | -> [--json | --template]

Exit codes:
    0  success (incl. inspect/improve reporting Unknown)
    1  validate: errors found; stats: no valid features or decisions;
       ingest: conversion failed
    2  usage / IO error (file not found, not a directory, unsupported type,
       refuse-to-overwrite)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from . import outputs
from .diff import diff as diff_asts
from .ingest import ConversionError, UnsupportedDocument, ingest
from .classification import score_artifacts
from .improve import improve_product
from .inspect import build_inspection, inspect_directory
from .parser import parse, parse_file
from .stats import collect_stats
from .validate import has_errors, validate

EXIT_OK = 0
EXIT_VALIDATION_FAILED = 1
EXIT_USAGE = 2


def _read(path: str):
    """Parse a file, or print an error and exit with EXIT_USAGE."""
    try:
        return parse_file(path)
    except FileNotFoundError:
        print(f"rac: file not found: {path}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    except OSError as exc:
        print(f"rac: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def cmd_validate(args: argparse.Namespace) -> int:
    product = _read(args.file)
    issues = validate(product)
    if args.json:
        print(outputs.render_validation_json(product, issues))
    else:
        print(outputs.render_validation_human(product, issues))
    return EXIT_VALIDATION_FAILED if has_errors(issues) else EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    old = _read(args.old)
    new = _read(args.new)
    result = diff_asts(old, new)
    if args.json:
        print(outputs.render_diff_json(result, args.old, args.new))
    else:
        print(outputs.render_diff_human(result, args.old, args.new))
    return EXIT_OK


def cmd_stats(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    stats = collect_stats(args.directory)
    if args.json:
        print(outputs.render_stats_json(stats))
    else:
        print(outputs.render_stats_human(stats))
    # Success as long as the portfolio has analysable content: at least one valid
    # feature or at least one decision. Invalid files are reported but don't fail
    # the run on their own. (A future --strict flag will fail the run if *any*
    # file is invalid, for CI use.)
    has_content = stats.valid_features > 0 or stats.decision_count > 0
    return EXIT_OK if has_content else EXIT_VALIDATION_FAILED


def cmd_ingest(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"rac: file not found: {args.file}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    try:
        result = ingest(args.file)
    except UnsupportedDocument as exc:  # unhandled type / missing extra
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    except ConversionError as exc:  # recognized file, failed to convert
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED

    if args.output:
        out = Path(args.output)
        if out.exists() and not args.force:
            print(
                f"rac: {args.output} already exists; pass --force to overwrite",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_USAGE)
        out.write_text(result.markdown, encoding="utf-8")
        if args.json:
            print(outputs.render_ingest_json(result, str(out)))
        else:
            print(
                f"Wrote {out} ({len(result.markdown)} chars, via {result.converter}).",
                file=sys.stderr,
            )
    else:
        # No -o (or explicit --stdout): preview the converted Markdown on stdout.
        if args.json:
            print(outputs.render_ingest_json(result, None))
        else:
            print(result.markdown)
    return EXIT_OK


def _read_markdown_input(target: str, command: str) -> str:
    """Read a Markdown file or stdin (``-``) for ``command`` (inspect/improve)."""
    if target == "-":
        return sys.stdin.read()
    path = Path(target)
    if not path.is_file():
        print(f"rac: file not found: {target}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    if path.suffix.lower() not in (".md", ".markdown"):
        print(
            f"rac: {command} expects a Markdown file; "
            f"convert it first with: rac ingest {target}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"rac: cannot read {target}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def cmd_inspect(args: argparse.Namespace) -> int:
    # Directory? Aggregate per-file results into type counts.
    if args.file != "-" and Path(args.file).is_dir():
        recursive = not args.top_level
        result = inspect_directory(args.file, recursive=recursive)
        if args.json:
            print(outputs.render_dir_inspect_json(result))
        else:
            print(outputs.render_dir_inspect_human(result))
        return EXIT_OK

    # Single file (or stdin).
    text = _read_markdown_input(args.file, "inspect")
    product = parse(text)
    result = build_inspection(product)
    if args.verbose and not args.json:
        print(outputs.render_inspect_verbose(result, score_artifacts(product)))
    elif args.json:
        print(outputs.render_inspect_json(result))
    else:
        print(outputs.render_inspect_human(result))
    # A completed inspection always succeeds — Unknown is a valid outcome.
    return EXIT_OK


def cmd_improve(args: argparse.Namespace) -> int:
    text = _read_markdown_input(args.file, "improve")
    result = improve_product(parse(text))
    if args.json:
        print(outputs.render_improve_json(result))
    elif args.template:
        print(outputs.render_improve_template(result))
    else:
        print(outputs.render_improve_human(result))
    # Advisory: a completed analysis always succeeds, with or without suggestions.
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    version_str = f"rac {__version__}"

    # Shared parent so `--version` works on the root parser *and* every
    # subcommand (e.g. `rac ingest foo.docx --version`).
    version_parent = argparse.ArgumentParser(add_help=False)
    version_parent.add_argument(
        "--version", action="version", version=version_str
    )

    parser = argparse.ArgumentParser(
        prog="rac",
        description="Requirements As Code — lint and diff Markdown requirements.",
        parents=[version_parent],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate",
        help="Validate a single requirement file.",
        parents=[version_parent],
    )
    p_validate.add_argument("file", help="Path to the requirement Markdown file.")
    p_validate.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_validate.set_defaults(func=cmd_validate)

    p_diff = sub.add_parser(
        "diff",
        help="Compare two versions of a requirement file.",
        parents=[version_parent],
    )
    p_diff.add_argument("old", help="Path to the old version.")
    p_diff.add_argument("new", help="Path to the new version.")
    p_diff.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_diff.set_defaults(func=cmd_diff)

    p_stats = sub.add_parser(
        "stats",
        help="Summarize a directory of requirement files.",
        parents=[version_parent],
    )
    p_stats.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_stats.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_stats.set_defaults(func=cmd_stats)

    p_ingest = sub.add_parser(
        "ingest",
        help="Convert a document (DOCX, PDF, HTML, PPTX, XLSX, Markdown) to Markdown.",
        parents=[version_parent],
    )
    p_ingest.add_argument("file", help="Path to the source document.")
    ingest_dest = p_ingest.add_mutually_exclusive_group()
    ingest_dest.add_argument(
        "-o", "--output", help="Write Markdown here instead of printing it."
    )
    ingest_dest.add_argument(
        "--stdout",
        action="store_true",
        help="Write Markdown to stdout (the default; explicit for pipelines).",
    )
    p_ingest.add_argument(
        "--force", action="store_true", help="Overwrite the output file if it exists."
    )
    p_ingest.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_inspect = sub.add_parser(
        "inspect",
        help="Identify a Markdown document's artifact type and structure.",
        parents=[version_parent],
    )
    p_inspect.add_argument(
        "file",
        help="A Markdown file, a directory, or '-' to read from stdin.",
    )
    p_inspect.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_inspect.add_argument(
        "--verbose",
        action="store_true",
        help="Show the classification breakdown and score (single file only).",
    )
    p_inspect.add_argument(
        "--top-level",
        action="store_true",
        help="When inspecting a directory, only its top-level files (no recursion).",
    )
    p_inspect.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_inspect.set_defaults(func=cmd_inspect)

    p_improve = sub.add_parser(
        "improve",
        help="Suggest missing sections (and templates) for an artifact.",
        parents=[version_parent],
    )
    p_improve.add_argument(
        "file",
        help="A Markdown file, or '-' to read from stdin.",
    )
    improve_mode = p_improve.add_mutually_exclusive_group()
    improve_mode.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    improve_mode.add_argument(
        "--template",
        action="store_true",
        help="Emit Markdown templates for the missing sections.",
    )
    p_improve.set_defaults(func=cmd_improve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
