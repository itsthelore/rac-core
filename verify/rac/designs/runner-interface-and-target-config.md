---
schema_version: 1
id: LV-KVW5PZK15VXM
type: design
---
# Runner Interface and Target Configuration

## Status

Proposed

Exploratory — the *how* for LV-ADR-002 (the pluggable runner) and the
target-agnostic property `faithful-session-to-test` REQ-003 requires. It fixes the
shapes LV-ADR-002 committed to behaviorally — the runner's inputs, the target
config, and the sandbox/credential handling the threat model (LV-ADR-003) demands.

## Context

LV-ADR-002 decided the test runner is a pluggable interface (local runner ships
open; a hosted VM-fabric runner is a drop-in backend) and that target + OS are
*injected*, never compiled into a test. `faithful-session-to-test` REQ-003 makes
target-agnosticism the property v0.2.0 must prove. Neither specifies the *shape* of
those inputs, and the security-sensitive parts (how an auth strategy is
represented, how secrets are referenced without being committed, how the terminal
is sandboxed) were left to improvisation — which LV-ADR-003 forbids. This design
fixes them.

## User Need

- A **developer** wants to declare their targets (dev, prod) and run the same
  compiled test against any of them by selecting a target, not by editing the test.
- The **runner** (local now, hosted later) needs a stable input contract so a
  compiled test runs identically across backends.
- **Security** (LV-ADR-003) needs auth/secret handling and terminal sandboxing to
  be specified, not ad hoc.

## Design

### Runner interface

A runner is the single execution seam (LV-ADR-002). Its input is a
`RunRequest`-shaped value:

```
RunRequest {
  test:        <compiled test reference>      // what to run
  target:      ResolvedTarget                 // where (baseURL + auth + safety)
  platform:    { os, browser }                // matrix selection
  capture:     { trace: true, video: bool }   // evidence to emit (redacted)
}
=> RunResult { status, redacted_trace_ref, blocked_actions[], summary }
```

The local runner runs Playwright on the host; the hosted runner satisfies the same
shape against a VM fabric. A compiled test references `RunRequest.target.baseURL`
and the injected auth; it contains **no** hardcoded host, credential, or OS.

### Target configuration

Targets are declared in a config file (e.g. `verify.targets.toml` / `.yaml`) in the
consuming repo, never in a test:

```toml
[targets.dev]
base_url   = "http://localhost:3000"
auth       = { strategy = "login-script", ref = "scripts/login-dev.ts" }
seedable   = true

[targets.prod]
base_url   = "https://app.example.com"
auth       = { strategy = "token", ref = "env:PROD_VERIFY_TOKEN" }
seedable   = false                 # => write-blocked by production-target-safety
allow_mutations = []               # explicit per-action allowlist (default empty)
```

- **`base_url`** is the injected `baseURL`.
- **`auth.strategy`** is one of a small set — `token` / `cookie` / `oauth` /
  `login-script` — and **`auth.ref`** is an *indirect* reference to the secret
  (`env:NAME`, a secret-store key, or a script path), **never the secret value**
  (`evidence-redaction-and-secret-hygiene` REQ-003/REQ-004).
- **`seedable`** drives `production-target-safety`: absent or `false` ⇒ the target
  is write-blocked and Run refuses mutating tests; `allow_mutations` is the explicit
  per-action escape hatch (default empty, fail-closed).

### Auth-strategy resolution

At run time the runner resolves `auth.ref` from the environment / secret store /
script into a live credential, injects it into the browser/terminal session, and
**never** lets it reach a trace, test, or log (redaction, LV-ADR-003). The resolved
credential lives only in the runner's process for the run's duration.

### Terminal sandbox contract (LV-ADR-003)

Drive's terminal runs in an isolated environment with an explicit, fail-closed
grant:

- a confined working directory (the project under test), **not** the developer's
  home or unrelated repos;
- explicit network egress scope (the target and what the test needs), not ambient;
- no ambient access to credential stores or SSH keys;
- target-derived content cannot expand the grant (prompt-injection containment).

Absent an explicit grant, an action is **denied**. The local runner implements this
with OS/container sandboxing; the hosted runner inherits the same contract on the
VM fabric.

## Constraints

- **Injection, not compilation** (LV-ADR-002, `faithful-session-to-test` REQ-003):
  target/OS/auth are inputs; the compiled test is target-agnostic.
- **Secrets by reference only** (`evidence-redaction-and-secret-hygiene`):
  `auth.ref` is indirect; no secret value in config, test, or trace.
- **Fail-closed safety** (`production-target-safety`): non-seedable ⇒ write-blocked;
  mutations require explicit allowlist.
- **One interface, two backends** (LV-ADR-002): local and hosted satisfy the same
  `RunRequest`/`RunResult` shape.
- **Sandbox is fail-closed** (LV-ADR-003): default-deny terminal authority.

## Rationale

Declaring targets as config with indirect secret refs is what makes a single
compiled test portable *and* safe — the test never sees a host or a secret, the
runner injects both. Folding `seedable`/`allow_mutations` into the same target
config makes prod-safety a property of *configuration the human controls*
(consistent with the human-trust boundary, RAC ADR-065) rather than agent judgement.
A single `RunRequest`/`RunResult` shape is the concrete form of LV-ADR-002's "one
interface, two backends," so hosting stays a drop-in.

## Alternatives

- **Per-test target/auth literals.** Rejected: breaks portability and embeds
  secrets (LV-ADR-002, redaction requirement).
- **A single shared credential per environment with broad scope.** Rejected:
  violates least-privilege (LV-ADR-003); credentials are scoped per target.
- **Infer seedability / safety from the URL or agent judgement.** Rejected by
  `production-target-safety`: safety must be declared and fail-closed, not inferred.
- **No terminal sandbox (trust the agent).** Rejected by LV-ADR-003: an
  unsandboxed shell with credentials is the core risk the threat model bounds.

## Open Questions

- The config file format and exact key set (TOML vs YAML; the above is indicative).
- How the OS/browser matrix is expressed in config vs at invocation.
- Whether the hosted runner needs additional `RunRequest` fields (region, VM image)
  and how those stay additive to the shared shape.

## Related Decisions

- lv-adr-002-pluggable-runner
- lv-adr-003-runtime-threat-model

## Related Requirements

- faithful-session-to-test
- production-target-safety
- evidence-redaction-and-secret-hygiene
