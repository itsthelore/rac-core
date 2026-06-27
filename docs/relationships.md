# Relationships

Artifacts rarely stand alone — a requirement informs a decision, a roadmap pursues a
requirement, a design references both. RAC lets you record those links **in the
Markdown itself** and then validate that they resolve.

## Declaring a relationship

Add one of the `## Related …` sections and list the ids of the artifacts you're
referencing, one per line:

```markdown
## Related Requirements
- login-flow

## Related Decisions
- adr-001
- adr-007
```

The five relationship sections, one per target type:

- `## Related Requirements`
- `## Related Decisions`
- `## Related Roadmaps`
- `## Related Prompts`
- `## Related Designs`

Decisions may also use `## Supersedes` to point at the decision they replace.

Each non-empty line is one reference. A leading list marker (`-`, `*`, `+`, or `1.`)
is stripped; the rest of the line is the id, matched case-insensitively against the
[identity](artifacts.md#artifact-identity) of every artifact RAC discovers. A
relationship section is only recognized on a type that declares it (so an unknown
document contributes no relationships).

## External references (Jira)

`## Related Jira` links an artifact to a Jira ticket — an *external* reference
that deliberately does not resolve to an in-corpus artifact (ADR-087). It turns
change traceability ("this ADR implements PROJ-1234") into corpus data instead of
prose:

```markdown
## Related Jira
- PROJ-1234
- https://acme.atlassian.net/browse/PROJ-5678
```

Each entry is a Jira key (`PROJ-1234`) or a full URL. The engine does **format-lint
only, offline**: `rac validate` flags an entry that is neither a well-formed key
nor a URL (`malformed-external-reference`, overridable per
[ADR-053](https://github.com/itsthelore/rac-core/blob/main/rac/decisions/adr-053-validation-severity-overrides.md)),
and `rac relationships --validate` never reports a Jira entry as a broken reference.
The engine **never contacts Jira** — checking that a ticket exists or is in an
allowed state needs a token and lives in the `lore-atlassian` satellite (ADR-090),
not the engine (ADR-002).

In `rac export --graph` an external edge carries `"external": true` and
`"resolved": false`, so a graph backend can tell a deliberate Jira link from a
dangling in-corpus reference (both are unresolved, only the external one is marked).

## Viewing relationships

```bash
rac relationships rac/          # human-readable report
rac relationships rac/ --json   # machine-readable
```

This lists the references RAC found. Finding none is not an error.

## Validating relationships

Add `--validate` to resolve every reference against the artifacts in the path:

```bash
rac relationships rac/ --validate
```

```text
Relationship Validation

Relationships Checked: 12
Validation Issues: 0
```

If every reference resolves uniquely, the command exits `0`. Otherwise it reports
each problem and exits `1`. The issue codes:

| Code | Meaning |
| --- | --- |
| `relationship-target-not-found` | The referenced id matches no artifact. |
| `relationship-target-ambiguous` | The referenced id matches more than one artifact. |
| `relationship-self-reference` | An artifact references itself. |
| `duplicate-artifact-identifier` | Two artifacts resolve to the same id. |
| `relationship-edge-unsupported` | A relationship section the artifact's type does not declare. |
| `relationship-target-type-mismatch` | A reference resolves to the wrong artifact type for the edge. |
| `relationship-target-superseded` | A live artifact points at a retired (superseded/deprecated) target. |
| `relationship-cycle` | A cycle in a directional, acyclic edge (`supersedes`). |

Exit codes follow the standard convention: `0` all references valid · `1` issues
found · `2` path not found.

## Graph integrity

Beyond resolving each reference, `rac relationships --validate` validates the
corpus *as a graph* (ADR-055). Each relationship kind has a declared schema —
its target type (**range**), whether it is directional, and whether it may form a
cycle:

- **Range.** `## Related Decisions` must point at a decision, `## Related
  Roadmaps` at a roadmap, and so on; `## Supersedes` is decision→decision. A
  reference that resolves to the wrong *recognized* type is
  `relationship-target-type-mismatch`. An untyped document target is exempt — it
  is a legitimate document (ADR-010), owned by referential integrity.
- **Acyclicity.** `supersedes` is an ordering edge, so a cycle (A supersedes B
  supersedes A) is illegal and reported as `relationship-cycle`. The undirected
  `related_*` links never cycle.
- **Status-consistency.** A live artifact of *any* type must not point at a
  retired one. Lifecycle status (ADR-051) is an optional `## Status` section per
  type — decisions/requirements/designs use `Proposed`/`Accepted` (live) and
  `Superseded`/`Deprecated` (retired); prompts use `Active`/`Deprecated`;
  roadmaps use `Planned` and `Superseded`/`Abandoned`. A reference to a retired
  target is `relationship-target-superseded`, except `supersedes` (by which a
  replacing decision legitimately points at the one it retires).

These checks are deterministic and read the same artifacts you author — no hidden
graph store (ADR-016). An agent over MCP can read the repository's overall
validation status from `get_summary` (the `validation_status` block), without a
fifth tool.

## Repository consistency

Run `--validate` across your whole `rac/` tree to catch drift as artifacts are added,
renamed, or removed — a broken reference usually means a target was renamed or a typo
crept into an id. For a higher-level view that also surfaces **orphaned** artifacts
(those nothing else references) and an overall relationship coverage percentage, use
[`rac portfolio`](cli.md#portfolio).

## See also

- [artifacts.md](artifacts.md#artifact-identity) — how ids are resolved.
- [repo-workflow.md](repo-workflow.md) — running these checks across a repository.
