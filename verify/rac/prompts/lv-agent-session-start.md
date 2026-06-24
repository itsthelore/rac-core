---
schema_version: 1
id: LV-KVW7ME5RQXCA
type: prompt
---
# lore-verify Agent Session Start

## Objective

Establish the working frame for an agent session on `lore-verify`, so changes stay
inside the product's boundary, respect its recorded decisions, and pass the
subproject's own gates before they are pushed.

`lore-verify` is the autonomous-QA consuming product decided in RAC ADR-083: an
agent given real developer tools (a browser, a terminal) that develops against a
target, converts the session into durable end-to-end tests, runs them across
targets and operating systems, and emits replayable trace artifacts. It is
prototyped in the `verify/` subdirectory of `rac-core` and extracted to
`itsthelore/lore-verify` once it ships (LV-ADR-001).

## Input

- The `verify/` subproject: its source (`src/lore_verify/`), tests, packaging, and
  its **own** RAC corpus under `verify/rac/` (repository key `LV`).
- The LV corpus: decisions (`LV-ADR-*`), requirements, designs, and roadmaps that
  govern this product.
- The published RAC contract this product consumes — `rac export --graph` and the
  `lore` MCP read tools — **never** RAC engine internals.

## Instructions

### Boundary — the rules that define this product (do not cross)

1. **Consume the contract, never the engine.** Read what to verify from `rac
   export --graph` (the `asset_edges` worklist, RAC ADR-084) — the `lore` MCP read
   tools serve only artifact-level reads. Never import `rac` internals, and never
   read the host repo's `.rac/` namespace (RAC ADR-063, LV-ADR-001).
2. **Write back only by proposing.** Evidence enters a Lore corpus only as a
   proposed `## Verified By` pull request a human reviews and merges (RAC ADR-065,
   LV-ADR-001, design `verified-by-write-back`). Never write a corpus directly; the
   produced PR MUST round-trip clean through `rac validate` / `rac relationships
   --validate`.
3. **Runtime and content live here, knowledge lives in Lore.** Driving the
   browser/terminal, running tests, and producing videos/traces are this product's
   job; RAC never does them (RAC ADR-017, ADR-024).

### Security — bind every runtime change to the threat model

The Drive module gives an autonomous agent a shell and live credentials against
targets that may be production. Every change touching Drive/Run derives from
LV-ADR-003 and its two requirements:

- The target is **untrusted input** (prompt-injection resistance is a design
  obligation); the terminal is **sandboxed and fail-closed** (LV-ADR-003,
  design `runner-interface-and-target-config`).
- **Secrets/PII are redacted before any trace, test, or log is persisted or
  attached to a PR**; target credentials are least-privilege and distinct from AI
  credentials (`evidence-redaction-and-secret-hygiene`).
- **Production is fail-closed**: non-seedable targets are write-blocked; mutations
  require explicit per-target allowlisting (`production-target-safety`).

### Before coding

1. Confirm you are on a feature branch, never on `main`.
2. Read the relevant LV roadmap item and the decisions/requirements it touches; do
   not expand scope beyond it.
3. Check against the `LV-ADR-*` decisions and the boundary rules above; if a task
   conflicts with a recorded decision, say so and stop.
4. For runtime/security-touching work, re-read LV-ADR-003 first.

### Grounding

The LV corpus is the source of truth for this product. Use the `rac` CLI against
`verify/rac/` (`rac find`, `rac resolve`, `rac relationships`) to ground changes;
recorded `LV-ADR-*` decisions take precedence over conventions inferred from code.
For the *consumed* RAC contract, read the published `rac export --graph` shape and
RAC ADR-084 — not RAC engine source.

### Testing

- Add coverage for new behaviour in `verify/tests/`.
- Run the `verify/` suite and `rac validate verify/rac/` before commit.

## Output

A correctly scoped, in-boundary change that passes the gates in Evaluation, with
commits following `lv-agent-commit-guidelines`.

## Constraints

- Never import RAC engine internals or read the host `.rac/` namespace (consume the
  published contract only).
- Never write a Lore corpus directly; propose a human-reviewed PR.
- Never persist or attach an unredacted trace; never embed a secret in a test.
- Never mutate a non-seedable/production target without explicit allowlisting.
- Never work on `main`; always use a feature branch.
- If a task conflicts with a recorded `LV-ADR`, say so and stop.

## Evaluation

Before pushing:

- `rac validate verify/rac/` and `rac relationships verify/rac/ --validate` exit 0.
- The `verify/` test suite, lint, and types pass with no `rac` source on the path
  (only the published contract) — the zero-coupling check (LV-ADR-001).
- Commits follow `lv-agent-commit-guidelines`: format, maintainer identity on
  author and committer, the DCO `Signed-off-by` trailer, and no tool attribution.

## Related Decisions

- lv-adr-001-product-identity
- lv-adr-003-runtime-threat-model
- lv-adr-004-ci-topology
