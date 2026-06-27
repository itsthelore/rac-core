# Security posture

RAC is **offline by design**. The `rac` CLI and the editor extension model
product knowledge from local Markdown files and emit local files and exit codes;
they make no network calls and send no telemetry. This document records that
posture as a control a security office can verify and sign — not a marketing
claim — and points at the artifacts that prove it.

The posture is self-attestable: it is backed by the package's own deterministic
behaviour, a committed SBOM, and a runnable network-isolation test. It is **not**
a hosted service or a third-party certification (see [Scope](#scope-and-non-goals)).

## The no-egress guarantee

- **No network access.** `rac` reads and writes the local filesystem only. None
  of its analysis paths — validation, relationships, review, the unified gate,
  search, and export — open a socket. This is enforced as an architectural
  invariant ([ADR-002](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-002-ai-optional.md)):
  RAC is deterministic and AI-optional, so the core never depends on a remote
  call.
- **No telemetry by default; provably off for regulated installs.** RAC collects
  no usage analytics in its default operation. The one optional exception is a
  consent-gated, content-free anonymous daily ping from the MCP server — a random
  install id, the version, and an active-repo count, never paths, queries, or
  content ([ADR-041](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-041-anonymous-usage-ping.md)) —
  which stays off unless you opt in. A regulated install can prove it stays off at
  runtime with `rac telemetry off --enterprise`: a tamper-evident hard-lock that
  forces the ping off and refuses re-enabling until explicitly unlocked
  ([ADR-086](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-086-air-gap-and-enterprise-telemetry-lock.md)).
  AI-assisted authoring is opt-in and bring-your-own-credentials
  ([ADR-035](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-035-byo-ai-credentials.md));
  nothing phones home on your behalf.
- **Optional read-access audit, local-only.** Regulated installs can record who
  consulted which decision over the MCP server — query and returned artifact IDs,
  never bodies — by enabling an `audit:` stanza in `.rac/config.yaml`
  ([ADR-084](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-084-read-access-audit-recorder.md)).
  It is off by default (responses stay byte-identical without it) and the engine
  never transmits it: the log is a local file, and shipping it to a sink is a
  separate collector's job. It is a strict addition to the no-egress posture, not
  an exception to it.
- **Deterministic, local-only data flow.** The same corpus state yields
  byte-identical JSON and SARIF output, with no timestamps and stable ordering
  (ADR-002). Nothing leaves the machine: input is local Markdown, output is local
  text and an exit code.

## Data flow

```
local Markdown (rac/)  ->  rac (pure, in-process analysis)  ->  local output
                                                                 (stdout: human / JSON / SARIF,
                                                                  files, exit code)
```

There is no intermediate service, no upload, and no callback. A CI gate uploads
SARIF to *your* GitHub Code Scanning from *your* runner — that egress is your
CI's, configured by you, not RAC's.

## Dependency surface

RAC declares three runtime dependencies (`pyproject.toml`, `[project].dependencies`):

| Dependency | Purpose |
| --- | --- |
| `markdown-it-py` | Markdown parsing (the artifact source format). |
| `pyyaml` | Frontmatter and `.rac/config.yaml` parsing. |
| `mcp` | The optional Model Context Protocol server surface. |

The full, machine-readable dependency list — including resolved versions — is the
committed [`sbom.json`](https://github.com/itsthelore/rac-core/blob/main/sbom.json)
at the repository root.

## How to verify

You can re-derive every part of this posture yourself, offline:

- **SBOM.** Regenerate and diff the Bill of Materials:

  ```bash
  python scripts/generate_sbom.py --stdout
  ```

  It emits a deterministic [CycloneDX 1.5](https://cyclonedx.org/) JSON document
  for the package and its runtime dependencies (no timestamps, stable ordering).
  `tests/test_sbom.py` guards the committed `sbom.json` against drift from the
  declared dependencies, so the SBOM can never silently fall behind.

- **No-egress test.** Run the network-isolation test, which patches
  `socket.socket` / `socket.create_connection` to raise on use, then exercises
  validation, relationships, review, the gate, search, and export over a fixture
  corpus — failing if any path attempts a socket:

  ```bash
  python -m pytest tests/test_no_egress.py -q
  ```

  This is the runnable control backing the no-egress claim.

- **Audit the dependency tree.** The three runtime dependencies above are the
  entire surface; there is no transitive network client in RAC's own code.

## Scope and non-goals

This posture is **self-attestable and offline-first**. It deliberately does not
include:

- a hosted control plane or any server-side component;
- per-user analytics or usage tracking;
- a third-party security certification.

The guarantee is that RAC runs locally with no egress and no telemetry, and that
this is verifiable from the repository. Anything beyond a self-attestable,
offline posture is out of scope for the project (v0.21.14 Non-Goals).

## See also

- [Governance](governance.md) — the `enforcement:` policy and `rac gate`.
- [Validation](validation.md) — the write-time gate and SARIF output.
- [ADR-002](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-002-ai-optional.md) — deterministic, AI-optional core.
- [ADR-035](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-035-byo-ai-credentials.md) — bring-your-own AI credentials.
- [ADR-041](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-041-anonymous-usage-ping.md) — the consent-gated, content-free anonymous ping.
- [ADR-084](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-084-read-access-audit-recorder.md) — the local-only, default-off read-access audit log.
- [ADR-086](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-086-air-gap-and-enterprise-telemetry-lock.md) — air-gap posture and the enterprise telemetry hard-lock.
