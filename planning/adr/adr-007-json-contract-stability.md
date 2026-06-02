ADR-006 JSON Contract Stability
Decision: JSON outputs are public APIs.
Meaning:

{
  "features": 12
}

shouldn't randomly become:

{
  "feature_count": 12
}

without versioning.

This matters enormously for future MCP integrations.