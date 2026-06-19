---
schema_version: 1
id: EVAL-2ABF382M9AKX
type: design
tags: [navigation, desktop]
---
# Sidebar Navigation

## Status

Accepted

## Context

On the desktop web app, writers move between documents, folders, and shared
spaces dozens of times a session. The navigation surface has to stay visible
without crowding the editor canvas.

## User Need

A writer on a wide screen needs to jump between documents and folders quickly
while keeping the document they are editing in view.

## Design

A persistent left sidebar lists folders and documents in a collapsible tree.
The sidebar can be pinned open or collapsed to a thin rail; the editor canvas
reflows to fill the freed space when it collapses.

## Constraints

The sidebar must not reduce the editor canvas below a readable minimum width,
and its collapsed state must persist per user.

## Rationale

A pinned sidebar suits wide desktop screens where horizontal space is ample and
fast lateral movement matters more than canvas width.
