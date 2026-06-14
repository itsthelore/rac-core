# Contributing to decisiongrounding

This benchmark is only worth running if it is credible to a skeptic who *wants*
the grounding layer to lose. These rules exist to protect that credibility. They
are not optional politeness; a contribution that violates them is rejected even
if the code is perfect.

## The credibility rules

### 1. Blind gold-labeling

Gold labels (the correct verdict, governing decision, prohibited/required
actions) MUST be written **before** and **independently** of running any arm,
and **without** knowing which arm produced which output. If you have already
seen an arm's answer to a task, you may not author or edit that task's gold
label. Label first, run second.

### 2. No win-only corpora

Scenarios MUST NOT be hand-authored to favour an arm. Production scenarios are
derived from **real or public ADR sets**, or a design partner's **real
incident** — not invented to make a chosen arm look good. The synthetic worked
scenarios in `scenarios/` exist solely to exercise the harness and are labelled
as such; they are never reported as results.

A corpus that only contains the kinds of decisions one arm handles well is a
win-only corpus. Include the cases your preferred arm is expected to *lose*
(easy single-decision ties, and the negative control where inventing a
constraint is the failure).

### 3. Publish losing results

If the grounded arm ties or loses — including the falsifier in the README
(grounded ≈ `naive_rag` on superseded + prohibition at N ≥ 50) — that result is
published, not buried. Append it to `results/` like any other run. A benchmark
that can only report wins is marketing.

### 4. Symmetric treatment of arms

Every arm gets the **same** answering model, the **same** prompt scaffold, and
**one** symmetric opportunity to populate the context window. Do not give your
arm a richer scaffold, a retry, a better model, or a second look. Differences
must live entirely in grounding assembly. Changes that alter the answering model
or scaffold for one arm only will be rejected.

### 5. Pre-registration is frozen

`spec/scenario-taxonomy.md` and `spec/scoring-rubric.md` are frozen before
results exist. Changing the taxonomy or rubric is a new **spec version** with a
rationale, not a quiet edit. Never reshape the question after seeing who won.

### 6. Append-only results

`results/` is append-only. Never mutate or delete a prior run file. Re-running
produces a new timestamped file. Each run records the pinned model + version +
temperature + seed so it reproduces.

## Adding a scenario

1. Create `scenarios/<id>/scenario.json` + a `corpus/` of markdown artifacts.
2. Validate against `schema/scenario.schema.json` (`pip install -e .[schema]`).
3. Write the gold label blind (rule 1). State its provenance (rule 2) in the
   `rationale`.
4. `make test`.

## Adding an arm

See "Add an arm" in the README. Then confirm it is scored by the same
deterministic scorer as every other arm — no arm gets a bespoke scorer.

## Decisions

Architecture decisions are recorded as RAC-style ADRs in `decisions/`
(`decisions/ADR-template.md`). The repo dogfoods the artifact format the
benchmark studies. If your change makes a non-obvious architectural choice,
record it as an ADR.
