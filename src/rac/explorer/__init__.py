"""RAC Explorer — an interactive terminal UI layered over RAC services (ADR-028).

Explorer only *presents*: every answer it shows is produced by the RAC
service layer (:mod:`rac.services`) and reached through a single adapter, so
the UI carries no repository intelligence of its own (ADR-015). Whatever
Explorer surfaces is equally reachable through ``rac <command>``.

The package splits along one axis — who may import Textual:

- :mod:`~rac.explorer.launch` is the ``run_explorer`` entry point. It imports
  the Textual application lazily so the base install runs without the
  ``explorer`` extra.
- :mod:`~rac.explorer.adapter` calls services and translates Core models into
  the frozen UI-state dataclasses in :mod:`~rac.explorer.state`.
- :mod:`~rac.explorer.app`, ``screens``, and ``widgets`` are the Textual
  application and the only modules permitted to import Textual.

Importing this package must not pull in Textual, so it stays usable from the
base install and from headless tests.
"""
