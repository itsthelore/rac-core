# Changelog

## 0.1.0

Initial release — a thin client over the `rac` CLI (no engine logic is
reimplemented).

- Live per-file validation and cross-artifact enforcement (broken and retired
  references) surfaced at the reference site.
- Authoring aids: artifact-ID completion in relationship sections,
  missing-section quick-fixes, and a New Artifact command.
- Navigation: status-aware hover, go-to-definition, find-all-references,
  clickable alias links, an Outline, and workspace symbols.
- Ambient awareness: a status-bar corpus health score and workspace-wide
  diagnostics.
- RAC Explorer: a self-contained, offline corpus viewer with a list/detail view
  and an Obsidian-style node-link graph, synced to the editor, served under a
  strict Content-Security-Policy.
- Runs entirely on your machine with no telemetry and no network access.
