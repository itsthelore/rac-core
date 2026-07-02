"""YAML frontmatter parsing — the artifact metadata envelope (ADR-025).

``split_frontmatter`` peels a leading ``---`` block off the Markdown body and
reports the line offset so downstream diagnostics keep file-accurate line
numbers. ``parse_frontmatter`` turns that raw YAML into a validated
:class:`~rac.core.metadata.ArtifactMetadata` plus a list of issues.

Strictness is the contract (ADR-025): malformed YAML, duplicate keys, unknown
fields, wrong types, and unsupported schema versions are all actionable
errors, never silently normalized. Documents without frontmatter are left
untouched — legacy support is a parser guarantee, not a special case.
PyYAML's ``SafeLoader`` already refuses arbitrary object construction; the
loaders below add duplicate-key rejection and adversarial-input bounds, both of
which stock YAML would otherwise accept (REQ-002).
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml
from yaml.nodes import Node

from .limits import MAX_FRONTMATTER_BYTES, MAX_FRONTMATTER_DEPTH, exceeds_byte_cap
from .metadata import (
    SUPPORTED_SCHEMA_VERSIONS,
    ArtifactMetadata,
    is_valid_id,
    normalize_id,
)
from .models import Issue

_DELIMITER = "---"
# The closing line may be the ``---`` delimiter or YAML's ``...`` document-end
# marker; both terminate the block.
_CLOSERS = ("---", "...")

# The complete frontmatter field schema — one canonical location per field
# (ADR-025); anything else is invalid-metadata-field, not ignored. Pinned equal
# to ``ArtifactMetadata``'s fields minus ``provenance`` by
# ``test_envelope_fields_agree``: add an envelope field in both places or the
# gate fails.
_SUPPORTED_FIELDS = ("schema_version", "id", "type", "relationships", "tags")


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (ADR-025)."""


def _no_duplicates(loader: _StrictLoader, node: yaml.MappingNode) -> dict:
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise yaml.MarkedYAMLError(
                problem=f"duplicate frontmatter key: {key!r}",
                problem_mark=key_node.start_mark,
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


class _BoundedLoader(_StrictLoader):
    """Strict loading plus the WS4 adversarial-input bounds (REQ-002).

    Forbidding YAML aliases kills the "billion laughs" alias-expansion bomb at
    its source, and the depth cap rejects deeply nested input as a structured
    ``malformed-frontmatter`` issue before PyYAML recurses into it. Inherits
    ``_StrictLoader``'s duplicate-key rejection and ``SafeLoader``'s refusal to
    construct arbitrary objects.
    """

    # Class attribute only seeds each fresh loader; ``compose_node`` promotes it
    # to a per-instance counter. A new loader per ``yaml.load`` call keeps this
    # safe — do not hoist the counter to shared class-level mutable state.
    _depth = 0

    def compose_node(self, parent: Node | None, index: int) -> Node | None:
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()
            raise yaml.MarkedYAMLError(
                problem="YAML aliases are not permitted in frontmatter",
                problem_mark=event.start_mark,
            )
        self._depth += 1
        if self._depth > MAX_FRONTMATTER_DEPTH:
            self._depth -= 1
            raise yaml.MarkedYAMLError(
                problem=f"frontmatter nesting exceeds the {MAX_FRONTMATTER_DEPTH}-level cap"
            )
        try:
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1


@dataclass
class FrontmatterSplit:
    """A document separated into raw frontmatter and Markdown body."""

    raw: str | None  # YAML text between the delimiters, or None when absent
    body: str  # the Markdown body (the whole text when no frontmatter)
    line_offset: int  # body line N is file line N + line_offset
    unterminated: bool = False  # opened with --- but never closed


def split_frontmatter(text: str) -> FrontmatterSplit:
    """Split a leading ``---`` frontmatter block from ``text``.

    Only a block whose first line is the delimiter counts — a mid-document
    ``---`` is a Markdown thematic break, not frontmatter (ADR-025). An opening
    delimiter with no closer is flagged ``unterminated`` and the whole text is
    returned as body, so parsing still proceeds and validation surfaces the
    error rather than losing the content.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != _DELIMITER:
        return FrontmatterSplit(raw=None, body=text, line_offset=0)
    for i in range(1, len(lines)):
        if lines[i].strip() in _CLOSERS:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            # The closer sits at index i, so body line N maps back to file line
            # N + (i + 1).
            return FrontmatterSplit(raw=raw, body=body, line_offset=i + 1)
    return FrontmatterSplit(raw=None, body=text, line_offset=0, unterminated=True)


def _issue(code: str, message: str, line: int | None = None) -> Issue:
    """Build an error-severity frontmatter issue — every issue here is an error."""
    return Issue("error", code, message, line)


def parse_frontmatter(raw: str) -> tuple[ArtifactMetadata | None, list[Issue]]:
    """Parse and schema-validate raw frontmatter YAML.

    Returns ``(metadata, issues)``. ``metadata`` is None when the block is
    wholly unusable — oversize, malformed YAML, a duplicate key, or not a
    mapping — because there is nothing to hand back. Field-level problems
    instead return the partially valid metadata alongside their issues so
    callers can still read whatever parsed.

    The field checks run in a fixed order (unknown fields, then schema_version,
    id, type, relationships, tags), each appending to a shared list. That order
    is contract: several tests assert full-list equality on the issue codes.
    """
    issues: list[Issue] = []

    # Cap the raw block before PyYAML sees it (WS4, REQ-002) so oversized front
    # matter cannot allocate unbounded ahead of validation.
    if exceeds_byte_cap(raw, MAX_FRONTMATTER_BYTES):
        return None, [
            _issue(
                "malformed-frontmatter",
                f"frontmatter exceeds the {MAX_FRONTMATTER_BYTES}-byte cap",
            )
        ]

    try:
        data = yaml.load(raw, Loader=_BoundedLoader)
    except yaml.MarkedYAMLError as exc:
        if exc.problem and "duplicate frontmatter key" in exc.problem:
            return None, [_issue("duplicate-frontmatter-key", exc.problem)]
        return None, [
            _issue("malformed-frontmatter", f"frontmatter is not valid YAML: {exc.problem}")
        ]
    except yaml.YAMLError as exc:
        return None, [_issue("malformed-frontmatter", f"frontmatter is not valid YAML: {exc}")]
    except RecursionError:
        # The depth cap should pre-empt this; catch it anyway so a crash never
        # escapes (REQ-002).
        return None, [_issue("malformed-frontmatter", "frontmatter nesting too deep to parse")]

    if not isinstance(data, dict):
        return None, [
            _issue(
                "malformed-frontmatter",
                "frontmatter must be a YAML mapping of supported fields",
            )
        ]

    _check_unknown_fields(data, issues)
    schema_version = _validate_schema_version(data, issues)
    artifact_id = _validate_id(data, issues)
    artifact_type = _validate_type(data, issues)
    relationships = _validate_relationships(data, issues)
    tags = _parse_tags(data, issues)

    metadata = ArtifactMetadata(
        # A non-int schema_version already produced an issue and was dropped to
        # None; an unsupported-but-int version is carried through as-is.
        schema_version=schema_version if isinstance(schema_version, int) else 0,
        id=artifact_id,
        type=artifact_type,
        relationships=relationships,
        tags=tags,
    )
    return metadata, issues


def _check_unknown_fields(data: dict, issues: list[Issue]) -> None:
    """Flag every key outside the supported envelope (ADR-025)."""
    for key in data:
        if key not in _SUPPORTED_FIELDS:
            issues.append(
                _issue(
                    "invalid-metadata-field",
                    f"unsupported frontmatter field: {key!r} "
                    f"(supported: {', '.join(_SUPPORTED_FIELDS)})",
                )
            )


def _validate_schema_version(data: dict, issues: list[Issue]) -> int | None:
    """Validate the required ``schema_version`` field.

    Returns the integer value (even when unsupported, so it survives onto the
    metadata) or None when it is absent or not an integer. ``bool`` is rejected
    despite being an ``int`` subclass.
    """
    if "schema_version" not in data:
        issues.append(
            _issue(
                "invalid-metadata-field",
                "frontmatter is missing required field 'schema_version'",
            )
        )
        return None
    value = data.get("schema_version")
    if not isinstance(value, int) or isinstance(value, bool):
        issues.append(
            _issue(
                "invalid-metadata-field",
                "frontmatter field 'schema_version' must be an integer",
            )
        )
        return None
    if value not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(
            _issue(
                "unsupported-schema-version",
                f"unsupported frontmatter schema_version: {value} "
                f"(supported: {', '.join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS)})",
            )
        )
    return value


def _validate_id(data: dict, issues: list[Issue]) -> str | None:
    """Validate the optional ``id`` field, returning it normalized or None."""
    value = data.get("id")
    if value is None:
        return None
    if not isinstance(value, str):
        issues.append(_issue("invalid-metadata-field", "frontmatter field 'id' must be a string"))
        return None
    if not is_valid_id(value):
        issues.append(
            _issue(
                "invalid-id-syntax",
                f"invalid artifact ID syntax: {value!r} "
                "(expected <KEY>-<12-char Crockford base32 suffix>, "
                "e.g. RAC-01JY4M8X2QZ7)",
            )
        )
        return None
    return normalize_id(value)


def _validate_type(data: dict, issues: list[Issue]) -> str | None:
    """Validate the optional ``type`` field against the spec registry."""
    value = data.get("type")
    if value is None:
        return None
    # Imported lazily: the spec registry imports back into core, so a top-level
    # import would form a cycle.
    from .artifacts import spec_for

    if not isinstance(value, str) or spec_for(value) is None:
        issues.append(
            _issue(
                "invalid-metadata-field",
                f"frontmatter field 'type' is not a registered artifact type: {value!r}",
            )
        )
        return None
    return value


def _validate_relationships(data: dict, issues: list[Issue]) -> dict[str, list[str]]:
    """Validate the optional ``relationships`` mapping (kind -> list of IDs).

    Returns the mapping with every target normalized, or ``{}`` when the field
    is absent or malformed.
    """
    value = data.get("relationships")
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(kind, str)
        and isinstance(targets, list)
        and all(isinstance(target, str) for target in targets)
        for kind, targets in value.items()
    ):
        issues.append(
            _issue(
                "invalid-metadata-field",
                "frontmatter field 'relationships' must map relationship "
                "kinds to lists of artifact IDs",
            )
        )
        return {}
    return {kind: [normalize_id(target) for target in targets] for kind, targets in value.items()}


def _parse_tags(data: dict, issues: list[Issue]) -> list[str]:
    """Validate the optional ``tags`` field — a list of non-empty strings."""
    tags = data.get("tags")
    if tags is None:
        return []
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
        issues.append(
            _issue(
                "invalid-metadata-field",
                "frontmatter field 'tags' must be a list of non-empty strings",
            )
        )
        return []
    return [t.strip() for t in tags]
