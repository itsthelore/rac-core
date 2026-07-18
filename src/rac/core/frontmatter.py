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
# A closing delimiter may also be the YAML document-end marker.
_CLOSERS = ("---", "...")

# The complete frontmatter field schema. One canonical location per field
# (ADR-025): anything else is invalid-metadata-field, not ignored. ``tags`` is
# the OKF-reserved descriptive field ADR-025 reserved and ADR-050 adopts —
# optional, additive, validated for shape only. Timestamps are deliberately
# absent: recency is git-derived, never stored in frontmatter (ADR-045).
_SUPPORTED_FIELDS = ("schema_version", "id", "type", "relationships", "tags")


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys (ADR-025)."""


def _no_duplicates(loader: _StrictLoader, node: yaml.MappingNode) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in seen
            if not duplicate:
                # `in` alone is not the full hashability probe: set.__contains__
                # coerces a set argument to frozenset, so a `!!set` key passes
                # the membership test and only add() raises.
                seen.add(key)
        except TypeError:
            # An unhashable key (`? []`, `[a]: v`, `? !!set {a}`) is malformed
            # input, never a crash: surface it as YAML-level failure like every
            # other envelope defect (the fuzz campaign's oracle-crash class,
            # repro pinned at rust/fuzz/pinned/oracle-crashes/unhashable-key/).
            raise yaml.MarkedYAMLError(
                problem=f"unhashable frontmatter key: {key!r}",
                problem_mark=key_node.start_mark,
            ) from None
        if duplicate:
            raise yaml.MarkedYAMLError(
                problem=f"duplicate frontmatter key: {key!r}",
                problem_mark=key_node.start_mark,
            )
    return loader.construct_mapping(node, deep=True)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


class _BoundedLoader(_StrictLoader):
    """Strict loading plus WS4 adversarial-input bounds (REQ-002).

    Forbids YAML aliases — which kills the "billion laughs" alias-expansion bomb
    at its source — and caps nesting depth so deeply nested input is rejected as
    a structured ``malformed-frontmatter`` issue before PyYAML recurses. Inherits
    ``_StrictLoader``'s duplicate-key rejection and ``SafeLoader``'s refusal to
    construct arbitrary objects.
    """

    # Per-instance nesting depth; the class default seeds each fresh loader.
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


def _expect(ok: bool, issues: list[Issue], message: str) -> bool:
    """Shared structural gate for the per-field frontmatter validators.

    Records an ``invalid-metadata-field`` issue with ``message`` unless ``ok``
    holds, and returns ``ok`` so a caller can short-circuit. Each validator owns
    its predicate and its message but routes rejection through here, so every
    wrong-shape field reports under the one code (ADR-060: share structural
    validation across per-type validators). Field problems that carry a *different*
    code — ``unsupported-schema-version``, ``invalid-id-syntax`` — are emitted
    directly by their validator, not through this helper.
    """
    if not ok:
        issues.append(_issue("invalid-metadata-field", message))
    return ok


def parse_frontmatter(raw: str) -> tuple[ArtifactMetadata | None, list[Issue]]:
    """Parse and schema-validate raw frontmatter YAML.

    Returns ``(metadata, issues)``. ``metadata`` is None when the block is
    unusable (malformed YAML, not a mapping, duplicate keys); field-level
    problems return the partially valid metadata alongside their issues so
    callers can still read what parsed.

    Issue order is part of the contract: unknown fields first, then
    ``schema_version``, ``id``, ``type``, ``relationships``, ``tags`` — the order
    the validators run below.
    """
    data, issues = _load_frontmatter_mapping(raw)
    if data is None:
        return None, issues

    _check_unknown_fields(data, issues)
    schema_version = _validate_schema_version(data, issues)
    artifact_id = _validate_id(data, issues)
    artifact_type = _validate_type(data, issues)
    relationships = _validate_relationships(data, issues)
    tags = _parse_tags(data, issues)

    metadata = ArtifactMetadata(
        schema_version=schema_version if isinstance(schema_version, int) else 0,
        id=artifact_id,
        type=artifact_type,
        relationships=relationships,
        tags=tags,
    )
    return metadata, issues


def _load_frontmatter_mapping(raw: str) -> tuple[dict | None, list[Issue]]:
    """Decode the raw YAML envelope into a mapping, or report why it is unusable.

    Returns ``(data, issues)``. On any envelope-level failure — oversize, invalid
    YAML, a duplicate key, or a non-mapping top level — ``data`` is None and
    ``issues`` holds the single terminal issue. On success ``data`` is the mapping
    and ``issues`` is empty, ready for the per-field validators to append to.
    """
    # Cap the raw block before PyYAML sees it (WS4, REQ-002), so an oversized
    # front matter cannot allocate unbounded ahead of validation.
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
        # Depth cap should pre-empt this, but never propagate a crash (REQ-002).
        return None, [_issue("malformed-frontmatter", "frontmatter nesting too deep to parse")]

    if not isinstance(data, dict):
        return None, [
            _issue(
                "malformed-frontmatter",
                "frontmatter must be a YAML mapping of supported fields",
            )
        ]
    return data, []


def _check_unknown_fields(data: dict, issues: list[Issue]) -> None:
    """Flag every key outside the canonical schema (ADR-025), in document order."""
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

    Returns the version when it is a supported int (an unsupported-but-integer
    version is returned as-is, with only its issue recorded); returns None when
    the field is absent or not an integer. ``bool`` is excluded because it is an
    ``int`` subclass but never a valid version.
    """
    schema_version = data.get("schema_version")
    if not _expect(
        "schema_version" in data,
        issues,
        "frontmatter is missing required field 'schema_version'",
    ):
        return schema_version
    if not _expect(
        isinstance(schema_version, int) and not isinstance(schema_version, bool),
        issues,
        "frontmatter field 'schema_version' must be an integer",
    ):
        return None
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append(
            _issue(
                "unsupported-schema-version",
                f"unsupported frontmatter schema_version: {schema_version} "
                f"(supported: {', '.join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS)})",
            )
        )
    return schema_version


def _validate_id(data: dict, issues: list[Issue]) -> str | None:
    """Validate the optional ``id`` field, returning the normalized id or None."""
    artifact_id = data.get("id")
    if artifact_id is None:
        return None
    if not _expect(isinstance(artifact_id, str), issues, "frontmatter field 'id' must be a string"):
        return None
    if not is_valid_id(artifact_id):
        issues.append(
            _issue(
                "invalid-id-syntax",
                f"invalid artifact ID syntax: {artifact_id!r} "
                "(expected <KEY>-<12-char Crockford base32 suffix>, "
                "e.g. RAC-01JY4M8X2QZ7)",
            )
        )
        return None
    return normalize_id(artifact_id)


def _validate_type(data: dict, issues: list[Issue]) -> str | None:
    """Validate the optional ``type`` field against the artifact spec registry."""
    artifact_type = data.get("type")
    if artifact_type is None:
        return None
    # Registered against the spec registry lazily to avoid a core cycle.
    from .artifacts import spec_for

    if not _expect(
        isinstance(artifact_type, str) and spec_for(artifact_type) is not None,
        issues,
        f"frontmatter field 'type' is not a registered artifact type: {artifact_type!r}",
    ):
        return None
    return artifact_type


def _validate_relationships(data: dict, issues: list[Issue]) -> dict[str, list[str]]:
    """Validate the optional ``relationships`` map and normalize its target ids."""
    relationships = data.get("relationships")
    if relationships is None:
        return {}
    well_formed = isinstance(relationships, dict) and all(
        isinstance(kind, str)
        and isinstance(targets, list)
        and all(isinstance(t, str) for t in targets)
        for kind, targets in relationships.items()
    )
    if not _expect(
        well_formed,
        issues,
        "frontmatter field 'relationships' must map relationship kinds to lists of artifact IDs",
    ):
        return {}
    return {kind: [normalize_id(t) for t in targets] for kind, targets in relationships.items()}


def _parse_tags(data: dict, issues: list[Issue]) -> list[str]:
    """Validate the optional ``tags`` field — a list of non-empty strings."""
    tags = data.get("tags")
    if tags is None:
        return []
    if not _expect(
        isinstance(tags, list) and all(isinstance(t, str) and t.strip() for t in tags),
        issues,
        "frontmatter field 'tags' must be a list of non-empty strings",
    ):
        return []
    return [t.strip() for t in tags]
