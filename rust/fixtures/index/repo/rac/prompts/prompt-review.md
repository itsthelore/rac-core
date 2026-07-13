---
schema_version: 1
id: FIX-0PR1REV1EW00
type: prompt
---
# Widget Cache Review Prompt

## Objective

Review widget cache changes for byte-neutral reads.

## Input

- The widget cache diff.

## Instructions

Check every warm read against a cold walk.

## Output

A pass/fail verdict with evidence.
