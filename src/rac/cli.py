"""Command-line interface for RAC.

Commands:
    rac validate <file.md | dir | -> [--json | --sarif] [--top-level]
    rac diff <old.md> <new.md> [--json]
    rac stats <directory> [--json]
    rac ingest <file> [-o OUT | --stdout] [--force] [--json]
    rac inspect <file.md | -> [--json]
    rac improve <file.md | -> [--json | --template]
    rac schema [--list] [type] [--json | --template]
    rac relationships <dir | file.md> [--validate] [--json] [--top-level]
    rac review <directory> [--json] [--top-level]
    rac gate <directory> [--json | --sarif] [--top-level]
    rac watchkeeper [directory] [--base REF] [--head REF]
                    [--format human|json|github] [--json] [--fail-on POLICY]
                    [--no-annotate]
    rac portfolio <directory> [--json] [--top-level]
    rac index [directory] [--json] [--top-level]
    rac export [directory] [--json | --html | --okf | --agent-rules [--check]]
               [--client CLIENT ...] [--out PATH]
    rac explorer [directory] [--top-level]
    rac mcp [--root PATH] [--telemetry]
    rac mcp-stats [--json | --share]
    rac telemetry [on | off | status]
    rac new <artifact-type> <output-path> [--json]
    rac templates [--json]
    rac init [directory] [--key KEY] [--json]
    rac quickstart [directory] [--key KEY] [--type TYPE] [--json]
    rac resolve <ID> [directory] [--json]
    rac find <query> [directory] [--type TYPE] [--json]
    rac migrate metadata <directory> [--dry-run] [--json]
    rac skill install [name] [--dir PATH] [--json]
    rac skill list [--json]
    rac hook install [--style post-commit|pre-commit] [--dir PATH] [--json]
    rac hook list [--json]

Exit codes:
    0  success (incl. inspect/improve reporting Unknown; relationships found or
       not; --validate with all references resolved; portfolio summary produced;
       index produced; artifact created; templates listed; find with or without
       matches; migration or dry run completed, even with nothing to migrate;
       explorer session quit by the user; mcp server shutdown on client
       disconnect; skill(s) installed; skills listed; mcp-stats summary
       produced, even from an empty or missing telemetry log; telemetry
       consent shown or changed, including when no endpoint key is
       configured; export payload produced — JSON to stdout, or the
       --html Portal file or --okf bundle written, an empty corpus
       included; watchkeeper
       comparison with nothing requiring attention under the chosen
       --fail-on policy, always with --fail-on none)
    1  validate: errors found; stats: no valid known artifacts; ingest:
       conversion failed; relationships --validate: broken/ambiguous/self
       references or duplicate identifiers found; review: invalid artifacts
       or broken relationships found (priority 1-2 issues); new: packaged
       template missing (broken installation) or malformed repository config;
       init: established key conflicts with the requested one; resolve:
       artifact not found or duplicate ID; migrate: malformed repository
       config or ID generation exhausted; skill install: any target file
       already exists (never overwritten; no-name installs refuse
       all-or-nothing) or packaged skill missing (broken installation);
       watchkeeper: review recommended (--fail-on error, the default) or
       any warning finding (--fail-on warning)
    2  usage / IO error (file not found, not a directory, unsupported type,
       refuse-to-overwrite, missing output directory, repository not
       initialized, invalid repository key, explorer extra not installed,
       mcp --root not a directory, skill --dir not a directory, unknown
       skill name, export --out without --html/--okf or unwritable, missing or
       corrupt vendored portal shell, watchkeeper revision unknown or
       directory not inside a git repository)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rac import consent
from rac import output as outputs
from rac.core.classification import score_artifacts
from rac.core.hooks import (
    DEFAULT_STYLE,
    HookNotFound,
    HookResourceMissing,
    available_hooks,
    hook_specs,
)
from rac.core.markdown import parse, parse_file
from rac.core.models import Product
from rac.core.schema import available_schemas, schema_reference
from rac.core.skills import SkillNotFound, SkillResourceMissing, skill_specs
from rac.core.templates import (
    TemplateNotFound,
    TemplateResourceMissing,
    available_templates,
)
from rac.core.validation import has_errors
from rac.output.portal import PortalSeamMissing, PortalShellMissing
from rac.services.agent_rules import (
    check_agent_rules,
    generate_agent_rules,
    unknown_clients,
)
from rac.services.create import (
    IdGenerationExhausted,
    MissingRepositoryConfig,
    OutputDirectoryMissing,
    OutputPathExists,
    create_artifact,
)
from rac.services.diff import diff as diff_asts
from rac.services.export import build_corpus_export
from rac.services.gate import build_gate
from rac.services.hook import HookFileExists, NotAGitWorkTree, install_hook
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
from rac.services.quickstart import DEFAULT_TYPE, CorpusNotEmpty, quickstart
from rac.services.recency import artifact_recency
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
from rac.services.review import DEFAULT_STALE_AFTER_DAYS, build_review
from rac.services.revisions import NotAGitRepository, RevisionNotFound
from rac.services.skill import SkillFileExists, install_skills
from rac.services.stats import collect_stats
from rac.services.validate import validate_directory, validate_product
from rac.services.watchkeeper import build_watchkeeper_report

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
        if args.sarif:
            print(outputs.render_validate_sarif(result))
        elif args.json:
            print(outputs.render_validate_dir_json(result))
        else:
            print(outputs.render_validate_dir_human(result))
        return EXIT_OK if result.ok else EXIT_VALIDATION_FAILED

    if args.sarif:
        # SARIF is a repository-scan artifact for CI code scanning (ADR-054);
        # there is no single-file SARIF surface.
        print("rac: --sarif applies to directory validation", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    product = _read_validate_input(args.file)
    start = "." if args.file == "-" else str(Path(args.file).parent)
    issues = validate_product(product, start)
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
    # Success as long as the portfolio has analysable content (at least one valid
    # feature/decision/roadmap/prompt/design) or is an empty day-one corpus.
    # `has_meaningful_content` and `is_empty` are computed behind the gate
    # (ADR-015); the CLI only reads them. An empty corpus is a valid state, not a
    # failure (v0.13.1): it exits 0, matching validate/review/portfolio. The
    # "files exist but none are valid known artifacts" failure is preserved for a
    # non-empty corpus, and will move behind a future --strict flag for CI use.
    return EXIT_OK if (stats.has_meaningful_content or stats.is_empty) else EXIT_VALIDATION_FAILED


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
    if args.sarif and not args.validate:
        print("rac: relationships --sarif requires --validate", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
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
        if args.sarif:
            print(outputs.render_relationships_sarif(report))
        elif args.json:
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
    if args.stale_after is not None and args.stale_after < 0:
        print("rac: --stale-after must be a non-negative number of days", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    report = build_review(
        args.directory, recursive=not args.top_level, stale_after_days=args.stale_after
    )
    if args.sarif:
        print(outputs.render_review_sarif(report))
    elif args.json:
        print(outputs.render_review_json(report))
    else:
        print(outputs.render_review_human(report))
    # Priority 1-2 findings (invalid artifacts, broken relationships) fail the
    # review; priority 3-4 findings are advisory (REQ-Repository-Review-Mode).
    return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED


def cmd_gate(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        report = build_gate(args.directory, recursive=not args.top_level)
    except MalformedRepositoryConfig as exc:  # unreadable/invalid .rac/config.yaml
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    if args.sarif:
        print(outputs.render_gate_sarif(report))
    elif args.json:
        print(outputs.render_gate_json(report))
    else:
        print(outputs.render_gate_human(report))
    # The gate fails when any finding is blocking under the corpus enforcement
    # policy; advisory findings annotate but never fail (ADR-049 / v0.21.14).
    return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED


def cmd_watchkeeper(args: argparse.Namespace) -> int:
    if args.directory is None:
        # ADR-018: rac/ is the conventional knowledge root — compare it when it
        # exists; otherwise the current directory.
        args.directory = "rac" if Path("rac").is_dir() else "."
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        report = build_watchkeeper_report(args.directory, base=args.base, head=args.head)
    except (NotAGitRepository, RevisionNotFound) as exc:
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(outputs.render_watchkeeper_json(report))
    elif output_format == "github":
        # stdout is the step-summary Markdown; annotations go to stderr so
        # `> "$GITHUB_STEP_SUMMARY"` keeps them in the step log, where the
        # runner turns workflow commands into inline annotations.
        print(outputs.render_watchkeeper_github(report))
        if args.annotate:
            for line in outputs.watchkeeper_annotations(report):
                print(line, file=sys.stderr)
    else:
        print(outputs.render_watchkeeper_human(report))
    # Failure policy (v0.12.2): `error` fails on a review recommendation,
    # `warning` also on any warning-severity finding, `none` never fails.
    if args.fail_on == "none":
        return EXIT_OK
    if report.review_recommended:
        return EXIT_VALIDATION_FAILED
    if args.fail_on == "warning" and report.has_warnings:
        return EXIT_VALIDATION_FAILED
    return EXIT_OK


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


def _agent_rules_root(directory: str, out: str | None) -> Path:
    """The directory the agent-rules files are written into.

    Explicit ``--out`` wins. Otherwise default to the corpus's repo root: the
    parent of a ``rac/`` directory (so ``rac export rac/ --agent-rules`` writes
    CLAUDE.md/AGENTS.md beside it), else the directory itself. A bare ``rac``
    with no parent component falls back to the current directory.
    """
    if out is not None:
        return Path(out)
    path = Path(directory.rstrip("/"))
    if path.name == "rac":
        return path.parent if str(path.parent) not in ("", ".") else Path(".")
    return path


def cmd_export(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    # Agent-rules is a distinct mode (ADR-067): a distilled, drift-guarded
    # projection of live decisions into per-client managed blocks. It owns --out
    # (the output root), --client (target selectors), --check (the drift gate),
    # and --json (machine output) — none of the export-payload modes apply.
    if args.agent_rules:
        return _cmd_agent_rules(args)
    if args.check:
        print("rac: --check requires --agent-rules", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    if args.client:
        print("rac: --client requires --agent-rules", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    if args.json and (args.html or args.okf):
        print("rac: --json cannot combine with --html or --okf", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    if args.out is not None and not (args.html or args.okf):
        print("rac: --out requires --html or --okf (--json writes to stdout)", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    export = build_corpus_export(args.directory)

    # OKF bundle (ADR-048): a derived tree of Markdown files written to a
    # directory, parallel to the JSON/HTML views. Recency feeds log.md (ADR-045).
    if args.okf:
        recency = artifact_recency(args.directory, with_creation=True)
        bundle = outputs.render_okf_bundle(export, recency, args.directory)
        out = args.out if args.out is not None else "okf-bundle"
        try:
            for rel, content in sorted(bundle.items()):
                dest = Path(out) / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
        except OSError as exc:
            print(f"rac: cannot write {out}: {exc}", file=sys.stderr)
            raise SystemExit(EXIT_USAGE) from None
        edges = len(export.relationships)
        print(f"wrote {out}/ — {export.artifact_count} artifact(s), {edges} relationship(s)")
        return EXIT_OK

    # JSON is the default mode (unlike sibling commands): the payload *is* the
    # product, and stdout keeps it pipeable. --json is an explicit no-op.
    if not args.html:
        print(outputs.render_export_json(export))
        return EXIT_OK

    try:
        html = outputs.render_export_html(export)
    except (PortalShellMissing, PortalSeamMissing) as exc:
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    out = args.out if args.out is not None else "lore-export.html"
    try:
        Path(out).write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"rac: cannot write {out}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    edges = len(export.relationships)
    print(f"wrote {out} — {export.artifact_count} artifact(s), {edges} relationship(s)")
    return EXIT_OK


def _cmd_agent_rules(args: argparse.Namespace) -> int:
    """`rac export --agent-rules [--check]` (v0.21.15, ADR-067).

    Generates (or, under --check, verifies) the drift-guarded managed block in
    each per-client agent-context file. --check never writes and exits non-zero
    on drift (a stale or missing block) — the CI gate. Output is human by
    default; --json emits the machine contract.
    """
    bad = unknown_clients(args.client)
    if bad:
        valid = "claude, agents, cursor, copilot"
        print(f"rac: unknown --client: {', '.join(bad)} (choose from {valid})", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)

    root = _agent_rules_root(args.directory, args.out)
    try:
        if args.check:
            result = check_agent_rules(args.directory, str(root), clients=args.client)
        else:
            result = generate_agent_rules(args.directory, str(root), clients=args.client)
    except OSError as exc:
        print(f"rac: cannot write under {root}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None

    if args.json:
        print(outputs.render_agent_rules_json(result))
    else:
        print(outputs.render_agent_rules_human(result))

    if args.check and result.drifted:
        return EXIT_VALIDATION_FAILED
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


def cmd_mcp(args: argparse.Namespace) -> int:
    if not Path(args.root).is_dir():
        print(f"rac: not a directory: {args.root}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    # Imported lazily: the MCP SDK is only needed when serving, and the base
    # CLI must not pay its import cost for every other command. stdout belongs
    # to the MCP protocol, so any diagnostics here go to stderr.
    from rac.mcp.server import run_server

    return run_server(args.root, telemetry_enabled=args.telemetry)


def cmd_mcp_stats(args: argparse.Namespace) -> int:
    # Imported lazily for the same reason as cmd_mcp: importing the telemetry
    # module executes the rac.mcp package, which pulls in the MCP SDK.
    from rac.mcp.telemetry import share_url, summarize

    summary = summarize()
    if args.share:
        print(share_url(summary))
    elif args.json:
        print(outputs.render_mcp_stats_json(summary))
    else:
        print(outputs.render_mcp_stats_human(summary))
    # An empty or missing log is a valid answer (telemetry is off by default),
    # like `rac find` with no matches.
    return EXIT_OK


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
        _maybe_ask_usage_sharing()
    return EXIT_OK


def cmd_quickstart(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        print(f"rac: not a directory: {args.directory}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        result = quickstart(args.directory, key=args.key, artifact_type=args.type)
    except TemplateNotFound as exc:  # unsupported type → usage error
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except InvalidRepositoryKey as exc:  # bad key syntax → usage error
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except OutputDirectoryMissing as exc:  # parent missing → usage error
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except (
        CorpusNotEmpty,  # corpus already has artifacts → refused
        RepositoryKeyConflict,  # established key differs → refused
        OutputPathExists,  # starter path already taken → refused (never overwrite)
    ) as exc:
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    except (
        MalformedRepositoryConfig,  # unreadable .rac/config.yaml
        TemplateResourceMissing,  # broken installation
        IdGenerationExhausted,  # broken entropy source
    ) as exc:  # operational errors
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    if args.json:
        print(outputs.render_quickstart_json(result))
    else:
        print(outputs.render_quickstart_human(result))
        _maybe_ask_usage_sharing()
    return EXIT_OK


def _maybe_ask_usage_sharing() -> None:
    """Ask the one-time usage-sharing question after a successful init (ADR-041).

    The CLI's only interactive prompt, deliberately narrow: a real TTY on both
    ends, no ``--json`` (the caller gates that), and no prior answer — either
    answer is persisted, so the question is asked at most once per machine.
    Empty input and EOF mean No; CI and pipes never reach ``input()``.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()) or consent.consent_recorded():
        return
    try:
        answer = input("\nShare anonymous usage to help shape Lore? [y/N] ")
    except EOFError:
        answer = ""
    if answer.strip().lower() in ("y", "yes"):
        consent.opt_in()
        print(
            "Sharing on — one anonymous daily ping. 'rac telemetry status' "
            "shows exactly what; 'rac telemetry off' stops it."
        )
    else:
        consent.decline()


def cmd_telemetry(args: argparse.Namespace) -> int:
    if args.action == "on":
        record = consent.opt_in()
        print(f"Sharing on. Install id: {record.install_id}")
        print(
            "One anonymous daily ping: install id, rac version, active-repo "
            "count. Never paths, queries, or content (ADR-041)."
        )
        if not consent.POSTHOG_API_KEY:
            print("Note: this build has no PostHog key configured; nothing will be sent.")
    elif args.action == "off":
        consent.opt_out()
        print("Sharing off. Nothing will be sent.")
    else:  # status
        status = consent.consent_status()
        print(f"Sharing: {'on' if status.sharing else 'off'}")
        print(f"Install id: {status.install_id or '(none)'}")
        print(f"Consented at: {status.consented_at or '(never)'}")
        print(f"Consent file: {status.path}")
        if status.sharing:
            print(
                "Shared daily: install id, rac version, active-repo count. "
                "Never paths, queries, or content (ADR-041)."
            )
        if not status.endpoint_configured:
            print("Endpoint key: not configured — nothing is sent.")
    return EXIT_OK


def cmd_skill(args: argparse.Namespace) -> int:
    if args.action == "list":
        if args.name is not None:
            print("rac: skill list takes no skill name", file=sys.stderr)
            raise SystemExit(EXIT_USAGE)
        specs = skill_specs()
        if args.json:
            print(outputs.render_skill_list_json(specs))
        else:
            print(outputs.render_skill_list_human(specs))
        return EXIT_OK

    if not Path(args.dir).is_dir():
        print(f"rac: not a directory: {args.dir}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        installation = install_skills(args.dir, args.name)
    except SkillNotFound as exc:  # unknown skill name → usage error
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except SkillFileExists as exc:  # refused; every existing file is untouched
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    except SkillResourceMissing as exc:  # broken installation
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    if args.json:
        print(outputs.render_skill_install_json(installation))
    else:
        print(outputs.render_skill_install_human(installation))
    return EXIT_OK


def cmd_hook(args: argparse.Namespace) -> int:
    if args.action == "list":
        specs = hook_specs()
        if args.json:
            print(outputs.render_hook_list_json(specs))
        else:
            print(outputs.render_hook_list_human(specs))
        return EXIT_OK

    if not Path(args.dir).is_dir():
        print(f"rac: not a directory: {args.dir}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        installation = install_hook(args.dir, args.style)
    except (HookNotFound, NotAGitWorkTree) as exc:  # usage errors → exit 2
        print(f"rac: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
    except HookFileExists as exc:  # refused; existing hook untouched
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    except HookResourceMissing as exc:  # broken installation
        print(f"rac: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    if args.json:
        print(outputs.render_hook_install_json(installation))
    else:
        print(outputs.render_hook_install_human(installation))
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
    p_validate_format = p_validate.add_mutually_exclusive_group()
    p_validate_format.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_validate_format.add_argument(
        "--sarif",
        action="store_true",
        help="Emit SARIF 2.1.0 for GitHub Code Scanning (directory validation only).",
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
        "--sarif",
        action="store_true",
        help="With --validate, emit SARIF 2.1.0 for GitHub Code Scanning "
        "(CI pull-request enforcement).",
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
        "--sarif",
        action="store_true",
        help="Emit SARIF 2.1.0 for GitHub Code Scanning (CI pull-request enforcement).",
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
    p_review.add_argument(
        "--stale-after",
        dest="stale_after",
        nargs="?",
        type=int,
        const=DEFAULT_STALE_AFTER_DAYS,
        default=None,
        metavar="DAYS",
        help=(
            "Add an advisory write-cadence finding when no artifact has been "
            f"committed within DAYS (default {DEFAULT_STALE_AFTER_DAYS} when given "
            "without a value). Informational; never fails the review. Needs git "
            "history."
        ),
    )
    p_review.set_defaults(func=cmd_review)

    p_gate = sub.add_parser(
        "gate",
        help="Enforce the corpus: validation, relationships, and review under "
        "the corpus enforcement policy.",
        parents=[version_parent],
    )
    p_gate.add_argument("directory", help="The RAC corpus directory to enforce.")
    gate_format = p_gate.add_mutually_exclusive_group()
    gate_format.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    gate_format.add_argument(
        "--sarif",
        action="store_true",
        help="Emit one SARIF 2.1.0 document over all findings for GitHub Code "
        "Scanning (CI pull-request enforcement).",
    )
    p_gate.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    p_gate.set_defaults(func=cmd_gate)

    p_watchkeeper = sub.add_parser(
        "watchkeeper",
        help="Review product knowledge changes between two repository states.",
        parents=[version_parent],
    )
    p_watchkeeper.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Corpus to compare (default: rac/ when present, else the current directory).",
    )
    p_watchkeeper.add_argument(
        "--base",
        default="main",
        help="Base state: a git revision or an existing directory (default: main).",
    )
    p_watchkeeper.add_argument(
        "--head",
        default=None,
        help="Head state: a git revision or an existing directory (default: the working tree).",
    )
    p_watchkeeper.add_argument(
        "--format",
        choices=["human", "json", "github"],
        default="human",
        help=(
            "Output format: human (default), json (stable contract), or github "
            "(step-summary Markdown on stdout, workflow-command annotations on stderr)."
        ),
    )
    p_watchkeeper.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable text (alias for --format json).",
    )
    p_watchkeeper.add_argument(
        "--fail-on",
        choices=["error", "warning", "none"],
        default="error",
        help=(
            "Failure policy: error (exit 1 when review is recommended, the default), "
            "warning (also on any warning finding), or none (never fail)."
        ),
    )
    p_watchkeeper.add_argument(
        "--no-annotate",
        dest="annotate",
        action="store_false",
        help="Suppress workflow-command annotations (github format only).",
    )
    p_watchkeeper.set_defaults(func=cmd_watchkeeper)

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

    p_export = sub.add_parser(
        "export",
        help="Export the corpus as a deterministic JSON payload or a self-contained HTML Portal.",
        parents=[version_parent],
    )
    p_export.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    # --html / --okf / --agent-rules are the mutually-exclusive write modes; the
    # default (none of them) writes the JSON payload to stdout. --json is *not*
    # in this group: for the default mode it is the explicit no-op it always was,
    # and for --agent-rules it toggles JSON vs human output (so --agent-rules
    # --json is valid). --json with --html/--okf is rejected in cmd_export.
    export_mode = p_export.add_mutually_exclusive_group()
    p_export.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable text (the default export mode "
        "writes JSON to stdout regardless; with --agent-rules, selects JSON output).",
    )
    export_mode.add_argument(
        "--html",
        action="store_true",
        help="Inject the payload into the vendored Portal shell and write one "
        "self-contained HTML file.",
    )
    export_mode.add_argument(
        "--okf",
        action="store_true",
        help="Write a derived OKF v0.1 bundle (one Markdown file per artifact, "
        "plus index.md and log.md) to a directory.",
    )
    export_mode.add_argument(
        "--agent-rules",
        action="store_true",
        help="Write per-client agent-context files (CLAUDE.md, AGENTS.md, "
        ".cursor/rules, .github/copilot-instructions.md) with a drift-guarded "
        "managed block distilled from live decisions (ADR-067).",
    )
    p_export.add_argument(
        "--check",
        action="store_true",
        help="With --agent-rules: verify committed files match the corpus "
        "without writing; exit non-zero on drift (the CI gate).",
    )
    p_export.add_argument(
        "--client",
        action="append",
        choices=["claude", "agents", "cursor", "copilot"],
        metavar="CLIENT",
        help="With --agent-rules: restrict to specific clients "
        "(claude|agents|cursor|copilot); repeatable. Default: all four.",
    )
    p_export.add_argument(
        "--out",
        default=None,
        help="Where --html writes the Portal (default: lore-export.html), "
        "--okf writes the bundle directory (default: okf-bundle), or "
        "--agent-rules writes the per-client files (default: the corpus's repo "
        "root — the parent of a rac/ directory). "
        "Exports are build artifacts: existing output is overwritten.",
    )
    p_export.set_defaults(func=cmd_export)

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

    p_mcp = sub.add_parser(
        "mcp",
        help="Serve RAC repository knowledge to agents over MCP (stdio).",
        parents=[version_parent],
    )
    p_mcp.add_argument(
        "--root",
        default=".",
        help="Repository root to serve (default: current directory).",
    )
    p_mcp.add_argument(
        "--telemetry",
        action="store_true",
        help=(
            "Record tool-call counts and metadata (never arguments or content) "
            "to a local log; off by default (ADR-040)."
        ),
    )
    p_mcp.set_defaults(func=cmd_mcp)

    p_mcp_stats = sub.add_parser(
        "mcp-stats",
        help="Summarize the local Guide telemetry log.",
        parents=[version_parent],
    )
    mcp_stats_mode = p_mcp_stats.add_mutually_exclusive_group()
    mcp_stats_mode.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    mcp_stats_mode.add_argument(
        "--share",
        action="store_true",
        help=(
            "Print a prefilled GitHub usage-report issue URL to review and "
            "submit in your browser; RAC sends nothing itself."
        ),
    )
    p_mcp_stats.set_defaults(func=cmd_mcp_stats)

    p_telemetry = sub.add_parser(
        "telemetry",
        help="Show or change anonymous usage-sharing consent (ADR-041).",
        parents=[version_parent],
    )
    p_telemetry.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["on", "off", "status"],
        help="on: opt in; off: opt out; status: show consent and what is shared (default).",
    )
    p_telemetry.set_defaults(func=cmd_telemetry)

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

    p_quickstart = sub.add_parser(
        "quickstart",
        help="Guided first run: establish identity and scaffold a first artifact in one step.",
        parents=[version_parent],
    )
    p_quickstart.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Repository root to set up (default: current directory).",
    )
    p_quickstart.add_argument(
        "--key",
        default=DEFAULT_KEY,
        help="Repository key used as the artifact ID prefix (default: RAC; "
        "2-10 uppercase alphanumeric characters starting with a letter).",
    )
    p_quickstart.add_argument(
        "--type",
        default=DEFAULT_TYPE,
        help="Starter artifact type (default: requirement). One of the "
        "canonical templates from `rac templates`.",
    )
    p_quickstart.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_quickstart.set_defaults(func=cmd_quickstart)

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

    p_skill = sub.add_parser(
        "skill",
        help="Install or list the bundled Claude Code agent skills.",
        parents=[version_parent],
    )
    p_skill.add_argument(
        "action",
        choices=["install", "list"],
        help="What to do: install bundled skill(s), or list them.",
    )
    p_skill.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Skill to install (default: all bundled skills, all-or-nothing).",
    )
    p_skill.add_argument(
        "--dir",
        default=".",
        help="Target project directory (default: current directory).",
    )
    p_skill.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_skill.set_defaults(func=cmd_skill)

    p_hook = sub.add_parser(
        "hook",
        help="Install or list the bundled git hooks (commit-time cadence nudge).",
        parents=[version_parent],
    )
    p_hook.add_argument(
        "action",
        choices=["install", "list"],
        help="What to do: install a bundled hook, or list them.",
    )
    p_hook.add_argument(
        "--style",
        choices=available_hooks(),
        default=DEFAULT_STYLE,
        help=(
            "Which hook to install (default: post-commit, an advisory cadence "
            "nudge that never blocks; pre-commit validates staged artifacts)."
        ),
    )
    p_hook.add_argument(
        "--dir",
        default=".",
        help="Target git repository directory (default: current directory).",
    )
    p_hook.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    p_hook.set_defaults(func=cmd_hook)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
