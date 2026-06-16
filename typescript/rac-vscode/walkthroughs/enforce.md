# See enforcement in your editor

This is the point of RAC: your recorded decisions are enforced where you work.

Open any artifact and, in a relationship section, reference a decision that does
not exist:

```markdown
## Related Decisions

- adr-does-not-exist
```

Save the file. The extension flags the broken reference **at the reference
site** — the same finding `rac relationships --validate` reports on the command
line, because the extension runs `rac` rather than guessing.

References to **retired** (superseded/deprecated) decisions are flagged
distinctly, so your agent — and your teammates — stop re-litigating settled
calls.

Other things to try: hover an artifact id for its status, go-to-definition on a
reference, or **RAC: Open Explorer** for the corpus graph.
