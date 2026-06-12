# Gaps — agent 4 (essay–artifact bridge)

## Gap: typed mapping from an external article to a corpus capability

- Instance: `rac/designs/growth-essay-mapping.md` records article-claim
  → capability mappings as a Markdown table inside a design's `## Design`
  section. The claims, the counterpart references, and the placement
  decisions are invisible to `rac relationships` and the MCP tools — an
  agent asked "which capability answers Article 1's third claim?" must
  parse free-form table prose.
- Instance: REQ-001/REQ-002 of
  `rac/requirements/rac-growth-essay-bridge.md` mandate that the mapping
  be "recorded in the corpus as an artifact", but the only expressible
  recording is prose; the requirement cannot be checked structurally.
- Minimal schema addition that would have sufficed: typed edge semantics
  on relationships (e.g. `answers`, `instantiates`) rather than the
  single untyped `## Related <Type>` form.

## Gap: no way to reference external or unpublished documents

- Instance: the essay series being mapped in
  `rac/designs/growth-essay-mapping.md` lives outside the repository
  (and Article 1 is unpublished, with no stable URL or path), so the
  article side of every mapping row is a derived-claim label, not a
  reference anything can resolve or validate.
- Instance: once an article publishes, there is still nowhere to record
  its URL as data — the same limitation agent 1 hit with competitor
  source URLs, which ended up in an HTML comment in `README.md`.
- Minimal schema addition that would have sufficed: an optional
  `## References` section accepting external URLs or repo-external
  document labels, resolvable to "exists/unverifiable" rather than to a
  corpus id.

## Gap: machine-readable gate/blocked status (re-confirmed)

- Instance: `rac/requirements/rac-growth-essay-bridge.md` REQ-004
  blocks publication behind GATE-1, expressed only as the conventional
  prose line `Blocked: GATE-1 (...)` under `## Status`; nothing can
  enumerate "everything currently blocked behind GATE-1" across the
  corpus. The design's Constraints section carries the same
  unqueryable line.
- Instance: BRIEF.md itself records this convention as a workaround,
  and every growth-programme artifact intended for public posting now
  repeats it.
- Minimal schema addition that would have sufficed: a validated
  optional `Blocked-By:` token under `## Status` with values drawn from
  a repo-configured gate list.
