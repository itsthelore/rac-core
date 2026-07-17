# Requirement Review Prompt

## Objective

Review a Requirement artifact and surface gaps before it goes to engineering.

## Input

A single RAC Requirement artifact in Markdown, including its Problem and
Requirements sections.

## Instructions

- Read the Problem and confirm it names a user or business need.
- Check that each requirement is a testable [REQ-NNN] statement.
- List any missing or weak sections.

## Output

A short Markdown report with two headings: "Strengths" and "Gaps", each a bullet list.

## Constraints

- Do not rewrite the requirement; only review it.
- Keep the report under 200 words.

## Examples

Input: a requirement with no Success Metrics. Output: a Gaps bullet noting the
missing metrics section.

## Evaluation

A good response identifies real, specific gaps a reviewer would agree with and
avoids vague feedback.

## Related Requirements

- ../requirements/checkout-speed.md
