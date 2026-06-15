# decisiongrounding

A reproducible benchmark that answers one question:

> Does a deterministic decision-grounding layer make a coding agent adhere to a
> team's **prior decisions** better than (a) dumping all the decision docs into
> context, (b) commodity RAG over the same docs, or (c) a general-purpose memory
> layer — and at what corpus size does any difference appear?

It is a **standalone** project. It does not depend on, or import, any specific
grounding implementation; the layer under test is just one arm behind a uniform
adapter.

## The objection this exists to test

> "Frontier models plus long context just absorb the decisions, so a persistence
> layer adds no durable value."

That objection is correct often enough that a benchmark which cannot reproduce
it is worthless marketing. So the threatening baselines are **mandatory**, not
courtesy arms:

- **`context_dump`** — paste every artifact into the answering model's context.
  This is the skeptic's position, implemented faithfully.
- **`naive_rag`** — embeddings + top-k over the same markdown. No typing, no
  relationship traversal.

A grounding layer earns its keep only by beating these — on the scenario types
where it should, at the corpus sizes where it should.

## The falsifier (stated up front)

**If the typed/grounded arm ≈ `naive_rag` on superseded + prohibition scenarios
at N ≥ 50, the retrieval thesis is dead.** We publish that result if we find it.
The benchmark is designed to be able to embarrass its sponsor; see
`CONTRIBUTING.md` ("publish losing results").

## How the comparison is kept fair

- **Held-constant answering model.** Every arm feeds context to the *same fixed
  answering model* with the *same prompt scaffold*, pinned by model + version +
  temperature + seed. Arms differ **only** in how they select and assemble the
  grounding context.
- **Symmetric grounding injection.** Each arm gets one equal opportunity to
  populate the answering model's context: `context_dump` supplies everything,
  `naive_rag` supplies its top-k, the grounded arm supplies its typed retrieval.
- **Deterministic scoring first.** Adherence is scored by structural inspection
  of the agent's proposed change (did it propose the prohibited migration? did it
  follow the superseded decision?). An LLM judge is a disclosed, unbuilt fallback
  — see `spec/scoring-rubric.md`.

### Symmetric-injection caveat (read this)

This benchmark isolates **retrieval/assembly quality**: given one symmetric shot
at the context window, which assembly strategy yields better decision-adherence?
It does **not** test whether a pull-based MCP grounding layer actually *gets
consulted* in production — whether an agent invokes the tool at the right moment
is a separate deployment question, out of scope here. Reading a favourable result
as "this layer will fix adherence in production" overstates what was measured.

## Headline metric and artifact

- **Headline metric:** decision-adherence rate.
- **Headline artifact:** an adherence-vs-corpus-size curve over
  N ∈ {10, 50, 150, 300} with rising conflict density — the story is the
  crossover point.
- Also reported: stale-decision rate, false-permit / false-prohibit rate,
  per-arm run-to-run variance, and **governing-decision recall** — did the arm's
  grounding actually contain the binding decision? Recall is the mechanistic
  explanation for why adherence moves (the analog of MemoryBench's Hit@K). There
  is deliberately **no** composite score.

## Run it (offline, no credentials)

```bash
cd decisiongrounding
make demo          # == python -m runner.cli demo
```

This runs the two real arms (`context_dump`, `naive_rag`) on the four worked
scenarios with a deterministic **offline** answering model, writes an
append-only report under `results/`, and emits the crossover chart
(`results/crossover.svg`, or `.png` with the `[chart]` extra).

> The offline answering model is a deterministic stand-in so the spine runs with
> zero credentials. **Its output is a harness illustration, NOT a benchmark
> result.** Real runs swap in the pinned Claude answering model and a real
> embedding backend (`pip install -e .[real]`) on real/public-derived corpora.
> See `decisions/ADR-0001-harness-foundation.md`.

### Run it for real (pinned model + real retrieval)

```bash
pip install -e ".[real,schema,chart]"
export ANTHROPIC_API_KEY=...        # pinned answering model: claude-opus-4-8
export VOYAGE_API_KEY=...           # real embeddings for naive_rag

# rac arm additionally needs the `rac` CLI on PATH (or set RAC_BIN)
python -m runner.cli compare \
  --arms context_dump,naive_rag,rac \
  --answering claude \
  --embedder voyage:voyage-3 \
  --scenarios scenarios/ --seed 0
```

This is where the thesis is actually tested. Until it runs on real/public-derived
corpora, the offline crossover is plumbing, not evidence.

Tests:

```bash
pip install -e .[dev]   # or: pip install pytest
make test
```

## What's real vs. stubbed in this pass

| Component | State |
| --- | --- |
| Scenario + RunResult JSON Schemas (Draft 2020-12) | ✅ real |
| Provider adapter contract | ✅ real |
| `context_dump`, `naive_rag`, `no_grounding` arms | ✅ real, runnable offline |
| Deterministic scorer + metrics + crossover chart | ✅ real |
| Runner CLI (`run` / `compare` / `demo`), append-only reports | ✅ real |
| Five worked scenarios (incl. negative control + conflicting-scoped) | ✅ real, synthetic |
| Governing-decision recall diagnostic | ✅ real |
| Pinned Claude answering model (`--answering claude`, Opus 4.8) | ✅ implemented; needs `[real]` + `ANTHROPIC_API_KEY` |
| Real embeddings (`--embedder voyage:…` / `st:…`) | ✅ implemented; needs `[real]` / `[local-embeddings]` |
| `rac` arm (typed retrieval, follows `supersedes`) | ✅ implemented; needs the `rac` CLI on PATH |
| `memory_provider` arm | ⏳ typed stub + TODO |
| LLM-judge fallback | ⏳ disclosed, not built |
| Full N=300 corpus (real/public-derived) | ⏳ next increment |

> **Pinned model caveat:** the answering model is `claude-opus-4-8`, which
> rejects `temperature`/`top_p`/`seed` (the API 400s on them). There is no
> temperature/seed knob to pin; the held-constant guarantee rests on the fixed
> model id + scaffold + structured JSON output, and run-to-run variance is
> reported as a metric. `temperature` is recorded as `null`.

## Repository layout

```
decisiongrounding/
  decisions/   ADR-0001 (harness foundation) + ADR template  — the repo dogfoods
               RAC-style ADRs to ground its own choices
  spec/        FROZEN scenario taxonomy + scoring rubric (pre-registration)
  schema/      JSON Schema (Draft 2020-12) for Scenario and RunResult
  providers/   uniform adapter (prepare/respond) + the arms + answering/embedding
  scenarios/   loader + four worked scenarios with tiny synthetic corpora
  scoring/     deterministic scorer, metrics, crossover dataset + chart
  runner/      CLI; pins model + seed; append-only report writer
  results/     append-only run outputs (generated; not committed)
  tests/       schema, scorer, and offline arm-smoke coverage
```

## Add an arm

1. Implement a `Provider` in `providers/` with `prepare(corpus)` and
   `respond(task) -> ProposedChange` (subclass `providers.base.Provider`; the
   shared `respond` already feeds the held-constant answering model — override it
   only if your grounding is task-dependent, as `naive_rag` does).
2. Register it in `providers/__init__.py` `ARMS` and, if it should run in the
   default demo, add it to `REAL_ARMS`.
3. Add it to the `arm` enum in `schema/run_result.schema.json`.
4. Run `make test` and `make compare ARMS=context_dump,naive_rag,your_arm`.

Your arm gets exactly one symmetric grounding opportunity and the same answering
model as every other arm. That is the whole point.
