---
schema_version: 1
id: EVAL-44R24W9NH93C
type: prompt
tags: [release, docs]
---
# Generate Release Notes

## Status

Active

## Objective

Draft human-readable release notes for an Aurora release from the merged pull
requests in the release, grouped so a reader can scan what changed.

## Input

A list of merged pull request titles and descriptions for the release, plus the
previous and new version numbers.

## Instructions

Group the changes into Features, Fixes, and Internal. Write one plain-language
bullet per change describing the user-visible effect, not the implementation.
Omit purely mechanical changes. Lead with the most user-visible features.

## Output

Markdown release notes: a heading with the new version, then the three grouped
sections, each a bulleted list. Omit a section that has no entries.

## Constraints

Do not invent changes that are not in the input. Keep each bullet to one
sentence and avoid internal ticket numbers in user-facing notes.
