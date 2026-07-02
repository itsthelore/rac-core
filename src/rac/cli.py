"""Command-line interface for RAC.

`rac` is a thin adapter over the service gate (ADR-005): every subcommand
normalizes its arguments, calls exactly one service or core function, hands the
result to one :mod:`rac.output` renderer, and picks an exit code. No domain
logic lives here — the CLI owns the argument grammar, the exit codes, a handful
of stderr error strings, the interactive consent prompt, and the usage-telemetry
and broken-pipe wrapping around dispatch.

Commands:
    rac validate <file.md | dir | -> [--json | --sarif] [--top-level]
    rac validate <file.md | -> --corpus <dir> [--json]
    rac diff <old.md> <new.md> [--json]
    rac stats <directory> [--json]
    rac ingest <file> [-o OUT | --stdout] [--force] [--json]
    rac inspect <file.md | dir | -> [--json] [--verbose] [--top-level]
    rac improve <file.md | -> [--json | --template]
    rac schema [--list] [type] [--json | --template]
    rac relationships <dir | file.md> [--validate] [--json | --sarif] [--top-level]
    rac rename <old-id> <new-id> <directory> [--json] [--apply] [--top-level]
    rac review <directory> [--json | --sarif] [--stale-after DAYS] [--top-level]
    rac doctor [directory] [--json] [--hub-threshold N] [--top-level]
    rac coverage [directory] [--json]
    rac gate <directory> [--json | --sarif] [--top-level]
    rac watchkeeper [directory] [--base REF] [--head REF]
                    [--format human|json|github] [--json] [--fail-on POLICY]
                    [--no-annotate]
    rac portfolio <directory> [--json] [--top-level]
    rac index [directory] [--json] [--top-level]
    rac export [directory] [--json | --html | --okf | --documents | --graph
               | --agent-rules [--check]] [--client CLIENT ...] [--out PATH]
    rac explorer [directory] [--top-level]
    rac mcp [--root PATH] [--telemetry]
    rac mcp-stats [--json | --share]
    rac telemetry [on | off | status] [--enterprise] [--unlock]
    rac usage [--json | --share]
    rac new <artifact-type> <output-path> [--json]
    rac templates [--json]
    rac init [directory] [--key KEY] [--ticketing PROVIDER] [--profile NAME] [--json]
    rac quickstart [directory] [--key KEY] [--type TYPE] [--json]
    rac resolve <ID> [directory] [--json] [--top-level]
    rac find <query> [directory] [--type TYPE | --decisions] [--json] [--explain]
    rac eval [--check | --update-baseline] [--json]
             [--root DIR] [--queries PATH] [--baseline PATH] [--config PATH]
    rac migrate metadata <directory> [--dry-run] [--json] [--top-level]
    rac skill install [name] [--dir PATH] [--json]
    rac skill list [--json]
    rac hook install [--style post-commit|pre-commit] [--dir PATH] [--json]
    rac hook list [--json]

Exit codes:
    0  success — including "empty" outcomes that are valid states rather than
       failures: an empty corpus, a query with no matches, a completed dry run
       with nothing to migrate, references that all resolve, an mcp-stats/usage
       summary over a missing log, a watchkeeper run with nothing to flag under
       the chosen --fail-on policy.
    1  a repository finding: validation errors; no valid known artifacts;
       ingest conversion failed; broken/ambiguous/self references or duplicate
       identifiers; priority 1-2 review findings; a fired eval gate; a doctor
       integrity error; an init key conflict; a resolve miss or duplicate id; a
       refused rename; a skill/hook target that already exists; a broken
       installation (missing packaged resource); watchkeeper review recommended.
    2  a usage or IO error: file not found, not a directory, unsupported type,
       refuse-to-overwrite, missing output directory, uninitialized repository,
       invalid key/type/profile, explorer extra absent, unknown skill/hook name,
       export --out without --html/--okf or an unwritable target, a missing or
       corrupt vendored Portal shell, an unknown watchkeeper revision or a
       directory outside git, an unreadable eval corpus or missing query set.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import NoReturn

from rac import consent, usage
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
from rac.core.validation import TICKETING_PROVIDER_NAMES, has_errors
from rac.output.portal import PortalSeamMissing, PortalShellMissing
from rac.services import coverage as coverage_service
from rac.services import doctor
from rac.services import eval as eval_service
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
from rac.services.export import (
    build_corpus_export,
    build_documents_export,
    build_graph_export,
)
from rac.services.gate import build_gate
from rac.services.hook import HookFileExists, NotAGitWorkTree, install_hook
from rac.services.improve import improve_product
from rac.services.index import build_repository_index
from rac.services.ingest import ConversionError, UnsupportedDocument, ingest
from rac.services.init import (
    DEFAULT_KEY,
    InvalidProfile,
    InvalidRepositoryKey,
    InvalidTicketingProvider,
    MalformedRepositoryConfig,
    RepositoryKeyConflict,
    init_repository,
)
from rac.services.inspect import build_inspection, inspect_directory
from rac.services.migrate import migrate_metadata
from rac.services.portfolio import build_portfolio_summary
from rac.services.profiles import PROFILE_NAMES
from rac.services.quickstart import DEFAULT_TYPE, CorpusNotEmpty, quickstart
from rac.services.recency import artifact_recency
from rac.services.relationships import (
    build_relationship_report,
    build_relationship_report_file,
    validate_relationships,
    validate_relationships_file,
)
from rac.services.rename import apply_rename, compute_rename
from rac.services.resolve import (
    OUTCOME_DUPLICATE,
    OUTCOME_RESOLVED,
    find_artifacts,
    find_decisions,
    resolve_artifact,
)
from rac.services.review import DEFAULT_STALE_AFTER_DAYS, build_review
from rac.services.revisions import NotAGitRepository, RevisionNotFound
from rac.services.skill import SkillFileExists, install_skills
from rac.services.stats import collect_stats
from rac.services.validate import (
    validate_directory,
    validate_product,
    validate_stdin_against_corpus,
)
from rac.services.watchkeeper import build_watchkeeper_report

from . import __version__

EXIT_OK = 0
EXIT_VALIDATION_FAILED = 1
EXIT_USAGE = 2


# --- shared plumbing ---------------------------------------------------------


def _usage_error(message: str) -> NoReturn:
    """Print ``rac: {message}`` to stderr and abort with the usage exit code.

    The input-validation convention (Trap #2): argument/IO problems *raise*
    ``SystemExit(EXIT_USAGE)`` here, distinct from ``cmd_telemetry``'s flag-combo
    guards, which ``return EXIT_USAGE`` without raising. ``from None`` keeps the
    traceback quiet when this fires from inside an ``except`` block.
    """
    print(f"rac: {message}", file=sys.stderr)
    raise SystemExit(EXIT_USAGE) from None


def _operational_error(exc: Exception) -> int:
    """Report a broken-installation / operational failure and return exit 1.

    The second tier of the exception ladder: unlike a usage error it does not
    raise — a broken packaged resource or unreadable config is a repository
    finding, reported as ``rac: {exc}`` and surfaced as ``EXIT_VALIDATION_FAILED``.
    """
    print(f"rac: {exc}", file=sys.stderr)
    return EXIT_VALIDATION_FAILED


def _require_dir(path: str) -> None:
    """Guard the ~15 directory-scanning handlers with one 'not a directory' check."""
    if not Path(path).is_dir():
        _usage_error(f"not a directory: {path}")


def _default_corpus_dir(directory: str | None) -> str:
    """Resolve an omitted directory to the conventional knowledge root (ADR-018).

    ``rac/`` when it exists, else the current directory — the default for
    ``watchkeeper`` and ``explorer``.
    """
    if directory is not None:
        return directory
    return "rac" if Path("rac").is_dir() else "."


def _read(path: str) -> Product:
    """Parse a single named file, or print an error and exit with EXIT_USAGE.

    A directly named file that is missing or unreadable is a usage error here —
    distinct from the corpus walk, where ``parse_file`` degrades such inputs
    gracefully so one bad file never aborts the walk (WS4, REQ-005).
    """
    if not Path(path).is_file():
        _usage_error(f"file not found: {path}")
    product = parse_file(path)
    if any(issue.code == "unreadable-artifact" for issue in product.parse_issues):
        _usage_error(f"cannot read {path}")
    return product


def _read_validate_input(target: str) -> Product:
    """Parse validation input from a Markdown file or stdin (``-``)."""
    if target == "-":
        return parse(sys.stdin.read(), source_path="-")
    return _read(target)


def _read_markdown_input(target: str, command: str) -> str:
    """Read a Markdown file or stdin (``-``) for ``command`` (inspect/improve)."""
    if target == "-":
        return sys.stdin.read()
    path = Path(target)
    if not path.is_file():
        _usage_error(f"file not found: {target}")
    if path.suffix.lower() not in (".md", ".markdown"):
        _usage_error(
            f"{command} expects a Markdown file; convert it first with: rac ingest {target}"
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        _usage_error(f"cannot read {target}: {exc}")


# --- validation, diffing, and single-artifact inspection ---------------------


def cmd_validate(args: argparse.Namespace) -> int:
    corpus = getattr(args, "corpus", None)

    # Directory target: validate every recognized artifact beneath it (v0.7.9).
    # Unknown-type files are skipped, matching `rac portfolio`; the legacy
    # requirement fallback applies only to explicit single-file input.
    if args.file != "-" and Path(args.file).is_dir():
        if corpus is not None:
            # --corpus resolves *one proposed document* against a corpus; a
            # directory target already validates every artifact in place, so the
            # flag is redundant and ambiguous there (ADR-067, v0.21.17).
            _usage_error("--corpus applies to stdin ('-') or a single file")
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
        _usage_error("--sarif applies to directory validation")

    product = _read_validate_input(args.file)

    # Corpus-aware single-document validation (v0.21.17, ADR-067): structural
    # findings *plus* the proposed document's references resolved against the
    # live corpus. This is the seam the generated Claude Code pre-edit hook pipes
    # proposed content into — a reference to a retired or missing decision blocks
    # before the edit lands. A structural error or any corpus reference finding
    # fails the run.
    if corpus is not None:
        if not Path(corpus).is_dir():
            _usage_error(f"--corpus is not a directory: {corpus}")
        source_path = "-" if args.file == "-" else str(Path(args.file))
        corpus_result = validate_stdin_against_corpus(product, corpus, source_path=source_path)
        if args.json:
            print(outputs.render_stdin_corpus_json(corpus_result))
        else:
            print(outputs.render_stdin_corpus_human(corpus_result))
        return EXIT_OK if corpus_result.ok else EXIT_VALIDATION_FAILED

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
    _require_dir(args.directory)
    stats = collect_stats(args.directory)
    if args.json:
        print(outputs.render_stats_json(stats))
    else:
        print(outputs.render_stats_human(stats))
    # Success while the portfolio has analysable content (at least one valid
    # feature/decision/roadmap/prompt/design) or is an empty day-one corpus.
    # `has_meaningful_content` and `is_empty` are computed behind the gate
    # (ADR-015); the CLI only reads them. An empty corpus is a valid state, not a
    # failure (v0.13.1) — it exits 0, matching validate/review/portfolio. The
    # "files exist but none are valid known artifacts" failure survives for a
    # non-empty corpus and will move behind a future --strict flag.
    return EXIT_OK if (stats.has_meaningful_content or stats.is_empty) else EXIT_VALIDATION_FAILED


def cmd_ingest(args: argparse.Namespace) -> int:
    if not Path(args.file).is_file():
        _usage_error(f"file not found: {args.file}")

    try:
        result = ingest(args.file)
    except UnsupportedDocument as exc:  # unhandled type / missing extra
        _usage_error(str(exc))
    except ConversionError as exc:  # recognized file, failed to convert
        return _operational_error(exc)

    if args.output:
        out = Path(args.output)
        if out.exists() and not args.force:
            _usage_error(f"{args.output} already exists; pass --force to overwrite")
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


def cmd_inspect(args: argparse.Namespace) -> int:
    # Directory target: aggregate per-file results into type counts.
    if args.file != "-" and Path(args.file).is_dir():
        result = inspect_directory(args.file, recursive=not args.top_level)
        if args.json:
            print(outputs.render_dir_inspect_json(result))
        else:
            print(outputs.render_dir_inspect_human(result))
        return EXIT_OK

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
            _usage_error("--template cannot be used with --list")
        if args.schema:
            _usage_error("schema name cannot be used with --list")
        if args.json:
            print(outputs.render_schema_list_json(names))
        else:
            print(outputs.render_schema_list_human(names))
        return EXIT_OK

    if not args.schema:
        _usage_error("schema name required unless --list is passed")

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
        _usage_error("relationships --sarif requires --validate")
    path = Path(args.path)
    # --recursive is the default; --top-level disables it (like `rac inspect`).
    if path.is_dir():
        is_dir = True
    elif path.is_file():
        if path.suffix.lower() not in (".md", ".markdown"):
            _usage_error(
                f"relationships expects a Markdown file or directory; "
                f"convert it first with: rac ingest {args.path}"
            )
        is_dir = False
    else:
        _usage_error(f"path not found: {args.path}")

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
        # Validation-style exit codes (REQ-007): 0 when everything resolves, 1
        # when any issue is found, 2 (above) for usage errors.
        return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED

    if is_dir:
        rel_report = build_relationship_report(args.path, recursive=not args.top_level)
    else:
        rel_report = build_relationship_report_file(args.path)
    if args.json:
        print(outputs.render_relationships_json(rel_report))
    else:
        print(outputs.render_relationships_human(rel_report))
    # A completed inspection always succeeds — finding no relationships is a
    # valid outcome, not an error (REQ-010).
    return EXIT_OK


def cmd_rename(args: argparse.Namespace) -> int:
    """Compute (and optionally apply) a corpus-wide artifact-id rename (v0.21.18).

    Default is a dry run: it prints the planned edit set and exits 0 for any
    valid plan (a preview always succeeds). An unresolvable/ambiguous OLD or an
    invalid/colliding NEW is a refusal: it prints the reason (human output to
    *stderr*) and exits 1 — the rename was rejected, not a usage error.
    ``--apply`` writes the edits and reports what changed. The engine owns the
    edit set (ADR-063); the CLI only renders and applies it.
    """
    _require_dir(args.directory)
    plan = compute_rename(args.directory, args.old, args.new, recursive=not args.top_level)

    if not plan.ok:
        if args.json:
            print(outputs.render_rename_json(plan))
        else:
            print(outputs.render_rename_human(plan), file=sys.stderr)
        # Every refusal (unknown/ambiguous OLD, invalid/colliding NEW,
        # filename-only alias) leaves the corpus untouched and exits 1 — a
        # rejected rename, distinct from EXIT_USAGE (2) for argument/IO errors.
        return EXIT_VALIDATION_FAILED

    if not args.apply:
        if args.json:
            print(outputs.render_rename_json(plan))
        else:
            print(outputs.render_rename_human(plan))
        return EXIT_OK

    result = apply_rename(plan)
    if args.json:
        print(outputs.render_rename_result_json(result))
    else:
        print(outputs.render_rename_result_human(result))
    return EXIT_OK


# --- repository intelligence -------------------------------------------------


def cmd_review(args: argparse.Namespace) -> int:
    _require_dir(args.directory)
    if args.stale_after is not None and args.stale_after < 0:
        _usage_error("--stale-after must be a non-negative number of days")
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


def cmd_doctor(args: argparse.Namespace) -> int:
    """Aggregate corpus health into one verdict with paste-ready fixes (WS3).

    Composes validate + relationships and adds high-fan-out hubs and an
    injection-style content heuristic. Exits non-zero only on a validation or
    relationship-integrity error; orphan/hub/injection warnings exit 0 (REQ-007).
    """
    _require_dir(args.directory)
    report = doctor.diagnose(
        args.directory,
        recursive=not args.top_level,
        hub_threshold=args.hub_threshold,
    )
    if args.json:
        print(doctor.render_doctor_json(report))
    else:
        print(doctor.render_doctor_human(report))
    return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED


def cmd_coverage(args: argparse.Namespace) -> int:
    """Report typed traceability coverage gaps — advisory, never a build failure.

    Unscheduled requirements, unapplied decisions, and unscoped roadmaps derived
    from the relationship graph (rac-traceability-coverage-report, WS-F).
    Coverage is a completeness signal for human judgement, so it always exits 0
    (REQ-005).
    """
    _require_dir(args.directory)
    report = coverage_service.analyze_coverage(args.directory)
    if args.json:
        print(coverage_service.render_coverage_json(report))
    else:
        print(coverage_service.render_coverage_human(report))
    return EXIT_OK


def cmd_gate(args: argparse.Namespace) -> int:
    _require_dir(args.directory)
    try:
        report = build_gate(args.directory, recursive=not args.top_level)
    except MalformedRepositoryConfig as exc:  # unreadable/invalid .rac/config.yaml
        return _operational_error(exc)
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
    args.directory = _default_corpus_dir(args.directory)
    _require_dir(args.directory)
    try:
        report = build_watchkeeper_report(args.directory, base=args.base, head=args.head)
    except (NotAGitRepository, RevisionNotFound) as exc:
        _usage_error(str(exc))
    output_format = "json" if args.json else args.format
    if output_format == "json":
        print(outputs.render_watchkeeper_json(report))
    elif output_format == "github":
        # stdout is the step-summary Markdown; annotations go to stderr so
        # `> "$GITHUB_STEP_SUMMARY"` keeps them in the step log, where the runner
        # turns workflow commands into inline annotations.
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
    _require_dir(args.directory)
    summary = build_portfolio_summary(args.directory, recursive=not args.top_level)
    if args.json:
        print(outputs.render_portfolio_json(summary))
    else:
        print(outputs.render_portfolio_human(summary))
    return EXIT_OK


def cmd_index(args: argparse.Namespace) -> int:
    _require_dir(args.directory)
    index = build_repository_index(args.directory, recursive=not args.top_level)
    if args.json:
        print(outputs.render_index_json(index))
    else:
        print(outputs.render_index_human(index))
    return EXIT_OK


# --- export and its agent-rules mode -----------------------------------------


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
    _require_dir(args.directory)

    # Agent-rules is a distinct mode (ADR-067): a distilled, drift-guarded
    # projection of live decisions into per-client managed blocks. It owns --out
    # (the output root), --client (target selectors), --check (the drift gate),
    # and --json (machine output) — none of the export-payload modes apply.
    if args.agent_rules:
        return _cmd_agent_rules(args)
    if args.check:
        _usage_error("--check requires --agent-rules")
    if args.client:
        _usage_error("--client requires --agent-rules")

    if args.json and (args.html or args.okf):
        _usage_error("--json cannot combine with --html or --okf")
    if args.out is not None and not (args.html or args.okf):
        _usage_error("--out requires --html or --okf (--json writes to stdout)")

    # Documents projection (v0.25.0 WS1, ADR-073): an ingestion-ready JSONL
    # stream for external memory/RAG backends — Markdown bodies, not the viewer's
    # HTML. Written to stdout so it stays pipeable (ADR-011); additive over the
    # default viewer JSON (ADR-007).
    if args.documents:
        print(outputs.render_documents_jsonl(build_documents_export(args.directory)))
        return EXIT_OK

    # Typed graph projection (v0.25.0 WS2, ADR-074): nodes + typed/directed edges
    # for graph backends, surfacing the real relationship graph (ADR-055) rather
    # than the viewer's flattened relates-to. Additive; stdout, pipeable.
    if args.graph:
        print(outputs.render_graph_json(build_graph_export(args.directory)))
        return EXIT_OK

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
            _usage_error(f"cannot write {out}: {exc}")
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
        _usage_error(str(exc))
    out = args.out if args.out is not None else "lore-export.html"
    try:
        Path(out).write_text(html, encoding="utf-8")
    except OSError as exc:
        _usage_error(f"cannot write {out}: {exc}")
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
        # Effectively unreachable from the CLI: argparse `choices` reject an
        # unknown --client with exit 2 first. Kept for direct-call parity.
        valid = "claude, agents, cursor, copilot"
        _usage_error(f"unknown --client: {', '.join(bad)} (choose from {valid})")

    root = _agent_rules_root(args.directory, args.out)
    try:
        if args.check:
            result = check_agent_rules(args.directory, str(root), clients=args.client)
        else:
            result = generate_agent_rules(args.directory, str(root), clients=args.client)
    except OSError as exc:
        _usage_error(f"cannot write under {root}: {exc}")

    if args.json:
        print(outputs.render_agent_rules_json(result))
    else:
        print(outputs.render_agent_rules_human(result))

    if args.check and result.drifted:
        return EXIT_VALIDATION_FAILED
    return EXIT_OK


# --- serving: explorer, mcp, and the two telemetry read-backs ----------------


def cmd_explorer(args: argparse.Namespace) -> int:
    args.directory = _default_corpus_dir(args.directory)
    _require_dir(args.directory)
    # Imported lazily: launch decides whether the explorer extra is installed,
    # and the base CLI must not pay an import cost for the optional TUI.
    from rac.explorer.launch import ExplorerUnavailable, run_explorer

    try:
        return run_explorer(args.directory, recursive=not args.top_level)
    except ExplorerUnavailable as exc:
        _usage_error(str(exc))


def cmd_mcp(args: argparse.Namespace) -> int:
    _require_dir(args.root)
    # Imported lazily: the MCP SDK is only needed when serving, and the base CLI
    # must not pay its import cost for every other command. stdout belongs to the
    # MCP protocol, so any diagnostics here go to stderr.
    from rac.mcp.audit import MalformedAuditConfig
    from rac.mcp.server import run_server

    try:
        return run_server(args.root, telemetry_enabled=args.telemetry)
    except MalformedAuditConfig as exc:  # bad `audit:` stanza (ADR-084)
        _usage_error(str(exc))


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


def cmd_usage(args: argparse.Namespace) -> int:
    """Unified read-back over the CLI-usage log and the Guide log (ADR-046, WS-E).

    `rac mcp-stats` stays Guide-only for back-compat; this command summarises
    both. An empty or missing log is a valid answer (telemetry is off by default).
    """
    from rac.mcp.telemetry import summarize as guide_summarize

    summary = usage.summarize_usage()
    guide = guide_summarize().to_dict()
    if args.share:
        print(usage.share_url(summary, guide))
    elif args.json:
        print(usage.render_json(summary, guide))
    else:
        print(usage.render_human(summary, guide))
    return EXIT_OK


# --- authoring and lifecycle -------------------------------------------------


def cmd_new(args: argparse.Namespace) -> int:
    try:
        # ``create_artifact`` is a module attribute so tests can monkeypatch
        # ``rac.cli.create_artifact``; keep the bare-name call for the live lookup.
        created = create_artifact(args.type, args.output_path)
    except TemplateNotFound as exc:  # unsupported type → usage error
        _usage_error(str(exc))
    except (OutputPathExists, OutputDirectoryMissing, MissingRepositoryConfig) as exc:
        _usage_error(str(exc))
    except (
        TemplateResourceMissing,  # broken installation
        MalformedRepositoryConfig,  # unreadable .rac/config.yaml
        IdGenerationExhausted,  # broken entropy source
    ) as exc:
        return _operational_error(exc)
    if args.json:
        print(outputs.render_new_json(created))
    else:
        print(outputs.render_new_human(created))
    return EXIT_OK


def cmd_templates(args: argparse.Namespace) -> int:
    names = available_templates()
    if args.json:
        print(outputs.render_templates_json(names))
    else:
        print(outputs.render_templates_human(names))
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    _require_dir(args.directory)
    try:
        result = init_repository(
            args.directory, key=args.key, ticketing=args.ticketing, profile=args.profile
        )
    except (InvalidRepositoryKey, InvalidTicketingProvider, InvalidProfile) as exc:
        _usage_error(str(exc))
    except (RepositoryKeyConflict, MalformedRepositoryConfig) as exc:
        return _operational_error(exc)
    if args.json:
        print(outputs.render_init_json(result))
    else:
        print(outputs.render_init_human(result))
        _maybe_ask_usage_sharing()
    return EXIT_OK


def cmd_quickstart(args: argparse.Namespace) -> int:
    _require_dir(args.directory)
    try:
        result = quickstart(args.directory, key=args.key, artifact_type=args.type)
    except TemplateNotFound as exc:  # unsupported type → usage error
        _usage_error(str(exc))
    except InvalidRepositoryKey as exc:  # bad key syntax → usage error
        _usage_error(str(exc))
    except OutputDirectoryMissing as exc:  # parent missing → usage error
        _usage_error(str(exc))
    except (
        CorpusNotEmpty,  # corpus already has artifacts → refused
        RepositoryKeyConflict,  # established key differs → refused
        OutputPathExists,  # starter path already taken → refused (never overwrite)
        MalformedRepositoryConfig,  # unreadable .rac/config.yaml
        TemplateResourceMissing,  # broken installation
        IdGenerationExhausted,  # broken entropy source
    ) as exc:
        return _operational_error(exc)
    if args.json:
        print(outputs.render_quickstart_json(result))
    else:
        print(outputs.render_quickstart_human(result))
        _maybe_ask_usage_sharing()
    return EXIT_OK


def cmd_resolve(args: argparse.Namespace) -> int:
    _require_dir(args.directory)
    result = resolve_artifact(args.directory, args.id, recursive=not args.top_level)
    if args.json:
        print(outputs.render_resolve_json(result))
    elif result.outcome == OUTCOME_RESOLVED:
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
    _require_dir(args.directory)
    if args.decisions:
        # `--decisions` is the live decision query (ADR-067): it implies the
        # decision type filter *and* restricts to live (Accepted, non-retired)
        # decisions — the deterministic "what did we decide about X" retrieval.
        # `--type` is redundant with it and mutually exclusive at the parser.
        result = find_decisions(args.directory, args.query, recursive=not args.top_level)
    else:
        result = find_artifacts(
            args.directory,
            args.query,
            artifact_type=args.type,
            recursive=not args.top_level,
        )
    if args.json:
        print(outputs.render_find_json(result, explain=args.explain))
    else:
        print(outputs.render_find_human(result, explain=args.explain))
    # An empty result is a valid outcome, not an error (a query always succeeds).
    return EXIT_OK


def cmd_eval(args: argparse.Namespace) -> int:
    """Score retrieval against the fixture benchmark, or gate against the baseline.

    Three modes (default report / ``--check`` gate / ``--update-baseline``): a
    clean report exits 0; the gate exits 1 on regression; any usage error
    (missing baseline, unreadable corpus, malformed query set) exits 2.
    ``--update-baseline`` is human-only — CI never passes it (REQ-006/REQ-007).
    """
    try:
        scorecard = eval_service.run_eval(args.root, args.queries)
        if args.update_baseline:
            Path(args.baseline).write_text(
                eval_service.render_metrics_json(scorecard.metrics) + "\n", encoding="utf-8"
            )
            print(f"rac eval: baseline updated -> {args.baseline}")
            return EXIT_OK
        if args.check:
            baseline = eval_service.load_baseline(args.baseline)
            config = eval_service.load_config(args.config)
            failures = eval_service.evaluate_gate(scorecard.metrics, baseline, config)
            if failures:
                for failure in failures:
                    print(failure.render())
                return EXIT_VALIDATION_FAILED
            print("rac eval: gate PASS")
            return EXIT_OK
        if args.json:
            print(eval_service.render_scorecard_json(scorecard))
        else:
            print(eval_service.render_scorecard_human(scorecard))
        return EXIT_OK
    except eval_service.EvalUsageError as exc:
        print(f"rac eval: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None


def cmd_migrate(args: argparse.Namespace) -> int:
    _require_dir(args.directory)
    try:
        report = migrate_metadata(
            args.directory, dry_run=args.dry_run, recursive=not args.top_level
        )
    except MissingRepositoryConfig as exc:
        _usage_error(str(exc))
    except (MalformedRepositoryConfig, IdGenerationExhausted) as exc:
        return _operational_error(exc)
    if args.json:
        print(outputs.render_migrate_json(report))
    else:
        print(outputs.render_migrate_human(report))
    # Completed migration (or dry run) always succeeds — nothing to migrate is a
    # valid outcome.
    return EXIT_OK


# --- packaged-resource installers --------------------------------------------


def cmd_skill(args: argparse.Namespace) -> int:
    if args.action == "list":
        if args.name is not None:
            _usage_error("skill list takes no skill name")
        specs = skill_specs()
        if args.json:
            print(outputs.render_skill_list_json(specs))
        else:
            print(outputs.render_skill_list_human(specs))
        return EXIT_OK

    _require_dir(args.dir)
    try:
        # ``install_skills`` is a module attribute for the same monkeypatch
        # reason as ``create_artifact``; the bare-name call keeps it live.
        installation = install_skills(args.dir, args.name)
    except SkillNotFound as exc:  # unknown skill name → usage error
        _usage_error(str(exc))
    except (SkillFileExists, SkillResourceMissing) as exc:  # refused / broken install
        return _operational_error(exc)
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

    _require_dir(args.dir)
    try:
        installation = install_hook(args.dir, args.style)
    except (HookNotFound, NotAGitWorkTree) as exc:  # usage errors → exit 2
        _usage_error(str(exc))
    except (HookFileExists, HookResourceMissing) as exc:  # refused / broken install
        return _operational_error(exc)
    if args.json:
        print(outputs.render_hook_install_json(installation))
    else:
        print(outputs.render_hook_install_human(installation))
    return EXIT_OK


# --- telemetry consent -------------------------------------------------------


def _maybe_ask_usage_sharing() -> None:
    """Ask the one-time usage-sharing question after a successful init (ADR-041).

    The CLI's only interactive prompt, deliberately narrow: a real TTY on both
    ends, no ``--json`` (the caller gates that), and no prior answer — either
    answer is persisted, so the question is asked at most once per machine. Empty
    input and EOF mean No; CI and pipes never reach ``input()``.
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
    enterprise = getattr(args, "enterprise", False)
    unlock = getattr(args, "unlock", False)
    # The enterprise flags are only meaningful with 'off' (ADR-086). These
    # guards *return* EXIT_USAGE rather than raising (Trap #2): a misused flag
    # combination is reported without an argparse-style abort.
    if (enterprise or unlock) and args.action != "off":
        print(
            "rac: --enterprise/--unlock are only valid with 'rac telemetry off'",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if unlock and not enterprise:
        print(
            "rac: --unlock requires --enterprise (use 'rac telemetry off --enterprise --unlock')",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if args.action == "on":
        if consent.load_consent().enterprise_locked:
            print(
                "rac: cannot opt in while the enterprise telemetry lock is set; "
                "remove it with 'rac telemetry off --enterprise --unlock' first "
                "(ADR-086).",
                file=sys.stderr,
            )
            return EXIT_USAGE
        record = consent.opt_in()
        print(f"Sharing on. Install id: {record.install_id}")
        print(
            "One anonymous daily ping: install id, rac version, active-repo "
            "count. Never paths, queries, or content (ADR-041)."
        )
        # Read the key through the module so the kill-switch monkeypatch is live.
        if not consent.POSTHOG_API_KEY:
            print("Note: this build has no PostHog key configured; nothing will be sent.")
    elif args.action == "off":
        if enterprise and unlock:
            consent.enterprise_unlock()
            print(
                "Enterprise lock removed. Sharing stays off; re-enable with "
                "'rac telemetry on' (ADR-086)."
            )
        elif enterprise:
            consent.enterprise_lock()
            print(
                "Sharing off and enterprise-locked. The daily ping is forced off "
                "and cannot be re-enabled until unlocked with "
                "'rac telemetry off --enterprise --unlock' (ADR-086)."
            )
        else:
            consent.opt_out()
            print("Sharing off. Nothing will be sent.")
    else:  # status
        status = consent.consent_status()
        if status.enterprise_locked:
            sharing = "locked (enterprise)"
        elif status.sharing:
            sharing = "on"
        else:
            sharing = "off"
        print(f"Sharing: {sharing}")
        print(f"Install id: {status.install_id or '(none)'}")
        print(f"Consented at: {status.consented_at or '(never)'}")
        print(f"Consent file: {status.path}")
        if status.enterprise_locked:
            print(
                "Enterprise lock: on — the daily ping is forced off. Remove with "
                "'rac telemetry off --enterprise --unlock' (ADR-086)."
            )
        elif status.sharing:
            print(
                "Shared daily: install id, rac version, active-repo count. "
                "Never paths, queries, or content (ADR-041)."
            )
        if not status.endpoint_configured:
            print("Endpoint key: not configured — nothing is sent.")
    return EXIT_OK


# --- parser construction -----------------------------------------------------

# The default recursion posture is a shared parent gesture: every dir-scanning
# subcommand recurses by default, --top-level opts out. --recursive is a
# vestigial no-op kept for the accepted-for-clarity argparse surface (only its
# inverse, --top-level, is read). Factored here so the ~11 identical declaration
# blocks live in one place.
_SCOPE_TOP_LEVEL_HELP = "Only the directory's top-level files (no recursion)."
_SCOPE_RECURSIVE_HELP = "Recurse into subdirectories (the default; accepted for clarity)."


def _add_scope(parser: argparse.ArgumentParser, *, recursive: bool = True) -> None:
    parser.add_argument("--top-level", action="store_true", help=_SCOPE_TOP_LEVEL_HELP)
    if recursive:
        parser.add_argument("--recursive", action="store_true", help=_SCOPE_RECURSIVE_HELP)


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )


def _add_analysis_commands(sub: argparse._SubParsersAction, parents: list) -> None:
    p_validate = sub.add_parser(
        "validate",
        help="Validate an artifact file, or every recognized artifact in a directory.",
        parents=parents,
    )
    p_validate.add_argument(
        "file", help="A Markdown artifact file, a directory, or '-' to read from stdin."
    )
    validate_format = p_validate.add_mutually_exclusive_group()
    validate_format.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    validate_format.add_argument(
        "--sarif",
        action="store_true",
        help="Emit SARIF 2.1.0 for GitHub Code Scanning (directory validation only).",
    )
    _add_scope(p_validate)
    p_validate.add_argument(
        "--corpus",
        metavar="DIR",
        help=(
            "Resolve the proposed document's references against the corpus at DIR "
            "(stdin '-' or a single file only). Reports references to retired or "
            "missing decisions in addition to structural findings. Used by the "
            "generated Claude Code pre-edit hook."
        ),
    )
    p_validate.set_defaults(func=cmd_validate)

    p_diff = sub.add_parser(
        "diff", help="Compare two versions of a requirement file.", parents=parents
    )
    p_diff.add_argument("old", help="Path to the old version.")
    p_diff.add_argument("new", help="Path to the new version.")
    _add_json(p_diff)
    p_diff.set_defaults(func=cmd_diff)

    p_stats = sub.add_parser(
        "stats", help="Summarize a directory of requirement files.", parents=parents
    )
    p_stats.add_argument("directory", help="Directory to scan recursively for *.md.")
    _add_json(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    p_ingest = sub.add_parser(
        "ingest",
        help="Convert a document (DOCX, PDF, HTML, PPTX, XLSX, Markdown) to Markdown.",
        parents=parents,
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
    _add_json(p_ingest)
    p_ingest.set_defaults(func=cmd_ingest)

    p_inspect = sub.add_parser(
        "inspect",
        help="Identify a Markdown document's artifact type and structure.",
        parents=parents,
    )
    p_inspect.add_argument("file", help="A Markdown file, a directory, or '-' to read from stdin.")
    _add_json(p_inspect)
    p_inspect.add_argument(
        "--verbose",
        action="store_true",
        help="Show the classification breakdown and score (single file only).",
    )
    _add_scope(p_inspect)
    p_inspect.set_defaults(func=cmd_inspect)

    p_improve = sub.add_parser(
        "improve",
        help="Suggest missing sections (and templates) for an artifact.",
        parents=parents,
    )
    p_improve.add_argument("file", help="A Markdown file, or '-' to read from stdin.")
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
        parents=parents,
    )
    p_schema.add_argument(
        "schema",
        nargs="?",
        help="Schema name, e.g. requirement, decision, roadmap, prompt, or design.",
    )
    p_schema.add_argument("--list", action="store_true", help="List available schemas.")
    schema_mode = p_schema.add_mutually_exclusive_group()
    schema_mode.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    schema_mode.add_argument(
        "--template", action="store_true", help="Emit a full Markdown starter template."
    )
    p_schema.set_defaults(func=cmd_schema)

    p_relationships = sub.add_parser(
        "relationships",
        help="Inspect explicit relationships across a directory (or single file).",
        parents=parents,
    )
    p_relationships.add_argument("path", help="A directory to scan, or a single Markdown file.")
    _add_json(p_relationships)
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
    _add_scope(p_relationships)
    p_relationships.set_defaults(func=cmd_relationships)

    p_rename = sub.add_parser(
        "rename",
        help="Safely rename an artifact id across the corpus (dry run; --apply writes).",
        parents=parents,
    )
    p_rename.add_argument("old", help="The existing artifact id (or alias) to rename.")
    p_rename.add_argument("new", help="The new artifact id, e.g. ADR-099.")
    p_rename.add_argument("directory", help="The corpus directory to scan.")
    _add_json(p_rename)
    p_rename.add_argument(
        "--apply",
        action="store_true",
        help="Apply the edit set to disk (default is a dry-run preview).",
    )
    _add_scope(p_rename, recursive=False)
    p_rename.set_defaults(func=cmd_rename)


def _add_intelligence_commands(sub: argparse._SubParsersAction, parents: list) -> None:
    p_review = sub.add_parser(
        "review",
        help="Review a repository: prioritized issues and suggested actions.",
        parents=parents,
    )
    p_review.add_argument("directory", help="Directory to scan recursively for *.md.")
    _add_json(p_review)
    p_review.add_argument(
        "--sarif",
        action="store_true",
        help="Emit SARIF 2.1.0 for GitHub Code Scanning (CI pull-request enforcement).",
    )
    _add_scope(p_review)
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

    p_doctor = sub.add_parser(
        "doctor",
        help="Diagnose corpus health in one pass, with a paste-ready fix per finding.",
        parents=parents,
    )
    p_doctor.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to diagnose recursively for *.md (default: current directory).",
    )
    _add_json(p_doctor)
    p_doctor.add_argument(
        "--hub-threshold",
        type=int,
        default=doctor.DEFAULT_HUB_THRESHOLD,
        help=(
            "Flag artifacts with more than this many resolved relationship edges "
            f"as high-fan-out hubs (default {doctor.DEFAULT_HUB_THRESHOLD})."
        ),
    )
    _add_scope(p_doctor)
    p_doctor.set_defaults(func=cmd_doctor)

    p_coverage = sub.add_parser(
        "coverage",
        help="Report typed traceability coverage gaps (advisory, never blocking).",
        parents=parents,
    )
    p_coverage.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to analyse recursively for *.md (default: current directory).",
    )
    _add_json(p_coverage)
    p_coverage.set_defaults(func=cmd_coverage)

    p_gate = sub.add_parser(
        "gate",
        help="Enforce the corpus: validation, relationships, and review under "
        "the corpus enforcement policy.",
        parents=parents,
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
    _add_scope(p_gate, recursive=False)
    p_gate.set_defaults(func=cmd_gate)

    p_watchkeeper = sub.add_parser(
        "watchkeeper",
        help="Review product knowledge changes between two repository states.",
        parents=parents,
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
        parents=parents,
    )
    p_portfolio.add_argument("directory", help="Directory to scan recursively for *.md.")
    _add_json(p_portfolio)
    _add_scope(p_portfolio)
    p_portfolio.set_defaults(func=cmd_portfolio)

    p_index = sub.add_parser(
        "index",
        help="Inventory every artifact in a repository (id, type, title, path).",
        parents=parents,
    )
    p_index.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    _add_json(p_index)
    _add_scope(p_index)
    p_index.set_defaults(func=cmd_index)


def _add_export_and_serving_commands(sub: argparse._SubParsersAction, parents: list) -> None:
    p_export = sub.add_parser(
        "export",
        help="Export the corpus as a deterministic JSON payload or a self-contained HTML Portal.",
        parents=parents,
    )
    p_export.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    # --html / --okf / --documents / --graph / --agent-rules are the mutually
    # exclusive write modes; the default (none of them) writes the JSON payload
    # to stdout. --json is *not* in the group: for the default mode it is the
    # explicit no-op it has always been, and with --agent-rules it toggles
    # JSON-vs-human output. --json with --html/--okf is rejected in cmd_export.
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
        "--documents",
        action="store_true",
        help="Write an ingestion-ready JSON Lines projection to stdout — one "
        "Markdown-bodied record per artifact, carrying id/type/status metadata — "
        "for external memory/RAG backends.",
    )
    export_mode.add_argument(
        "--graph",
        action="store_true",
        help="Write the corpus as a typed node+edge JSON graph to stdout — edges "
        "carry their relationship kind (supersedes/related_*) and direction — for "
        "graph/GraphRAG backends.",
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
        parents=parents,
    )
    p_explorer.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Repository to explore (default: rac/ when present, else the current directory).",
    )
    _add_scope(p_explorer)
    p_explorer.set_defaults(func=cmd_explorer)

    p_mcp = sub.add_parser(
        "mcp",
        help="Serve RAC repository knowledge to agents over MCP (stdio).",
        parents=parents,
    )
    p_mcp.add_argument(
        "--root", default=".", help="Repository root to serve (default: current directory)."
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
        "mcp-stats", help="Summarize the local Guide telemetry log.", parents=parents
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

    p_usage = sub.add_parser(
        "usage",
        help="Summarize recorded CLI and Guide usage (content-free, local).",
        parents=parents,
    )
    usage_mode = p_usage.add_mutually_exclusive_group()
    usage_mode.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    usage_mode.add_argument(
        "--share",
        action="store_true",
        help=(
            "Print a prefilled GitHub usage-report issue URL to review and "
            "submit in your browser; RAC sends nothing itself."
        ),
    )
    p_usage.set_defaults(func=cmd_usage)


def _add_authoring_commands(sub: argparse._SubParsersAction, parents: list) -> None:
    p_new = sub.add_parser(
        "new", help="Create a new artifact from its canonical template.", parents=parents
    )
    p_new.add_argument(
        "type", help="Artifact type, e.g. requirement, decision, roadmap, prompt, or design."
    )
    p_new.add_argument(
        "output_path", help="Where to write the artifact (taken literally; never overwritten)."
    )
    _add_json(p_new)
    p_new.set_defaults(func=cmd_new)

    p_templates = sub.add_parser(
        "templates",
        help="List the canonical artifact templates available to `rac new`.",
        parents=parents,
    )
    _add_json(p_templates)
    p_templates.set_defaults(func=cmd_templates)

    p_init = sub.add_parser(
        "init",
        help="Establish the repository identity namespace (.rac/config.yaml).",
        parents=parents,
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
        "--ticketing",
        choices=TICKETING_PROVIDER_NAMES,
        default=None,
        metavar="PROVIDER",
        help="External ticketing provider for ## Related Tickets references "
        f"(one of: {', '.join(TICKETING_PROVIDER_NAMES)}). Writes ticketing.provider "
        "to .rac/config.yaml; omit to leave it unset (ADR-087).",
    )
    p_init.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default=None,
        metavar="NAME",
        help="Apply a built-in config profile on a fresh init "
        f"(one of: {', '.join(PROFILE_NAMES)}). Writes .mcp.json client wiring and "
        "(enterprise) an enforcement-policy stanza — configuration only, never "
        "prose; never overwrites an existing file (ADR-088).",
    )
    _add_json(p_init)
    p_init.set_defaults(func=cmd_init)

    p_quickstart = sub.add_parser(
        "quickstart",
        help="Guided first run: establish identity and scaffold a first artifact in one step.",
        parents=parents,
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
    _add_json(p_quickstart)
    p_quickstart.set_defaults(func=cmd_quickstart)

    p_resolve = sub.add_parser(
        "resolve", help="Resolve an artifact ID to its type, title, and path.", parents=parents
    )
    p_resolve.add_argument("id", help="Artifact ID (canonical or legacy alias).")
    p_resolve.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    _add_json(p_resolve)
    _add_scope(p_resolve)
    p_resolve.set_defaults(func=cmd_resolve)

    p_find = sub.add_parser(
        "find", help="Search artifacts by ID, title, filename, or path.", parents=parents
    )
    p_find.add_argument("query", help="Case-insensitive substring to search for.")
    p_find.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    # `--type` and `--decisions` both narrow the search; `--decisions` is the
    # live decision query (decision type + Accepted/non-retired filter), so the
    # two are mutually exclusive (ADR-067).
    find_scope = p_find.add_mutually_exclusive_group()
    find_scope.add_argument(
        "--type", help="Only match artifacts of this type (requirement, decision, ...)."
    )
    find_scope.add_argument(
        "--decisions",
        action="store_true",
        help=(
            "Only live decisions (Accepted, non-retired) — the 'what did we "
            "decide about X / is X ruled out' query (ADR-067)."
        ),
    )
    _add_json(p_find)
    p_find.add_argument(
        "--explain",
        action="store_true",
        help=(
            "Show why each match was retrieved: the matched field, terms, and "
            "tier (additive `evidence`, ADR-037/ADR-038)."
        ),
    )
    _add_scope(p_find)
    p_find.set_defaults(func=cmd_find)

    p_eval = sub.add_parser(
        "eval",
        help="Score retrieval against the grounding benchmark; gate CI against the baseline.",
        parents=parents,
    )
    eval_mode = p_eval.add_mutually_exclusive_group()
    eval_mode.add_argument(
        "--check",
        action="store_true",
        help=(
            "CI gate: re-score and fail (exit 1) on a hard-negative violation, a "
            "metric below its floor, or a metric below baseline minus tolerance."
        ),
    )
    eval_mode.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Human-only re-baseline: overwrite the baseline with the current "
            "metrics. CI must never pass this."
        ),
    )
    p_eval.add_argument(
        "--json", action="store_true", help="Emit the full scorecard JSON instead of tables."
    )
    p_eval.add_argument(
        "--root",
        default=eval_service.DEFAULT_CORPUS,
        help="Fixture corpus directory (default: tests/eval/corpus).",
    )
    p_eval.add_argument(
        "--queries",
        default=eval_service.DEFAULT_QUERIES,
        help="Query set JSON (default: tests/eval/queries.json).",
    )
    p_eval.add_argument(
        "--baseline",
        default=eval_service.DEFAULT_BASELINE,
        help="Baseline metrics JSON (default: tests/eval/baseline.json).",
    )
    p_eval.add_argument(
        "--config",
        default=eval_service.DEFAULT_CONFIG,
        help="Gate config (floors + tolerance) JSON (default: tests/eval/eval-config.json).",
    )
    p_eval.set_defaults(func=cmd_eval)

    p_migrate = sub.add_parser(
        "migrate",
        help="Migrate existing artifacts onto canonical frontmatter identity.",
        parents=parents,
    )
    p_migrate.add_argument(
        "target", choices=["metadata"], help="What to migrate (this release: metadata)."
    )
    p_migrate.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be migrated without writing any file.",
    )
    _add_json(p_migrate)
    _add_scope(p_migrate)
    p_migrate.set_defaults(func=cmd_migrate)


def _add_resource_commands(sub: argparse._SubParsersAction, parents: list) -> None:
    p_skill = sub.add_parser(
        "skill", help="Install or list the bundled Claude Code agent skills.", parents=parents
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
        "--dir", default=".", help="Target project directory (default: current directory)."
    )
    _add_json(p_skill)
    p_skill.set_defaults(func=cmd_skill)

    p_hook = sub.add_parser(
        "hook",
        help="Install or list the bundled git hooks (commit-time cadence nudge).",
        parents=parents,
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
        "--dir", default=".", help="Target git repository directory (default: current directory)."
    )
    _add_json(p_hook)
    p_hook.set_defaults(func=cmd_hook)

    p_telemetry = sub.add_parser(
        "telemetry",
        help="Show or change anonymous usage-sharing consent (ADR-041).",
        parents=parents,
    )
    p_telemetry.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["on", "off", "status"],
        help="on: opt in; off: opt out; status: show consent and what is shared (default).",
    )
    p_telemetry.add_argument(
        "--enterprise",
        action="store_true",
        help="With 'off': hard-lock the ping off and refuse 'on' until unlocked (ADR-086).",
    )
    p_telemetry.add_argument(
        "--unlock",
        action="store_true",
        help="With 'off --enterprise': remove the enterprise hard-lock (ADR-086).",
    )
    p_telemetry.set_defaults(func=cmd_telemetry)


def build_parser() -> argparse.ArgumentParser:
    # A shared `--version` parent, added to the root parser *and* every
    # subparser, so `--version` works everywhere (e.g. `rac ingest foo.docx
    # --version`) and short-circuits before a required positional is checked.
    version_parent = argparse.ArgumentParser(add_help=False)
    version_parent.add_argument("--version", action="version", version=f"rac {__version__}")
    parents = [version_parent]

    parser = argparse.ArgumentParser(
        prog="rac",
        description="Requirements As Code — lint and diff Markdown requirements.",
        parents=parents,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    _add_analysis_commands(sub, parents)
    _add_intelligence_commands(sub, parents)
    _add_export_and_serving_commands(sub, parents)
    _add_authoring_commands(sub, parents)
    _add_resource_commands(sub, parents)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # parse_args is OUTSIDE the try: an argparse SystemExit (a usage error, or
    # --version) has no command to record and must not be treated as a dispatched
    # command (Trap #4).
    args = parser.parse_args(argv)

    # CLI usage telemetry (ADR-046, WS-E): record one content-free event per
    # completed command, after dispatch, gated by recorded consent. Write-only
    # and silent-fail, so it never alters output or exit codes (ADR-032).
    command = getattr(args, "command", "") or ""
    start = time.monotonic()
    outcome = usage.OUTCOME_EXCEPTION
    try:
        result = args.func(args)
        outcome = usage.OUTCOME_OK if result == 0 else usage.OUTCOME_ERROR
        return result
    except SystemExit as exc:
        outcome = usage.OUTCOME_OK if exc.code in (0, None) else usage.OUTCOME_ERROR
        raise
    except BrokenPipeError:
        # The downstream consumer closed the pipe (e.g. `rac export … | head`):
        # die quietly instead of dumping a traceback. Pointing stdout's fd at
        # devnull absorbs the interpreter's exit-time flush of the dead pipe,
        # which would otherwise print "Exception ignored" noise to stderr.
        outcome = usage.OUTCOME_ERROR
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1
    finally:
        usage.record_command(command, outcome, int((time.monotonic() - start) * 1000))


if __name__ == "__main__":
    raise SystemExit(main())
