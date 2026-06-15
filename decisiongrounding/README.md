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
  --embedder voyage:voyage-4-large \
  --scenarios scenarios/ --seed 0
```

`naive_rag` embeds corpus sections with Voyage's `document` role and the task
with its `query` role, so the RAG baseline uses asymmetric query/document
embeddings the way Voyage intends — a fair, strong baseline, not a strawman.
The default Voyage model is `voyage-4-large` (Voyage's current flagship);
override with `--embedder voyage:<model>`. Each report records the embedder id +
dimension and the installed `anthropic`/`voyageai` versions (`backend_versions`)
so a run says exactly what produced it.

The **crossover** can also run on the real backends:

```bash
# Real-model crossover. --ns keeps the API spend small (arms x scenarios x |ns|).
python -m runner.cli demo \
  --answering claude --embedder voyage:voyage-4-large --ns 10,50
```

This is where the thesis is actually tested — but note the boundary: with
`--answering claude` you get a real-*model* crossover **on the tiny synthetic
scenarios**. That is the plumbing for evidence, not the evidence. The real
result requires real/public-derived corpora (see CONTRIBUTING.md); until then
the crossover is plumbing, not evidence.

### Real-corpus pilot (PEP supersession)

`scenarios_real/` holds the first **real, public-derived** corpus: the
**PEP 386 → PEP 440** version-scheme supersession. PEP 386 carries
`Status: Superseded` / `Superseded-By: 440`; PEP 440 (`Replaces: 386`) states
"this PEP MUST be used … and supersedes PEP 386 … Tools SHOULD ignore any
versions which cannot be parsed by the rules in this PEP." An agent that reaches
for PEP 386's retired `verlib`/`NormalizedVersion` scheme is following a
superseded decision; the adherent move is to cite PEP 440 instead. See
`decisions/ADR-0002-real-corpus-pilot-peps.md`.

The PEPs are ingested as **RAC-native `decision` artifacts**: each carries the
verbatim PEP under a `## Source Text` section, wrapped in a decision envelope
(`Status`/`Context`/`Decision`/`Consequences`) plus a directional `## Supersedes`
edge — every envelope value derived from the PEP's own headers — so the `rac` arm
can classify them and follow the supersedes edge (see
`decisions/ADR-0003-rac-arm-pep-integration.md`). The corpus is pinned to one
immutable commit of `python/peps` and fully reproducible — nothing in it is
hand-written PEP prose:

```bash
# Regenerate the corpus from the pin, or verify it reproduces byte-for-byte.
python -m ingest.peps build  --out scenarios_real/peps_version_supersession
python -m ingest.peps verify --out scenarios_real/peps_version_supersession
```

Run the pilot for real (needs `[real]` + both keys, exactly as above):

```bash
python -m runner.cli compare \
  --arms context_dump,naive_rag,no_grounding,rac \
  --answering claude --embedder voyage:voyage-4-large \
  --scenarios scenarios_real --seed 0
```

The `rac` arm is the grounding layer under test: it follows the typed
`supersedes` edge and supplies the live PEP 440, where `naive_rag` can surface
PEP 386's appealing `verlib` section without the header that marks it superseded.
It needs the `rac` CLI on PATH (`pip install -e .` from the repo root, or set
`RAC_BIN`); drop `,rac` to run the baselines alone.

This produces the first genuine decision-adherence result (win, tie, or loss)
on a real corpus; like every run it is appended to `results/`. The build
environment for this pilot had no API keys, so the scenario is offline-validated
(loads, schema-validates, scores, and the `rac` arm's supersedes-following is
verified against the real `rac` CLI) and the real numbers are produced by whoever
holds the keys.

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
| `rac` arm (typed retrieval, follows `supersedes`) | ✅ verified against the `rac` CLI on the real corpus; needs `rac` on PATH |
| Real/public-derived scenario (PEP 386→440 supersession) | ✅ corpus built, pinned + verifiable; real run needs `[real]` + keys |
| `memory_provider` arm | ⏳ typed stub + TODO |
| LLM-judge fallback | ⏳ disclosed, not built |
| Full N=300 corpus (real/public-derived) | ⏳ next increment (more real pairs) |

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
  scenarios/   loader + worked scenarios with tiny synthetic corpora
  scenarios_real/  real/public-derived corpora (PEP supersession pilot)
  ingest/      deterministic ingest of public artifacts (PEPs) into corpora
  scoring/     deterministic scorer, metrics, crossover dataset + chart
  runner/      CLI; pins model + seed; append-only report writer
  results/     append-only run outputs (generated; not committed)
  tests/       schema, scorer, ingest, real-corpus, and offline arm-smoke coverage
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
