"""Explorer command registry and routing (v0.8.1, DESIGN-command-surface).

The `/` surface is backed by this single registry: an action not registered
here is not discoverable. Routing is the only logic that lives in Explorer —
every answer comes from Core services through the adapter (ADR-015).

Search and commands share the one entry point: input whose first word is not
a registered command name is a search, so users never have to decide which
they are doing. This module imports neither Textual nor Core, keeping the
routing unit-testable without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass

# The implicit route for input that names no registered command.
SEARCH = "search"


@dataclass(frozen=True)
class CommandSpec:
    """One discoverable command on the `/` surface."""

    name: str
    usage: str
    summary: str


@dataclass(frozen=True)
class Invocation:
    """A routed input: a registry command (or SEARCH) plus its arguments."""

    command: str
    args: str


REGISTRY: tuple[CommandSpec, ...] = (
    CommandSpec("open", "open <ref>", "Open an artifact by ID or alias"),
    CommandSpec("find", "find <query> [type]", "Search artifacts by ID, title, or path"),
    CommandSpec("browse", "browse [type]", "Browse all artifacts"),
    CommandSpec("health", "health", "Show repository health and attention items"),
    CommandSpec(
        "recommendations", "recommendations", "Show recommendations with impact and actions"
    ),
    CommandSpec("import", "import <source> [target]", "Convert a document into Markdown"),
    CommandSpec("home", "home", "Return to the repository home"),
    CommandSpec("help", "help", "List available commands"),
    CommandSpec("quit", "quit", "Quit the Explorer"),
)

_NAMES = {spec.name: spec for spec in REGISTRY}

# Shown when the surface is empty: teach by example (DESIGN-command-surface).
EXAMPLES: tuple[str, ...] = (
    "open req-001",
    "find payments",
    "browse decision",
)


def parse(text: str) -> Invocation:
    """Route raw surface input to a command or a search.

    A leading ``/`` is tolerated (users may type it out of habit); matching
    on the command name is casefolded. Anything else — including input that
    merely *contains* a command name — is a search.
    """
    stripped = text.strip().lstrip("/").strip()
    head, _, rest = stripped.partition(" ")
    if head.casefold() in _NAMES:
        return Invocation(command=head.casefold(), args=rest.strip())
    return Invocation(command=SEARCH, args=stripped)


def suggestions(text: str) -> tuple[CommandSpec, ...]:
    """Registry commands whose name starts with the (partial) first word."""
    head = text.strip().lstrip("/").strip().partition(" ")[0].casefold()
    return tuple(spec for spec in REGISTRY if spec.name.startswith(head))
