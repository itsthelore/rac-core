"""OKF v0.1 carrier-profile constants (ADR-048).

OKF (Open Knowledge Format) is an *informative* carrier profile for a RAC
corpus. The two mechanically checkable facts about it live here in core so the
bundle exporter (:mod:`rac.output.okf`) and the write-time conformance gate
(:mod:`rac.services.okf_conformance`) read one deterministic definition rather
than each restating it (ADR-002):

* how each RAC ``type`` names its OKF counterpart, and
* which filenames OKF generates and therefore reserves.
"""

from __future__ import annotations

# RAC ``type`` -> OKF ``type`` label (docs/okf-profile.md is the normative
# statement). Every registered RAC type must have an entry: a type missing here
# would be dropped silently from an exported bundle, so conformance treats the
# omission as an error rather than accepting it. Order follows the profile doc.
OKF_TYPE = {
    "requirement": "Requirement",
    "decision": "ADR",
    "design": "Design",
    "roadmap": "Roadmap",
    "prompt": "Prompt",
}

# Filenames OKF generates for a bundle -- ``index.md`` (progressive-disclosure
# entry point) and ``log.md`` (chronological history). A *typed* artifact placed
# at one of these paths collides with the generated file and is flagged; an
# *untyped* document there is a legitimate hand-authored entry point (ADR-010)
# and is left untouched.
RESERVED_FILENAMES = ("index.md", "log.md")
