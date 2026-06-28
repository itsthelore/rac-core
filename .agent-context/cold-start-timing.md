# Cold-start timing — install to first validated artifact

Measured 2026-06-28 against the **released** PyPI package `rac-core==2026.6.5`
(the distribution renamed from `requirements-as-code`), on Linux, Python 3.11.15,
in a fresh `venv`. Wall-clock, `date +%s.%N` around each step. This satisfies
`rac-growth-adoption` REQ-003 (timed against a released package, recorded here).

**Network:** packages fetched from PyPI through the environment's HTTPS proxy;
the pip HTTP cache state was not controlled, so download time on a genuinely cold
cache or a slow link would be higher (REQ-003 / the "install time dominates"
risk).

## Path A — `pip` in a fresh venv, canonical `rac quickstart` one-command path

| Step | Command | Wall clock |
| --- | --- | --- |
| 1 | `python3 -m venv /tmp/coldstart-venv` | 4.58 s |
| 2 | `pip install rac-core==2026.6.5` | 9.06 s |
| 3 | `rac --version` → `rac 2026.6.5` | ~0.1 s |
| 4 | `rac quickstart` (identity + first artifact, one command) | 0.21 s |
| 5 | Edit the TODO placeholders (human; not timed) | — |
| 6 | `rac validate rac/requirements/first-requirement.md` → PASS, exit 0 | 0.21 s |

Machine total: **≈ 14.2 s**. Result: `PASS`, 0 errors, 1 advisory warning
(`missing normative keyword` on the placeholder REQ). The artifact validates
**as scaffolded** — editing is for meaning, not to pass the check — so the path
reaches a passing first artifact in one command before `validate`.

`rac quickstart` removes the only prior snag (it creates `rac/<family>/` and the
artifact itself), so the old `mkdir -p` step is gone.

## Path B — `uv tool install`

`uv tool install rac-core==2026.6.5`: **1.09 s**; `rac --version` →
`rac 2026.6.5` immediately. Zero post-install configuration.

## REQ-001 — both names, all installers resolve to a working `rac`

| Install | Time | Result |
| --- | --- | --- |
| `pip install rac-core==2026.6.5` | 9.06 s | `rac 2026.6.5` |
| `pip install requirements-as-code` (shim 2026.6.99 → `rac-core`) | 7.86 s | `rac 2026.6.5` |
| `uv tool install rac-core==2026.6.5` | 1.09 s | `rac 2026.6.5` |

The transitional `requirements-as-code` shim still resolves to `rac-core`, so the
pre-rename install instructions keep working.

## Verdict — two bars (REQ-002 human, REQ-006 machine)

- **Human-inclusive (REQ-002, ≤5 min):** holds with a wide margin — the budget is
  consumed almost entirely by human reading and editing, not tooling.
- **Machine (REQ-006, <30 s):** install → first `rac validate` pass is **≈14 s**
  end to end (`pip` ~9 s + venv ~4.6 s dominate), comfortably under 30 s; with
  `uv tool` the install leg is ~1 s. **RAC's own commands** — `rac quickstart`
  (0.21 s) + `rac validate` (0.21 s) = **≈0.42 s**, the sub-second part RAC
  controls and the cold-start contract test guards. Package install and venv
  creation are environment/network costs, reported here, not RAC's to bound.

Both bars hold against the released `rac-core==2026.6.5`, on `pip`, the
`requirements-as-code` shim, and `uv tool`.

## Caveats

- Network was the environment proxy with an uncontrolled pip cache; a cold cache
  or slow link adds download time (stated per the REQ-003 risk).
- `pipx` itself was not installed in this environment; `pip` and `uv tool` were
  exercised directly, and `pipx install rac-core` uses the same resolver as `pip`.
