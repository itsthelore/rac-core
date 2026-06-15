# Scenario Taxonomy (FROZEN — pre-registration)

This taxonomy is frozen before results exist. Changing it is a new spec version,
not an edit. It exists so that no one — including the authors — can reshape the
question after seeing which arm wins.

A scenario is: a project corpus (typed markdown artifacts with relationships) +
an agent task (a prompt and the concrete action the agent is about to take) +
the binding decision(s) + a gold label written **blind** to which arm produced
which output. See `../schema/scenario.schema.json`.

## The five types

| Type | What it tests | Correct behaviour | Weight |
| --- | --- | --- | --- |
| `simple_adherence` | A single, easily retrieved decision governs. | Follow it. | Light — **expected tie** |
| `superseded_decision` | ADR-B supersedes ADR-A. | Follow **B**, not A. | **Over-weighted** |
| `prohibition_at_point_of_action` | A decision forbids the action the agent is about to take. | Refrain / escalate. | **Over-weighted** |
| `conflicting_scoped` | Multiple decisions apply with different scopes. | Apply the in-scope one. | **Over-weighted** |
| `negative_control` | **No** decision constrains the action. | Proceed; do **not** invent a constraint. | Mandatory control |

### Why these weights

The discriminating types (superseded, prohibition, conflicting/scoped) are where
retrieval/assembly quality should separate arms. `simple_adherence` cases are
included and labelled `expected_tie: true` so that ties are recognised as ties,
not mistaken for signal. The `negative_control` exists to catch hallucinated /
false prohibitions — the failure mode where an LLM-mediated arm invents a
constraint from a topically-adjacent decision. Deterministic typed retrieval
should beat LLM-mediated arms here.

## Discriminator mechanisms (what each type stresses)

- **superseded_decision** stresses *relationship survival*. Whole-corpus or
  typed retrieval preserves the `supersedes` edge; chunked top-k can retrieve
  the old rule without the section that marks it superseded, producing a
  stale-decision failure.
- **prohibition_at_point_of_action** stresses *recall at scale*. The prohibition
  must survive retrieval as the corpus grows; if it falls out of the retrieved
  set the agent proceeds (a false permit).
- **conflicting_scoped** stresses *scope discrimination* (typed, not built this
  pass — see worked-scenario coverage below).
- **negative_control** stresses *restraint*: not manufacturing a prohibition.

## Corpus-size sweep

The headline artifact sweeps corpus size N ∈ {10, 50, 150, 300} with rising
conflict density and plots per-arm decision-adherence. The story is the
crossover point. In this scaffold, larger-N corpora are grown with clearly
labelled synthetic `note` padding; production corpora MUST be real (see below
and `../CONTRIBUTING.md`).

## Worked-scenario coverage this pass

Five worked scenarios ship under `../scenarios/`: `simple_adherence_logging`
(expected tie), `superseded_decision`, `prohibition_language_migration` (modelled
on a real-world-style unauthorized implementation-language migration),
`conflicting_scoped_retry` (a scope conflict where the in-scope handler rule
governs over the out-of-scope background-jobs rule), and
`negative_control_cache_ttl`. All five scenario types are exercised; the
discriminating three (`superseded_decision`, `prohibition_at_point_of_action`,
`conflicting_scoped`) drive the crossover curve.

## Provenance rule (non-negotiable)

Production scenarios MUST be derived from real/public ADR sets or a design
partner's real incident — never hand-authored to favour an arm. Gold labels MUST
be written blind to which arm produced which output. The synthetic worked
scenarios here exist only to exercise the harness; they are not benchmark
results.
