# RAC Agent Instructions

Before coding:
- Refresh from origin/main unless told otherwise.
- Read the target roadmap file and relevant ADRs.
- Produce a plan before implementation.
- Do not expand release scope beyond the roadmap.

Release discipline:
- Work on a feature branch, not main.
- Do not include Claude attribution in commits.
- After GitHub merge, refresh local main.
- Prune merged branches when asked.

Architecture:
- Prefer schema-driven artifact behavior.
- Do not add artifact-specific validation paths if a generic path can handle it.
- Keep classification separate from validation.
- Invalid but recognizable artifacts may still classify as their artifact type.

Testing:
- Add negative boundary tests for each new artifact type.
- Test that adjacent artifact types do not misclassify as each other.
- Run pytest before commit.