"""RAC Explorer — interactive terminal UI over RAC services (v0.8.0, ADR-028).

Explorer is a *presentation* layer: it consumes RAC service-layer APIs
(asdecided.services) through a dedicated adapter and implements no repository
intelligence of its own (ADR-015). Anything visible in Explorer is also
obtainable through ``decided <command>`` or an equivalent service call.

Layout:

- ``launch``  — ``run_explorer`` entry point; lazily imports the Textual app
  so the base install works without the ``explorer`` extra.
- ``adapter`` — invokes services, translates Core models into UI state.
- ``state``   — frozen UI-state dataclasses widgets render.
- ``app`` / ``screens`` / ``widgets`` — the Textual application (the only
  modules that import Textual).

This package import stays Textual-free.
"""
