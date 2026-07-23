"""Note-tool (PKM) ingest — Obsidian and its siblings (ADR-079).

Note-tool exports (Obsidian, Logseq, Notion, Roam) are *already* Markdown,
organised as a graph of interlinked notes, so they are ingested by
**normalisation**, not markitdown (ADR-072): each note becomes a RAC-shaped
draft, wikilinks become **candidate** ``## Related`` references for a human to
promote (never asserted edges — ADR-074, ADR-065), and conversion is
deterministic and offline (ADR-002) — identical export yields byte-identical
drafts, nothing is dropped (lossless by default), and nothing is overwritten.

This is the directory/graph analogue of :mod:`asdecided.services.ingest`'s file
converters: a :class:`VaultConverter` takes an export *directory* and emits a
*set* of drafts, whereas a ``DocumentConverter`` takes one binary file and emits
one Markdown string. The markitdown path for binary documents is untouched, and
these converters pull no third-party dependency — they are pure text
normalisation over stdlib.

Obsidian is the first tool (this module's reference converter); Logseq, Notion,
and Roam register beside it and reuse the shared wikilink resolution below, so
one tool's export-format drift cannot break another.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

# Directories that are tool configuration, not notes: never walked for content.
_SKIP_DIRS = {".obsidian", ".trash", ".git", "logseq", "bak", ".recycle"}

# A wikilink: optional ``!`` (embed/transclusion), then ``[[ ... ]]``. The inner
# text is ``target`` with an optional ``#heading`` / ``^block`` fragment and an
# optional ``|alias``: ``[[target#frag|alias]]``.
_WIKILINK_RE = re.compile(r"(?P<embed>!?)\[\[(?P<inner>[^\[\]]+)\]\]")

# A standard Markdown inline link ``[text](url)``. Notion exports use these (with
# URL-encoded relative paths to hashed ``.md`` files) rather than wikilinks.
_MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<url>[^)]+)\)")


@dataclass(frozen=True)
class Wikilink:
    """One parsed ``[[wikilink]]`` occurrence (ADR-079)."""

    raw: str  # the full matched text, e.g. "[[Note|alias]]" or "![[embed]]"
    target: str  # the note-name portion, trimmed
    alias: str | None
    fragment: str | None  # heading (#) or block (^) reference, without the sigil
    embed: bool  # True for ![[...]] transclusions


@dataclass
class NoteDraft:
    """One note normalised into a reviewable RAC-shaped draft (ADR-003).

    ``related`` are the resolved wikilink targets offered as candidate
    ``## Related`` references — candidates for human promotion, not asserted
    edges. ``warnings`` records ambiguous and unresolved links left inline
    verbatim, so the human review starts from a complete, honest draft.
    """

    source_path: str  # POSIX, relative to the vault root
    suggested_filename: str  # POSIX, relative to the output root
    markdown: str
    related: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class VaultIngestResult:
    """The full outcome of ingesting one export directory (ADR-003).

    ``skipped_sources`` names export files that were recognised but not converted
    — Notion database CSVs, whose rows already arrive as their own ``.md`` page
    exports (so converting the CSV too would double-import). Reported, never
    silently dropped.
    """

    converter: str
    root: str
    drafts: list[NoteDraft] = field(default_factory=list)
    skipped_sources: list[str] = field(default_factory=list)

    @property
    def note_count(self) -> int:
        return len(self.drafts)

    @property
    def resolved_link_count(self) -> int:
        return sum(len(d.related) for d in self.drafts)

    @property
    def warning_count(self) -> int:
        return sum(len(d.warnings) for d in self.drafts)


@runtime_checkable
class VaultConverter(Protocol):
    """Turns a note-tool export directory into a set of RAC-shaped drafts.

    The graph analogue of ``DocumentConverter``: ``detect`` recognises the
    export shape (a marker directory/file) so a bare ``decided ingest <dir>`` routes
    deterministically, and ``convert_vault`` walks the export and normalises each
    note. Implementations pull no third-party dependency.
    """

    name: str

    def detect(self, root: Path) -> bool: ...

    def convert_vault(self, root: Path) -> VaultIngestResult: ...


# --- Shared normalisation (reused by every note-tool converter) --------------


def parse_wikilinks(text: str) -> list[Wikilink]:
    """Every ``[[wikilink]]`` in ``text``, in document order (deterministic)."""
    links: list[Wikilink] = []
    for match in _WIKILINK_RE.finditer(text):
        inner = match.group("inner")
        target_part, _, alias = inner.partition("|")
        alias = alias.strip() or None
        # A fragment is a #heading or ^block ref on the target; either sigil ends
        # the note name. Split on the first of whichever appears.
        target = target_part
        fragment: str | None = None
        for sigil in ("#", "^"):
            if sigil in target:
                target, _, fragment = target.partition(sigil)
                fragment = fragment.strip() or None
                break
        links.append(
            Wikilink(
                raw=match.group(0),
                target=target.strip(),
                alias=alias,
                fragment=fragment,
                embed=match.group("embed") == "!",
            )
        )
    return links


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split leading ``---`` YAML frontmatter from the body, both preserved.

    Returns ``(frontmatter_block, body)`` where ``frontmatter_block`` includes
    its ``---`` fences (or is empty when there is none). Lossless: the bytes are
    partitioned, never rewritten.
    """
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---", 4)
    if end == -1:
        return "", text
    # Include the closing fence line and the newline after it, if present.
    fence_end = text.find("\n", end + 1)
    if fence_end == -1:
        return text, ""
    return text[: fence_end + 1], text[fence_end + 1 :]


class _Resolver:
    """Deterministic wikilink resolution over one export's note set.

    Obsidian-style: a link names a note, resolved by exact relative path first,
    then by unique basename stem. Multiple stems sharing a name are *ambiguous*
    (reported, never guessed); no match is *unresolved* (left inline). Purely a
    function of the note paths, so results are byte-identical across machines.
    """

    def __init__(self, note_paths: list[str]) -> None:
        self._by_relpath = {p.casefold(): p for p in note_paths}
        self._by_stem: dict[str, list[str]] = {}
        for path in note_paths:
            stem = Path(path).stem.casefold()
            self._by_stem.setdefault(stem, []).append(path)

    def resolve(self, target: str) -> tuple[str | None, bool]:
        """Return ``(resolved_relpath, ambiguous)`` for a link target.

        ``resolved_relpath`` is None when unresolved; ``ambiguous`` is True when
        a bare name matched more than one note. A *path-qualified* target
        (containing ``/``) resolves only by exact relative path; a *bare* name
        resolves by unique basename stem, and a name shared by several notes is
        ambiguous — reported, never guessed to one (REQ-003).
        """
        key = target.strip().replace("\\", "/")
        if "/" in key:
            for candidate in (key, f"{key}.md"):
                hit = self._by_relpath.get(candidate.casefold())
                if hit is not None:
                    return hit, False
            return None, False
        # A bare name resolves by stem, whether or not the link wrote the ``.md``
        # extension (Obsidian omits it, Notion includes it).
        stem_matches = self._by_stem.get(Path(key).stem.casefold(), [])
        if len(stem_matches) == 1:
            return stem_matches[0], False
        if len(stem_matches) > 1:
            return None, True
        return None, False


def _link_url(target: str) -> str:
    """A link URL safe in inline Markdown: angle-bracketed when it needs it."""
    if any(ch in target for ch in " ()"):
        return f"<{target}>"
    return target


def _normalise_body(body: str, resolver: _Resolver, self_path: str, draft: NoteDraft) -> str:
    """Rewrite resolved note links inline; leave the rest verbatim (lossless).

    A resolved, non-embed ``[[Note]]`` becomes a plain Markdown link and its
    target is recorded as a candidate ``## Related`` reference. Embeds
    (``![[...]]``, often media), self-links, and ambiguous/unresolved links are
    left exactly as written — nothing is dropped, nothing is guessed (REQ-003,
    REQ-007). Deterministic: a single left-to-right pass.
    """
    related: list[str] = []
    warnings: list[str] = []
    result: list[str] = []
    last = 0
    for match in _WIKILINK_RE.finditer(body):
        result.append(body[last : match.start()])
        last = match.end()
        link = parse_wikilinks(match.group(0))[0]
        if link.embed:
            result.append(link.raw)  # transclusions/media stay verbatim
            continue
        resolved, ambiguous = resolver.resolve(link.target)
        if resolved is not None:
            label = link.alias or link.target
            result.append(f"[{label}]({_link_url(resolved)})")
            # A note linking to itself is not a candidate relationship.
            if resolved != self_path and resolved not in related:
                related.append(resolved)
        else:
            result.append(link.raw)  # unresolved/ambiguous: leave inline
            reason = "ambiguous" if ambiguous else "unresolved"
            warnings.append(f"{reason} wikilink {link.raw}")
    result.append(body[last:])
    draft.related = related
    draft.warnings = warnings
    return "".join(result)


def _normalise_notion_body(body: str, resolver: _Resolver, self_path: str, draft: NoteDraft) -> str:
    """Collect candidate links from a Notion page; leave the body verbatim.

    Notion exports use standard Markdown links (``[text](Page%20Name%20<hash>.md)``)
    with URL-encoded relative paths, not wikilinks. An internal link to another
    exported ``.md`` page becomes a candidate ``## Related`` reference; external
    links (``http``/``mailto``) and non-page links are left alone. The body is not
    rewritten — the links are already valid Markdown — so it is lossless by
    construction (REQ-007). Deterministic: a single left-to-right pass.
    """
    from urllib.parse import unquote

    related: list[str] = []
    warnings: list[str] = []
    for match in _MD_LINK_RE.finditer(body):
        url = match.group("url").strip()
        if url.startswith(("http://", "https://", "mailto:", "#", "//")):
            continue
        target = unquote(url.split("#", 1)[0].split("?", 1)[0])
        if not target.endswith(".md"):
            continue  # only links to other exported pages are relationships
        resolved, ambiguous = resolver.resolve(target)
        if resolved is not None:
            if resolved != self_path and resolved not in related:
                related.append(resolved)
        else:
            reason = "ambiguous" if ambiguous else "unresolved"
            warnings.append(f"{reason} link [{match.group('text')}]({url})")
    draft.related = related
    draft.warnings = warnings
    return body


_CANDIDATE_NOTE = (
    "<!-- Candidate relationships imported from wikilinks (ADR-079): review and "
    "promote to real references before this becomes an artifact; not asserted. -->"
)


def _assemble_draft(frontmatter: str, body: str, draft: NoteDraft) -> str:
    """Compose the draft: preserved frontmatter, normalised body, candidate links.

    Lossless (REQ-007): the frontmatter block and body bytes are preserved; the
    only addition is a clearly-marked candidate ``## Related`` section listing the
    resolved targets, appended so a human promotes them (never asserted).
    """
    parts = [frontmatter, body]
    text = "".join(parts)
    if draft.related:
        if not text.endswith("\n"):
            text += "\n"
        related_lines = "\n".join(f"- {target}" for target in draft.related)
        text += f"\n{_CANDIDATE_NOTE}\n\n## Related\n\n{related_lines}\n"
    return text


# A per-tool body normaliser: rewrites/collects candidate links against the
# note's own path and records them on the draft, returning the body to assemble.
_Normaliser = Callable[[str, _Resolver, str, NoteDraft], str]


def _emit_draft(
    source_path: str,
    suggested_filename: str,
    frontmatter: str,
    body: str,
    resolver: _Resolver,
    normalise: _Normaliser,
) -> NoteDraft:
    """Assemble one note into a draft — the emit step every converter shares.

    ``source_path`` and ``suggested_filename`` are carried **separately**: for
    the Markdown-directory tools they are the same relative path, but Roam's
    ``source_path`` is the raw page title while ``suggested_filename`` is its
    sanitised :func:`_roam_filename` — both are byte-pinned, so they must not be
    collapsed into one value. ``suggested_filename`` is the note's own path for
    self-link detection. ``normalise`` (wikilink or Notion-Markdown) rewrites the
    body and records candidate ``## Related`` targets on the draft;
    :func:`_assemble_draft` then composes preserved frontmatter + normalised body
    + candidate links.
    """
    draft = NoteDraft(source_path=source_path, suggested_filename=suggested_filename, markdown="")
    normalised = normalise(body, resolver, suggested_filename, draft)
    draft.markdown = _assemble_draft(frontmatter, normalised, draft)
    return draft


def _walk_notes(root: Path) -> list[str]:
    """Every ``.md`` note under ``root``, POSIX-relative, sorted (deterministic)."""
    notes: list[str] = []
    for path in root.rglob("*.md"):
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts[:-1]):
            continue
        notes.append(path.relative_to(root).as_posix())
    return sorted(notes)


def _convert_note_dir(root: Path, name: str, normalise: _Normaliser) -> VaultIngestResult:
    """Walk a Markdown-directory export and emit one draft per note (ADR-079).

    The shared body every directory-based note tool reuses: one deterministic
    walk feeds the resolver and the per-note emit (frontmatter preserved, links
    normalised via ``normalise`` and offered as candidate ``## Related``
    references, everything else verbatim). Only the link ``normalise`` differs
    between tools — wikilinks for Obsidian/Logseq, Markdown links for Notion —
    so each converter passes its own. Tool-specific syntax a converter does not
    rewrite (Logseq block references and properties, media embeds) flows through
    untouched, so losslessness holds by construction.
    """
    note_paths = _walk_notes(root)
    resolver = _Resolver(note_paths)
    result = VaultIngestResult(converter=name, root=str(root))
    for rel in note_paths:
        text = (root / rel).read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        result.drafts.append(_emit_draft(rel, rel, frontmatter, body, resolver, normalise))
    return result


def _convert_vault(root: Path, name: str) -> VaultIngestResult:
    """Ingest a wikilink-based vault (Obsidian, Logseq) through the shared walk."""
    return _convert_note_dir(root, name, _normalise_body)


class ObsidianConverter:
    """Ingest an Obsidian vault: ``.md`` notes, ``[[wikilinks]]``, YAML frontmatter.

    Detects the vault by its ``.obsidian/`` configuration directory. Each note is
    normalised through the shared wikilink resolver, its frontmatter preserved
    verbatim, and its resolved links offered as candidate ``## Related``
    references — deterministic, offline, and lossless (ADR-079, ADR-002).
    """

    name = "obsidian"

    def detect(self, root: Path) -> bool:
        return (root / ".obsidian").is_dir()

    def convert_vault(self, root: Path) -> VaultIngestResult:
        return _convert_vault(root, self.name)


class LogseqConverter:
    """Ingest a Logseq graph: ``pages/`` and ``journals/`` Markdown, ``[[page links]]``.

    Detects the graph by its ``logseq/`` configuration directory. Logseq shares
    Obsidian's ``[[page]]`` link syntax, so it reuses the same resolver: page
    links become candidate ``## Related`` references, ambiguous or unresolved ones
    are reported, never guessed. Logseq-specific syntax — block references
    ``((block-id))``, ``key:: value`` properties, and outliner ``- `` bullets — is
    left verbatim (lossless); block-reference resolution and ``#tag`` page links
    are later enhancements, not guessed here.
    """

    name = "logseq"

    def detect(self, root: Path) -> bool:
        return (root / "logseq").is_dir()

    def convert_vault(self, root: Path) -> VaultIngestResult:
        return _convert_vault(root, self.name)


# The Notion export signature: a page filename ends in a space plus the page's
# 32-hex id (dashes stripped), e.g. ``My Page 1a2b…f9.md``.
_NOTION_FILE_RE = re.compile(r" [0-9a-f]{32}\.md$")


class NotionConverter:
    """Ingest a Notion "Markdown & CSV" export: hashed pages, standard links, CSVs.

    Detected by Notion's hashed page filenames. Notion uses standard Markdown
    links (not wikilinks), so it normalises through :func:`_normalise_notion_body`
    rather than the wikilink resolver — internal page links become candidate
    ``## Related`` references, everything else verbatim (lossless). Database CSVs
    are reported as ``skipped_sources`` rather than converted: Notion already
    exports each row as its own ``.md`` page, so the CSV is a redundant index
    (mapping CSVs to artifacts is a later enhancement, per the design's open
    question).
    """

    name = "notion"

    def detect(self, root: Path) -> bool:
        return any(_NOTION_FILE_RE.search(path.name) for path in root.rglob("*.md"))

    def convert_vault(self, root: Path) -> VaultIngestResult:
        result = _convert_note_dir(root, self.name, _normalise_notion_body)
        result.skipped_sources = sorted(
            path.relative_to(root).as_posix() for path in root.rglob("*.csv")
        )
        return result


# --- Roam (a JSON graph export, not a directory of Markdown) -----------------


def parse_roam_pages(text: str) -> list[dict] | None:
    """Parse Roam's JSON graph export, or None if ``text`` is not that shape.

    Roam exports the whole graph as one JSON file: a list of page objects, each
    with a ``title`` and a tree of ``children`` blocks (``{"string": ...,
    "children": [...]}``). Recognised structurally so detection needs no marker
    file.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, list) or not data:
        return None
    if not all(isinstance(page, dict) for page in data):
        return None
    if not any("title" in page and "children" in page for page in data):
        return None
    return data


def _flatten_roam_blocks(blocks: object, depth: int = 0) -> list[str]:
    """Flatten a Roam block tree into indented Markdown outliner bullets.

    Each block's ``string`` becomes a ``- `` bullet indented by its depth; nested
    ``children`` recurse. Block strings (the content, including ``[[links]]``,
    ``#tags``, and ``((block refs))``) are preserved verbatim; Roam's internal
    block metadata (uids, timestamps) is structural, not content, and is not
    carried.
    """
    lines: list[str] = []
    if not isinstance(blocks, list):
        return lines
    for block in blocks:
        if not isinstance(block, dict):
            continue
        string = block.get("string", "")
        if not isinstance(string, str):
            string = ""
        lines.append("  " * depth + "- " + string)
        lines.extend(_flatten_roam_blocks(block.get("children"), depth + 1))
    return lines


def _roam_filename(title: str) -> str:
    """A flat, deterministic draft filename for a Roam page title."""
    return f"{title.replace('/', '-').replace(chr(92), '-').strip()}.md"


def convert_roam_pages(pages: list[dict], source: str) -> VaultIngestResult:
    """Turn parsed Roam pages into drafts, reusing the shared wikilink machinery.

    Each page's block tree is flattened to outliner Markdown with its title as an
    ``# H1`` (so the title is never lost), then run through the same
    ``[[wikilink]]`` normalisation as Obsidian and Logseq: ``[[Page]]`` links
    resolve to candidate ``## Related`` references, ``((block refs))`` and
    ``#tags`` stay verbatim. Deterministic and offline (ADR-079, ADR-002).
    """
    titled = [page for page in pages if isinstance(page.get("title"), str)]
    note_paths = [_roam_filename(page["title"]) for page in titled]
    resolver = _Resolver(note_paths)
    result = VaultIngestResult(converter="roam", root=source)
    for page in titled:
        title = page["title"]
        rel = _roam_filename(title)
        body_lines = _flatten_roam_blocks(page.get("children"))
        body = f"# {title}\n\n" + "\n".join(body_lines)
        if body_lines:
            body += "\n"
        # source_path is the raw title, suggested_filename the sanitised
        # _roam_filename — carried separately (both byte-pinned). No frontmatter:
        # the H1-plus-outliner body is synthesised, not read from a file.
        result.drafts.append(_emit_draft(title, rel, "", body, resolver, _normalise_body))
    return result


def roam_result_for_file(path: Path) -> VaultIngestResult | None:
    """Ingest a bare Roam ``.json`` export file, or None if it is not one.

    Lets ``decided ingest graph.json`` work directly — the common case, since Roam
    exports the graph as a single JSON download rather than a directory.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    pages = parse_roam_pages(text)
    if pages is None:
        return None
    return convert_roam_pages(pages, str(path))


class RoamConverter:
    """Ingest a Roam JSON graph export: one file, a tree of pages and blocks.

    Detects a Roam ``.json`` export inside the directory (Roam exports one JSON
    file for the whole graph). Unlike the Markdown-directory tools, its input is a
    block tree, so it flattens each page to outliner Markdown and then reuses the
    shared wikilink normalisation — ``[[page links]]`` become candidate
    ``## Related`` references, block references and tags stay verbatim.
    """

    name = "roam"

    def detect(self, root: Path) -> bool:
        return any(roam_result_for_file(path) is not None for path in sorted(root.glob("*.json")))

    def convert_vault(self, root: Path) -> VaultIngestResult:
        for path in sorted(root.glob("*.json")):
            result = roam_result_for_file(path)
            if result is not None:
                return result
        return VaultIngestResult(converter=self.name, root=str(root))


# Registry — first converter whose ``detect`` matches wins; ``--from`` selects by
# name. Order is deterministic.
_VAULT_CONVERTERS: list[VaultConverter] = [
    ObsidianConverter(),
    LogseqConverter(),
    NotionConverter(),
    RoamConverter(),
]


def vault_converters() -> list[VaultConverter]:
    """Every registered note-tool converter, in registration order."""
    return list(_VAULT_CONVERTERS)


def converter_by_name(name: str) -> VaultConverter | None:
    """The converter with ``name`` (the ``--from`` selector), or None."""
    for converter in _VAULT_CONVERTERS:
        if converter.name == name:
            return converter
    return None


def detect_converter(root: Path) -> VaultConverter | None:
    """The converter whose export shape ``root`` matches, or None (deterministic)."""
    for converter in _VAULT_CONVERTERS:
        if converter.detect(root):
            return converter
    return None


def converter_names() -> list[str]:
    """The names accepted by ``--from``, sorted."""
    return sorted(c.name for c in _VAULT_CONVERTERS)
