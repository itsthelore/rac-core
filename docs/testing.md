# Testing & Contributing

This page is for contributors working on RAC itself: how to set up a local
environment, run the test suite, and verify a change before opening a pull request.

## Local setup

RAC requires **Python 3.11+**. Work inside a virtual environment and install the
package in editable mode with the `dev` extra, which pulls in `pytest` and the
libraries used to generate test fixtures:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

If you prefer not to activate the environment, call the interpreter directly —
`.venv/bin/python` — which is what the examples below do.

## Running the tests

The suite lives in `tests/` (configured via `testpaths` in `pyproject.toml`), so
`pytest` needs no arguments:

```bash
.venv/bin/python -m pytest        # or: .venv/bin/pytest
```

Useful variations:

```bash
.venv/bin/python -m pytest -q                      # quieter output
.venv/bin/python -m pytest tests/test_validate.py  # one module
.venv/bin/python -m pytest -k relationships        # match by name
```

Tests are organized per capability — `test_validate.py`, `test_inspect.py`,
`test_relationships.py`, `test_schema.py`, and so on — with Markdown inputs under
`tests/fixtures/`. When you add a behavior, add fixtures and a matching test,
including negative cases (an invalid file, or a neighboring artifact type that must
*not* classify as the new one).

Every `tests/test_*.py` must belong to exactly one CI battery in
`.github/workflows/tests.yml` — `tests/test_ci_batteries.py` fails the suite if a
file is orphaned, duplicated, or stale, so add new test files to the matrix as you
create them.

## Lint, format, and types

CI gates on ruff and mypy (configured in `pyproject.toml`); run them locally
before pushing:

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m ruff format --check src/ tests/   # or without --check to apply
.venv/bin/python -m mypy src/
```

Coverage is reported (not gated) in CI; the same view locally:

```bash
.venv/bin/python -m pytest -q --cov=src/rac --cov-report=term-missing
```

## Source layout

The package uses a `src/` layout. The import package `rac` is organized into layers
([ADR-023](../rac/decisions/adr-023-clean-break-internal-refactors.md)):

```text
src/rac/
  cli.py       command-line entry point
  core/        domain primitives: parsing, classification, identity, schemas
  services/    repository capabilities: inspect, stats, relationships, ingest
  output/      human, JSON, and template rendering
  explorer/    consumer boundary
```

## Verify before a pull request

1. **Run the suite and the static gates** — all must pass:

   ```bash
   .venv/bin/python -m pytest
   .venv/bin/python -m ruff check src/ tests/
   .venv/bin/python -m ruff format --check src/ tests/
   .venv/bin/python -m mypy src/
   ```

2. **Review your artifact changes** with RAC's own tooling:

   ```bash
   .venv/bin/rac validate rac/
   .venv/bin/rac relationships rac/ --validate
   .venv/bin/rac review rac/
   ```

   `validate` checks every recognized artifact against its schema;
   `relationships --validate` flags references that no longer resolve; `review`
   combines both into one prioritized report. Each exits `1` on blocking
   findings — and the same gates run in CI (`tests/test_dogfood.py`), so a red
   result here will be a red build.

3. **Follow the commit conventions** in
   [`rac/prompts/rac-agent-commit-guidelines.md`](../rac/prompts/rac-agent-commit-guidelines.md):
   `<type>(<area>): <summary> [reference]`.
