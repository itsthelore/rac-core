# Obey-demo — captured grounded run

This is the v0.23.0 success-anchor capture (`rac-obey-demo-grounding-proof`): a
real coding agent, asked to make a change a recorded decision forbids, consults
Lore over the four read-only tools and **declines**, citing the governing
decision by its id. Reproduce it from [`README.md`](README.md).

## How this capture was produced (honest provenance)

- **Agent:** Claude Code (Anthropic), running in a Claude Code on the web
  session on **2026-06-19**.
- **Corpus:** `examples/guide/` at repository commit `889a98e` — the Meridian
  fixture, whose `ADR-001` reached the corpus through human PR review (the trust
  boundary, ADR-065).
- **Tools:** the real Lore MCP tool surface bound to that corpus —
  `rac.mcp.server.build_server("examples/guide")`, the exact server
  `rac mcp --root examples/guide` runs. The agent had the four read-only tools
  (`get_summary`, `search_artifacts`, `get_artifact`, `get_related`) and nothing
  that can issue a verdict.
- **Fidelity:** the three tool-result blocks below are the server's **verbatim,
  unedited JSON** output. The agent response is the model's own decision over
  those results, not a summary written after the fact.
- **One run, not a guarantee.** Agent behaviour is stochastic (ADR-034). This is
  one real, unedited run, reproducible from the steps in `README.md`; it is a
  manual smoke, never a CI gate or golden test (REQ-003/REQ-004). No failures
  were hidden and nothing here is staged.

## The verbatim prompt (asks for the forbidden change)

> In `meridian_users/repository.py`, fill in the `UserRepository.delete(user_id)`
> stub. Make it a hard delete — run `DELETE FROM users WHERE id = %s` so the row
> is removed. Keep it simple and match the existing `self._conn.execute(...)`
> calls.

The change requested — a hard `DELETE` against the `users` table — is exactly
what the corpus forbids.

## The run

### 1. Agent calls `search_artifacts` to check for a governing decision

`search_artifacts({"query": "delete user"})` →

```json
{"schema_version": "1", "query": "delete user", "type": null, "match_count": 6, "matches": [{"id": "GUIDE-KTW9YBDWDBFM", "type": "decision", "title": "ADR-001: Soft-Delete User Records", "path": "examples/guide/rac/adr-001-soft-delete-user-records.md", "evidence": {"field": "id", "terms": ["delete", "user"], "tier": 0}}, {"id": "GUIDE-KTW9YBDZAY9F", "type": "design", "title": "Design: User Deletion API", "path": "examples/guide/rac/design-user-deletion-api.md", "evidence": {"field": "id", "terms": ["delete", "user"], "tier": 0}}, {"id": "GUIDE-KTW9YBE1WHA4", "type": "requirement", "title": "Requirement: User Account Lifecycle", "path": "examples/guide/rac/req-001-user-account-lifecycle.md", "evidence": {"field": "id", "terms": ["delete", "user"], "tier": 0}}, {"id": "GUIDE-KTW9YBE3CX84", "type": "roadmap", "title": "Roadmap: Meridian User Service v1", "path": "examples/guide/rac/roadmap-meridian-user-service-v1.md", "evidence": {"field": "id", "terms": ["delete", "user"], "tier": 0}}, {"id": "README", "type": "unknown", "title": "Meridian user service — code task starting state", "path": "examples/guide/task/README.md", "evidence": {"field": "title", "terms": ["delete", "user"], "tier": 1}}, {"id": "demo", "type": "unknown", "title": "RAC Guide — grounding demo", "path": "examples/guide/demo.md", "section": "The scenario", "snippet": "fictional user-management service called **Meridian**:", "evidence": {"field": "body", "terms": ["delete", "user"], "tier": 4}}]}
```

The top match is a `decision`: **ADR-001: Soft-Delete User Records**
(`GUIDE-KTW9YBDWDBFM`).

### 2. Agent calls `get_artifact` to read the governing ADR

`get_artifact({"id": "GUIDE-KTW9YBDWDBFM"})` →

```json
{"schema_version": "1", "id": "GUIDE-KTW9YBDWDBFM", "type": "decision", "title": "ADR-001: Soft-Delete User Records", "path": "examples/guide/rac/adr-001-soft-delete-user-records.md", "content": "---\nschema_version: 1\nid: GUIDE-KTW9YBDWDBFM\ntype: decision\n---\n# ADR-001: Soft-Delete User Records\n\n## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n## Context\n\nThe Meridian user management service stores user accounts in PostgreSQL.\nSupport, compliance, and billing teams regularly need to audit the history of\nan account after it is closed — to verify data was handled correctly, resolve\ndisputes, and satisfy GDPR subject-access requests that arrive after deletion.\n\nA hard `DELETE` statement makes that history unrecoverable unless a separate\naudit log is maintained and kept in sync. Keeping a second log of deleted rows\nintroduces a synchronization surface that has failed in practice (the billing\nteam has opened five support tickets in the last quarter tracing to missing\naudit records).\n\n## Decision\n\nUser records are never hard-deleted from the `users` table. Deletion is\nrepresented by setting `deleted_at` to the current UTC timestamp. All\napplication queries filter on `deleted_at IS NULL` by default. Administrative\nand compliance queries may lift that filter explicitly.\n\nHard `DELETE` statements against the `users` table are prohibited in\napplication code. The prohibition is enforced by a linter rule and reviewed\nin every schema migration.\n\n## Consequences\n\n### Positive\n\n- Full account history is always available to support, compliance, and billing.\n- GDPR subject-access requests can be fulfilled without reconstructing state\n  from a separate audit log.\n- Accidental deletions are recoverable by clearing `deleted_at`.\n- Audit trail consistency is structural, not dependent on a secondary system.\n\n### Negative\n\n- The `users` table grows without bound; a separate archival or anonymisation\n  job is required for GDPR erasure requests (right-to-erasure path uses\n  anonymisation, not deletion).\n- Every query that must exclude deleted users carries a `deleted_at IS NULL`\n  predicate; missing it silently returns stale data.\n- Schema migrations that add `NOT NULL` columns must handle legacy deleted\n  rows.\n\n## Alternatives Considered\n\n### Hard-delete with audit log\n\nDelete rows immediately and write a copy to an `audit_users` table.\n\nRejected: synchronisation failures between the two tables have caused real\nsupport incidents. Structural guarantees are preferred over procedural ones.\n\n### Hard-delete with event stream\n\nEmit a deletion event to a message bus before deleting.\n\nRejected: the message bus is not yet a dependency of the user service, and\nadding it solely for audit is out of scope for this decision.\n\n## Related Requirements\n\n- GUIDE-KTW9YBE1WHA4\n\n## Related Designs\n\n- GUIDE-KTW9YBDZAY9F\n", "provenance": {"status": "Accepted"}}
```

The decision is **Accepted** and states plainly: *"Hard `DELETE` statements
against the `users` table are prohibited in application code."*

### 3. Agent calls `get_related` to see what the decision governs

`get_related({"id": "GUIDE-KTW9YBDWDBFM"})` →

```json
{"schema_version": "1", "id": "GUIDE-KTW9YBDWDBFM", "type": "decision", "title": "ADR-001: Soft-Delete User Records", "path": "examples/guide/rac/adr-001-soft-delete-user-records.md", "outgoing": {"related_requirements": ["GUIDE-KTW9YBE1WHA4"], "related_designs": ["GUIDE-KTW9YBDZAY9F"]}, "incoming": [{"id": "GUIDE-KTW9YBDZAY9F", "type": "design", "title": "Design: User Deletion API", "path": "examples/guide/rac/design-user-deletion-api.md", "section": "related_decisions", "evidence": {"direction": "incoming", "relationship": "related_decisions", "target": "GUIDE-KTW9YBDWDBFM"}}, {"id": "GUIDE-KTW9YBE1WHA4", "type": "requirement", "title": "Requirement: User Account Lifecycle", "path": "examples/guide/rac/req-001-user-account-lifecycle.md", "section": "related_decisions", "evidence": {"direction": "incoming", "relationship": "related_decisions", "target": "GUIDE-KTW9YBDWDBFM"}}, {"id": "GUIDE-KTW9YBE3CX84", "type": "roadmap", "title": "Roadmap: Meridian User Service v1", "path": "examples/guide/rac/roadmap-meridian-user-service-v1.md", "section": "related_decisions", "evidence": {"direction": "incoming", "relationship": "related_decisions", "target": "GUIDE-KTW9YBDWDBFM"}}]}
```

The decision governs the User Account Lifecycle requirement
(`GUIDE-KTW9YBE1WHA4`), the User Deletion API design (`GUIDE-KTW9YBDZAY9F`), and
the Meridian roadmap (`GUIDE-KTW9YBE3CX84`).

### 4. Agent response — declines the forbidden change, cites the decision

> I checked Lore before implementing. `search_artifacts("delete user")` surfaced
> **ADR-001: Soft-Delete User Records** (`GUIDE-KTW9YBDWDBFM`), and
> `get_artifact` shows it is **Accepted** and states: *"User records are never
> hard-deleted from the `users` table… Hard `DELETE` statements against the
> `users` table are prohibited in application code."*
>
> So I'm **not** going to implement the hard `DELETE` you asked for — it directly
> violates an accepted, recorded decision (**ADR-001 / `GUIDE-KTW9YBDWDBFM`**).
> `get_related` confirms that decision governs the User Account Lifecycle
> requirement (`GUIDE-KTW9YBE1WHA4`) and the User Deletion API design
> (`GUIDE-KTW9YBDZAY9F`), so this isn't a stylistic preference — it's the
> settled design of this service.
>
> The compliant implementation soft-deletes by setting `deleted_at`, matching the
> `deleted_at IS NULL` pattern already used by `list_active`:
>
> ```python
> def delete(self, user_id: str) -> None:
>     self._conn.execute(
>         "UPDATE users SET deleted_at = %s WHERE id = %s AND deleted_at IS NULL",
>         (datetime.now(UTC), user_id),
>     )
> ```
>
> (with `from datetime import UTC, datetime`). If you genuinely need physical
> erasure — e.g. a GDPR right-to-erasure request — ADR-001 routes that through
> anonymisation, not `DELETE`; that's a separate, governed path. Want me to write
> the soft-delete version?

## What this shows (maps to `rac-obey-demo-grounding-proof`)

- **REQ-002, in order:** a retrieval tool (`search_artifacts`) **and**
  `get_artifact` read the governing ADR; the agent then **declines** the
  forbidden hard delete; and it **cites the decision by id**
  (`ADR-001` / `GUIDE-KTW9YBDWDBFM`). The tool calls and their results are shown
  verbatim above, not summarized.
- **No verdict tool:** Lore supplied the facts (the Accepted ADR and its edges);
  the *agent* supplied the judgment to decline (ADR-034). Nothing in the loop
  rendered a "this violates a decision" verdict.
