---
schema_version: 1
id: LV-KVW7MEE7CYRD
type: prompt
---
# lore-verify Commit and PR Guidelines

## Objective

Produce commits and pull requests for `lore-verify` that read cleanly, carry the
maintainer identity, and meet the Developer Certificate of Origin posture the
`itsthelore` organisation adopted (RAC ADR-071) — which `lore-verify` inherits as a
sibling repository. This extends the RAC commit standard with the one thing it does
not mention: the DCO sign-off.

## Input

- The change being committed, and the LV roadmap item / decision it belongs to.
- The maintainer identity used on `main`.

## Instructions

### Commit format

Use `<type>(<area>): <imperative summary> [reference]`, the RAC standard. Allowed
types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`. Suggested LV areas:
`drive`, `compile`, `run`, `runner`, `targets`, `redaction`, `contract`, `corpus`,
`release`. Reference an LV roadmap (`[roadmap:v0.1.0]`) or issue (`[issue:#n]`)
where one applies; unscheduled corpus work may omit it.

```text
feat(compile): add N-run fidelity gate [roadmap:v0.1.0]
docs(decision): record runtime threat model (LV-ADR-003)
```

### DCO sign-off (the addition)

Every commit MUST carry a `Signed-off-by:` trailer matching the author identity,
per the DCO posture (RAC ADR-071). Use `git commit -s`, or add the trailer
explicitly:

```text
Signed-off-by: Tom Ballard <tom@armytage.co>
```

The same applies to commits in any PR `lore-verify` opens. (This is the rule
rac-core's own commit guidelines do not state, because the DCO landed after them;
for `lore-verify` it is mandatory.)

### Identity

Author and committer MUST both be the maintainer identity used on `main`, never a
tool identity. Set both before committing and verify with:

```bash
git log -1 --format='%an <%ae> / %cn <%ce>'
```

### No tool attribution

No generated-by footer, no AI-assistant attribution, no `Co-Authored-By:` trailer
naming a tool, and no session-link URL — in commits, PR titles/bodies, or
review/issue comments. Strip any harness-appended attribution before committing.
The `Signed-off-by` DCO trailer is required; tool trailers are forbidden.

## Output

A commit, or series, conforming to the format above, each carrying the maintainer
identity on author and committer, the DCO `Signed-off-by` trailer, and no tool
attribution.

## Constraints

- Every commit is signed off (DCO, RAC ADR-071); none carries tool attribution.
- Author and committer are the maintainer identity, never a tool identity.
- Summaries are imperative and specific; the history should read as the product's
  story.

## Evaluation

- `git log` shows each commit with a `Signed-off-by` trailer and the maintainer
  identity on both author and committer.
- No commit, PR, or comment carries a generated-by footer, a tool `Co-Authored-By`,
  or a session link.

## Related Decisions

- lv-adr-001-product-identity
