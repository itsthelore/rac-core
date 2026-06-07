"""RAC service layer.

Repository and artifact capabilities — inspection, improvement, relationship
operations, portfolio/repository intelligence, ingestion, and diffing. Services
provide stable APIs consumed by the CLI, Explorer, tests, and future
integrations (ADR-008, ADR-015). They depend on :mod:`rac.core`, never on the
CLI or output layers.
"""
