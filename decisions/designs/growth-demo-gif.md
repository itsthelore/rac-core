---
schema_version: 1
id: RAC-KTYB6RMYBQ5X
type: design
---
# README Demo GIF — Init to Validated Artifact

## Context

The README needs a short visual proof of RAC's first-value loop. The
adoption requirement (`rac-growth-adoption`, REQ-004) calls for a demo
GIF of at most 20 seconds showing init → author → validate. It
complements the existing "90-second demo (link on launch)" placeholder;
it does not replace it. This design is the shot list only — nothing is
recorded as part of it.

## User Need

An evaluator skimming the README wants to see, without installing
anything, that RAC produces first value in seconds: scaffold a project,
author a requirement, get a deterministic PASS. The GIF must be legible
at README column width and loop cleanly.

## Design

Recorded in a clean terminal, one project directory, cuts between shots
(no live typing of prose — the edited file is pre-prepared). Target 20
seconds total.

1. (0–2 s) Empty project. Type and run `rac init`. Output:
   `Initialized repository key RAC` / `Config: .rac/config.yaml`.
2. (2–6 s) Run
   `rac new requirement rac/requirements/login-flow.md`.
   Output shows `Created requirement artifact` and the minted ID.
3. (6–13 s) Cut to the file in an editor: TODO placeholders replaced
   with a short `## Problem` paragraph and two `[REQ-NNN]` lines.
   Hold ~3 s on the finished file.
4. (13–18 s) Cut back to the terminal. Run `rac validate rac/`.
   Output: `PASS`, `0 error(s)`. Hold ~2 s on the PASS line.
5. (18–20 s) End card: `pip install requirements-as-code` on one line.
   Loop back to shot 1.

## Constraints

- Total duration at most 20 seconds (REQ-004 in `rac-growth-adoption`).
- Shows only released commands and real output — no mocked terminal
  text; re-record rather than edit output frames if the CLI changes.
- Font large enough to read at GitHub README width (~80 columns max in
  frame); dark-on-light or light-on-dark with strong contrast.
- File size suitable for a README (target under 2 MB; trim hold times
  before cutting shots if over).
- No sound, no captions that scroll faster than they can be read; each
  command stays on screen at least 1.5 s.
- Does not remove or replace the README's "90-second demo (link on
  launch)" placeholder.

## Related Requirements

- rac-growth-adoption
