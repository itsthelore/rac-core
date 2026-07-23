# Meridian user service — code task starting state

This is the minimal code slice the grounding demo runs against. It is a small,
plausible cut of the Meridian user management service described by the
`examples/guide/decisions/` corpus: a PostgreSQL-backed repository layer and a thin
service layer, with the existing account-lifecycle patterns visible.

The task (see `../demo.md`) asks an agent to implement account deletion. The
repository already creates, reads, and updates users; the one piece missing is
the deletion path.

## Layout

- `meridian_users/db.py` — a tiny fake database connection used so the slice
  runs without a real PostgreSQL instance. It records the SQL it is asked to
  execute, which is what the demo inspects.
- `meridian_users/repository.py` — the data-access layer. `create`, `get`, and
  `list_active` are implemented; `delete` is the stub the task fills in.
- `meridian_users/service.py` — the service layer that the deletion endpoint
  calls into.

## Why this slice

The repository already shows the soft-delete pattern in `list_active`
(`WHERE deleted_at IS NULL`) and in the `deleted_at` column, so a compliant
implementation has everything it needs in context. The naive implementation —
a hard `DELETE FROM users WHERE id = %s` — is the obvious thing to write and is
exactly what ADR-001 (`GUIDE-KTW9YBDWDBFM`, *Soft-Delete User Records*)
prohibits. That gap is the demo.

This directory is intentionally outside `examples/guide/decisions/`, so it does not
affect `decided validate examples/guide/decisions/` or the corpus relationship checks.
