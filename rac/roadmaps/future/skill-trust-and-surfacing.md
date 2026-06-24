---
schema_version: 1
id: RAC-KVTP8K78NM4E
type: roadmap
---
# RAC — Skill Trust and Surfacing (Future)

## Status

Planned

Unscheduled — captured for future consideration from the agent-runtime deep dive
(OpenClaw, Hermes, GBrain). Nothing here is committed; it graduates out of
`future/` into a versioned series if a concrete need (notably third-party skills)
appears.

## Context

Lore ships agent skills (`rac skill install` / `list`), bundled first-party and
kept byte-identical to the dogfood copies. The deep dive into agent runtimes
surfaced a cluster of *skill-surface* patterns Lore does not have, all
deterministic and AI-free:

- **OpenClaw** has mature skill packaging — `openclaw skills verify` (a trust
  envelope + security scan), a fail-closed `security.installPolicy`, declarative
  static gating (`requires.bins/anyBins/env/config`, `os`, `always`), and a public
  registry with `install @owner/slug` resolution.
- **Hermes** retrieves skills by *progressive disclosure* (`skills_list` →
  `skill_view`) and has an open issue to replace a ~4.5k-token skill broadcast with
  ranked/pinned retrieval — a token-budget lesson.
- **GBrain** validates its skill tree for reachability and non-overlap
  (`check-resolvable`, MECE/DRY).

These matter most if Lore ever distributes or accepts **third-party** skills,
where "is this skill safe and supported here?" becomes a real question. They sit
naturally on Lore's existing boundaries: skill/artifact content is untrusted until
human review (ADR-065), the engine stays deterministic and offline (ADR-002), and
tool/skill surfaces respect a response budget (ADR-033).

## Outcomes

- A distributed skill can be **verified before install** — a deterministic trust
  envelope and security scan, with a fail-closed install policy — so a stranger's
  skill is checked, not trusted (ADR-065).
- A skill declares its **environment requirements statically** (binaries, env,
  config, OS), so an unsupported skill is gated deterministically rather than
  failing at run time.
- Skill metadata is **surfaced to clients within a token budget** (ranked/limited),
  not broadcast wholesale (ADR-033).

## Initiatives

### Initiative 1 — Skill verification and fail-closed install policy

A `rac skill verify` that statically inspects a skill package (structure, declared
capabilities, injection-style content) and a configurable fail-closed install
policy, mirroring OpenClaw's `verify` + `installPolicy`. This is the
untrusted-content boundary of ADR-065 applied to skills; when scheduled it needs a
skill-trust-boundary ADR.

### Initiative 2 — Declarative static gating manifest

A skill manifest gains optional deterministic gating — `requires` (binaries, env
vars, config keys) and `os` — evaluated statically so `rac skill install`/`list`
can mark a skill supported or unsupported on this machine without running it.

### Initiative 3 — Optional skills registry and slug install

A content-addressed skill index with `install <owner>/<slug>` resolution. Gated on
a product decision to support third-party skills at all — today Lore bundles
first-party skills only, so this is the most speculative initiative and is recorded
as a fork, not a commitment.

### Initiative 4 — Token-budgeted skill surfacing

When skill metadata is surfaced to a client, rank and limit it to a budget rather
than broadcasting the full set (Hermes' progressive-disclosure lesson; ADR-033).

### Initiative 5 — Skill-tree resolvability check

A deterministic validation that the installed skill set is reachable and
non-overlapping (GBrain's `check-resolvable`), so skills do not silently shadow one
another.

## Constraints

- Deterministic and offline (ADR-002): verification, gating, and surfacing are
  static checks; no model, no network, no execution of the skill.
- Untrusted by default (ADR-065): verification informs a human; nothing is trusted
  because it passed a scan.
- The read-only knowledge engine and its MCP surface are unaffected; this concerns
  the skill-distribution surface only.

## Non-Goals

- Executing or sandboxing skills at runtime (that is the agent client's job).
- Any AI-judged skill quality or auto-generated skills.
- Committing to third-party skill distribution before the product decision is made.

## Success Measures

- A skill from outside the package can be inspected and either cleared or rejected
  by a deterministic policy before anything is installed.
- An unsupported skill (missing a required binary) is reported as unsupported by a
  static check, not by a runtime failure.
- Surfacing a large skill set to a client stays within a stated token budget.

## Assumptions

- Third-party or distributed skills are a plausible future direction; until then
  these patterns are dormant intent, correctly unscheduled.
- Static verification and gating are high-value precisely because they need no AI
  and no execution.

## Risks

- Building verification before any third-party skills exist would be speculative.
  Mitigation: this stays in `future/` until a concrete distribution need appears.
- A trust envelope could imply safety it cannot guarantee. Mitigation: framed as an
  input to human review (ADR-065), never an automatic trust grant.

## Related Decisions

- adr-065
- adr-002
- adr-033
