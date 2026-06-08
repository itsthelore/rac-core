# RAC — Requirements as Code

**Treat product knowledge like source code.**

RAC is an open-source toolkit for managing requirements, decisions, roadmaps, prompts, and design artifacts directly inside your repository.

Write your product thinking in Markdown.
Version it with Git.
Inspect it. Improve it. Connect it. Use it as context for humans and AI.

```bash
pip install requirements-as-code
```

---

## Why RAC?

Modern software teams have a problem.

The code is structured.

The tests are automated.

The infrastructure is versioned.

But the reasoning behind what we build is scattered across:

* documents
* tickets
* chats
* whiteboards
* AI conversations

The context disappears.

RAC brings that knowledge back into the repository.

If code deserves version control, the decisions behind the code do too.

---

## Requirements are just the beginning

Despite the name, RAC is not only about requirements.

RAC supports structured product artifacts:

* Requirements — what needs to exist
* Decisions — why choices were made
* Roadmaps — where the product is heading
* Prompts — reusable AI collaboration patterns
* Designs — product experience thinking

Everything remains plain Markdown.

No proprietary formats.

No hosted platform.

No lock-in.

---

## Example

Create a requirement:

```bash
rac init requirement login-flow.md
```

Write naturally:

```markdown
# Login Flow

## Context

Users need a secure way to access their account.

## Requirement

Users should be able to authenticate using email and password.

## Acceptance Criteria

- User can enter credentials
- Invalid attempts show an error
- Successful login redirects to dashboard
```

Inspect it:

```bash
rac inspect login-flow.md
```

Improve it:

```bash
rac improve login-flow.md
```

RAC helps identify missing context before humans or AI depend on it.

---

## Repository intelligence

RAC understands collections of artifacts.

```bash
rac inspect .
```

Understand:

* what knowledge exists
* what is missing
* artifact completeness
* repository health

Your product knowledge becomes queryable.

Or list everything as a machine-readable inventory:

```bash
rac index
rac index --json
```

`rac index` answers one question — what exists, where, and what type — so consumers
like Explorer, IDEs, CI, and AI agents can build navigation without re-scanning files.

---

## Built for AI-native development

AI is only as useful as the context you provide.

RAC helps create durable context that AI tools can consume:

* structured requirements
* architectural decisions
* design constraints
* product direction
* reusable prompts

Your repository becomes the source of truth.

---

## Git is the database

RAC does not replace your existing workflow.

It builds on it.

You already have:

* history
* branches
* reviews
* ownership
* collaboration

RAC treats Git as the system of record for product knowledge.

---

## Explorer

RAC includes a terminal interface for exploring your product knowledge.

```bash
rac explorer
```

Navigate your repository:

* browse artifacts
* inspect relationships
* understand product health
* discover missing context

Explorer is a viewer.

RAC Core remains the intelligence layer.

---

## Philosophy

RAC believes:

* Markdown is enough.
* Git is enough.
* Product knowledge should live beside the product.
* AI needs structured context, not more chat history.
* The reasoning behind software matters.

Requirements as Code is not about writing more documentation.

It is about making product knowledge durable.

---

## Status

RAC is early and evolving quickly.

Current focus:

* artifact schemas
* repository intelligence
* AI-ready context
* terminal-first workflows

Contributions, ideas, and experiments welcome.

---

## Install

```bash
pip install requirements-as-code
```

```bash
uv tool install requirements-as-code
```

---

## License

MIT
