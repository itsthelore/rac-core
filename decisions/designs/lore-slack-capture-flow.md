---
schema_version: 1
id: RAC-KVSV66Z4X71Z
type: design
---
# Lore Slack Capture Flow

## Status

Proposed

Exploratory — this records the reasoning from a research pass into the Slack
ingest path so it lives in the corpus, not a tool's scratch space (ADR-047). It
is not an accepted build. It deepens **Host C** of `lore-capture-surfaces` into a
worked, end-to-end pipeline, and answers one question precisely: when Slack is the
ingest point, how does captured knowledge get *written* and *approved by a human*.

## Context

`lore-capture-surfaces` named four hosts for the capture core and flagged the
Slack bot (Host C) as the most operationally complex — a hosted, multi-tenant
service that crosses a data-governance boundary. This design works that host out
in detail. The motivating question is the one a reviewer asks first: *who approves
what gets recorded, and where does that approval actually happen?*

The research lands on a single load-bearing finding: **"approval" is two distinct
gates, on two different actors, in two different systems.** Conflating them is the
classic mistake, because the author confirming their own capture is not, in any
governance sense, a control. The corpus already encodes the right boundary —
ADR-065 makes human pull-request review the trust boundary — so this design mostly
shows how a Slack flow *respects* recorded decisions rather than inventing new
ones: ADR-065 (PR review is the trust boundary), ADR-017 (attribution is history,
not work), ADR-035 (user-managed AI credentials), and ADR-002 / ADR-067 (no AI in
the engine).

A claim convention note: load-bearing operational facts below are drawn from
primary Slack and GitHub documentation and from established security guidance
(separation of duties / four-eyes — NIST AC-5, OWASP, SLSA two-party review).
Fast-moving areas (Slack's AI/assistant and Workflow Builder surfaces) are flagged
where they appear.

## User Need

Three roles meet in this flow:

- **The author** — someone in a Slack thread who has just made or recorded a
  decision and wants it captured, without leaving Slack, learning Markdown, or
  touching git.
- **The maintainer** — who must be able to judge whether the proposed artifact
  faithfully reflects what was decided, and ratify it into the trusted record.
- **The admin** — who governs whether thread content may cross to an external
  model at all, and needs the data flow disclosed.

The need is to get a faithful, reviewable artifact out of a conversation **without
letting the person who said it be the one who admits it to the record.**

## Design

### The pipeline, end to end

1. **Trigger (capture).** A **message shortcut** ("Save as decision") or a slash
   command starts the flow. Slack hands the app a `trigger_id` (usable for ~3
   seconds to open a modal) plus the message's `channel` and `ts`.

2. **Interview (structure).** Because Block Kit **modals cap at 100 blocks and a
   three-view stack**, a genuine multi-turn interview belongs in the
   **assistant-thread** surface (`assistant.threads.*`), not a single modal; a
   light capture can use a modal form. Either way: capture the raw text first,
   then ask two-to-four pre-filled confirmation questions. The model runs in the
   **host**, never the engine (ADR-002, ADR-067), through a user-configured
   gateway (ADR-035). *(Slack's assistant APIs are fast-moving — treat that
   surface as version-sensitive.)*

3. **Acknowledge in 3 s, then work async — and stay idempotent.** Slack requires
   an HTTP 200 within **3 seconds**, but an LLM call plus a git write will not
   finish that fast, so the endpoint **acks immediately and processes on a
   worker**. The Events API is **at-least-once** with a **three-retry storm**
   (immediate, ~1 min, ~5 min) carrying `X-Slack-Retry-Num`, so the worker must
   **dedup on the event's `event_id`** (a store with a TTL longer than the retry
   window). Dedup alone does not make the *write* idempotent: derive a
   deterministic artifact id/filename from `(channel, ts)` so reprocessing
   updates in place, and rely on the GitHub Contents API's `sha` precondition to
   return a 409 conflict rather than silently creating a divergent second
   artifact.

4. **Gate 1 — the author confirms (fidelity, *not* a trust boundary).** In Slack,
   a `primary` **Approve** and a `danger` **Reject** button (optionally a
   `confirm` dialog), or a modal submit. The interaction payload's `user`
   identifies who clicked. This gate answers *"did we capture what you meant"* —
   a **data-quality** check. It is **not** a trust boundary, and crucially
   **Slack does not enforce four-eyes**: the app sees `user.id` but nothing stops
   the author approving their own capture, so this gate must never be treated as
   ratification.

5. **Write — a draft pull request.** The app writes through a **GitHub App**: it
   mints a short-lived (≈1 hour) **installation access token** scoped to the repo,
   acting as its own bot identity, with **least privilege — only `contents:write`
   + `pull_requests:write` + `metadata:read`** (avoiding `.github/workflows` so no
   `workflows` permission is needed). The sequence is *get base ref → create a
   branch → write the artifact file → open a `draft: true` pull request*. The PR
   body links the **`chat.getPermalink`** back to the originating thread as
   provenance, and credits the human author with a `Co-authored-by:` trailer. Two
   hard rules from the research: the bot **must not hold approval power**, and it
   **must not be on a ruleset bypass list** — because a GitHub App's own review
   *can* satisfy required reviews if it has write/admin, which would silently
   defeat the gate (the self-approval footgun).

6. **Gate 2 — an independent maintainer reviews and merges (the trust boundary).**
   This is where ADR-065 actually lives. Branch protection requires an approving
   review **from someone other than the author/last pusher**, with **CODEOWNERS**
   *combined with* that not-the-author rule (CODEOWNERS alone is self-satisfiable
   if the author is an owner), **dismiss-stale-approvals** on new commits, and a
   **required status check running `rac validate` / `rac relationships
   --validate`** so nothing invalid can merge. The reviewer follows the Slack
   permalink to judge fidelity, then merges — and only then does the artifact
   enter the trusted, agent-grounding corpus.

7. **Audit.** Traceability assembles from **four independent records across two
   systems**: the Slack permalink (source), the Slack click log (who captured /
   confirmed), the GitHub PR review (who ratified), and the signed commit history
   (the merge). Because they live in different systems, forging the chain requires
   cross-system collusion.

8. **Governance.** Slack's strong privacy guarantees are **first-party only** —
   the moment thread content is sent to an external model it leaves Slack's trust
   boundary, and that assurance becomes the operator's to provide. The mitigations
   are the BYO-gateway posture ADR-035 already mandates: route inference through a
   user-controlled OpenAI-compatible endpoint (a self-hosted LiteLLM proxy or a
   local model), retention/telemetry off (a config choice, not a default),
   region-pinned; **store metadata and the permalink, not the raw transcript**;
   and treat thread content as untrusted input (prompt injection), which is the
   same posture ADR-065 already takes. Slack Marketplace / Enterprise-Grid add
   disclosure, least-privilege scopes, TLS 1.2+, and request-signature
   verification, and admins can gate the app.

### The spine

The whole pipeline reduces to one rule: **the bot proposes, an independent human
disposes.** Gate 1 makes the capture faithful; Gate 2 makes it trusted; the two
are deliberately different people, checks, and systems.

## Constraints

- **The trust boundary is human PR review (ADR-065).** Admission to the corpus
  happens only at an independent maintainer's merge — never at the author's Slack
  confirmation, and never by the writer bot.
- **No AI in the engine (ADR-002, ADR-067); credentials are user-managed
  (ADR-035).** The interview model and any classification run in the host, behind
  a configurable OpenAI-compatible gateway with retention off.
- **Attribution is history, not work (ADR-017).** Record who captured and who
  approved (identity + timestamp + permalink) as provenance; never add owner,
  assignee, sprint, or due-date fields.
- **Not a content store (ADR-024).** Persist the permalink and the resulting
  artifact in git; do not store raw Slack transcripts.
- **Thin client over the contract (ADR-063).** The bot drives the `rac` CLI / Git
  + GitHub APIs; it adds nothing to `rac-core`.
- **Installed surface is a `lore-*` product (ADR-068).** The Slack app is
  Lore-brand, hosted separately from the engine.
- **Operational invariants.** Ack < 3 s then process async; dedup on `event_id`;
  idempotent write keyed on `(channel, ts)` with the Contents API `sha` guard; the
  writer bot has least-privilege scopes, no approval power, and no ruleset bypass.

## Rationale

The two-gate model is forced by security first principles, not preference.
Separation of duties (NIST SP 800-53 AC-5), the four-eyes / two-person rule, OWASP
secure-SDLC ("reviewed by individuals other than the originating author"), and
SLSA's source track ("the uploader and reviewer are two different trusted
persons") all say the same thing: an actor who originates a change cannot also be
the control that authorizes it. The author's Slack confirmation can only attest
*intent* ("you transcribed me correctly"); it provides no independent assurance of
*validity* ("this should enter the record"). Treating it as the trust boundary is
functionally self-approval, which the literature classifies as the *absence* of a
control rather than a weak one.

Opening the capture as a **draft PR** is precisely what lets GitHub's platform
machinery — required reviews, not-the-author, CODEOWNERS, dismiss-stale, required
status checks — apply; writing straight to the trusted branch would bypass all of
it. Least-privilege GitHub-App tokens (short-lived, own identity, repo-scoped) make
the writer auditable and revocable, and withholding approval power from the bot is
what stops the self-approval footgun. The permalink is not decoration: per the
provenance principle, the independent reviewer cannot judge fidelity without access
to the source the artifact claims to capture.

The trade-off accepted: this host carries real operational and governance weight
(a hosted service, a GitHub App, a model boundary crossing) — justified because
Slack is where many decisions are actually made and never recorded, and this is
the path that captures them without weakening the trust boundary.

## Alternatives

- **Single gate — the author confirms in Slack and it lands — rejected.** That is
  self-approval; it satisfies no separation-of-duties requirement and admits
  unreviewed content to the record.
- **Bot writes straight to the trusted branch — rejected.** It bypasses every
  required-review control; the draft PR is the mechanism that makes capture a
  *reviewable proposal*.
- **Give the writer bot approval / merge power (or a ruleset bypass) — rejected.**
  A GitHub App review can satisfy required reviews if it has write/admin, silently
  defeating Gate 2; the writer must only ever *open* the PR.
- **Store the raw Slack transcript in the artifact — rejected.** It violates "not
  a content store" (ADR-024) and Slack's "store metadata, not data" guidance;
  persist the permalink and the structured artifact instead.
- **Inherit Slack's privacy guarantees for the external model call — rejected as
  unsound.** Those guarantees are first-party; a third-party export must provide
  its own (BYO-gateway, retention off, disclosure).

## Accessibility

- **Provenance legibility.** Every artifact carries a working link back to the
  Slack thread it came from, so a reviewer (or a later reader) can always reach
  the source; a draft is clearly marked *proposed* until merged.
- **Keyboard-first by construction.** The Slack surfaces (buttons, modals, threads)
  are natively keyboard- and screen-reader-operable; confirmations should state who
  approved and what happened in text, not colour alone.
- **Plain-language interview.** Questions are essential-only and pre-filled, so a
  non-technical author is never shown schema jargon or empty required fields.

## Style Guidance

- The Slack app is a `lore-*` product (ADR-068); the engine stays `rac-*`.
- Keep the two gates verbally distinct: the author *confirms* (fidelity); an
  independent maintainer *approves/ratifies* (trust boundary). Never call the
  Slack confirmation an approval of the record.
- Cite load-bearing operational facts in prose with their source and carry the
  caveat; flag the fast-moving Slack AI/Workflow-Builder surfaces rather than
  asserting frozen behaviour.

## Open Questions

- Interview surface: the richer **assistant-thread** (more capability, more
  version risk) versus a **capped modal** (simpler, shallower) — which clears a
  typical Enterprise-Grid admin review?
- **Permalink durability**: a permalink breaks if the source message is deleted or
  expires under a retention policy; what is recorded so provenance survives the
  source?
- The exact **idempotency key** and dedup TTL, and how a same-thread re-capture
  updates rather than duplicates.
- The **Enterprise-Grid admin posture**: what disclosures and scopes clear app
  approval for an app that exports message content to a model.

## Related Decisions

- ADR-002
- ADR-017
- ADR-024
- ADR-035
- ADR-063
- ADR-065
- ADR-067
- ADR-068

## Related Roadmaps

- rac-capture-skill
- lore-capture-followups
