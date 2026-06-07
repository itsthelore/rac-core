# Minor Release Gate

Before completing any 0.x.n release:

## Duplication
- Did this release add artifact-specific classification logic?
- Did it duplicate validation, schema, template, stats, or improve behavior?
- Can new behavior be expressed through ArtifactSpec instead?
- Are there two sources of truth for sections, metadata, or guidance?

## Simplification
- What code became obsolete?
- What branch or special case can be removed?
- Did any file grow past the agreed limit?
- Should a helper be extracted?
- Did this release increase the number of artifact-specific conditionals?

## Verification
- Are there negative classification tests?
- Are adjacent artifact types tested against each other?
- Are incomplete-but-recognizable artifacts tested?
- Are CLI human and JSON outputs tested?
- Was pytest run before commit?