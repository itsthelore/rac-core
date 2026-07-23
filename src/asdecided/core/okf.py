"""OKF v0.1 carrier-profile constants (ADR-048).

The RAC ``type`` → OKF ``type`` mapping and OKF's reserved filenames live here,
in core, so the OKF bundle export (``output/okf.py``) and the write-time OKF
conformance check (``services/okf_conformance.py``) share one definition
(ADR-002: a single deterministic source of truth). ADR-048 makes OKF an
informative carrier profile; these constants are the checkable part of it.
"""

from __future__ import annotations

# RAC ``type`` → OKF ``type`` (ADR-048; docs/okf-profile.md is the normative
# statement). The five enumerated RAC types map one-to-one. A registered RAC type
# absent here is an OKF conformance error, never a silent drop from the bundle.
OKF_TYPE = {
    "requirement": "Requirement",
    "decision": "ADR",
    "design": "Design",
    "roadmap": "Roadmap",
    "prompt": "Prompt",
}

# OKF reserves these filenames for generated entry points: ``index.md`` for
# progressive disclosure and ``log.md`` for chronological history. A *typed
# artifact* at one of these paths would collide with the generated bundle file
# (a conformance error); an *untyped* document at index.md/log.md is a legitimate
# reserved entry point and is left alone (ADR-010).
RESERVED_FILENAMES = ("index.md", "log.md")
