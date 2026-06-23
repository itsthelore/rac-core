---
schema_version: 1
id: RAC-KVTSPM9V9VDQ
type: design
tags: [extensibility, plugins, registry, validation, architecture]
---
# Design: Third-Party Artifact Type Extensibility

## Context

ADR-077 decides *that* RAC will discover third-party artifact types through an
entry-point group, isolate their failures, load their templates from the
contributing package, and route them through generic structural validation, while
keeping custom relationship types deferred (ADR-055) and making `ArtifactSpec` a
published contract (extending ADR-062). This design is the *how*: the concrete
seam that turns the closed `ARTIFACT_SPECS` tuple into a discoverable registry,
the exact dispatch insertion point in validation, the template-resolution branch,
and the test shape that proves the change is inert when no plugin is installed.

It is recorded now, with no engine change, because the implementation is deferred
post-PMF and (for any public invitation) behind GATE-2. Writing the mechanism down
while it is fresh keeps the eventual build a scoped exercise rather than a
re-derivation, and lets the gates validate the plan as corpus knowledge.

## User Need

Two audiences, one mechanism:

- A **team** whose corpus needs a sixth, domain-specific type (a `runbook`, a
  `policy`) wants `rac new`, `rac validate`, `rac inspect`, and `rac schema` to
  handle it the same way they handle a requirement — by installing a package, not
  forking the engine.
- A **plugin author** wants to declare one `ArtifactSpec` and one template in a
  small `rac-<bundle>` package, register them under a documented entry-point group,
  and trust that a malformed bundle degrades to a warning rather than breaking
  every RAC command for their users.

Neither needs new analysis behaviour. The need is that the existing deterministic,
section-heading machinery becomes reachable by installed types it did not ship
with.

## Design

### 1. The registry seam (load-bearing)

Every consumer today binds the constant directly (`from .artifacts import
ARTIFACT_SPECS`). A `from x import CONST` binding is captured at import time, so
the set cannot be made dynamic by mutating the tuple — and a frozen module global
must not be mutated anyway. The whole design rests on converting **constant access
into function access**.

A new module `core/artifact_registry.py` owns discovery, caching, failure
isolation, and the merged view:

- `artifact_specs() -> tuple[ArtifactSpec, ...]` — built-ins first, then
  discovered third-party specs; cached for the process.
- `spec_for(name) -> ArtifactSpec | None` — linear scan over `artifact_specs()`
  (moves here from `artifacts.py`).
- `is_builtin(name) -> bool` — membership in the frozen set of built-in names.
- `_reset_cache()` — test seam only.

`artifacts.py` keeps owning the built-in spec *data* (the five `ArtifactSpec`
definitions); the registry imports that data, never the reverse, so there is no
import cycle. Consumers repoint from the constant to `artifact_specs()`. The edits
are mechanical and already enumerated by exploration: `classification.py`
(`score_artifacts`), `templates.py` (`available_templates` and the membership
check), `schema.py` (`available_schemas`, `schema_reference`), `services/inspect.py`
and `services/portfolio.py` (the `{spec.name: 0 ...}` count seeds),
`services/relationships.py` and `core/identity.py` (which already take a `spec`
or call `spec_for`), and `validation.py`. Callers that pass a literal built-in
name (`spec_for("requirement")`, etc.) keep working because built-ins are always
present.

### 2. Discovery and failure isolation

`artifact_specs()` appends discovered specs by mirroring the `explorer` launcher's
lazy-import, fail-soft precedent. Discovery iterates the entry points of group
`rac.artifact_specs`, loads each, and admits its spec(s) through one guard:

1. **Contract check** — the loaded object is an `ArtifactSpec` with a non-empty
   string `name`/`display` and a non-empty `required` tuple.
2. **Built-in collision** — a name already owned by a built-in is skipped
   (built-ins always win).
3. **Duplicate third-party** — a name already loaded is skipped (first wins,
   deterministic given a stable iteration order).
4. **Normalisation** — the name must already be its normalised
   (stripped, case-folded) form, so classification and section matching stay
   deterministic.

Each rejection is a `warnings.warn(..., ArtifactSpecWarning)` plus a skip — never a
raise. Routing through `warnings` rather than `print(..., file=sys.stderr)` is
deliberate: the golden CLI tests pin stdout/stderr byte-for-byte, so a warnings
channel keeps the "no plugin → output unchanged" guarantee structurally true and
lets a malformed-plugin test assert with `pytest.warns` without touching golden
fixtures. Caching makes discovery run once per process.

### 3. Validation routing

`validation.py::validate` classifies the product, then dispatches. The change
inserts **one type-agnostic branch** after the five built-in arms and **before**
the Unknown/legacy requirement fallback:

> if `spec_for(type)` returns a spec and `not is_builtin(type)` → route to a new
> `_validate_generic(product, spec)`.

`_validate_generic` is pure composition of the existing ADR-060 shared helpers —
`_validate_title`, `_validate_required_sections` (iterates `spec.required`), and
`_validate_status_metadata` (iterates `spec.metadata`) — and adds no new logic. It
is the same shape the `decision`/`prompt`/`design` validators already have. Those
named validators are deliberately *not* collapsed into it in this change, to
preserve their REQ-traceable docstrings and avoid golden churn.

The branch keys on a predicate, never a type name, so REQ-004 ("no
artifact-specific branches in core") holds. The four invariants are preserved:
the five built-ins keep their explicit arms; `requirement` still reaches its
bespoke arm because `is_builtin("requirement")` is true; an Unknown document has
no spec (`spec_for` returns `None`) and falls through unchanged; only a
registered third-party type reaches the generic validator.

### 4. Template resolution

`ArtifactSpec` gains one appended optional field, a `(package, resource)` reference
to a template; built-ins leave it unset. `load_template` branches on the spec
rather than the type name: unset → the `rac.templates` path (unchanged); set →
`resources.files(package).joinpath(resource)`. The caught-exception set widens to
include `ModuleNotFoundError` alongside `FileNotFoundError`, so a plugin naming a
missing package degrades to `TemplateResourceMissing` (an operational error,
exit 1), never a traceback. `available_templates()` follows the registry from the
seam in section 1, so a custom type appears in `rac new` and `rac templates`
automatically. `rac schema` needs no change — it is already fully spec-driven, and
its starter-body defaults degrade to a generic "describe this section" for an
unknown section name.

### 5. Relationships scope (v1)

Per ADR-077 decision 4 and ADR-055, v1 introduces no new edge kinds. A custom
artifact may declare the built-in relationship sections (`## Related Decisions`,
etc.) and reference built-in types — `services/relationships.py::_collect` already
handles that by iterating `spec.optional`. A custom type is **not** added to any
built-in edge's `range`, so a built-in `related_*` reference resolving to a
custom-type artifact still flags `relationship-target-type-mismatch`. That sharp
edge is recorded and pinned by a test, so the deferral is a deliberate, observable
decision rather than an accident. Auto-derived `related_<type>` edges are left for
a future relationships ADR.

### 6. `ArtifactSpec` stability boundary

Publishing the entry point makes `ArtifactSpec` a compatibility surface, so it
joins `rac.__all__` and is re-exported from the top-level package (ADR-062's
mechanism: the surface *is* `__all__`). The dataclass is already frozen with
all-defaulted optional fields; the stated rule is append-only (new fields optional
and appended last, existing fields unchanged). An `from rac import ArtifactSpec`
surface test guards it.

### 7. Sequencing and the smallest reversible step

The implementation order is: registry seam → discovery + isolation → validation
routing → templates → relationships scope → schema/CLI fall-out → `ArtifactSpec`
surface → tests. The **smallest reversible first step** is the registry seam alone
(section 1) returning only the built-in tuple: a pure, mechanical refactor that is
provably inert (the whole suite plus golden output pass unchanged) and trivially
revertible, isolating the one invasive change — constant access becoming function
access across ~8 modules — from all plugin semantics, which then layer on
additively behind the seam.

## Constraints

- **Inert when absent (REQ-001).** With no plugin installed, `artifact_specs()`
  equals the built-in tuple and every command's output is byte-for-byte unchanged;
  this is the acceptance gate for the seam and the regression net for every later
  step.
- **Determinism (ADR-002).** No semantic or LLM scoring; classification stays the
  existing deterministic scorer. Collision rules are fixed before any plugin can
  affect a corpus.
- **Additive contracts (ADR-007).** Result `to_dict()` shapes and per-type count
  maps gain keys, never lose or repurpose them; no `schema_version` bump.
- **No mandatory dependency (REQ-005).** `importlib.metadata` and
  `importlib.resources` are stdlib; nothing from a contributing package is
  imported beyond its entry point.
- **Deferred boundaries.** Custom relationship types stay deferred (ADR-055); any
  public invitation stays behind GATE-2 (CLA, ADR-071). This design enables the
  engine; it does not announce the ecosystem.

## Rationale

The constant-to-function seam is the one genuinely invasive move, and isolating it
as the first, inert step de-risks everything else, which becomes additive. Reusing
the ADR-060 helpers for generic validation means a custom type inherits correct
structural checks with no new code and no per-type branch, honouring REQ-004
literally. Carrying the template location as data on the spec — rather than a
callable — keeps loading inside RAC's deterministic `importlib.resources` path so
RAC owns error mapping and offline behaviour. Keeping the graph layer code-defined
holds the line ADR-055 drew and keeps graph-integrity checks independent of which
plugins happen to be installed.

## Alternatives

- **Collapse the four spec-driven validators into `_validate_generic` now.**
  Deferred: correct eventually, but it churns golden output and erases
  REQ-traceable docstrings; do it as a later cleanup, not inside this change.
- **A loader callable on the entry point for templates.** Rejected (ADR-077
  decision 3): arbitrary code at template time breaks offline determinism.
- **Exempt custom-type targets from the built-in range check in v1.** Rejected for
  v1: it is a behaviour change to the built-in graph contract; left for the future
  relationships ADR so the change is deliberate.

## Accessibility

Not applicable — this is a code-level extension mechanism with no user-facing UI.
Plugin-authoring documentation, when GATE-2 clears, follows the repository's
existing readable-prose conventions.

## Style Guidance

- The new module is `core/artifact_registry.py`; the public accessor is
  `artifact_specs()` (verb-free noun accessor, matching `available_schemas()` /
  `available_templates()`).
- The warning type is `ArtifactSpecWarning(UserWarning)`; the new optional field
  name reads as data (`template_resource`), not behaviour.
- The validation branch stays type-agnostic — keyed on `is_builtin`, never on a
  named custom type.

## Open Questions

- Whether a future opt-out (an env var or config flag) is needed if a slow plugin
  taxes start-up; deferred until a real plugin proves the latency risk.
- Whether `ArtifactSpec` warrants a narrower public construction factory rather
  than direct export; the dataclass is stable, so direct export is preferred until
  field churn appears.
- The trigger that schedules implementation (PMF signal and/or a design partner),
  and the separate GATE-2 trigger for any public ecosystem invitation.

## Related Decisions

- adr-077
- adr-052
- adr-055
- adr-062
- adr-021
- adr-060
- adr-002
- adr-007

## Related Requirements

- rac-growth-extensibility
