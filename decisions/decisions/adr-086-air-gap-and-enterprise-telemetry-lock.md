---
schema_version: 1
id: RAC-KW47GFBHK31W
type: decision
---
# ADR-086: Air-Gap Posture and Enterprise Telemetry Hard-Lock

## Status

Accepted

## Category

Product

## Context

The first item on a regulated firm's checklist for any AI-adjacent tool is "does
this exfiltrate our source to a public API?" Lore's answer is "no, by design" —
but only if the docs say so prominently and the telemetry path can be provably
switched off.

The stance already exists; it is just scattered. ADR-002 makes AI optional and
the engine offline; ADR-035 keeps inference on user-managed credentials with no
RAC cloud dependency; ADR-066 keeps the grounding eval embedding-free and
LLM-judge-free; ADR-067 makes the agent surface the only integration boundary;
ADR-040 and ADR-041 keep telemetry content-free and fence the only network import
to `mcp/ping.py`. What is missing is a single citable statement and a provable
runtime off-switch: the ping kill switch today is a build-time constant
(`POSTHOG_API_KEY`) that is currently populated, so "it is empty" is not a
runtime guarantee an operator can assert.

## Decision

Record the consolidated air-gap posture as a citable decision, and add a runtime
enterprise lock.

- **The posture, stated once:** the engine makes no LLM calls and no network
  calls except the single, consent-gated, content-free daily ping (ADR-041);
  retrieval and validation are deterministic and offline (ADR-002, ADR-066);
  inference, when used at all, runs on the operator's own credentials (ADR-035);
  the agent surface is the only thing infosec must gate (ADR-067). This ADR is
  the canonical reference the docs (README, SECURITY) point to.
- **`rac telemetry off --enterprise`** forces the kill state at runtime. Because
  `POSTHOG_API_KEY` is populated, this is a runtime force, not an assertion over
  an empty constant: it unconditionally disables the ping, writes a persistent
  enterprise-lock to the telemetry config, and `rac telemetry status` reports
  "locked (enterprise)". While locked, `rac telemetry on` refuses.
- **Reversibility is explicit and tamper-evident.** The lock is removed only by a
  documented action (`rac telemetry off --enterprise --unlock`, or deleting the
  lock file), and `status` always shows the current lock state. It is never a
  silent toggle.
- The lock governs the anonymous ping only; the local audit recorder (ADR-084)
  is a separate, separately-governed capability and is unaffected.

## Consequences

### Positive

- The procurement question has a one-line, citable answer backed by an ADR id
  and a provable runtime switch.
- The lock decouples the operator's guarantee from a build-time constant: an
  enterprise can prove the ping is off on their machines regardless of how the
  package was built.

### Negative

- A new flag and a persistent lock file add a small surface to the telemetry
  command and its tests.
- "Locked unless explicitly unlocked" is slightly more to explain than a single
  empty constant.

### Risks

- The lock is mistaken for the whole air-gap story. Mitigation: the posture
  statement is the citable core; the lock is one provable control within it.
- An operator expects the lock to also gag the audit recorder. Mitigation: the
  decision states the scope explicitly; the recorder is default-absent anyway
  (ADR-084).

## Alternatives Considered

### Leave the stance scattered across ADRs and READMEs

Do nothing new; rely on the existing decisions.

#### Disadvantages

- An infosec reviewer cannot cite "no exfiltration by design" from one place, and
  cannot prove the ping is off at runtime. The checklist stalls.

### A fully one-way, irreversible lock

Once enterprise-locked, never reversible by the CLI.

#### Disadvantages

- Too brittle for legitimate configuration changes (a machine repurposed out of
  the regulated estate); an explicit, documented, tamper-evident unlock is
  honest without being a foot-gun.

The consolidated posture plus a reversible-by-explicit-action runtime lock is
selected.

## Relationship to Other Decisions

- ADR-040, ADR-041: the lock forces the kill state the ping's design already
  allows; the content-free guarantee is unchanged.
- ADR-002, ADR-035, ADR-066, ADR-067: the posture this ADR consolidates and makes
  citable.
- ADR-084: the audit recorder is out of scope of the lock; named here to prevent
  confusion.
- ADR-085: an instance of the rule — a provable control delivered as
  configuration, for everyone, not a mode.

## Related Requirements

- rac-trust-transparency
