# Security Model

This document describes the trust and threat model for **RAC Core** and the
**Lore** read-only MCP server in this repository. It is scoped to that surface:
it explains what the read-only guarantee does and does not protect, and how to
report a vulnerability. It deliberately does **not** promise a vulnerability-
response SLA, a content sanitizer, or any automated per-artifact trust verdict.

## Trust model

RAC stores product knowledge — requirements, decisions (ADRs), designs,
roadmaps, and prompts — as Markdown artifacts in a git repository. A coding
agent reads that content through the Lore MCP tools and treats it as
authoritative grounding.

**Artifact content is authoritative because a human reviewed and merged it in a
pull request.** Human PR review is the trust boundary (ADR-065). The read-only
MCP server protects the *store* — it never writes, never executes artifact
content, and re-reads from disk on every call — but it does **not** vet the
*meaning* of what it serves. Content that has not been through PR review —
an unmerged branch, a local working copy, or anything ingested by a machine
without human acceptance — is **out of scope and must not be treated as
trusted**.

What the read-only guarantee protects:

- The serving surface cannot modify, delete, or corrupt the repository.
- Tool output is deterministic and bounded; adversarial input cannot crash,
  hang, or exhaust memory in the serving path (it is reported as structured
  data and the corpus walk continues past it).

What it does **not** protect:

- It makes no judgement about whether an artifact's *content* is correct, safe,
  or non-malicious. That judgement is the human reviewer's and the consuming
  agent's.

## Threat: the artifact as an attack surface

A poisoned artifact, or a hostile pull request, can carry text engineered to
steer the consuming agent away from recorded decisions — for example:

- imperative overrides ("ignore the previous instructions…"),
- impersonation of system / agent / tool instructions,
- text that argues the agent should disregard a recorded decision.

Because the agent ingests artifact content as grounding, such text is the
primary attack surface — not the server.

## Mitigation

**The mitigation is human PR review.** Nothing is merged — and therefore nothing
becomes trusted grounding — without a human accepting it. Two deterministic,
offline *aids* support that review; neither is a guarantee and neither is a gate:

- **`rac doctor`** flags instruction-like / injection-style content as a
  WARNING for a human to look at (owned by the doctor diagnostic). It is a
  heuristic review aid: it never auto-edits content, never hard-fails a run on
  its own, and makes no claim that flagged content *is* unsafe — only that a
  human should review it.
- **`get_artifact`** surfaces the artifact's reviewed `## Status` under its
  `provenance` object, so a consumer can distinguish a reviewed `Accepted`
  decision from a `Proposed` draft. This is a *reported fact*, not a
  trustworthiness score or a safety verdict.

RAC never sanitizes, rewrites, redacts, or filters artifact content. The
trust boundary stays human PR review (ADR-065); the aids inform that review,
they do not replace it.

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub's **"Report a
vulnerability"** flow on this repository's **Security** tab (private security
advisories). Please do not open a public issue for a security report. This is
the report channel; it does not carry a response-time commitment.
