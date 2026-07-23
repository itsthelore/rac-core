"""Command-line interface for RAC.

Commands:
    rac validate <file.md | dir | -> [--json | --sarif] [--top-level]
    rac validate <file.md | -> --corpus <dir> [--json]
    rac diff <old.md> <new.md> [--json]
    rac stats <directory> [--json]
    rac ingest <file> [-o OUT | --stdout] [--force] [--json]
    rac inspect <file.md | -> [--json]
    rac improve <file.md | -> [--json | --template]
    rac schema [--list] [type] [--json | --template]
    rac relationships <dir | file.md> [--validate] [--json] [--top-level]
    rac rename <old-id> <new-id> <directory> [--json] [--apply] [--top-level]
    rac review <directory> [--json] [--top-level]
    rac doctor [directory] [--json] [--hub-threshold N] [--top-level]
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
    rac telemetry [on | off | status]
    rac new <artifact-type> <output-path> [--json]
    rac templates [--json]
    rac init [directory] [--key KEY] [--json]
    rac quickstart [directory] [--key KEY] [--type TYPE] [--json]
    rac resolve <ID> [directory] [--json]
    rac find <query> [directory] [--type TYPE] [--json] [--explain]
    rac eval [--check | --update-baseline] [--json]
             [--root DIR] [--queries PATH] [--baseline PATH] [--config PATH]
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
       eval --check: a gate rule fired (hard-negative violation, a metric below
       its floor, or a metric below baseline minus tolerance);
       doctor: a validation or relationship-integrity error is present (orphan,
       hub, and injection findings are warnings and exit 0);
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
       directory not inside a git repository, eval corpus unreadable or query
       set / baseline / config missing or malformed)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from asdecided import consent, usage
from asdecided import output as outputs
from asdecided.core.classification import score_artifacts
from asdecided.core.hooks import (
    DEFAULT_STYLE,
    HookNotFound,
    HookResourceMissing,
    available_hooks,
    hook_specs,
)
from asdecided.core.markdown import parse, parse_file
from asdecided.core.models import Product
from asdecided.core.schema import available_schemas, schema_reference
from asdecided.core.skills import SkillNotFound, SkillResourceMissing, skill_specs
from asdecided.core.templates import (
    TemplateNotFound,
    TemplateResourceMissing,
    available_templates,
)
from asdecided.core.validation import TICKETING_PROVIDER_NAMES, has_errors
from asdecided.output.portal import PortalSeamMissing, PortalShellMissing

# Per-command service imports are deferred into their cmd_* handlers so a single
# invocation loads only the service stack it runs (Movement B / ADR-046 hot path).
# Two groups stay resident at module scope:
#   * symbols build_parser() reads eagerly for help text/defaults — its module
#     loads every invocation regardless, so deferring is pointless churn:
#     doctor.DEFAULT_HUB_THRESHOLD, eval defaults, init.DEFAULT_KEY,
#     profiles.PROFILE_NAMES, quickstart.DEFAULT_TYPE, review.DEFAULT_STALE_AFTER_DAYS
#     (init also owns the repository-config errors several handlers catch);
#   * create_artifact and install_skills, which the frozen tests monkeypatch as
#     ``asdecided.cli.<name>`` — deferring them would remove the module attribute and
#     break ``monkeypatch.setattr`` (test_create.py, test_skill.py). Their whole
#     module loads with them, so the sibling create/skill symbols stay too.
from asdecided.services import doctor
from asdecided.services import eval as eval_service
from asdecided.services.create import (
    IdGenerationExhausted,
    MissingRepositoryConfig,
    OutputDirectoryMissing,
    OutputPathExists,
    create_artifact,
)
from asdecided.services.init import (
    DEFAULT_KEY,
    InvalidOrgEndpoint,
    InvalidProfile,
    InvalidRepositoryKey,
    InvalidTicketingProvider,
    MalformedRepositoryConfig,
    RepositoryKeyConflict,
    init_repository,
)
from asdecided.services.profiles import PROFILE_NAMES, MalformedClientConfig
from asdecided.services.quickstart import DEFAULT_TYPE, CorpusNotEmpty, quickstart
from asdecided.services.review import DEFAULT_STALE_AFTER_DAYS, build_review
from asdecided.services.skill import SkillFileExists, install_skills

from . import __version__

if TYPE_CHECKING:
    from collections.abc import Callable

    from asdecided.services.note_ingest import VaultIngestResult
    from asdecided.services.resolve import SearchResult

EXIT_OK = 0
EXIT_VALIDATION_FAILED = 1
EXIT_USAGE = 2


def _usage_error(message: str) -> NoReturn:
    """Print ``decided: <message>`` to stderr and exit with EXIT_USAGE.

    Centralises the uniform usage-guard stanza (a hand-written ``decided:`` stderr
    line paired with ``raise SystemExit(EXIT_USAGE)``). Sites that build a
    differently prefixed message (eval's ``decided eval:`` namespace, the schema
    renderer-built unknown-name blob), print to stderr *without* raising
    (resolve duplicate/not-found, rename's dry-run refusal, watchkeeper's
    github annotations), or signal usage with ``return EXIT_USAGE`` instead of
    a raise (telemetry) keep their explicit form.
    """
    print(f"decided: {message}", file=sys.stderr)
    raise SystemExit(EXIT_USAGE)


def _cache_enabled(args: argparse.Namespace) -> bool:
    """Whether the persistent cache is active for this invocation (ADR-112).

    On by default; ``--no-cache`` disables it per invocation and a non-empty
    ``DECIDED_NO_CACHE`` disables it environment-wide — the escape for callers that
    cannot pass flags (CI containers, hooks, third-party harnesses).
    """
    return args.cache and not os.environ.get("DECIDED_NO_CACHE")


def _emit(
    args: argparse.Namespace,
    *,
    human: Callable[[], str],
    json: Callable[[], str] | None = None,
    sarif: Callable[[], str] | None = None,
) -> None:
    """Print the format-appropriate rendering to stdout for a uniform output fork.

    Owns the shared ``--sarif`` → ``--json`` → human precedence ladder that
    nearly every handler repeats. Each renderer is a zero-argument callable, so
    only the selected format is built — byte-for-byte the behaviour of the
    hand-written ladders it replaces. Handlers that route a rendering to stderr,
    add a mode the ladder omits (``--template``/``--share``/``--verbose``/
    ``github``), or branch the exit code on the render outcome keep their
    explicit ladder rather than calling this.
    """
    if sarif is not None and args.sarif:
        print(sarif())
    elif json is not None and args.json:
        print(json())
    else:
        print(human())


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
    """Parse validation input from a Markdown file or stdin."""
    if target == "-":
        return parse(sys.stdin.read(), source_path="-")
    return _read(target)


def cmd_validate(args: argparse.Namespace) -> int:
    from asdecided.services.validate import (
        validate_directory,
        validate_directory_incremental,
        validate_product,
        validate_stdin_against_corpus,
    )

    corpus = getattr(args, "corpus", None)

    # Directory? Validate every recognized artifact beneath it (v0.7.9).
    # Unknown-type files are skipped, matching `decided portfolio` semantics; the
    # legacy requirement fallback applies only to explicit single-file input.
    if args.file != "-" and Path(args.file).is_dir():
        if corpus is not None:
            # --corpus resolves *one proposed document* against a corpus; a
            # directory target already validates every artifact in place, so the
            # flag is redundant and ambiguous there (ADR-067, v0.21.17).
            _usage_error("--corpus applies to stdin ('-') or a single file")
        # The cache reuses per-file results across runs (ADR-106), byte-identical
        # to the uncached path; on by default per ADR-112, with --no-cache /
        # DECIDED_NO_CACHE restoring the full revalidation and --verify forcing the
        # full-hash freshness floor.
        result = (
            validate_directory_incremental(
                args.file,
                recursive=not args.top_level,
                verify=getattr(args, "verify", False),
            )
            if _cache_enabled(args)
            else validate_directory(args.file, recursive=not args.top_level)
        )
        _emit(
            args,
            human=lambda: outputs.render_validate_dir_human(result),
            json=lambda: outputs.render_validate_dir_json(result),
            sarif=lambda: outputs.render_validate_sarif(result),
        )
        return EXIT_OK if result.ok else EXIT_VALIDATION_FAILED

    if args.sarif:
        # SARIF is a repository-scan artifact for CI code scanning (ADR-054);
        # there is no single-file SARIF surface.
        _usage_error("--sarif applies to directory validation")

    product = _read_validate_input(args.file)

    # Corpus-aware single-document validation (v0.21.17, ADR-067): structural
    # findings *plus* the proposed document's references resolved against the
    # live corpus. This is the seam the generated Claude Code pre-edit hook
    # pipes proposed content into — a reference to a retired or missing decision
    # blocks before the edit lands. Either a structural error or any corpus
    # reference finding fails the run.
    if corpus is not None:
        if not Path(corpus).is_dir():
            _usage_error(f"--corpus is not a directory: {corpus}")
        source_path = "-" if args.file == "-" else str(Path(args.file))
        corpus_result = validate_stdin_against_corpus(product, corpus, source_path=source_path)
        _emit(
            args,
            human=lambda: outputs.render_stdin_corpus_human(corpus_result),
            json=lambda: outputs.render_stdin_corpus_json(corpus_result),
        )
        return EXIT_OK if corpus_result.ok else EXIT_VALIDATION_FAILED

    start = "." if args.file == "-" else str(Path(args.file).parent)
    issues = validate_product(product, start)
    _emit(
        args,
        human=lambda: outputs.render_validation_human(product, issues),
        json=lambda: outputs.render_validation_json(product, issues),
    )
    return EXIT_VALIDATION_FAILED if has_errors(issues) else EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    from asdecided.services.diff import diff as diff_asts

    old = _read(args.old)
    new = _read(args.new)
    result = diff_asts(old, new)
    _emit(
        args,
        human=lambda: outputs.render_diff_human(result, args.old, args.new),
        json=lambda: outputs.render_diff_json(result, args.old, args.new),
    )
    return EXIT_OK


def cmd_stats(args: argparse.Namespace) -> int:
    from asdecided.services.stats import collect_stats

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    stats = collect_stats(args.directory)
    _emit(
        args,
        human=lambda: outputs.render_stats_human(stats),
        json=lambda: outputs.render_stats_json(stats),
    )
    # Success as long as the portfolio has analysable content (at least one valid
    # feature/decision/roadmap/prompt/design) or is an empty day-one corpus.
    # `has_meaningful_content` and `is_empty` are computed behind the gate
    # (ADR-015); the CLI only reads them. An empty corpus is a valid state, not a
    # failure (v0.13.1): it exits 0, matching validate/review/portfolio. The
    # "files exist but none are valid known artifacts" failure is preserved for a
    # non-empty corpus, and will move behind a future --strict flag for CI use.
    return EXIT_OK if (stats.has_meaningful_content or stats.is_empty) else EXIT_VALIDATION_FAILED


def cmd_ingest(args: argparse.Namespace) -> int:
    from asdecided.services.ingest import ConversionError, UnsupportedDocument, ingest

    path = Path(args.file)
    if path.is_dir():
        return _cmd_ingest_vault(args, path)
    if not path.is_file():
        _usage_error(f"path not found: {args.file}")
    # A bare Roam JSON graph export ingests directly (its canonical export is one
    # .json file, not a directory); non-Roam .json falls through to the error.
    if path.suffix.lower() == ".json":
        from asdecided.services.note_ingest import roam_result_for_file

        roam_result = roam_result_for_file(path)
        if roam_result is not None:
            return _emit_vault_result(args, roam_result)
    if args.from_tool:
        _usage_error("--from applies to a note-tool export directory, not a single file.")

    try:
        result = ingest(args.file)
    except UnsupportedDocument as exc:  # unhandled type / missing extra
        _usage_error(str(exc))
    except ConversionError as exc:  # recognized file, failed to convert
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED

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


def _cmd_ingest_vault(args: argparse.Namespace, root: Path) -> int:
    """Ingest a note-tool export directory into RAC-shaped drafts (ADR-079).

    Deterministic and offline: each note becomes a draft, wikilinks become
    candidate ``## Related`` references (never asserted), and nothing is
    overwritten. With ``-o`` the drafts are written for review; without it, a
    summary previews what would convert and what needs human attention.
    """
    from asdecided.services.note_ingest import converter_by_name, converter_names, detect_converter

    if args.stdout:
        _usage_error("--stdout is not supported for a directory export; use -o <dir>.")

    converter = converter_by_name(args.from_tool) if args.from_tool else detect_converter(root)
    if converter is None:
        _usage_error(
            f"could not detect a note-tool export in {root}. "
            f"Pass --from with one of: {', '.join(converter_names())}"
        )

    return _emit_vault_result(args, converter.convert_vault(root))


def _emit_vault_result(args: argparse.Namespace, result: VaultIngestResult) -> int:
    """Write drafts (never overwriting) and print the summary for a vault ingest."""
    written: list[str] = []
    skipped: list[str] = []
    if args.output:
        out_dir = Path(args.output)
        for draft in result.drafts:
            dest = out_dir / draft.suggested_filename
            if dest.exists() and not args.force:
                skipped.append(str(dest))  # never overwrite an existing artifact (REQ-006)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(draft.markdown, encoding="utf-8")
            written.append(str(dest))

    _emit(
        args,
        human=lambda: outputs.render_vault_ingest_human(result, written, skipped, args.output),
        json=lambda: outputs.render_vault_ingest_json(result, written, skipped, args.output),
    )
    return EXIT_OK


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


def cmd_inspect(args: argparse.Namespace) -> int:
    from asdecided.services.inspect import build_inspection, inspect_directory

    # Directory? Aggregate per-file results into type counts.
    if args.file != "-" and Path(args.file).is_dir():
        recursive = not args.top_level
        result = inspect_directory(args.file, recursive=recursive)
        _emit(
            args,
            human=lambda: outputs.render_dir_inspect_human(result),
            json=lambda: outputs.render_dir_inspect_json(result),
        )
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
    from asdecided.services.improve import improve_product

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
        _emit(
            args,
            human=lambda: outputs.render_schema_list_human(names),
            json=lambda: outputs.render_schema_list_json(names),
        )
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
    from asdecided.services.relationships import (
        build_relationship_report,
        build_relationship_report_file,
        validate_relationships,
        validate_relationships_file,
    )

    if args.sarif and not args.validate:
        _usage_error("relationships --sarif requires --validate")
    path = Path(args.path)
    # --recursive is the default; --top-level disables it. If both are given,
    # --top-level wins (mirrors `decided inspect`).
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
        _emit(
            args,
            human=lambda: outputs.render_relationship_validation_human(report),
            json=lambda: outputs.render_relationship_validation_json(report),
            sarif=lambda: outputs.render_relationships_sarif(report),
        )
        # Validation-style exit codes (REQ-007): 0 when everything resolves, 1 when
        # any issue is found, 2 (above) for usage errors.
        return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED

    if is_dir:
        rel_report = build_relationship_report(args.path, recursive=not args.top_level)
    else:
        rel_report = build_relationship_report_file(args.path)
    _emit(
        args,
        human=lambda: outputs.render_relationships_human(rel_report),
        json=lambda: outputs.render_relationships_json(rel_report),
    )
    # A completed inspection always succeeds — finding no relationships is a valid
    # outcome, not an error (REQ-010).
    return EXIT_OK


def cmd_rename(args: argparse.Namespace) -> int:
    """Compute (and optionally apply) a corpus-wide artifact-id rename (v0.21.18).

    Default is a dry run: it prints the planned edit set and exits 0 for any valid
    plan (a preview always succeeds). An unresolvable/ambiguous OLD or an
    invalid/colliding NEW is a refusal: it prints the reason and exits
    EXIT_VALIDATION_FAILED (1) — the rename was rejected, not a usage error.
    ``--apply`` writes the edits and reports what changed. The engine owns the
    edit set (ADR-063); the CLI only renders and applies it.
    """
    from asdecided.services.rename import apply_rename, compute_rename

    directory = Path(args.directory)
    if not directory.is_dir():
        _usage_error(f"not a directory: {args.directory}")

    plan = compute_rename(args.directory, args.old, args.new, recursive=not args.top_level)

    if not plan.ok:
        if args.json:
            print(outputs.render_rename_json(plan))
        else:
            print(outputs.render_rename_human(plan), file=sys.stderr)
        # Every refusal (unknown/ambiguous OLD, invalid/colliding NEW,
        # filename-only alias) leaves the corpus untouched and exits 1 — the
        # rename was rejected. EXIT_USAGE (2) is reserved for argument/IO errors
        # like "not a directory" above, so a refused rename stays distinguishable
        # from a misused command.
        return EXIT_VALIDATION_FAILED

    if not args.apply:
        _emit(
            args,
            human=lambda: outputs.render_rename_human(plan),
            json=lambda: outputs.render_rename_json(plan),
        )
        # A valid dry-run preview always succeeds.
        return EXIT_OK

    result = apply_rename(plan)
    _emit(
        args,
        human=lambda: outputs.render_rename_result_human(result),
        json=lambda: outputs.render_rename_result_json(result),
    )
    return EXIT_OK


def cmd_review(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    if args.stale_after is not None and args.stale_after < 0:
        _usage_error("--stale-after must be a non-negative number of days")
    report = build_review(
        args.directory, recursive=not args.top_level, stale_after_days=args.stale_after
    )
    _emit(
        args,
        human=lambda: outputs.render_review_human(report),
        json=lambda: outputs.render_review_json(report),
        sarif=lambda: outputs.render_review_sarif(report),
    )
    # Priority 1-2 findings (invalid artifacts, broken relationships) fail the
    # review; priority 3-4 findings are advisory (REQ-Repository-Review-Mode).
    return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED


def cmd_doctor(args: argparse.Namespace) -> int:
    """Aggregate corpus health into one verdict with paste-ready fixes (WS3).

    Composes validate + relationships and adds high-fan-out hubs and an
    injection-style content heuristic. Exits non-zero only on a validation or
    relationship-integrity error; orphan/hub/injection warnings exit 0 (REQ-007).
    """
    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    report = doctor.diagnose(
        args.directory,
        recursive=not args.top_level,
        hub_threshold=args.hub_threshold,
    )
    _emit(
        args,
        human=lambda: doctor.render_doctor_human(report),
        json=lambda: doctor.render_doctor_json(report),
    )
    return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED


def cmd_coverage(args: argparse.Namespace) -> int:
    """Report typed traceability coverage gaps — advisory, never a build failure.

    Unscheduled requirements, unapplied decisions, and unscoped roadmaps derived
    from the relationship graph (rac-traceability-coverage-report, WS-F). Coverage
    is a completeness signal for human judgement, so it always exits 0 (REQ-005).
    """
    from asdecided.services import coverage as coverage_service

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    report = coverage_service.analyze_coverage(args.directory)
    _emit(
        args,
        human=lambda: coverage_service.render_coverage_human(report),
        json=lambda: coverage_service.render_coverage_json(report),
    )
    return EXIT_OK


def cmd_gate(args: argparse.Namespace) -> int:
    from asdecided.services.gate import build_gate

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    try:
        report = build_gate(args.directory, recursive=not args.top_level)
    except MalformedRepositoryConfig as exc:  # unreadable/invalid .decided/config.yaml
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    _emit(
        args,
        human=lambda: outputs.render_gate_human(report),
        json=lambda: outputs.render_gate_json(report),
        sarif=lambda: outputs.render_gate_sarif(report),
    )
    # The gate fails when any finding is blocking under the corpus enforcement
    # policy; advisory findings annotate but never fail (ADR-049 / v0.21.14).
    return EXIT_OK if report.ok else EXIT_VALIDATION_FAILED


def cmd_watchkeeper(args: argparse.Namespace) -> int:
    from asdecided.services.revisions import NotAGitRepository, RevisionNotFound
    from asdecided.services.watchkeeper import build_watchkeeper_report

    if args.directory is None:
        # ADR-018: rac/ is the conventional knowledge root — compare it when it
        # exists; otherwise the current directory.
        args.directory = "rac" if Path("rac").is_dir() else "."
    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    try:
        report = build_watchkeeper_report(args.directory, base=args.base, head=args.head)
    except (NotAGitRepository, RevisionNotFound) as exc:
        _usage_error(str(exc))
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
    from asdecided.services.portfolio import build_portfolio_summary

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    recursive = not args.top_level
    summary = build_portfolio_summary(args.directory, recursive=recursive)
    _emit(
        args,
        human=lambda: outputs.render_portfolio_human(summary),
        json=lambda: outputs.render_portfolio_json(summary),
    )
    return EXIT_OK


def cmd_index(args: argparse.Namespace) -> int:
    from asdecided.services.index import build_repository_index

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    recursive = not args.top_level
    index = build_repository_index(args.directory, recursive=recursive)
    _emit(
        args,
        human=lambda: outputs.render_index_human(index),
        json=lambda: outputs.render_index_json(index),
    )
    return EXIT_OK


def _agent_rules_root(directory: str, out: str | None) -> Path:
    """The directory the agent-rules files are written into.

    Explicit ``--out`` wins. Otherwise default to the corpus's repo root: the
    parent of a ``rac/`` directory (so ``decided export rac/ --agent-rules`` writes
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
    from asdecided.services.export import (
        build_corpus_export,
        build_documents_export,
        build_graph_export,
    )

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")

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
    # HTML. Written to stdout so it stays pipeable (ADR-011); the export contract
    # is additive and leaves the default viewer JSON untouched (ADR-007).
    if args.documents:
        print(outputs.render_documents_jsonl(build_documents_export(args.directory)))
        return EXIT_OK

    # Typed graph projection (v0.25.0 WS2, ADR-074): nodes + typed/directed edges
    # for graph backends, surfacing the real relationship graph (ADR-055) rather
    # than the viewer's flattened relates-to. Additive; stdout, pipeable (ADR-011).
    if args.graph:
        print(outputs.render_graph_json(build_graph_export(args.directory)))
        return EXIT_OK

    export = build_corpus_export(args.directory)

    # OKF bundle (ADR-048): a derived tree of Markdown files written to a
    # directory, parallel to the JSON/HTML views. Recency feeds log.md (ADR-045).
    if args.okf:
        from asdecided.services.recency import artifact_recency

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
    """`decided export --agent-rules [--check]` (v0.21.15, ADR-067).

    Generates (or, under --check, verifies) the drift-guarded managed block in
    each per-client agent-context file. --check never writes and exits non-zero
    on drift (a stale or missing block) — the CI gate. Output is human by
    default; --json emits the machine contract.
    """
    from asdecided.services.agent_rules import (
        check_agent_rules,
        generate_agent_rules,
        unknown_clients,
    )

    bad = unknown_clients(args.client)
    if bad:
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

    _emit(
        args,
        human=lambda: outputs.render_agent_rules_human(result),
        json=lambda: outputs.render_agent_rules_json(result),
    )

    if args.check and result.drifted:
        return EXIT_VALIDATION_FAILED
    return EXIT_OK


def cmd_explorer(args: argparse.Namespace) -> int:
    if args.directory is None:
        # ADR-018: rac/ is the conventional knowledge root — open it when it
        # exists; otherwise the current directory (v0.8.1).
        args.directory = "rac" if Path("rac").is_dir() else "."
    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    # Imported lazily: launch decides whether the explorer extra is installed,
    # and the base CLI must not pay an import cost for the optional TUI.
    from asdecided.explorer.launch import ExplorerUnavailable, run_explorer

    try:
        return run_explorer(args.directory, recursive=not args.top_level)
    except ExplorerUnavailable as exc:
        _usage_error(str(exc))


def cmd_mcp(args: argparse.Namespace) -> int:
    if not Path(args.root).is_dir():
        _usage_error(f"not a directory: {args.root}")
    # Imported lazily: the MCP SDK is only needed when serving, and the base
    # CLI must not pay its import cost for every other command. stdout belongs
    # to the MCP protocol, so any diagnostics here go to stderr.
    from asdecided.mcp.audit import MalformedAuditConfig
    from asdecided.mcp.server import run_server
    from asdecided.mcp.transport import AuditSinkUnavailable

    try:
        return run_server(
            args.root,
            telemetry_enabled=args.telemetry,
            transport_name=args.transport,
            host=args.host,
            port=args.port,
            path=args.path,
            cache_enabled=_cache_enabled(args),
        )
    except MalformedAuditConfig as exc:  # bad `audit:` stanza (ADR-084)
        _usage_error(str(exc))
    except AuditSinkUnavailable as exc:  # HTTP without a working audit sink (ADR-084)
        _usage_error(str(exc))


def cmd_mcp_stats(args: argparse.Namespace) -> int:
    # Imported lazily for the same reason as cmd_mcp: importing the telemetry
    # module executes the asdecided.mcp package, which pulls in the MCP SDK.
    from asdecided.mcp.telemetry import share_url, summarize

    summary = summarize()
    if args.share:
        print(share_url(summary))
    elif args.json:
        print(outputs.render_mcp_stats_json(summary))
    else:
        print(outputs.render_mcp_stats_human(summary))
    # An empty or missing log is a valid answer (telemetry is off by default),
    # like `decided find` with no matches.
    return EXIT_OK


def cmd_usage(args: argparse.Namespace) -> int:
    """Unified read-back over the CLI-usage log and the Guide log (ADR-046, WS-E).

    `decided mcp-stats` stays Guide-only for back-compat; this command summarises
    both. An empty or missing log is a valid answer (telemetry is off by default).
    """
    from asdecided.mcp.telemetry import summarize as guide_summarize

    summary = usage.summarize_usage()
    guide = guide_summarize().to_dict()
    if args.share:
        print(usage.share_url(summary, guide))
    elif args.json:
        print(usage.render_json(summary, guide))
    else:
        print(usage.render_human(summary, guide))
    return EXIT_OK


def cmd_new(args: argparse.Namespace) -> int:
    try:
        created = create_artifact(args.type, args.output_path)
    except TemplateNotFound as exc:  # unsupported type → usage error
        _usage_error(str(exc))
    except (
        OutputPathExists,
        OutputDirectoryMissing,
        MissingRepositoryConfig,
    ) as exc:
        _usage_error(str(exc))
    except (
        TemplateResourceMissing,  # broken installation
        MalformedRepositoryConfig,  # unreadable .decided/config.yaml
        IdGenerationExhausted,  # broken entropy source
    ) as exc:  # operational errors
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    _emit(
        args,
        human=lambda: outputs.render_new_human(created),
        json=lambda: outputs.render_new_json(created),
    )
    return EXIT_OK


def cmd_resolve(args: argparse.Namespace) -> int:
    from asdecided.services.resolve import OUTCOME_DUPLICATE, OUTCOME_RESOLVED, resolve_artifact

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    result = resolve_artifact(args.directory, args.id, recursive=not args.top_level)
    if args.json:
        print(outputs.render_resolve_json(result))
    else:
        if result.outcome == OUTCOME_RESOLVED:
            print(outputs.render_resolve_human(result))
        elif result.outcome == OUTCOME_DUPLICATE:
            print(
                f"decided: duplicate artifact ID: {args.id}\n\nFound in:\n"
                + "\n".join(f"- {p}" for p in result.duplicate_paths),
                file=sys.stderr,
            )
        else:
            print(f"decided: artifact not found: {args.id}", file=sys.stderr)
    # Not-found and duplicate identity are both repository findings (exit 1);
    # they stay distinguishable by message and by the JSON error field.
    return EXIT_OK if result.outcome == OUTCOME_RESOLVED else EXIT_VALIDATION_FAILED


def _find_from_store(args: argparse.Namespace) -> SearchResult:
    """Serve `decided find` from the persistent index store (ADR-112, default-on).

    Reuses ``DerivedIndexCache.load_or_build``: a warm run against an unchanged
    corpus serves from the memory-mapped store with no walk/parse/graph rebuild
    — freshness confirmed by the persisted stat manifest, or the full-hash
    floor under ``--verify`` — and a cold run builds fresh and writes the store
    for the next invocation. The result is byte-identical to the uncached walk
    — the store fast path and the fresh build are branched exactly as
    ``mcp/server.py`` does (ADR-104 parity). When the store cannot be written,
    ``load_or_build`` returns a fresh ``DerivedIndex`` and the ``else``
    branches handle it.
    """
    from asdecided.services.derived_cache import DerivedIndexCache
    from asdecided.services.index_store import ReadModelView
    from asdecided.services.resolve import find_decisions_in, search_index

    view = DerivedIndexCache().load_or_build(
        args.directory, recursive=not args.top_level, verify=args.verify
    )
    if args.decisions:
        if isinstance(view, ReadModelView):
            return view.find_decisions(args.query)
        return find_decisions_in(
            view.index_entries,
            view.live_decision_paths,
            args.query,
            field_tokens_by_path=view.field_tokens_by_path,
        )
    if isinstance(view, ReadModelView):
        return view.search(args.query, artifact_type=args.type, tags=args.tags)
    return search_index(
        view.index_entries,
        args.query,
        artifact_type=args.type,
        tags=args.tags,
        field_tokens_by_path=view.field_tokens_by_path,
    )


def cmd_find(args: argparse.Namespace) -> int:
    from asdecided.services.resolve import find_artifacts, find_decisions

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    if _cache_enabled(args):
        # Default store reuse (ADR-112): serve from the persistent index store
        # instead of a fresh walk, byte-identical to the uncached path below;
        # --no-cache / DECIDED_NO_CACHE select the walk.
        result = _find_from_store(args)
    elif args.decisions:
        # `--decisions` is the live decision query (ADR-067): it implies the
        # decision type filter *and* restricts to live (Accepted, non-retired)
        # decisions — the deterministic "what did we decide about X" retrieval.
        # `--type` is redundant with it and mutually exclusive at the parser.
        result = find_decisions(
            args.directory,
            args.query,
            recursive=not args.top_level,
        )
    else:
        result = find_artifacts(
            args.directory,
            args.query,
            artifact_type=args.type,
            recursive=not args.top_level,
            tags=args.tags,
        )
    # Freshness phase 1 (ADR-045): join git-derived staleness onto matches after
    # ranking, so the matched set and order are unchanged (REQ-005) and the fields
    # degrade to null outside git (REQ-003).
    from asdecided.services.recency import annotate_search_recency

    annotate_search_recency(result.matches, args.directory)
    _emit(
        args,
        human=lambda: outputs.render_find_human(result, explain=args.explain),
        json=lambda: outputs.render_find_json(result, explain=args.explain),
    )
    # An empty result is a valid outcome, not an error (a query always succeeds).
    return EXIT_OK


def cmd_decisions_for(args: argparse.Namespace) -> int:
    """List the live decisions whose `## Applies To` scope governs a code path.

    The read side of the code-scope vocabulary (decision-to-code-proximity
    Initiative 2): a pure function of declared `## Applies To` references and the
    query path (ADR-066), reading fresh per call (ADR-032). An ungoverned or
    outside-repository path is a valid empty result, not an error (a query always
    succeeds).
    """
    from asdecided.services.scope import decisions_for_path

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    result = decisions_for_path(
        args.directory,
        args.path,
        recursive=not args.top_level,
    )
    _emit(
        args,
        human=lambda: outputs.render_decisions_for_human(result),
        json=lambda: outputs.render_decisions_for_json(result),
    )
    return EXIT_OK


def cmd_eval(args: argparse.Namespace) -> int:
    """Score retrieval against the fixture benchmark, or gate against the baseline.

    Three modes (default report / ``--check`` gate / ``--update-baseline``):
    a clean report exits 0; the gate exits 1 on regression; any usage error
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
    from asdecided.services.migrate import migrate_metadata

    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    try:
        report = migrate_metadata(
            args.directory,
            dry_run=args.dry_run,
            recursive=not args.top_level,
        )
    except MissingRepositoryConfig as exc:
        _usage_error(str(exc))
    except (MalformedRepositoryConfig, IdGenerationExhausted) as exc:
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    _emit(
        args,
        human=lambda: outputs.render_migrate_human(report),
        json=lambda: outputs.render_migrate_json(report),
    )
    # Completed migration (or dry run) always succeeds — nothing to migrate
    # is a valid outcome.
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
    try:
        result = init_repository(
            args.directory,
            key=args.key,
            ticketing=args.ticketing,
            profile=args.profile,
            org_endpoint=args.org_endpoint,
        )
    except (
        InvalidRepositoryKey,
        InvalidTicketingProvider,
        InvalidProfile,
        InvalidOrgEndpoint,
    ) as exc:
        _usage_error(str(exc))
    except (RepositoryKeyConflict, MalformedRepositoryConfig, MalformedClientConfig) as exc:
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    _emit(
        args,
        human=lambda: outputs.render_init_human(result),
        json=lambda: outputs.render_init_json(result),
    )
    if not args.json:
        _maybe_ask_usage_sharing()
    return EXIT_OK


def cmd_quickstart(args: argparse.Namespace) -> int:
    if not Path(args.directory).is_dir():
        _usage_error(f"not a directory: {args.directory}")
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
    ) as exc:
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    except (
        MalformedRepositoryConfig,  # unreadable .decided/config.yaml
        TemplateResourceMissing,  # broken installation
        IdGenerationExhausted,  # broken entropy source
    ) as exc:  # operational errors
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    _emit(
        args,
        human=lambda: outputs.render_quickstart_human(result),
        json=lambda: outputs.render_quickstart_json(result),
    )
    if not args.json:
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
        answer = input("\nShare anonymous usage to help shape AsDecided? [y/N] ")
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
    # The enterprise flags are only meaningful with 'off' (ADR-086).
    if (enterprise or unlock) and args.action != "off":
        print(
            "decided: --enterprise/--unlock are only valid with 'rac telemetry off'",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if unlock and not enterprise:
        print(
            "decided: --unlock requires --enterprise (use 'rac telemetry off --enterprise --unlock')",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if args.action == "on":
        if consent.load_consent().enterprise_locked:
            print(
                "decided: cannot opt in while the enterprise telemetry lock is set; "
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


def cmd_skill(args: argparse.Namespace) -> int:
    if args.action == "list":
        if args.name is not None:
            _usage_error("skill list takes no skill name")
        specs = skill_specs()
        _emit(
            args,
            human=lambda: outputs.render_skill_list_human(specs),
            json=lambda: outputs.render_skill_list_json(specs),
        )
        return EXIT_OK

    if not Path(args.dir).is_dir():
        _usage_error(f"not a directory: {args.dir}")
    try:
        installation = install_skills(args.dir, args.name)
    except SkillNotFound as exc:  # unknown skill name → usage error
        _usage_error(str(exc))
    except SkillFileExists as exc:  # refused; every existing file is untouched
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    except SkillResourceMissing as exc:  # broken installation
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    _emit(
        args,
        human=lambda: outputs.render_skill_install_human(installation),
        json=lambda: outputs.render_skill_install_json(installation),
    )
    return EXIT_OK


def cmd_hook(args: argparse.Namespace) -> int:
    from asdecided.services.hook import HookFileExists, NotAGitWorkTree, install_hook

    if args.action == "list":
        specs = hook_specs()
        _emit(
            args,
            human=lambda: outputs.render_hook_list_human(specs),
            json=lambda: outputs.render_hook_list_json(specs),
        )
        return EXIT_OK

    if not Path(args.dir).is_dir():
        _usage_error(f"not a directory: {args.dir}")
    try:
        installation = install_hook(args.dir, args.style)
    except (HookNotFound, NotAGitWorkTree) as exc:  # usage errors → exit 2
        _usage_error(str(exc))
    except HookFileExists as exc:  # refused; existing hook untouched
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    except HookResourceMissing as exc:  # broken installation
        print(f"decided: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILED
    _emit(
        args,
        human=lambda: outputs.render_hook_install_human(installation),
        json=lambda: outputs.render_hook_install_json(installation),
    )
    return EXIT_OK


def cmd_templates(args: argparse.Namespace) -> int:
    names = available_templates()
    _emit(
        args,
        human=lambda: outputs.render_templates_human(names),
        json=lambda: outputs.render_templates_json(names),
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    version_str = f"rac {__version__}"

    # Shared parent so `--version` works on the root parser *and* every
    # subcommand (e.g. `decided ingest foo.docx --version`).
    version_parent = argparse.ArgumentParser(add_help=False)
    version_parent.add_argument("--version", action="version", version=version_str)

    # Shared flag vocabularies added to subcommands via ``parents=[…]`` so the
    # repeated --json / --top-level / --recursive definitions live in one place.
    # Only subcommands whose flag help and defaults match byte-for-byte use these:
    # a bespoke --json help (export/eval/watchkeeper), a --json inside a mutually
    # exclusive group (validate/improve/schema/gate/mcp-stats/usage), or a
    # differently-worded --top-level (validate/inspect/relationships/rename/
    # decisions-for) keeps its inline definition. dest/default/behaviour are
    # unchanged; only the definition site moves.
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument(
        "--json", action="store_true", help="Emit JSON instead of human-readable text."
    )
    scope_parent = argparse.ArgumentParser(add_help=False)
    scope_parent.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the directory (no recursion).",
    )
    scope_parent.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )

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
    # Incremental directory validation (ADR-106, default-on per ADR-112). Reuses
    # per-file validation results keyed by content-hash × config fingerprint, so a
    # re-validate after a small changeset recomputes only the changed files —
    # byte-identical to the uncached run. Disposable cache under
    # $XDG_CACHE_HOME/rac (DECIDED_CACHE_DIR overrides); deleting it costs only latency.
    p_validate.add_argument(
        "--cache",
        action="store_true",
        default=True,
        help=(
            "Reuse per-file validation results across runs, recomputing only "
            "changed files; disposable and byte-identical to the uncached run "
            "(directory validation only; the default, kept as an explicit "
            "affirmation, ADR-112)."
        ),
    )
    p_validate.add_argument(
        "--no-cache",
        action="store_false",
        dest="cache",
        help=(
            "Disable the validation-result cache: revalidate every file from "
            "disk for this invocation (the pre-ADR-112 default; DECIDED_NO_CACHE=1 "
            "disables it environment-wide)."
        ),
    )
    p_validate.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Re-read every file's bytes when checking cache freshness (the "
            "full-hash floor): catches the size- and mtime-preserving rewrites "
            "the default stat scan accepts (S5, ADR-105/ADR-112). The uncached "
            "path always reads every file, so this matters only with the cache "
            "enabled."
        ),
    )
    p_validate.set_defaults(func=cmd_validate)

    p_diff = sub.add_parser(
        "diff",
        help="Compare two versions of a requirement file.",
        parents=[version_parent, json_parent],
    )
    p_diff.add_argument("old", help="Path to the old version.")
    p_diff.add_argument("new", help="Path to the new version.")
    p_diff.set_defaults(func=cmd_diff)

    p_stats = sub.add_parser(
        "stats",
        help="Summarize a directory of requirement files.",
        parents=[version_parent, json_parent],
    )
    p_stats.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_stats.set_defaults(func=cmd_stats)

    p_ingest = sub.add_parser(
        "ingest",
        help=(
            "Convert a document (DOCX, PDF, HTML, PPTX, XLSX, Markdown) — or a "
            "note-tool export (Obsidian, Logseq, Notion, or a Roam JSON graph) — "
            "to RAC-shaped Markdown."
        ),
        parents=[version_parent, json_parent],
    )
    p_ingest.add_argument("file", help="Path to the source document or note-tool export directory.")
    ingest_dest = p_ingest.add_mutually_exclusive_group()
    ingest_dest.add_argument(
        "-o",
        "--output",
        help="Write Markdown here (a file for a document, a directory for a note-tool export).",
    )
    ingest_dest.add_argument(
        "--stdout",
        action="store_true",
        help="Write Markdown to stdout (the default for a document; explicit for pipelines).",
    )
    # Note-tool export ingest (ADR-079): choices are literals so the base CLI does
    # not import the ingest layer just to build the parser; the converter registry
    # is the runtime source of truth and a battery test pins these to it.
    p_ingest.add_argument(
        "--from",
        dest="from_tool",
        choices=("obsidian", "logseq", "notion", "roam"),
        help="Force a note-tool converter for a directory export (default: auto-detect).",
    )
    p_ingest.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output; never overwrites by default.",
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_inspect = sub.add_parser(
        "inspect",
        help="Identify a Markdown document's artifact type and structure.",
        parents=[version_parent, json_parent],
    )
    p_inspect.add_argument(
        "file",
        help="A Markdown file, a directory, or '-' to read from stdin.",
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
        parents=[version_parent, json_parent],
    )
    p_relationships.add_argument("path", help="A directory to scan, or a single Markdown file.")
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

    p_rename = sub.add_parser(
        "rename",
        help="Safely rename an artifact id across the corpus (dry run; --apply writes).",
        parents=[version_parent, json_parent],
    )
    p_rename.add_argument("old", help="The existing artifact id (or alias) to rename.")
    p_rename.add_argument("new", help="The new artifact id, e.g. ADR-099.")
    p_rename.add_argument("directory", help="The corpus directory to scan.")
    p_rename.add_argument(
        "--apply",
        action="store_true",
        help="Apply the edit set to disk (default is a dry-run preview).",
    )
    p_rename.add_argument(
        "--top-level",
        action="store_true",
        help="Only the directory's top-level files (no recursion).",
    )
    p_rename.set_defaults(func=cmd_rename)

    p_review = sub.add_parser(
        "review",
        help="Review a repository: prioritized issues and suggested actions.",
        parents=[version_parent, json_parent, scope_parent],
    )
    p_review.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_review.add_argument(
        "--sarif",
        action="store_true",
        help="Emit SARIF 2.1.0 for GitHub Code Scanning (CI pull-request enforcement).",
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

    p_doctor = sub.add_parser(
        "doctor",
        help="Diagnose corpus health in one pass, with a paste-ready fix per finding.",
        parents=[version_parent, json_parent, scope_parent],
    )
    p_doctor.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to diagnose recursively for *.md (default: current directory).",
    )
    p_doctor.add_argument(
        "--hub-threshold",
        type=int,
        default=doctor.DEFAULT_HUB_THRESHOLD,
        help=(
            "Flag artifacts with more than this many resolved relationship edges "
            f"as high-fan-out hubs (default {doctor.DEFAULT_HUB_THRESHOLD})."
        ),
    )
    p_doctor.set_defaults(func=cmd_doctor)

    p_coverage = sub.add_parser(
        "coverage",
        help="Report typed traceability coverage gaps (advisory, never blocking).",
        parents=[version_parent, json_parent],
    )
    p_coverage.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to analyse recursively for *.md (default: current directory).",
    )
    p_coverage.set_defaults(func=cmd_coverage)

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
        parents=[version_parent, json_parent, scope_parent],
    )
    p_portfolio.add_argument("directory", help="Directory to scan recursively for *.md.")
    p_portfolio.set_defaults(func=cmd_portfolio)

    p_index = sub.add_parser(
        "index",
        help="Inventory every artifact in a repository (id, type, title, path).",
        parents=[version_parent, json_parent, scope_parent],
    )
    p_index.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
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
        parents=[version_parent, scope_parent],
    )
    p_explorer.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Repository to explore (default: rac/ when present, else the current directory).",
    )
    p_explorer.set_defaults(func=cmd_explorer)

    p_mcp = sub.add_parser(
        "mcp",
        help="Serve RAC repository knowledge to agents over MCP (stdio or HTTP).",
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
    # HTTP transport (ADR-098): stdio stays the default so every existing
    # `.mcp.json` — including ADR-088 profile output — is byte-unchanged. HTTP
    # fronts one always-current checkout for the whole team; it is mandatory
    # audit-on and grows no authentication (auth belongs to the deployment
    # proxy, ADR-085). Choices and defaults are literals here so the base CLI
    # never pays the MCP SDK import cost; ``asdecided.mcp.transport`` is the runtime
    # source of truth and a battery test pins these to it.
    p_mcp.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help=(
            "Transport to serve on: 'stdio' (default, one process per developer) "
            "or 'http' (one shared endpoint; mandatory audit-on, ADR-098)."
        ),
    )
    p_mcp.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for --transport http (default: 127.0.0.1; loopback).",
    )
    p_mcp.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind for --transport http (default: 8000).",
    )
    p_mcp.add_argument(
        "--path",
        default="/mcp",
        help="HTTP path to serve for --transport http (default: /mcp).",
    )
    # Derived-index cache (ADR-099, default-on per ADR-112). Reuses the expensive
    # derived structures under an unchanged corpus content hash, byte-identically
    # to the uncached path; location is $XDG_CACHE_HOME/rac/derived (DECIDED_CACHE_DIR
    # overrides). Deleting the cache costs only latency.
    p_mcp.add_argument(
        "--cache",
        action="store_true",
        default=True,
        help=(
            "Reuse content-addressed derived structures across calls; disposable "
            "and byte-identical to the uncached path (the default, kept as an "
            "explicit affirmation, ADR-112)."
        ),
    )
    p_mcp.add_argument(
        "--no-cache",
        action="store_false",
        dest="cache",
        help=(
            "Disable the derived-structure cache: re-read and rebuild from disk "
            "on every call (the pre-ADR-112 default; DECIDED_NO_CACHE=1 disables it "
            "environment-wide)."
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

    p_usage = sub.add_parser(
        "usage",
        help="Summarize recorded CLI and Guide usage (content-free, local).",
        parents=[version_parent],
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

    p_new = sub.add_parser(
        "new",
        help="Create a new artifact from its canonical template.",
        parents=[version_parent, json_parent],
    )
    p_new.add_argument(
        "type",
        help="Artifact type, e.g. requirement, decision, roadmap, prompt, or design.",
    )
    p_new.add_argument(
        "output_path",
        help="Where to write the artifact (taken literally; never overwritten).",
    )
    p_new.set_defaults(func=cmd_new)

    p_templates = sub.add_parser(
        "templates",
        help="List the canonical artifact templates available to `decided new`.",
        parents=[version_parent, json_parent],
    )
    p_templates.set_defaults(func=cmd_templates)

    p_init = sub.add_parser(
        "init",
        help="Establish the repository identity namespace (.decided/config.yaml).",
        parents=[version_parent, json_parent],
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
        "to .decided/config.yaml; omit to leave it unset (ADR-087).",
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
    p_init.add_argument(
        "--org-endpoint",
        default=None,
        metavar="URL",
        help="Wire the shared org AsDecided endpoint (an http:// or https:// URL, "
        "ADR-117): ensure a 'lore-org' entry in .mcp.json and .cursor/mcp.json. "
        "Applies to fresh and already-initialized repositories; merges into an "
        "existing file, touching only the 'lore-org' key.",
    )
    p_init.set_defaults(func=cmd_init)

    p_quickstart = sub.add_parser(
        "quickstart",
        help="Guided first run: establish identity and scaffold a first artifact in one step.",
        parents=[version_parent, json_parent],
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
        "canonical templates from `decided templates`.",
    )
    p_quickstart.set_defaults(func=cmd_quickstart)

    p_resolve = sub.add_parser(
        "resolve",
        help="Resolve an artifact ID to its type, title, and path.",
        parents=[version_parent, json_parent, scope_parent],
    )
    p_resolve.add_argument("id", help="Artifact ID (canonical or legacy alias).")
    p_resolve.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan recursively for *.md (default: current directory).",
    )
    p_resolve.set_defaults(func=cmd_resolve)

    p_find = sub.add_parser(
        "find",
        help="Search artifacts by ID, title, filename, or path.",
        parents=[version_parent, json_parent, scope_parent],
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
        "--type",
        help="Only match artifacts of this type (requirement, decision, ...).",
    )
    find_scope.add_argument(
        "--decisions",
        action="store_true",
        help=(
            "Only live decisions (Accepted, non-retired) — the 'what did we "
            "decide about X / is X ruled out' query (ADR-067)."
        ),
    )
    p_find.add_argument(
        "--tag",
        action="append",
        dest="tags",
        metavar="TAG",
        help=(
            "Only match artifacts carrying this frontmatter tag (repeatable; all "
            "required). Narrows the query by tag (ADR-109)."
        ),
    )
    # Persistent store reuse (ADR-112): on by default. Freshness is verified by
    # the persisted stat manifest (only stat-changed files are re-read); the
    # store lives under $XDG_CACHE_HOME/rac/derived (DECIDED_CACHE_DIR overrides)
    # and is disposable — deleting it costs only latency.
    p_find.add_argument(
        "--cache",
        action="store_true",
        default=True,
        help=(
            "Serve from the persistent index store, skipping the walk and parse "
            "on an unchanged corpus; disposable and byte-identical to the "
            "uncached run (the default; kept as an explicit affirmation, "
            "ADR-112)."
        ),
    )
    p_find.add_argument(
        "--no-cache",
        action="store_false",
        dest="cache",
        help=(
            "Disable the persistent cache: walk, parse, and rebuild from disk "
            "for this invocation (the pre-ADR-112 default; DECIDED_NO_CACHE=1 "
            "disables it environment-wide)."
        ),
    )
    p_find.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Re-read every file's bytes when checking cache freshness (the "
            "full-hash floor): catches the size- and mtime-preserving rewrites "
            "the default stat scan accepts (S5, ADR-105/ADR-112). The uncached "
            "walk always reads every file, so this matters only with the cache "
            "enabled."
        ),
    )
    p_find.add_argument(
        "--explain",
        action="store_true",
        help=(
            "Show why each match was retrieved: the matched field, terms, and "
            "tier (additive `evidence`, ADR-037/ADR-038)."
        ),
    )
    p_find.set_defaults(func=cmd_find)

    p_decisions_for = sub.add_parser(
        "decisions-for",
        help="List the decisions whose `## Applies To` scope governs a code path.",
        parents=[version_parent, json_parent],
    )
    p_decisions_for.add_argument(
        "path",
        help="Repository file or directory path (POSIX or native; repo-relative or absolute).",
    )
    p_decisions_for.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Corpus directory to scan recursively for *.md (default: current directory).",
    )
    p_decisions_for.add_argument(
        "--top-level",
        action="store_true",
        help="Only the top-level files in the corpus directory (no recursion).",
    )
    p_decisions_for.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories (the default; accepted for clarity).",
    )
    p_decisions_for.set_defaults(func=cmd_decisions_for)

    p_eval = sub.add_parser(
        "eval",
        help="Score retrieval against the grounding benchmark; gate CI against the baseline.",
        parents=[version_parent],
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
        parents=[version_parent, json_parent, scope_parent],
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
    p_migrate.set_defaults(func=cmd_migrate)

    p_skill = sub.add_parser(
        "skill",
        help="Install or list the bundled Claude Code agent skills.",
        parents=[version_parent, json_parent],
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
    p_skill.set_defaults(func=cmd_skill)

    p_hook = sub.add_parser(
        "hook",
        help="Install or list the bundled git hooks (commit-time cadence nudge).",
        parents=[version_parent, json_parent],
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
    p_hook.set_defaults(func=cmd_hook)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Frozen retirement oracle only. The installed `decided` entry point is
    # asdecided.dispatch:main and never calls this implementation.
    parser = build_parser()
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
        # The downstream consumer closed the pipe (e.g. `decided export … | head`):
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
