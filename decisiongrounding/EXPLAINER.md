# DecisionGrounding — what it is, how to run it, and why it matters

A plain-language companion to the README, for anyone — technical or not — who
wants to understand why this benchmark exists before reading the code.

## The one-sentence version

DecisionGrounding is a fair, reproducible test of a simple but expensive
question: **when a team uses an AI coding assistant, does giving it a structured
memory of the team's past decisions actually make it follow those decisions
better — or do today's powerful models already handle that on their own?**

## The background

Software teams make decisions constantly: "we don't let code talk to the
database directly," "the orders service stays in Go unless an architect signs
off," "logs must be JSON." These decisions are usually written down somewhere
(often as short documents called ADRs — Architecture Decision Records).

AI coding assistants are now writing real code. The risk is that an assistant,
not knowing or not remembering a past decision, confidently does the wrong
thing — re-introduces a banned pattern, follows a rule the team has since
replaced, or rewrites a service in a new language nobody approved. Real
incidents like this have happened.

A growing industry says the fix is a **decision-grounding layer**: a structured,
typed memory that feeds the right past decisions to the assistant at the right
moment. That sounds great. But there's a sharp, fair objection:

> "Modern AI models are so capable, and can read so much text at once, that you
> can just paste all the decision documents in and they'll figure it out. A
> special memory layer adds no durable value."

**DecisionGrounding exists to settle that argument with evidence instead of
opinion** — and it's deliberately built to be believed even when the answer is
unflattering to the memory-layer idea.

## How it works (in plain terms)

It pits several "contestants" against each other on the exact same task, with
the exact same AI model answering. The only thing that changes between
contestants is *how the relevant past decisions are gathered and handed to the
model*:

- **Paste everything** — dump all the decision documents into the model. (This
  is the skeptic's position.)
- **Commodity search** — a standard "find the most similar documents" approach,
  no understanding of which decision replaced which.
- **The grounding layer** — structured retrieval that knows, for example, that
  Decision B officially replaced Decision A, and hands over B, not A.

Each contestant gets one fair shot at supplying context; the model then proposes
what it would do, and the benchmark checks — automatically, by inspecting the
proposal — whether it respected the team's decisions.

**The headline result is a single chart:** how often each contestant follows the
team's decisions as the pile of decisions grows from small to large. The
interesting moment is the *crossover* — the point (if any) where the structured
approach starts to win. The benchmark even states its own kill switch up front:
if the structured approach is no better than plain search on the hardest cases,
the idea is declared dead. That honesty is the point.

## How a non-technical person can set it up

You don't need to be an engineer to run the built-in demonstration. You do need
to copy-paste a few commands into a terminal.

1. **Install Python** (a free programming runtime), version 3.11 or newer, from
   python.org. On Mac it's often already there.
2. **Get the code.** Download the project folder (`decisiongrounding`) — your
   engineer can share it, or you can download it from the repository as a ZIP
   and unzip it.
3. **Open a terminal** (the Terminal app on Mac, or "Command Prompt" /
   "PowerShell" on Windows) and move into the folder:
   ```
   cd decisiongrounding
   ```
4. **Run the demonstration:**
   ```
   make demo
   ```
   (If `make` isn't available, use: `python -m runner.cli demo`.)

That's it. It runs entirely on your machine, needs no accounts, keys, or
internet, and finishes in seconds. It prints a small table and saves a chart
(`results/crossover.svg`) you can open in any web browser.

**Important honesty note:** this built-in demo uses a *stand-in* for the AI
model so it can run for free, instantly, with no setup. It proves the machinery
works and illustrates the idea — it is **not** a real scientific result. A real
result requires plugging in an actual AI model and real decision documents,
which is a step your engineering team would run (it needs paid API access). The
project is explicit about this distinction everywhere, on purpose.

## Why it's important

- **It turns a sales argument into a measurement.** Instead of "trust us, our
  memory layer helps," you get a number and a chart, on a frozen, public method
  that anyone can re-run.
- **It's built to be trusted by skeptics.** The toughest baselines (just paste
  everything; just do ordinary search) are mandatory, not afterthoughts. The
  scoring is mostly automatic and mechanical, not a vague "does this look good?"
  judgment. The method is locked down *before* any results exist, results are
  append-only, and there's a public commitment to publish losing results.
- **It answers a real budget question.** "Should we buy/build a decision-memory
  layer, or is our model good enough already?" — and, crucially, "at what size
  of decision history does it start to matter?" A small startup and a large
  enterprise may get different answers, and the chart shows where the line is.
- **It protects against a real failure mode.** AI assistants confidently doing
  things a team already decided against is a genuine source of risk. Measuring
  who avoids that — and avoids inventing fake rules that don't exist — is
  directly useful.

## The honest caveats (because credibility is the whole point)

- It measures *the quality of gathering and handing over the right decisions*.
  It does **not** measure whether, in day-to-day production, the assistant
  actually bothers to consult its memory at the right moment — that's a separate
  question about how the tool is wired into real workflows.
- The free built-in demo simulates the outcome to show the plumbing; the real
  verdict requires real AI models and real decision documents.
- Decision sets used for published results must come from real teams or public
  sources, with the "right answers" written down *before* seeing which
  contestant produced what — so nobody can rig the test.

If those guardrails hold, the result is believable. If the structured layer
wins, that's a real signal it adds durable value. If it doesn't, that's an
equally real signal — and the benchmark publishes it either way.
