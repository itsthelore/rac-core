"""Safe artifact-id rename — the engine-owned refactor contract (v0.21.18).

Renaming an artifact id by hand corrupts cross-artifact links: every inbound
``## Related X`` / ``## Supersedes`` reference that named the old id silently
dangles, and the artifact's own declared identity drifts out of step with the
references that point at it. This module is the deterministic, reversible engine
contract that computes — and applies — the corpus-wide edit set for a rename, so
the editor (and any other thin client, ADR-063) never computes references
itself: it previews and invokes this plan.

Design (roadmap v0.21.18 — Safe Rename & Refactor, Initiative 1):

* **Resolution reuses the one identity model.** ``old_ref`` is resolved against
  the same alias resolution index relationship validation uses
  (:func:`rac.services.relationships._build_resolution_index`), so "what does
  this reference point at" has a single answer across the engine (ADR-016).
* **The raw reference text is the source of truth (ADR-016).** An edit replaces
  exactly the ``old_ref`` token inside a relationship list line, preserving the
  surrounding text (``- ADR-001 (blocked)`` -> ``- ADR-099 (blocked)``). It does
  *not* re-serialize the parsed document — formatting is preserved by editing the
  file text line-by-line.
* **Token-specific, not alias-broad.** Rename operates on the ``old_ref`` token a
  reference actually wrote. A referencing line that names a *different* alias of
  the same target (e.g. the canonical frontmatter id) is left untouched — the
  safe, predictable behaviour, and the one that stays reversible.
* **Additive and reversible (ADR-007).** The plan is a stable dict; computing and
  applying ``new_ref`` -> ``old_ref`` after a rename restores the original bytes.
* **No semantic inference.** Resolution, collision, and token replacement are all
  deterministic; nothing is guessed.

The target's *own* identity is rewritten only when ``old_ref`` matches an
**editable, declared** identity field in the file — the canonical frontmatter
``id``, a ``## ID`` section value, or the type's ``spec.id_field`` value. When
``old_ref`` resolves only through a filename-derived alias (the filename prefix
or stem) there is no in-file token to rewrite without renaming the file, which is
out of scope (Non-Goals); rather than leave ``new_ref`` dangling, the rename
refuses with a clear reason.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from re import Match

from rac.core.artifacts import ArtifactSpec, spec_for
from rac.core.corpus import CorpusEntry, walk_corpus
from rac.core.identity import artifact_identifiers
from rac.core.models import Product
from rac.services.relationships import (
    RELATIONSHIP_SECTIONS,
    _build_resolution_index,
)

# Stable reason codes for an empty/invalid plan (part of the JSON contract,
# ADR-007). They name *why* a rename cannot proceed, deterministically.
REASON_OLD_NOT_FOUND = "old-ref-not-found"
REASON_OLD_AMBIGUOUS = "old-ref-ambiguous"
REASON_NEW_COLLIDES = "new-ref-collides"
REASON_NEW_INVALID = "new-ref-invalid"
REASON_OLD_FILENAME_ONLY = "old-ref-filename-only"

# Where a rewritten identity token lived in the target file — reported in the plan
# so a reviewer can see exactly which identity field the rename touched.
IDENTITY_FRONTMATTER = "frontmatter_id"
IDENTITY_ID_SECTION = "id_section"
IDENTITY_ID_FIELD = "id_field"

# A human identifier shape: ``<letters>-<digits>`` (e.g. ``ADR-099``), optionally
# with further ``-suffix`` segments. ``new_ref`` must be a non-empty token with no
# surrounding whitespace; this guards against a caller passing a whole line or an
# empty string. It deliberately does *not* require a canonical RAC-id — a rename
# names a human-readable identifier, the form references actually use.
_NEW_REF_RE = re.compile(r"^[A-Za-z][\w.-]*$")

# A well-formed leading Markdown list marker, mirroring the relationships parser:
# the marker (and the whitespace after it) is preserved on the rewritten line; the
# reference text after it is where the token is replaced.
_LIST_MARKER_RE = re.compile(r"^(\s*(?:[-*+]|\d+\.)\s+)(.*)$")

# Frontmatter ``id:`` line, e.g. ``id: RAC-KV80X4TH9AZR`` — value may be quoted.
_FRONTMATTER_ID_RE = re.compile(r"^(\s*id\s*:\s*)(['\"]?)([^'\"#]+?)(\2)(\s*(?:#.*)?)$")

# A ``## ID`` heading (case-insensitive, whitespace-trimmed).
_ID_HEADING_RE = re.compile(r"^\s*##\s+id\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class RenameEdit:
    """One line-level replacement in the corpus-wide edit set.

    ``line`` is 1-based. ``old_line``/``new_line`` are the exact line text
    (without the trailing newline) before and after the edit; applying the plan
    replaces ``old_line`` with ``new_line`` at ``line`` in ``path``. The kind
    distinguishes an inbound reference rewrite from the target's identity rewrite.
    """

    path: str
    line: int
    old_line: str
    new_line: str
    kind: str  # "reference" | "identity"


@dataclass
class RenamePlan:
    """A deterministic, reversible corpus-wide rename edit set (ADR-007).

    ``ok`` is True when ``old_ref`` resolved to exactly one target, ``new_ref`` is
    a valid non-colliding identifier, and the target's identity is rewritable.
    When ``ok`` is False, ``reason`` carries one of the stable ``REASON_*`` codes
    and ``edits`` is empty. ``target_path`` is the resolved artifact (the one
    whose identity is being renamed); ``identity_field`` names which identity the
    rename rewrote (one of the ``IDENTITY_*`` constants) or None when the plan is
    invalid.
    """

    directory: str
    recursive: bool
    old_ref: str
    new_ref: str
    ok: bool
    target_path: str | None = None
    identity_field: str | None = None
    reason: str | None = None
    edits: list[RenameEdit] = field(default_factory=list)

    @property
    def reference_edits(self) -> int:
        return sum(1 for e in self.edits if e.kind == "reference")

    @property
    def identity_edits(self) -> int:
        return sum(1 for e in self.edits if e.kind == "identity")

    @property
    def files_changed(self) -> int:
        return len({e.path for e in self.edits})

    def to_dict(self) -> dict:
        """Stable JSON shape (ADR-007). Additive: keys are never repurposed."""
        return {
            "directory": self.directory,
            "recursive": self.recursive,
            "old_ref": self.old_ref,
            "new_ref": self.new_ref,
            "ok": self.ok,
            "reason": self.reason,
            "target_path": self.target_path,
            "identity_field": self.identity_field,
            "files_changed": self.files_changed,
            "reference_edits": self.reference_edits,
            "identity_edits": self.identity_edits,
            "edits": [
                {
                    "path": e.path,
                    "line": e.line,
                    "old_line": e.old_line,
                    "new_line": e.new_line,
                    "kind": e.kind,
                }
                for e in self.edits
            ],
        }


@dataclass
class RenameResult:
    """The outcome of applying a :class:`RenamePlan` to disk."""

    directory: str
    old_ref: str
    new_ref: str
    applied: bool
    files_changed: int
    reference_edits: int
    identity_edits: int
    target_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "directory": self.directory,
            "old_ref": self.old_ref,
            "new_ref": self.new_ref,
            "applied": self.applied,
            "target_path": self.target_path,
            "files_changed": self.files_changed,
            "reference_edits": self.reference_edits,
            "identity_edits": self.identity_edits,
        }


def _items(directory: str, recursive: bool) -> list[tuple[str, Product, ArtifactSpec | None]]:
    """Every document under ``directory`` as ``(path, product, spec)`` (one walk).

    Sorted-path order (``walk_corpus`` is deterministic), so the plan below is
    deterministic by construction.
    """
    entries: list[CorpusEntry] = list(walk_corpus(directory, recursive=recursive))
    return [(str(e.path), e.product, spec_for(e.artifact_type)) for e in entries]


def _resolve_target(
    items: list[tuple[str, Product, ArtifactSpec | None]],
    old_ref: str,
) -> tuple[str | None, str | None]:
    """Resolve ``old_ref`` to exactly one target path.

    Returns ``(target_path, reason)``: a path with no reason on success, or
    ``(None, REASON_*)`` when the reference is unknown or ambiguous. Reuses the
    same alias resolution index relationship validation uses (ADR-016).
    """
    index = _build_resolution_index(items)
    targets = sorted({p for p, _ in index.get(old_ref.casefold(), [])})
    if not targets:
        return None, REASON_OLD_NOT_FOUND
    if len(targets) > 1:
        return None, REASON_OLD_AMBIGUOUS
    return targets[0], None


def _collides(
    items: list[tuple[str, Product, ArtifactSpec | None]],
    new_ref: str,
    target_path: str,
) -> bool:
    """True when ``new_ref`` already names an identifier of some *other* artifact.

    Renaming onto an existing identifier would create a duplicate identity, so the
    rename refuses. The target itself is excluded — ``new_ref`` legitimately
    becomes the target's identity. Matching is case-insensitive, mirroring
    resolution.
    """
    folded = new_ref.casefold()
    for path, product, spec in items:
        if path == target_path:
            continue
        if folded in {i.casefold() for i in artifact_identifiers(product, spec, path)}:
            return True
    return False


def _replace_token(text: str, old_ref: str, new_ref: str) -> str | None:
    """Replace the leading ``old_ref`` token in reference ``text`` (after the marker).

    The reference token is the identifier at the start of the reference text;
    anything after it (a note like ``(blocked)``, a trailing path segment) is
    preserved verbatim (ADR-016). Matching is case-insensitive and anchored at the
    start, so only a reference that *names* ``old_ref`` is rewritten. Returns the
    rewritten text, or None when ``text`` does not begin with the token.
    """
    # Fold exactly the prefix that is sliced off below: casefold can change a
    # string's length (ß → ss), so folding all of ``text`` and slicing by
    # ``len(old_ref)`` could split mid-token and corrupt the reference.
    folded_old = old_ref.casefold()
    if text[: len(old_ref)].casefold() != folded_old:
        return None
    rest = text[len(old_ref) :]
    # The token must be whole: the next character (if any) must not be an
    # identifier character, else ``ADR-1`` would match inside ``ADR-10``.
    if rest and (rest[0].isalnum() or rest[0] in "_-."):
        return None
    return new_ref + rest


def _reference_edits(
    items: list[tuple[str, Product, ArtifactSpec | None]],
    target_path: str,
    old_ref: str,
    new_ref: str,
) -> list[RenameEdit]:
    """Every inbound relationship line whose reference token equals ``old_ref``.

    Scans the raw file text for each artifact's relationship sections, finds the
    list line carrying the reference, and rewrites just the ``old_ref`` token.
    Working from the raw text (not the parsed Product) preserves formatting and
    yields exact line numbers. Deterministic: artifacts in sorted-path order,
    lines in file order.
    """
    edits: list[RenameEdit] = []
    for path, product, spec in items:
        if spec is None:
            continue
        # The relationship sections this artifact actually declares and populates.
        present = {
            section
            for section in spec.optional
            if section in RELATIONSHIP_SECTIONS and product.sections.get(section)
        }
        if not present:
            continue
        raw_lines = Path(path).read_text(encoding="utf-8").splitlines()
        for line_no, raw in _relationship_reference_lines(raw_lines, present):
            marker_match = _LIST_MARKER_RE.match(raw)
            prefix, ref_text = (
                (marker_match.group(1), marker_match.group(2)) if marker_match else ("", raw)
            )
            rewritten = _replace_token(ref_text.strip(), old_ref, new_ref)
            if rewritten is None:
                continue
            # Preserve the original leading whitespace/marker and any trailing
            # whitespace by rebuilding only the reference portion.
            new_line = prefix + raw[len(prefix) :].replace(ref_text.strip(), rewritten, 1)
            if new_line != raw:
                edits.append(
                    RenameEdit(
                        path=path,
                        line=line_no,
                        old_line=raw,
                        new_line=new_line,
                        kind="reference",
                    )
                )
    return edits


def _relationship_reference_lines(
    raw_lines: list[str],
    sections: set[str],
) -> list[tuple[int, str]]:
    """1-based ``(line_no, raw_line)`` for every reference line in ``sections``.

    Walks the raw Markdown tracking the current ``##`` section; inside a relevant
    relationship section, yields each non-empty line. Heading match mirrors the
    parser (trimmed, case-insensitive). The raw text is the source of truth, so
    this avoids re-serializing the parsed document.
    """
    result: list[tuple[int, str]] = []
    current: str | None = None
    for i, raw in enumerate(raw_lines, start=1):
        stripped = raw.strip()
        if stripped.startswith("## "):
            current = stripped[3:].strip().casefold()
            continue
        if stripped.startswith("#"):
            current = None  # any other heading ends the section
            continue
        if current in sections and stripped:
            result.append((i, raw))
    return result


def _identity_edit(
    target_path: str,
    product: Product,
    spec: ArtifactSpec | None,
    old_ref: str,
    new_ref: str,
) -> tuple[RenameEdit | None, str | None, str | None]:
    """The target's own identity rewrite, when ``old_ref`` is an editable declaration.

    Returns ``(edit, identity_field, reason)``. Precedence mirrors
    :func:`rac.core.identity.artifact_identifier` for the *declared* (editable)
    fields only — frontmatter ``id``, ``## ID`` section value, ``spec.id_field``
    value. A filename-derived match (prefix or stem) has no editable token, so it
    returns ``(None, None, REASON_OLD_FILENAME_ONLY)`` — the caller refuses rather
    than leave ``new_ref`` dangling.
    """
    raw = Path(target_path).read_text(encoding="utf-8")
    raw_lines = raw.splitlines()
    folded_old = old_ref.casefold()

    # 1. Canonical frontmatter ``id`` — only rewritten when ``old_ref`` IS it.
    if product.metadata is not None and product.metadata.id:
        if product.metadata.id.casefold() == folded_old:
            edit = _frontmatter_id_edit(raw_lines, old_ref, new_ref)
            if edit is not None:
                return edit, IDENTITY_FRONTMATTER, None

    # 2. ``## ID`` section value.
    edit = _id_section_edit(raw_lines, folded_old, new_ref)
    if edit is not None:
        return edit, IDENTITY_ID_SECTION, None

    # 3. The type's declared ``spec.id_field`` section value.
    if spec is not None and spec.id_field:
        edit = _named_section_value_edit(raw_lines, spec.id_field, folded_old, new_ref)
        if edit is not None:
            return edit, IDENTITY_ID_FIELD, None

    # 4. Filename-derived alias only — no editable in-file identity token.
    return None, None, REASON_OLD_FILENAME_ONLY


def _frontmatter_id_edit(raw_lines: list[str], old_ref: str, new_ref: str) -> RenameEdit | None:
    """Rewrite the value of the frontmatter ``id:`` line (within the leading ---)."""
    if not raw_lines or raw_lines[0].strip() != "---":
        return None
    for i in range(1, len(raw_lines)):
        if raw_lines[i].strip() == "---":
            break
        m = _FRONTMATTER_ID_RE.match(raw_lines[i])
        if m and m.group(3).strip().casefold() == old_ref.casefold():
            new_line = f"{m.group(1)}{m.group(2)}{new_ref}{m.group(4)}{m.group(5)}"
            if new_line != raw_lines[i]:
                return RenameEdit(
                    path="",  # filled by caller
                    line=i + 1,
                    old_line=raw_lines[i],
                    new_line=new_line,
                    kind="identity",
                )
    return None


def _id_section_edit(raw_lines: list[str], folded_old: str, new_ref: str) -> RenameEdit | None:
    """Rewrite the first value line under a ``## ID`` heading."""
    return _section_first_value_edit(raw_lines, _ID_HEADING_RE.match, folded_old, new_ref)


def _named_section_value_edit(
    raw_lines: list[str], section: str, folded_old: str, new_ref: str
) -> RenameEdit | None:
    """Rewrite the first value line under the ``## <section>`` heading."""
    pattern = re.compile(rf"^\s*##\s+{re.escape(section)}\s*$", re.IGNORECASE)
    return _section_first_value_edit(raw_lines, pattern.match, folded_old, new_ref)


def _section_first_value_edit(
    raw_lines: list[str],
    heading_match: Callable[[str], Match[str] | None],
    folded_old: str,
    new_ref: str,
) -> RenameEdit | None:
    """Find a heading via ``heading_match`` and rewrite its first value-line token.

    The first non-empty line under the heading is the section's single value
    (the same first-value rule :func:`rac.core.identity._first_value` uses). The
    ``old_ref`` token is replaced, preserving any list marker and trailing text.
    """
    in_section = False
    for i, raw in enumerate(raw_lines):
        stripped = raw.strip()
        if stripped.startswith("#"):
            in_section = bool(heading_match(raw))
            continue
        if not in_section or not stripped:
            continue
        # First value line of the section.
        marker = _LIST_MARKER_RE.match(raw)
        prefix, value = (marker.group(1), marker.group(2)) if marker else ("", raw)
        rewritten = _replace_token(value.strip(), folded_old, new_ref)
        in_section = False  # only the first value line is the identity
        if rewritten is None:
            continue
        new_line = prefix + raw[len(prefix) :].replace(value.strip(), rewritten, 1)
        if new_line != raw:
            return RenameEdit(path="", line=i + 1, old_line=raw, new_line=new_line, kind="identity")
    return None


def compute_rename(
    directory: str,
    old_ref: str,
    new_ref: str,
    recursive: bool = True,
) -> RenamePlan:
    """Compute the deterministic, reversible corpus-wide rename edit set (v0.21.18).

    ``old_ref`` must resolve to exactly one artifact; ``new_ref`` must be a valid
    identifier that does not already collide with another artifact's identity, and
    the target's identity must be rewritable in-file (not filename-only). On any
    failure the plan is ``ok=False`` with a stable ``REASON_*`` code and no edits.

    The edit set, in deterministic order, is: every inbound relationship line whose
    reference token equals ``old_ref`` (rewritten token, surrounding text
    preserved), followed by the target's own identity rewrite. Edits are sorted by
    path then line, so the plan is byte-identical across runs (ADR-002 / ADR-007).
    """
    new_ref = new_ref.strip()
    if not _NEW_REF_RE.match(new_ref):
        return RenamePlan(
            directory=directory,
            recursive=recursive,
            old_ref=old_ref,
            new_ref=new_ref,
            ok=False,
            reason=REASON_NEW_INVALID,
        )

    items = _items(directory, recursive)
    target_path, reason = _resolve_target(items, old_ref)
    if target_path is None:
        return RenamePlan(
            directory=directory,
            recursive=recursive,
            old_ref=old_ref,
            new_ref=new_ref,
            ok=False,
            reason=reason,
        )

    # A no-op rename (new == old, case-insensitively) is treated as a collision-free
    # success only if it is genuinely identical; otherwise the collision check runs.
    if new_ref.casefold() != old_ref.casefold() and _collides(items, new_ref, target_path):
        return RenamePlan(
            directory=directory,
            recursive=recursive,
            old_ref=old_ref,
            new_ref=new_ref,
            ok=False,
            target_path=target_path,
            reason=REASON_NEW_COLLIDES,
        )

    by_path = {p: (prod, spec) for p, prod, spec in items}
    target_product, target_spec = by_path[target_path]
    identity_edit, identity_field, id_reason = _identity_edit(
        target_path, target_product, target_spec, old_ref, new_ref
    )
    if identity_edit is None:
        # No editable in-file identity equals ``old_ref`` (filename-only alias):
        # the rename cannot make ``new_ref`` resolve without renaming the file,
        # which is out of scope. Refuse rather than leave a dangling new id.
        return RenamePlan(
            directory=directory,
            recursive=recursive,
            old_ref=old_ref,
            new_ref=new_ref,
            ok=False,
            target_path=target_path,
            reason=id_reason,
        )

    edits = _reference_edits(items, target_path, old_ref, new_ref)
    # Attach the target path to the identity edit (built without it).
    edits.append(
        RenameEdit(
            path=target_path,
            line=identity_edit.line,
            old_line=identity_edit.old_line,
            new_line=identity_edit.new_line,
            kind="identity",
        )
    )
    edits.sort(key=lambda e: (e.path, e.line))

    return RenamePlan(
        directory=directory,
        recursive=recursive,
        old_ref=old_ref,
        new_ref=new_ref,
        ok=True,
        target_path=target_path,
        identity_field=identity_field,
        edits=edits,
    )


def apply_rename(plan: RenamePlan) -> RenameResult:
    """Apply ``plan``'s edits to disk (exact line replacements).

    Reversible: applying ``compute_rename(dir, new, old)`` after this restores the
    original bytes. Each file is read, its target lines are replaced (1-based,
    verified against ``old_line`` to fail loudly on drift), and rewritten with its
    original trailing-newline shape preserved. An invalid plan applies nothing.
    """
    if not plan.ok:
        return RenameResult(
            directory=plan.directory,
            old_ref=plan.old_ref,
            new_ref=plan.new_ref,
            applied=False,
            files_changed=0,
            reference_edits=0,
            identity_edits=0,
            target_path=plan.target_path,
        )

    by_file: dict[str, list[RenameEdit]] = {}
    for edit in plan.edits:
        by_file.setdefault(edit.path, []).append(edit)

    for path, edits in by_file.items():
        original = Path(path).read_text(encoding="utf-8")
        had_final_newline = original.endswith("\n")
        lines = original.splitlines()
        for edit in edits:
            idx = edit.line - 1
            if idx < 0 or idx >= len(lines) or lines[idx] != edit.old_line:
                raise ValueError(
                    f"rename: stale plan for {path} line {edit.line}: "
                    "file changed since the plan was computed"
                )
            lines[idx] = edit.new_line
        text = "\n".join(lines)
        if had_final_newline:
            text += "\n"
        Path(path).write_text(text, encoding="utf-8")

    return RenameResult(
        directory=plan.directory,
        old_ref=plan.old_ref,
        new_ref=plan.new_ref,
        applied=True,
        files_changed=plan.files_changed,
        reference_edits=plan.reference_edits,
        identity_edits=plan.identity_edits,
        target_path=plan.target_path,
    )


__all__ = [
    "RenameEdit",
    "RenamePlan",
    "RenameResult",
    "compute_rename",
    "apply_rename",
    "REASON_OLD_NOT_FOUND",
    "REASON_OLD_AMBIGUOUS",
    "REASON_NEW_COLLIDES",
    "REASON_NEW_INVALID",
    "REASON_OLD_FILENAME_ONLY",
    "IDENTITY_FRONTMATTER",
    "IDENTITY_ID_SECTION",
    "IDENTITY_ID_FIELD",
]
