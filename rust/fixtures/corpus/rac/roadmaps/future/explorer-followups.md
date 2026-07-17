# Explorer Follow-ups (deferred from v0.8.x)

Informal scoping note. Two design decisions were made deliberately during the
v0.8.x Explorer series and flagged for a later pass. Captured here so they are
not lost; neither is a defect.

## 1. Recommendation "impact" copy lives in Explorer, not Core

**Scoped into v0.8.11** (explorer-followups): `ReviewIssue` gains an
additive `impact` field owned by Core; the Explorer renders it and drops
its own copy.

Deferred from v0.8.3 (recommendations).

Today each recommendation's *impact* line ("why it matters") is fixed
presentation copy keyed by the Core finding code, held in
`rac.explorer.adapter` alongside the other display labels. The finding,
severity, action, and path all come from Core's review service; only the
impact sentence is Explorer-authored.

This kept v0.8.3 presentation-only and avoided changing a JSON contract the
roadmap did not call for. The trade-off: a CLI/JSON consumer of `rac review`
does not see the impact text, and the copy is not validated as corpus content.

Follow-up option: add an additive `impact` field to `ReviewIssue` (a versioned
JSON-contract change, ADR-007), with Core owning the per-code text. Explorer
would then render Core's impact rather than its own. Worth doing if the review
service grows or another consumer needs impact.

## 2. Editor preference persistence and terminal-editor support

**Landed in v0.8.8** (explorer-command-palette): the `editor` preference in
`/settings` with preference → `$VISUAL` → `$EDITOR` resolution, and a
suspend/resume path for terminal editors. The remaining piece — the
first-run editor prompt — is **scoped into v0.8.11** (explorer-followups).

Deferred from v0.8.4 (action workflows) and v0.8.6 (preferences).

`rac explorer` resolves the editor from `$VISUAL` / `$EDITOR` and launches it
fire-and-forget (`Popen`), which suits GUI editors (Cursor, VS Code, …) per
DESIGN-editor-integration. Two pieces were left out:

- A persisted editor preference and first-run editor selection. The
  preferences file (v0.8.6) already has a home for it
  (`$XDG_CONFIG_HOME/rac/explorer.json`); adding an `editor` key plus a
  first-run prompt is the natural extension.
- Terminal editors (vim, neovim, emacs -nw) that need the TUI suspended while
  the editor owns the terminal, then resumed on exit. This requires
  `App.suspend()` handling and is a larger interaction change than the
  fire-and-forget GUI path.

Follow-up option: extend `rac.explorer.preferences` with an `editor` setting
and offer it during first run; add a suspend/resume path for terminal editors
behind editor-type detection.

## References

- rac/roadmaps/v0.8.x-explorer/v0.8.11-explorer-followups.md
- rac/roadmaps/v0.8.x-explorer/v0.8.3-explorer-recommendations.md
- rac/roadmaps/v0.8.x-explorer/v0.8.4-explorer-action-workflow.md
- rac/roadmaps/v0.8.x-explorer/v0.8.6-explorer-maturity.md
- rac/designs/explorer-editor-integrations.md
