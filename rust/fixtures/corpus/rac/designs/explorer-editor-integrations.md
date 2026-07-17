# Design: Explorer Editor Integration

## Status

Proposed

## Purpose

Define how Explorer integrates with external editing environments.

Explorer identifies findings.

External tools perform authoring and modification.

## Design Principles

### Existing Tools First

Users should continue using their preferred editor.

Examples include:

- Cursor
- VS Code
- Windsurf
- Vim
- Neovim
- Emacs
- JetBrains IDEs

### Explorer Is Not An Editor

Explorer shall not implement:

- text editing
- document authoring
- content management

### Fast Transition

Opening an artifact should require minimal user effort.

## Configuration

Explorer shall support a configured default editor (v0.8.8): the `editor`
preference in `$XDG_CONFIG_HOME/rac/explorer.json`, set from the `/settings`
view or by editing the file.

Resolution order:

1. the `editor` preference
2. `$VISUAL`
3. `$EDITOR`

## Terminal Editors

GUI editors (Cursor, VS Code, …) launch fire-and-forget and Explorer keeps
running.

Terminal editors (vi, vim, nvim, emacs, nano, helix, micro) need the
terminal: Explorer suspends itself, runs the editor in the foreground, and
resumes when the editor exits. Where the runtime cannot suspend, Explorer
reports guidance instead of failing.

The live watcher (v0.8.9) holds while a terminal editor owns the screen and
rescans the moment Explorer resumes, so a saved edit is visible immediately
on return — the edit-and-look loop closes without a keystroke.

## First Run Experience

Users may select a preferred editor during onboarding.

Editor configuration should be modifiable later.

## Open Behaviour

Explorer should support:

### Open Artifact

Open artifact directly.

### Open Artifact At Location

Future enhancement.

### Open Multiple Artifacts

Future enhancement.

## Fallback Behaviour

If no editor is configured:

- prompt user
- use system default editor
- provide configuration guidance

## Related Artifacts

- DESIGN-first-run-experience
- DESIGN-action-workflows