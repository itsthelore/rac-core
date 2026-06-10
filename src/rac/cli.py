"""Command-line interface for RAC.

Commands:
    rac validate <file.md | dir | -> [--json] [--top-level]
    rac diff <old.md> <new.md> [--json]
    rac stats <directory> [--json]
    rac ingest <file> [-o OUT | --stdout] [--force] [--json]
    rac inspect <file.md | -> [--json]
    rac improve <file.md | -> [--json | --template]
    rac schema [--list] [type] [--json | --template]
    rac relationships <dir | file.md> [--validate] [--json] [--top-level]
    rac review <directory> [--json] [--top-level]
    rac portfolio <directory> [--json] [--top-level]
    rac index [directory] [--json] [--top-level]
    rac explorer [directory] [--top-level]
    rac new <artifact-type> <output-path> [--json]
    rac templates [--json]
    rac init [directory] [--key KEY] [--json]
    rac resolve <ID> [directory] [--json]
    rac find <query> [directory] [--type TYPE] [--json]
    rac migrate metadata <directory> [--dry-run] [--json]

Exit codes:
    0  success (incl. inspect/improve reporting Unknown; relationships found or
       not; --validate with all references resolved; portfolio summary produced;
       index produced; artifact created; templates listed; find with or without
       matches; migration or dry run completed, even with nothing to migrate;
       explorer session quit by the user)
    1  validate: errors found; stats: no valid known artifacts; ingest:
       conversion failed; relationships --validate: broken/ambiguous/self
       references or duplicate identifiers found; review: invalid artifacts
       or broken relationships found (priority 1-2 issues); new: packaged
       template missing (broken installation) or malformed repository config;
       init: established key conflicts with the requested one; resolve:
       artifact not found or duplicate ID; migrate: malformed repository
       config or ID generation exhausted
    2  usage / IO error (file not found, not a directory, unsupported type,
       refuse-to-overwrite, missing output directory, repository not
       initialized, invalid repository key, explorer extra not installed)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rac import output as outputs
from rac.core.classification import score_artifacts
from rac.core.markdown import parse, parse_file
from rac.core.models import Product
from rac.core.schema import available_schemas, schema_reference
from rac.core.templates import (
    TemplateNotFound,
    TemplateResourceMissing,
    available_templates,
)
from rac.core.validation import has_errors, validate
from rac.services.create import (
    IdGenerationExhausted,
    MissingRepositoryConfig,
    OutputDirectoryMissing,
    OutputPathExists,
    create_artifact,
)
from rac.services.diff import diff as diff_asts
from rac.services.improve import improve_product
from rac.services.index import build_repository_index
from rac.services.ingest import ConversionError, UnsupportedDocument, ingest
from rac.services.init import (
    DEFAULT_KEY,
    InvalidRepositoryKey,
    MalformedRepositoryConfig,
    RepositoryKeyConflict,
    init_repository,
)
from rac.services.inspect import build_inspection, inspect_directory
from rac.services.migrate import migrate_metadata
from rac.services.portfolio import build_portfolio_summary
from rac.services.relationships import (
    build_relationship_report,
    build_relationship_report_file,
    validate_relationships,
    validate_relationships_file,
)
from rac.services.resolve import (
    OUTCOME_DUPLICATE,
    OUTCOME_RESOLVED,
    find_artifacts,
    resolve_artifact,
)
from rac.services.review import build_review
from rac.services.stats import collect_stats
from rac.services.validate import validate_directory

from . import __version__

EXIT_OK = 0
EXIT_VALIDATION_FAILED = 1
EXIT_USAGE = 2


def _read(path: str) -> Product:
    """Parse a file, or print an error and exit with EXIT_USAGE."""
    try:
        return parse_file(path)
    except FileNotFoundError:
        print(f"rac: file not found: {path}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except OSError as exc:
        print(f"rac: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None


def _read_validate_input(target: str) -> Product:
    """Parse validation input from a Markdown file or stdin."""
    if target == "-":
        return parse(sys.stdin.read(), source_path="-")
    return _read(target)


def cmd_validate(args: argparse.Namespace) -> int:
    # Directory? Validate every recognized artifact beneath it (v0.7.9).
    # Unknown-type files are skipped, matching `rac portfolio` semantics; the
    # legacy requirement fallback applies only to explicit single-file input.
    if args.file != "-" and Path(args.file).is_dir():
        result = validate_directory(args.file, recursive=not args.top_level)
        if args.json:
            print(outputs.render_validate_dir_json(result))
        else:
            print(outputs.render_validate_dir_human(result))
        return EXIT_OK if result.ok else EXIT_VALIDATION_FAILED

    product = _read_validate_input(args.file)
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
    # feature, one decision, one valid roadmap, one valid prompt, or one valid
    # design. Invalid files are reported but don't fail the run on their own. (A
    # future --strict flag will fail the run if *any* file is invalid, for CI use.)
    has_content = (
        stats.valid_features > 0
        or stats.decision_count > 0
        or stats.valid_roadmaps > 0
        or stats.valid_prompts > 0
        or stats.valid_designs > 0
    )
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
        raise SystemExit(EXIT_USAGE) from None
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
            f"rac: {command} expects a Markdown file; convert it first with: rac ingest {target}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"rac: cannot read {target}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None


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
    inspection = build_inspection(product)
    if args.verbose and not args.json:
        print(outputs.render_inspect_verbose(inspection, score_artifacts(product)))
    elif args.json:
        print(outputs.render_inspect_json(inspection))
    else:
        print(outputs.render_inspect_human(inspection))
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


def cmd_schema(args: argparse.Namespace) -> int:
    names = available_schemas()
    if args.list:
        if args.template:
            print("rac: --template cannot be used with --list", file=sys.stderr)
            raise SystemExit(EXIT_USAGE)
        if args.schema:
            print("rac: schema name cannot be used with --list", file=sys.stderr)
            raise SystemExit(EXIT_USAGE)
        if args.json:
            print(outputs.render_schema_list_json(names))
        else:
            print(outputs.render_schema_list_human(names))
        return EXIT_OK

    if not args.schema:
        print("rac: schema name required unless --list is passed", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    ref = schema_reference(args.schema)
    if ref is None:
        print(outputs.render_unknown_schema(args.schema, names), file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    if args.json:
        print(outputs.render_schema_json(ref))
    elif args.template:
        print(outputs.render_schema_template(ref))
    else:
        print(outputs.render_schema_human(ref))
    return EXIT_OK


def cmd_relationships(args: argparse.Namespace) -> int:
    path = Path(args.path)
    # --recursive is the default; --top-level disables it. If both are given,
    # --top-level wins (mirrors `rac inspect`).
    if path.is_dir():
        is_dir = True
    elif path.is_file():
        if path.suffix.lower() not in (".md", ".markdown"):
            print(
                f"rac: relationships expects a Markdown file or directory; "
                f"convert it first with: rac ingest {args.path}",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_USAGE)
        is_dir = False
    else:
        print(f"rac: path not found: {args.path}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    if args.validate:
        if is_dir:
            report = validate_relationships(args.path, recursive=not args.top_level)
        else:
            report = validate_relationships_file(args.path)
        if args.json:
            print(outputs.render_relationship_validation_json(report))
        else:
            print(outputs.render_relationship_validation_human(report))
        # Validation-style exit codes (REQ-007): 0 when everything resolves, 1 when
        # any issue is found, 2 (above) for usage errors.
        return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED

    if is_dir:
        rel_report = build_relationship_report(args.path, recursive=not args.top_level)
    else:
        rel_report = build_relationship_report_file(args.path)
    if args.json:
        print(outputs.render_relationships_json(rel_report))
    else:
        print(outputs.render_relationships_human(rel_report))
    # A completed inspection always succeeds — finding no relationships is a valid
    # outcome, not an error (REQ-010).
    return EXIT_OK


def cmd_review(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    report = build_review(args.directory, recursive=not args.top_level)
    if args.json:
        print(outputs.render_review_json(report))
    else:
        print(outputs.render_review_human(report))
    # Priority 1-2 findings (invalid artifacts, broken relationships) fail the
    # review; priority 3-4 findings are advisory (REQ-Repository-Review-Mode).
    return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED


def cmd_portfolio(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    recursive = not args.top_level
    summary = build_portfolio_summary(args.directory, recursive=recursive)
    if args.json:
        print(outputs.render_portfolio_json(summary))
    else:
        print(outputs.render_portfolio_human(summary))
    return EXIT_OK


def cmd_index(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    recursive = not args.top_level
    index = build_repository_index(args.directory, recursive=recursive)
    if args.json:
        print(outputs.render_index_json(index))
    else:
        print(outputs.render_index_human(index))
    return EXIT_OK


def cmd_explorer(args: argparse.Namespace) -> int:
    if args.directory is None:
        # ADR-018: rac/ is the conventional knowledge root — open it when it
        # exists; otherwise the current directory (v0.8.1).
        args.directory = "rac" if Path("rac").is_dir() else "."
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    # Imported lazily: launch decides whether the explorer extra is installed,
    # and the base CLI must not pay an import cost for the optional TUI.
    from rac.explorer.launch import ExplorerUnavailable, run_explorer

    try:
        return run_explorer(args.directory, recursive=not args.top_level)
    except ExplorerUnavailable as exc:
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None


def cmd_new(args: argparse.Namespace) -> int:
    try:
        created = create_artifact(args.type, args.output_path)
    except TemplateNotFound as exc:  # unsupported type → usage error
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except (
        OutputPathExists,
        OutputDirectoryMissing,
        MissingRepositoryConfig,
    ) as exc:
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except (
        TemplateResourceMissing,  # broken installation
        MalformedRepositoryConfig,  # unreadable .rac/config.yaml
        IdGenerationExhausted,  # broken entropy source
    ) as exc:  # operational errors
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    if args.json:
        print(outputs.render_new_json(created))
    else:
        print(outputs.render_new_human(created))
    return EXIT_OK


def cmd_resolve(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    result = resolve_artifact(args.directory, args.id, recursive=not args.top_level)
    if args.json:
        print(outputs.render_resolve_json(result))
    else:
        if result.outcome == OUTCOME_RESOLVED:
            print(outputs.render_resolve_human(result))
        elif result.outcome == OUTCOME_DUPLICATE:
            print(
                f"rac: duplicate artifact ID: {args.id}\n\nFound in:\n"
                + "\n".join(f"- {p}" for p in result.duplicate_paths),
                file=sys.stderr,
            )
        else:
            print(f"rac: artifact not found: {args.id}", file=sys.stderr)
    # Not-found and duplicate identity are both repository findings (exit 1);
    # they stay distinguishable by message and by the JSON error field.
    return EXIT_OK if result.outcome == OUTCOME_RESOLVED else EXIT_VALIDATION_FAILED


def cmd_find(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    result = find_artifacts(
        args.directory,
        args.query,
        artifact_type=args.type,
        recursive=not args.top_level,
    )
    if args.json:
        print(outputs.render_find_json(result))
    else:
        print(outputs.render_find_human(result))
    # An empty result is a valid outcome, not an error.
    return EXIT_OK


def cmd_migrate(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        report = migrate_metadata(
            args.directory,
            dry_run=args.dry_run,
            recursive=not args.top_level,
        )
    except MissingRepositoryConfig as exc:
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except (MalformedRepositoryConfig, IdGenerationExhausted) as exc:
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    if args.json:
        print(outputs.render_migrate_json(report))
    else:
        print(outputs.render_migrate_human(report))
    # Completed migration (or dry run) always succeeds — nothing to migrate
    # is a valid outcome.
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        result = init_repository(args.directory, key=args.key)
    except InvalidRepositoryKey as exc:
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except (RepositoryKeyConflict, MalformedRepositoryConfig) as exc:
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    if args.json:
        print(outputs.render_init_json(result))
    else:
        print(outputs.render_init_human(result))
    return EXIT_OK


def cmd_templates(args: argparse.Namespace) -> int:
    names = available_templates()
    if args.json:
        print(outputs.render_templates_json(names))
    else:
        print(outputs.render_templates_human(names))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    version_str = f"rac {__version__}"

    # Shared parent so `--version` works on the root parser *and* every
    # subcommand (e.g. `rac ingest foo.docx --version`).
    version_parent = argparse.ArgumentParser(add_help=False)
    version_parent.add_argument("--version", action="version", version=version_str)

    parser = argparse.ArgumentParser(
        prog="rac",
        description="Requirements As Code — lint and diff Markdown requirements.",
        parents=[version_parent],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate",
        help="Validate an artifact file, or every recognized artifact in a directory.",
        parents=[version_parent],
    )
    p_validate.add_argument(
        "file",
        help="A Markdown artifact file, a directory, or '-' to read from stdin.",
    )
    p_validate.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_validate.add_argument(
        "--top-level",
        action="store_true",
        help="When validating a directory, only its top-level files (no recursion).",
    )
    p_validate.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
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
    ingest_dest.add_argument("-o", "--output", help="Write Markdown here instead of printing it.")
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

    p_schema = sub.add_parser(
        "schema",
        help="Show registered artifact schemas and starter templates.",
        parents=[version_parent],
    )
    p_schema.add_argument(
        "schema",
        nargs="?",
        help="Schema name, e.g. requirement, decision, roadmap, prompt, or design.",
    )
    p_schema.add_argument(
        "--list",
        action="store_true",
        help="List available schemas.",
    )
    schema_mode = p_schema.add_mutually_exclusive_group()
    schema_mode.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    schema_mode.add_argument(
        "--template",
        action="store_true",
        help="Emit a full Markdown starter template.",
    )
    p_schema.set_defaults(func=cmd_schema)

    p_relationships = sub.add_parser(
        "relationships",
        help="Inspect explicit relationships across a directory (or single file).",
        parents=[version_parent],
    )
    p_relationships.add_argument("path", help="A directory to scan, or a single Markdown file.")
    p_relationships.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_relationships.add_argument(
        "--validate",
        action="store_true",
        help="Resolve references against discovered artifacts; exit 1 if any are "
        "broken, ambiguous, self-referencing, or have duplicate identifiers.",
    )
    p_relationships.add_argument(
        "--top-level",
        action="store_true",
        help="When inspecting a directory, only its top-level files (no recursion).",
    )
    p_relationships.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_relationships.set_defaults(func=cmd_relationships)

    p_review = sub.add_parser(
        "review",
        help="Review a repository: prioritized issues and suggested actions.",
        parents=[version_parent],
    )
    p_review.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_review.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_review.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_review.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_review.set_defaults(func=cmd_review)

    p_portfolio = sub.add_parser(
        "portfolio",
        help="Repository intelligence summary: artifact counts, health score, and attention items.",
        parents=[version_parent],
    )
    p_portfolio.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_portfolio.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_portfolio.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_portfolio.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_portfolio.set_defaults(func=cmd_portfolio)

    p_index = sub.add_parser(
        "index",
        help="Inventory every artifact in a repository (id, type, title, path).",
        parents=[version_parent],
    )
    p_index.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    p_index.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_index.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_index.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_index.set_defaults(func=cmd_index)

    p_explorer = sub.add_parser(
        "explorer",
        help="Launch the interactive terminal Explorer (needs the explorer extra).",
        parents=[version_parent],
    )
    p_explorer.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Repository to explore (default: rac/ when present, else the current directory).",
    )
    p_explorer.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_explorer.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_explorer.set_defaults(func=cmd_explorer)

    p_new = sub.add_parser(
        "new",
        help="Create a new artifact from its canonical template.",
        parents=[version_parent],
    )
    p_new.add_argument(
        "type",
        help="Artifact type, e.g. requirement, decision, roadmap, prompt, or design.",
    )
    p_new.add_argument(
        "output_path",
        help="Where to write the artifact (taken literally; never overwritten).",
    )
    p_new.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_new.set_defaults(func=cmd_new)

    p_templates = sub.add_parser(
        "templates",
        help="List the canonical artifact templates available to `rac new`.",
        parents=[version_parent],
    )
    p_templates.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_templates.set_defaults(func=cmd_templates)

    p_init = sub.add_parser(
        "init",
        help="Establish the repository identity namespace (.rac/config.yaml).",
        parents=[version_parent],
    )
    p_init.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Repository root to initialize (default: current directory).",
    )
    p_init.add_argument(
        "--key",
        default=DEFAULT_KEY,
        help="Repository key used as the artifact ID prefix (default: RAC; "
        "2-10 uppercase alphanumeric characters starting with a letter).",
    )
    p_init.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_init.set_defaults(func=cmd_init)

    p_resolve = sub.add_parser(
        "resolve",
        help="Resolve an artifact ID to its type, title, and path.",
        parents=[version_parent],
    )
    p_resolve.add_argument("id", help="Artifact ID (canonical or legacy alias).")
    p_resolve.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    p_resolve.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_resolve.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_resolve.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_resolve.set_defaults(func=cmd_resolve)

    p_find = sub.add_parser(
        "find",
        help="Search artifacts by ID, title, filename, or path.",
        parents=[version_parent],
    )
    p_find.add_argument("query", help="Case-insensitive substring to search for.")
    p_find.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    p_find.add_argument(
        "--type",
        help="Only match artifacts of this type (requirement, decision, ...).",
    )
    p_find.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_find.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_find.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_find.set_defaults(func=cmd_find)

    p_migrate = sub.add_parser(
        "migrate",
        help="Migrate existing artifacts onto canonical frontmatter identity.",
        parents=[version_parent],
    )
    p_migrate.add_argument(
        "target",
        choices=["metadata"],
        help="What to migrate (this release: metadata).",
    )
    p_migrate.add_argument(
        "directory",
        help="Directory to scan recursively for *.md.",
    )
    p_migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be migrated without writing any file.",
    )
    p_migrate.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_migrate.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_migrate.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_migrate.set_defaults(func=cmd_migrate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
