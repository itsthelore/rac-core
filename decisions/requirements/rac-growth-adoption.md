---
schema_version: 1
id: RAC-KTYB6QBZNTD0
type: requirement
---
# RAC Growth — Adoption Surface

## Status

Proposed

## Problem

A new user evaluating RAC has to take its value on trust. The path from
"heard about it" to "first validated artifact on my machine" is not
measured, not demonstrated visually, and depends on the user assembling
the steps themselves from the quickstart. Every extra minute in that path
loses evaluators. The install, first-run, and demonstration surface
should make first value fast, observable, and repeatable.

## Requirements

- [REQ-001] RAC is installable with `pipx install rac-core` and with `uv tool install rac-core` — the canonical distribution since the PyPI rename — and the transitional `requirements-as-code` shim still resolves to it. The `rac` command works immediately after install with zero post-install configuration (no config files, environment variables, or accounts required before first use).

- [REQ-002] On a clean machine, a user can go from starting the install to a first artifact passing `rac validate` in under five minutes with zero configuration: canonically `rac quickstart` then `rac validate` (one command before the check, REQ-005), or the explicit path — install, then `rac init`, `rac new`, edit the TODO placeholders, `rac validate`.

- [REQ-003] The cold-start path in REQ-002 is timed against a released package version and the measurement recorded in the repository (`.agent-context/cold-start-timing.md`), so the five-minute claim is evidence-backed rather than asserted.

- [REQ-004] The README carries a demo GIF of at most 20 seconds showing the init → author → validate loop (`rac init`, `rac new`, edit, `rac validate`), produced from the shot list in the `growth-demo-gif` design; the GIF complements the existing "90-second demo (link on launch)" placeholder and does not replace it.

- [REQ-005] `rac quickstart` offers a guided first-run path that establishes the repository identity and scaffolds a first artifact in one step, reducing the cold-start command count from three (`rac init`, `rac new`, `rac validate`) to one before the validation check; it writes a single starter artifact only into an empty corpus and refuses otherwise (ADR-044). Delivered by the v0.13.0 roadmap.

- [REQ-006] Beyond the human-inclusive five-minute budget (REQ-002), the *machine* cold start — install through a first `rac validate` pass, excluding human reading and editing — completes in under 30 seconds on a typical environment (warm package cache), recorded against a released package. RAC's own commands (`rac quickstart` and `rac validate`) contribute well under one second of that budget — the part RAC controls and the part the cold-start contract test guards; package install and venv creation are not RAC's to bound and are reported, not gated.

## Success Metrics

- Human-inclusive cold start (install → first `rac validate` pass) under
  five minutes on a clean environment, recorded with timings (REQ-002).
- Machine cold start (install → first `rac validate` pass, excluding human
  reading/editing) under 30 seconds on a typical environment, recorded;
  RAC's own commands sub-second (REQ-006).
- Both `pipx` and `uv tool` installs verified to produce a working `rac`
  command with no further configuration.
- README demo GIF present, ≤20 seconds, showing init → author →
  validate.

## Risks

- Install time dominates the five-minute budget on slow networks; the
  measurement should state the network conditions observed.
- The GIF goes stale as CLI output changes; it should be cheap to
  re-record from the shot list.
- `pipx` and `uv` resolve dependencies differently from `pip`; the
  zero-configuration claim must be verified per installer, not assumed.

## Assumptions

- Python 3.11+ is available on the target machine, as `pyproject.toml`
  requires; installing Python itself is outside the five-minute budget.
- The published PyPI package `rac-core` (and the `requirements-as-code`
  shim that depends on it) matches the local checkout closely enough that
  local timing is representative.

## Related Requirements

- rac-growth-agent-skill

## Related Designs

- growth-demo-gif

## Related Roadmaps

- v0.13.0-guided-first-run
