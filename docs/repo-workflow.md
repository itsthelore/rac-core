# Repository Workflow

RAC runs against any directory of Markdown files, but it shines when a repository
gives its product knowledge an intentional home. This page describes the convention
RAC itself uses.

## The `rac/` knowledge directory

Collect your artifacts under a top-level `rac/` directory, grouped by type:

```text
rac/
  requirements/   # what needs to exist
  decisions/      # ADRs — why choices were made
  designs/        # product experience thinking
  prompts/        # reusable AI collaboration patterns
  roadmaps/       # where the product is heading
  assets/         # supporting images and files
```

The directory layout is a convention, not a requirement — RAC classifies each file by
its [section headings](artifacts.md#how-classification-works), not its folder. Grouping
by type simply keeps a growing corpus navigable and makes `stats`/`portfolio` output
easy to read.

### Three documentation layers

RAC's own repository separates concerns into three layers
([ADR-022](https://github.com/tcballard/requirements-as-code/blob/main/rac/decisions/adr-022-documentation-boundaries.md)):

- **`README.md`** — the front door: what RAC is and how to try it.
- **`docs/`** — user-facing guides (this directory).
- **`rac/`** — RAC's internal, structured product knowledge.

`rac/` is the corpus RAC manages; `docs/` is documentation *for people*. Keep them
distinct: users shouldn't need to read internal roadmaps or ADRs to be productive.

## Naming

- Requirements / prompts / designs: a descriptive slug — `login-flow.md`.
- Decisions: `adr-NNN-slug.md` — `adr-001-markdown-first.md`.
- Roadmaps: `vX.Y.Z-slug.md` — `v0.7.6-document-structure.md`.

See [artifacts.md](artifacts.md) for the sections each type expects.

## Everyday commands

Run these from the repository root:

```bash
rac validate rac/                 # validate every recognized artifact in the tree
rac stats rac/                    # counts, quality signals, per-type breakdown
rac relationships rac/ --validate # check that cross-artifact references resolve
rac review rac/                   # all of the above as one prioritized worklist
rac portfolio rac/                # one-screen health summary + attention list
rac index rac/ --json             # flat inventory for tools, CI, and agents
```

To check a single file as you edit it:

```bash
rac validate rac/requirements/login-flow.md
rac inspect  rac/requirements/login-flow.md
```

## In review and CI

Because everything is Markdown in Git, documentation and artifacts move through the
same pull-request workflow as code. A natural pre-merge check is `rac review rac/`
— it validates every artifact, resolves every reference, and exits `1` if anything
blocking is found, so reviewers see whether new or edited artifacts are complete
and their links still resolve. RAC runs exactly this gate over its own `rac/`
corpus in CI. See [testing.md](testing.md) for the contributor verification
workflow.
