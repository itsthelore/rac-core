"""Command-line interface for RAC.

Commands:
    rac validate <file.md> [--json]
    rac diff <old.md> <new.md> [--json]
    rac stats <directory> [--json]

Exit codes:
    0  success (validate: no errors; diff: ran; stats: >=1 valid feature)
    1  validate: errors found; stats: no valid features in the directory
    2  usage / IO error (e.g. file not found, path is not a directory)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from . import outputs
from .diff import diff as diff_asts
from .parser import parse_file
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
    # Success as long as the portfolio has at least one valid feature. Invalid
    # files are reported but don't fail the run on their own. (A future --strict
    # flag will fail the run if *any* file is invalid, for CI use.)
    return EXIT_OK if stats.valid_features > 0 else EXIT_VALIDATION_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rac",
        description="Requirements As Code — lint and diff Markdown requirements.",
    )
    parser.add_argument("--version", action="version", version=f"rac {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate", help="Validate a single requirement file."
    )
    p_validate.add_argument("file", help="Path to the requirement Markdown file.")
    p_validate.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_validate.set_defaults(func=cmd_validate)

    p_diff = sub.add_parser(
        "diff", help="Compare two versions of a requirement file."
    )
    p_diff.add_argument("old", help="Path to the old version.")
    p_diff.add_argument("new", help="Path to the new version.")
    p_diff.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_diff.set_defaults(func=cmd_diff)

    p_stats = sub.add_parser(
        "stats", help="Summarize a directory of requirement files."
    )
    p_stats.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_stats.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_stats.set_defaults(func=cmd_stats)

    # Future command (rac review <file>) will register here.
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
