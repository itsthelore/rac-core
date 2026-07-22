"""Bundled artifact-spec registry — the shared source both RAC engines read.

``artifact-specs.json`` is the canonical, language-neutral encoding of
``ARTIFACT_SPECS`` (the ordered requirement/decision/roadmap/prompt/design
specs) and the relationship-section descriptions. It ships with the
distribution and is loaded via ``importlib.resources``, mirroring how
templates ship under :mod:`asdecided.templates` and hooks under :mod:`asdecided.hooks`.

ADR-063 Guard 1: the Python engine (:mod:`asdecided.core.artifacts`) and the Rust
engine (``rac-engine::spec``, which embeds this same file via ``include_str!``)
both read this one file, so classification and validation cannot drift between
them. The upstream source of truth is ``itsthelore/rac-spec``; this is the
in-repo vendored copy, kept byte-identical by the sync gate. Do not hand-edit —
change the upstream and re-sync.
"""
