---
schema_version: 1
id: RAC-KVTS86ZGVJV7
type: decision
---
# ADR-077: The Two-Gate Capture Write Model

## Status

Accepted

## Category

Architecture

## Context

Lore's capture surfaces turn a person's input into an artifact and write it to
the repository. The first of these — the `rac-capture` skill — has shipped, and
the `lore-capture-surfaces` design names more to come (a desktop overlay, a Slack
bot, a web modal). Each crosses the same threshold: a surface takes knowledge
from an author and proposes it for the corpus.

ADR-065 already names the corpus-wide trust boundary — artifact content is
untrusted until a human accepts it through pull-request review — but it does not
say *who* performs that review relative to *who authored the change*, which is the
question a capture flow makes acute. A capture surface has a natural temptation to
treat the author's own confirmation ("yes, that is what I meant") as enough to
land the artifact. Security and change-management practice is unambiguous that an
actor who originates a change cannot also be the control that authorizes it:
separation of duties (NIST SP 800-53 AC-5), the four-eyes / two-person rule, OWASP
secure-SDLC guidance that changes be "reviewed by individuals other than the
originating author," and SLSA's source track, which requires that "the uploader
and reviewer are two different trusted persons." The platforms a capture host runs
on do not enforce this for us — Slack, for instance, surfaces who clicked but does
nothing to stop an author approving their own request.

## Decision

A capture surface uses **two distinct gates, on two different actors**:

- **Gate 1 — fidelity.** The author confirms, in the host, that the surface
  captured what they meant. This is a data-quality check; it is **not** a trust
  boundary and confers no authority to enter the record. A host must not rely on
  the host platform to enforce independence at this gate.
- **Gate 2 — the trust boundary.** An **independent** maintainer reviews and
  merges the pull request. This is the trust boundary, extending ADR-065 to the
  capture path, and it is enforced by the platform's required-review controls
  together with a "someone other than the author/last pusher" rule.

**Corollary:** a capture host or bot only *proposes* — it opens a draft pull
request — and never holds approval or merge power, and is never placed on a
review-bypass list.

## Consequences

Capture stays low-friction (a draft can be committed freely) while the record
stays trustworthy (an independent merge admits it), and the model is uniform
across every capture host, composing with existing branch-protection machinery
rather than inventing an approval system.

The trade-offs accepted: capture can never simply *land* an artifact — there is
always a human merge step by someone other than the author. The guarantee is
procedural, so a project that does not actually require independent review
inherits no protection. And the "someone other than the author" rule must be set
explicitly: required reviews plus the not-the-author setting, because CODEOWNERS
alone is self-satisfiable when the author is themselves a listed owner, and a
GitHub App's own review can satisfy a required review if the app holds
write/admin — so the writer must never be granted that standing.

## Alternatives Considered

### Single gate — the author confirms and it lands

Treat the in-host confirmation as sufficient to write to the record. Rejected:
this is self-approval, which the separation-of-duties literature classifies as the
*absence* of a control, not a weak one.

### The writer writes straight to the trusted branch

Skip the pull request and commit directly. Rejected: it bypasses every
required-review control. The draft PR is precisely the mechanism that turns a
capture into a *reviewable proposal*.

### Give the writer bot approval or merge power

Let the capture bot approve or merge its own proposal. Rejected: a bot review can
satisfy a required review when the app has write/admin, silently defeating Gate 2;
the writer must only ever open the PR.

## Related Decisions

- ADR-017
- ADR-065
- ADR-067

## Related Designs

- lore-capture-surfaces
- lore-slack-capture-flow
