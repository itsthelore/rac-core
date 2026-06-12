# Gaps — agent 1 (positioning and comparison)

## Gap: link from a requirement to the non-artifact file that satisfies it

- Instance: `rac/requirements/rac-growth-positioning.md` REQ-001 to
  REQ-005 are satisfied by the "How this relates to spec-driven
  development" section of `README.md`. The schema's only linking
  mechanism is `## Related <Type>` sections pointing at corpus-internal
  artifact ids, so there is no way to record that the README section is
  the satisfying surface; a reviewer must rediscover the mapping by
  hand.
- Instance: the pre-existing `rac/requirements/rac-trust-transparency.md`
  has the same problem — FR-6 and FR-10 target README content (CI
  badge, trust section) with no recorded link to it.
- Minimal schema addition that would have sufficed: an optional
  `## Satisfied By` section accepting repo-relative file paths (with
  optional anchor), validated for file existence.

## Gap: external source citations as structured data

- Instance: REQ-004 in `rac-growth-positioning.md` requires every
  comparison-table claim to be verifiable from the competitor's own
  docs. The source URLs (github.com/github/spec-kit,
  github.com/Fission-AI/OpenSpec README and docs/cli.md) had to be
  recorded as an HTML comment in `README.md`, invisible to `rac
  validate`, `rac relationships`, and the MCP tools — the corpus cannot
  represent "this claim is grounded in that external URL" or check it
  for staleness.
- Minimal schema addition that would have sufficed: an optional
  `## Sources` section on artifacts accepting one URL per line, exposed
  through `get_artifact`.

## Gap: machine-readable record of a failed verification

- Instance: Kiro was excluded from the comparison table because
  https://kiro.dev/docs/specs/ returned HTTP 403 to automated fetches
  on 2026-06-12. That exclusion rationale lives only in prose (a
  Risks bullet in `rac-growth-positioning.md` and an HTML comment in
  `README.md`); nothing in the corpus can flag "re-verify this when the
  source becomes reachable".
- Minimal schema addition that would have sufficed: none specific —
  this would be covered by the `## Sources` section above if entries
  could carry a verified/unverifiable status token.
