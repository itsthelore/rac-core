"""The ``/`` command registry and its routing (DESIGN-command-surface).

The command surface is exactly this registry: a verb not listed here is not
discoverable. Routing is the only decision Explorer makes locally — the
answers all come from Core services via the adapter (ADR-015).

Search and commands share a single entry field: any input whose first word is
not a registered command name is treated as a search, so a user never has to
choose between "searching" and "running a command". Importing neither Textual
nor Core keeps this routing unit-testable without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass

# The fallback route for input that names no registered command.
SEARCH = "search"


@dataclass(frozen=True)
class CommandSpec:
    """One discoverable command on the ``/`` surface."""

    name: str
    usage: str
    summary: str


@dataclass(frozen=True)
class Invocation:
    """A routed input: a registry command (or ``SEARCH``) plus its arguments."""

    command: str
    args: str


# Order is contract (test_registry_is_the_v0810_contract): the help listing and
# the empty-palette suggestions both render the registry in this exact order.
REGISTRY: tuple[CommandSpec, ...] = (
    CommandSpec("open", "open <ref>", "Open an artifact by ID or alias"),
    CommandSpec("find", "find <query> [type]", "Search artifacts by ID, title, or path"),
    CommandSpec("browse", "browse [type]", "Browse the sidebar; a type lists results"),
    CommandSpec(
        "list", "list [type|text]", "List artifacts; a type scopes, other text searches names"
    ),
    CommandSpec("health", "health", "Show repository health and attention items"),
    CommandSpec("stats", "stats", "Show portfolio statistics"),
    CommandSpec(
        "recommendations", "recommendations", "Show recommendations with impact and actions"
    ),
    CommandSpec("new", "new <type> <path>", "Create an artifact from its template"),
    CommandSpec("import", "import <source> [target]", "Convert a document into Markdown"),
    CommandSpec("relationships", "relationships <ref>", "Traverse an artifact's relationships"),
    CommandSpec("resume", "resume", "Reopen the last artifact in this repository"),
    CommandSpec("schema", "schema [type]", "Show an artifact type's expected structure"),
    CommandSpec("settings", "settings", "View and change Explorer settings"),
    CommandSpec("home", "home", "Return to the repository home"),
    CommandSpec("help", "help", "List available commands"),
    CommandSpec("quit", "quit", "Quit the Explorer"),
)

_NAMES = {spec.name: spec for spec in REGISTRY}

# Alternative spellings that route to a registered command, so muscle memory
# from earlier releases keeps working without enlarging the visible registry.
_ALIASES = {"preferences": "settings"}

# Rendered when the surface is empty: teach the grammar by example.
EXAMPLES: tuple[str, ...] = (
    "open req-001",
    "find payments",
    "browse decision",
)


def parse(text: str) -> Invocation:
    """Route raw surface input to a command or a search.

    A leading ``/`` is tolerated (users type it out of habit) and command-name
    matching is casefolded. Only the *first* word can name a command; input
    that merely contains a command word (``the open question``) is a search.
    """
    stripped = text.strip().lstrip("/").strip()
    head, _, rest = stripped.partition(" ")
    name = _ALIASES.get(head.casefold(), head.casefold())
    if name in _NAMES:
        return Invocation(command=name, args=rest.strip())
    return Invocation(command=SEARCH, args=stripped)


def suggestions(text: str) -> tuple[CommandSpec, ...]:
    """Registry commands whose name starts with the (partial) first word.

    Preserves registry order, so empty input yields the whole registry.
    """
    head = text.strip().lstrip("/").strip().partition(" ")[0].casefold()
    return tuple(spec for spec in REGISTRY if spec.name.startswith(head))
