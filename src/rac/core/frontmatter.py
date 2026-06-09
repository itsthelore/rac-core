"""YAML frontmatter parsing — the artifact metadata envelope (ADR-025, v0.7.11).

``split_frontmatter`` separates a leading ``---`` block from the Markdown body
(reporting the line offset so downstream diagnostics keep file-accurate line
numbers); ``parse_frontmatter`` turns the raw YAML into a validated
:class:`~rac.core.metadata.ArtifactMetadata` plus a list of issues.

Parsing is strict where ADR-025 demands it: malformed YAML, duplicate keys,
unknown fields, wrong types, and unsupported schema versions are all
actionable errors — never silently normalized. Artifacts without frontmatter
are untouched (legacy support is a parser guarantee, not a special case).
PyYAML's ``SafeLoader`` already refuses arbitrary object construction; the
subclass below adds duplicate-key rejection, which stock YAML accepts.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .metadata import (
    SUPPORTED_SCHEMA_VERSIONS,
    ArtifactMetadata,
    is_valid_id,
    normalize_id,
)
from .models import Issue

_DELIMITER = "---"
# A closing delimiter may also be the YAML document-end marker.
_CLOSERS = ("---", "...")

# The complete frontmatter field schema. One canonical location per field
# (ADR-025): anything else is invalid-metadata-field, not ignored.
_SUPPORTED_FIELDS = ("schema_version", "id", "type", "relationships")


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (ADR-025)."""


def _no_duplicates(loader: _StrictLoader, node: yaml.MappingNode):
    seen: set = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise yaml.MarkedYAMLError(
                problem=f"duplicate frontmatter key: {key!r}",
                problem_mark=key_node.start_mark,
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates
)


@dataclass
class FrontmatterSplit:
    """A document separated into raw frontmatter and Markdown body."""

    raw: str | None  # YAML text between the delimiters, or None when absent
    body: str  # the Markdown body (whole text when no frontmatter)
    line_offset: int  # body line N is file line N + line_offset
    unterminated: bool = False  # opened with --- but never closed


def split_frontmatter(text: str) -> FrontmatterSplit:
    """Split a leading ``---`` frontmatter block from ``text``.

    Only a block starting at the very first line counts (ADR-025: a *leading*
    YAML frontmatter block). An opening delimiter with no closing line is
    reported via ``unterminated`` and the whole text is treated as body so
    parsing can still proceed and validation can surface the error.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != _DELIMITER:
        return FrontmatterSplit(raw=None, body=text, line_offset=0)
    for i in range(1, len(lines)):
        if lines[i].strip() in _CLOSERS:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            return FrontmatterSplit(raw=raw, body=body, line_offset=i + 1)
    return FrontmatterSplit(raw=None, body=text, line_offset=0, unterminated=True)


def _issue(code: str, message: str, line: int | None = None) -> Issue:
    return Issue("error", code, message, line)


def parse_frontmatter(raw: str) -> tuple[ArtifactMetadata | None, list[Issue]]:
    """Parse and schema-validate raw frontmatter YAML.

    Returns ``(metadata, issues)``. ``metadata`` is None when the block is
    unusable (malformed YAML, not a mapping, duplicate keys); field-level
    problems return the partially valid metadata alongside their issues so
    callers can still read what parsed.
    """
    issues: list[Issue] = []
    try:
        data = yaml.load(raw, Loader=_StrictLoader)
    except yaml.MarkedYAMLError as exc:
        if exc.problem and "duplicate frontmatter key" in exc.problem:
            return None, [_issue("duplicate-frontmatter-key", exc.problem)]
        return None, [
            _issue("malformed-frontmatter", f"frontmatter is not valid YAML: {exc.problem}")
        ]
    except yaml.YAMLError as exc:
        return None, [
            _issue("malformed-frontmatter", f"frontmatter is not valid YAML: {exc}")
        ]

    if not isinstance(data, dict):
        return None, [
            _issue(
                "malformed-frontmatter",
                "frontmatter must be a YAML mapping of supported fields",
            )
        ]

    for key in data:
        if key not in _SUPPORTED_FIELDS:
            issues.append(
                _issue(
                    "invalid-metadata-field",
                    f"unsupported frontmatter field: {key!r} "
                    f"(supported: {', '.join(_SUPPORTED_FIELDS)})",
                )
            )

    schema_version = data.get("schema_version")
    if "schema_version" not in data:
        issues.append(
            _issue(
                "invalid-metadata-field",
                "frontmatter is missing required field 'schema_version'",
            )
        )
    elif not isinstance(schema_version, int) or isinstance(schema_version, bool):
        issues.append(
            _issue(
                "invalid-metadata-field",
                "frontmatter field 'schema_version' must be an integer",
            )
        )
        schema_version = None
    elif schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(
            _issue(
                "unsupported-schema-version",
                f"unsupported frontmatter schema_version: {schema_version} "
                f"(supported: {', '.join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS)})",
            )
        )

    artifact_id = data.get("id")
    if artifact_id is not None:
        if not isinstance(artifact_id, str):
            issues.append(
                _issue(
                    "invalid-metadata-field",
                    "frontmatter field 'id' must be a string",
                )
            )
            artifact_id = None
        elif not is_valid_id(artifact_id):
            issues.append(
                _issue(
                    "invalid-id-syntax",
                    f"invalid artifact ID syntax: {artifact_id!r} "
                    "(expected <KEY>-<12-char Crockford base32 suffix>, "
                    "e.g. RAC-01JY4M8X2QZ7)",
                )
            )
            artifact_id = None
        else:
            artifact_id = normalize_id(artifact_id)

    artifact_type = data.get("type")
    if artifact_type is not None:
        # Registered against the spec registry lazily to avoid a core cycle.
        from .artifacts import spec_for

        if not isinstance(artifact_type, str) or spec_for(artifact_type) is None:
            issues.append(
                _issue(
                    "invalid-metadata-field",
                    f"frontmatter field 'type' is not a registered artifact type: "
                    f"{artifact_type!r}",
                )
            )
            artifact_type = None

    relationships = data.get("relationships")
    parsed_relationships: dict[str, list[str]] = {}
    if relationships is not None:
        if not isinstance(relationships, dict) or not all(
            isinstance(kind, str)
            and isinstance(targets, list)
            and all(isinstance(t, str) for t in targets)
            for kind, targets in relationships.items()
        ):
            issues.append(
                _issue(
                    "invalid-metadata-field",
                    "frontmatter field 'relationships' must map relationship "
                    "kinds to lists of artifact IDs",
                )
            )
        else:
            parsed_relationships = {
                kind: [normalize_id(t) for t in targets]
                for kind, targets in relationships.items()
            }

    metadata = ArtifactMetadata(
        schema_version=schema_version if isinstance(schema_version, int) else 0,
        id=artifact_id,
        type=artifact_type,
        relationships=parsed_relationships,
    )
    return metadata, issues
