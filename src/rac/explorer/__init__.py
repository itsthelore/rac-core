"""RAC Explorer boundary package (consumer of RAC services).

Intentionally empty for v0.7.4. Explorer is a *presentation* layer: when it is
built it must consume existing RAC service-layer APIs (rac.services) rather than
implementing its own repository intelligence (ADR-015). Anything visible in
Explorer must also be obtainable through ``rac <command>`` or an equivalent
service call.
"""
