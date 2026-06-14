---
schema_version: 1
id: RAC-KV3SME4EAE84
type: decision
tags: [validation, enforcement, onboarding, config]
---
# ADR-053: Validation Severity Overrides via .rac/config.yaml (Warnings-First Onboarding)

## Status

Proposed

## Category

Architecture

## Context

RAC's validation severities are fixed in code: each rule emits `error` or
`warning`, and a directory `rac validate` fails when any artifact carries an
error (ADR-049 makes that gate the product). That is correct for a corpus RAC
grew with, but hostile to adoption: a team pointing `rac validate` at a legacy
repository for the first time is failed on hundreds of pre-existing findings at
once. The brief that scopes this series makes *warnings-first onboarding* a
requirement — a team must be able to start with findings as warnings and tighten
the gate over time.

RAC already has a committed, discoverable repository config — `.rac/config.yaml`,
established by `rac init` and resolved by `load_repository_config` (ADR-026). The
question is how to express per-repository severity policy without (a) loosening
the default gate, (b) breaking determinism (ADR-002), or (c) drifting toward the
custom-type JSON-Schema registry ADR-052 deferred.

## Decision

1. **A `validation` section in `.rac/config.yaml`** carries optional severity
   overrides. It is committed and versioned, so CI and every teammate share the
   same policy — a per-developer local file would not keep CI green and is not
   offered.

   ```yaml
   validation:
     rules:                 # rule code -> error | warning | off
       ambiguous-verb: off
       too-many-requirements: warning
     types:                 # artifact type -> error | warning  (a ceiling)
       roadmap: warning
   ```

2. **Two granularities.** A per-rule-code entry sets a finding's severity by its
   stable code (`error`/`warning`/`off`); a per-type entry caps a whole artifact
   type at `error` or `warning`. `off` (rule-only) suppresses the finding.

3. **Precedence: rule beats type.** A per-type `warning` ceiling downgrades that
   type's `error` findings to `warning`; a per-rule-code entry is more specific
   and wins, so a downgraded type can still force one rule back to `error`. This
   is a pure post-processing pass (`rac.core.overrides.apply_overrides`) applied
   before status and exit code are computed, so a downgraded type or rule keeps
   the run green.

4. **Scope: the `rac validate` entrypoints only.** Overrides apply to directory
   and single-file `rac validate` (core findings and OKF conformance findings,
   which gain a `severity`). The repository model behind `review`, `watchkeeper`,
   and `portfolio` is unchanged (it validates with no overrides), so those
   surfaces keep reporting the corpus as authored.

5. **Determinism preserved (ADR-002).** The overrides live in a committed file,
   so the same repository state yields the same findings and exit code. Malformed
   shapes or unknown severity values are a hard error
   (`MalformedRepositoryConfig`), never silently ignored. (YAML resolves the bare
   word `off` to a boolean; the loader coerces it back so authors need not quote
   it.)

6. **Not a registry or a dialect.** This is a flat, hand-managed severity map —
   not a JSON-Schema vocabulary and not the custom-type registry ADR-052 defers.
   The per-type knob keys on any type string, so it is forward-compatible with a
   future custom-type registry without anticipating one.

## Consequences

### Positive

- Warnings-first onboarding: a team can adopt RAC on a legacy repo with CI green
  from day one, then tighten the gate rule-by-rule or type-by-type.
- Policy is shared and reviewable (committed config), not per-developer drift.
- Reuses the existing config file and discovery walk; no new file, no dependency.

### Negative

- Validation severity is now influenced by repository config, so reproducing a
  result requires the `.rac/config.yaml` as well as the artifacts. Mitigated: the
  config is committed and versioned, so determinism holds.
- A team could over-suppress and hollow out the gate. Mitigated: overrides are
  visible in the committed config and in `rac validate` output; the default
  (no `validation` section) is the strict gate.

### Neutral

- `review`/`watchkeeper`/`portfolio` deliberately ignore overrides; whether they
  should honour them is a separate, later decision.

## Alternatives Considered

- **A per-developer, git-ignored local override file.** Rejected: it would not
  keep CI green for the team, which is the whole point of warnings-first.
- **A new dedicated `.rac/overrides.cfg` file.** Rejected: a second config file
  and parser for no benefit over a section in the existing `.rac/config.yaml`.
- **A global `--strict`/`--lenient` flag instead of config.** Rejected: too
  coarse (no per-rule/per-type control) and not shared with CI by default.
- **Per-rule severity baked into a custom-type JSON-Schema registry.** Rejected:
  that is the machinery ADR-052 deferred; overrides need none of it.

## Related Decisions

- ADR-049
- ADR-052
- ADR-026
- ADR-002
- ADR-007
- ADR-010

## Related Requirements

- rac-cross-artifact-enforcement
- rac-growth-adoption
