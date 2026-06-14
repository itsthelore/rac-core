# Validation: overrides & SARIF

`rac validate` is RAC's write-time gate: it fails when any artifact carries an
error-severity finding, and (over a directory) when the corpus is not a
conformant OKF v0.1 bundle. Two features make that gate adoptable in CI on a
real, pre-existing repository.

## Severity overrides (warnings-first onboarding)

Pointing `rac validate` at a legacy corpus for the first time can surface many
pre-existing findings at once. Rather than fail the build on all of them, a
repository can downgrade or silence specific findings in its committed
`.rac/config.yaml`, then tighten the gate over time. The decision behind this is
[ADR-053](https://github.com/tcballard/requirements-as-code/blob/main/rac/decisions/adr-053-validation-severity-overrides.md).

Add an optional `validation` section:

```yaml
repository_key: RAC

validation:
  rules:                 # rule code -> error | warning | off
    ambiguous-verb: off
    too-many-requirements: warning
  types:                 # artifact type -> error | warning  (a ceiling)
    roadmap: warning
```

- **`rules`** sets a finding's severity by its stable code (the `[code]` shown in
  `rac validate` output, e.g. `invalid-decision-status`). `off` suppresses the
  finding entirely.
- **`types`** caps a whole artifact type at `error` or `warning`. A `warning`
  ceiling downgrades that type's errors so they no longer fail the run.
- **Precedence:** a per-rule entry is more specific and **wins** over the
  per-type ceiling — so a downgraded type can still force one rule back to
  `error`.

The config is committed and versioned, so CI and every teammate share the same
policy (a per-developer file would not keep CI green). Determinism holds: the
same corpus *and config* yield the same findings and exit code. An absent
`validation` section is a pure no-op — the default gate is strict.

Overrides apply to `rac validate` only; `rac review`, `rac watchkeeper`, and
`rac portfolio` report the corpus as authored.

A typical onboarding path: start by capping noisy types to `warning`, get CI
green, then remove entries (or restore `error`) rule-by-rule as the corpus is
cleaned up.

## SARIF output for GitHub Code Scanning

`rac validate <dir> --sarif` emits a [SARIF 2.1.0](https://json-schema.org/)
document covering core validation findings and OKF conformance findings, so a CI
job can upload it and have GitHub Code Scanning annotate findings inline on a
pull request. The decision behind this is
[ADR-054](https://github.com/tcballard/requirements-as-code/blob/main/rac/decisions/adr-054-sarif-validation-output.md).

```bash
rac validate rac/ --sarif > rac.sarif
```

- `--sarif` is mutually exclusive with `--json`, and applies to directory
  validation only (single-file `--sarif` is a usage error).
- Severity maps to the SARIF `level` (`error`/`warning`); suppressed (`off`)
  findings never appear. A finding's line becomes a `region` when known.
- Output is deterministic and offline: results are sorted, no timestamps are
  emitted, and the same corpus state produces a byte-identical document.

The exit code is unchanged by the output format: `rac validate` still exits `1`
when an error-severity finding remains after overrides, and `0` otherwise.

A worked example of the output is checked in at
[`docs/examples/rac-validate.sarif.json`](examples/rac-validate.sarif.json): one
`error` (an out-of-enum decision status), two recommended-section `warning`s, and
a line-anchored `ambiguous-verb` finding (note the `region.startLine`).

## See also

- [CLI Reference](cli.md) — all `rac validate` flags and exit codes.
- [OKF Profile](okf-profile.md) — the conformance findings SARIF also reports.
- [Repository Workflow](repo-workflow.md) — `rac init` and `.rac/config.yaml`.
