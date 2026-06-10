# Contributing to RAC

Thanks for your interest in improving RAC. The project is early and evolving
quickly — contributions, ideas, and experiments are welcome.

## Local setup

Requires **Python 3.11+**.

```bash
git clone https://github.com/tcballard/requirements-as-code.git
cd requirements-as-code
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Verify a change

These commands must all pass before you open a pull request:

```bash
pytest

ruff check src/ tests/
ruff format --check src/ tests/
mypy src/

rac validate rac/

rac relationships rac/ --validate
```

- `pytest` runs the full suite, including the **dogfood gate** (RAC's own
  planning corpus under `rac/` must pass RAC) and **golden output tests**
  (CLI output is pinned byte-for-byte).
- If you intentionally changed what the CLI prints, refresh the goldens and
  commit the diff — it will be reviewed as a product change:

  ```bash
  RAC_UPDATE_GOLDEN=1 python -m pytest tests/test_golden.py
  ```

See [docs/testing.md](docs/testing.md) for test layout, fixtures, and useful
pytest variations.

## Documentation expectations

- `docs/` is the public documentation: quickstart, CLI reference, artifact
  types, relationships, repository workflow. If your change alters a command's
  behavior, flags, output, or exit codes, update [docs/cli.md](docs/cli.md) in
  the same pull request.
- User-visible changes get a line in [CHANGELOG.md](CHANGELOG.md) under
  **Unreleased** — user impact over implementation details.
- JSON output is a stable, versioned contract: field changes must be additive
  and `schema_version`-gated (see `rac/decisions/`).

## RAC artifact expectations

The `rac/` directory is RAC's own product knowledge — requirements, decisions
(ADRs), roadmaps, prompts, and designs — maintained with the same care as code:

- Behavior changes that reflect a product decision should trace to an artifact
  under `rac/` (a roadmap initiative or an ADR).
- Artifacts you add or edit must keep the corpus green: `rac validate rac/`,
  `rac relationships rac/ --validate`, and `rac review rac/` all run in CI.

## Commit conventions

Follow [`rac/prompts/rac-agent-commit-guidelines.md`](rac/prompts/rac-agent-commit-guidelines.md):

```text
<type>(<area>): <imperative summary> [roadmap:vX.Y.Z]
```

with `type` one of `feat`, `fix`, `test`, `docs`, `refactor`, `chore`. Keep
commits small and single-purpose.

## License

By contributing you agree your contributions are licensed under the
[MIT License](LICENSE).
