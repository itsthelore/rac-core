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

Exit codes follow the standard convention: `0` all references valid · `1` issues
found · `2` path not found.

## Repository consistency

Run `--validate` across your whole `rac/` tree to catch drift as artifacts are added,
renamed, or removed — a broken reference usually means a target was renamed or a typo
crept into an id. For a higher-level view that also surfaces **orphaned** artifacts
(those nothing else references) and an overall relationship coverage percentage, use
[`rac portfolio`](cli.md#portfolio).

## See also

- [artifacts.md](artifacts.md#artifact-identity) — how ids are resolved.
- [repo-workflow.md](repo-workflow.md) — running these checks across a repository.
