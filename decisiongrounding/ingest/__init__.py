"""Deterministic ingest of real, public artifacts into benchmark corpora.

This package turns public decision documents (currently Python PEPs) into
`decisiongrounding` corpus artifacts WITHOUT hand-writing their prose, so a
skeptic can reproduce the corpus byte-for-byte from an immutable upstream pin.
The gold label and task are always authored by hand and blind (CONTRIBUTING.md
rule 1); ingest only produces the mechanical, verifiable corpus material.
"""
