"""Agent-rules projection — `rac export --agent-rules [--check]` (v0.21.15).

Distils the *live* corpus into a small, stable "managed block" that committed
per-client agent-context files (``CLAUDE.md``, ``AGENTS.md``, ``.cursor/rules``,
``.github/copilot-instructions.md``) carry, so an AI coding agent sees the
decisions the team has already settled and stops re-litigating them (roadmap
v0.21.15; governed by ADR-067).

ADR-067 fixes the boundary this service must honour exactly:

- The projection is **distilled**, not the whole corpus: one pointer line per
  live decision (its canonical identifier + title, optionally its category) —
  the "what did we already decide / what is ruled out" digest — never the
  decision bodies. Inlining the corpus is an explicit non-goal (attention
  budget; the agent reaches the ``lore`` MCP tools for ground truth).
- "Live" is deterministic and structural (ADR-002): a decision is live when its
  ``## Status`` is *Accepted* and it is not retired (Superseded/Deprecated).
  Retired states come from the type spec (``spec.retired_status``), so the rule
  is spec-driven, never a hard-coded set — the same definition relationship
  validation already uses (ADR-051). No semantic verdict enters the engine.
- The block is **drift-guarded**: it embeds a provenance digest (sha256 over the
  canonical projection), and ``--check`` re-derives the digest from the live
  corpus and fails when a committed file's embedded digest differs or is absent.
  The digest — not a timestamp — is the freshness signal, so two generations of
  the same corpus are byte-identical (ADR-002).

This is a pure projection over the corpus walk; it computes nothing semantic and
holds no model. Generation only ever *replaces the managed block*; any prose a
user keeps outside the markers in their own ``CLAUDE.md`` is preserved verbatim.

JSON shapes returned here are a stable public contract (ADR-007).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from rac.core.artifacts import spec_for
from rac.core.corpus import walk_corpus
from rac.core.identity import artifact_identifier
from rac.core.models import Product

# The artifact type whose live members the block distils. ADR-067 scopes the
# managed block to decisions (bans + closed-decision pointers); roadmap scope
# fences are an optional future addition and are deliberately not projected here
# (kept minimal and deterministic — see the roadmap's Initiative 1 note).
_DECISION_TYPE = "decision"

# The canonical "live" status for a decision: structural, case-insensitive, the
# first non-empty line of ``## Status`` (the same first-line rule inspect and
# relationship validation use). Not a semantic judgement — a string match.
_LIVE_STATUS = "accepted"

# Stable managed-block markers. HTML comments survive Markdown rendering, so the
# block stays invisible in a rendered CLAUDE.md while remaining machine-locatable.
# The BEGIN marker carries the provenance digest so ``--check`` can compare
# without re-deriving the file's own content hash.
_BEGIN_PREFIX = "<!-- BEGIN RAC MANAGED BLOCK (digest: "
_BEGIN_SUFFIX = ") -->"
_END_MARKER = "<!-- END RAC MANAGED BLOCK -->"

# A short header inside the block, so a human opening the file knows what owns it
# and how to regenerate it. Deterministic — no timestamp.
_GENERATED_HEADER = (
    "<!-- Managed by `rac export --agent-rules`. Edit decisions in rac/, not here;"
    " content outside this block is preserved. -->"
)


@dataclass(frozen=True)
class AgentRulesTarget:
    """One per-client agent-context file the managed block is written into.

    ``client`` is the stable selector value (``--client``); ``path`` is the
    file's location relative to the output root.
    """

    client: str
    path: str

    def to_dict(self) -> dict:
        return {"client": self.client, "path": self.path}


# The four targets ADR-067 / the roadmap name, in deterministic (selector) order.
# Cursor uses a single ``.cursor/rules`` file (a plain rules file carrying the
# managed block); the others are Markdown.
TARGETS: tuple[AgentRulesTarget, ...] = (
    AgentRulesTarget("agents", "AGENTS.md"),
    AgentRulesTarget("claude", "CLAUDE.md"),
    AgentRulesTarget("copilot", ".github/copilot-instructions.md"),
    AgentRulesTarget("cursor", ".cursor/rules"),
)

_TARGET_BY_CLIENT = {t.client: t for t in TARGETS}


def targets_for(clients: list[str] | None) -> list[AgentRulesTarget]:
    """Resolve ``--client`` selectors to targets (all four when ``None``).

    Order is always the deterministic ``TARGETS`` order, regardless of the order
    selectors were given, so output never depends on argument order.
    """
    if not clients:
        return list(TARGETS)
    wanted = set(clients)
    return [t for t in TARGETS if t.client in wanted]


def unknown_clients(clients: list[str] | None) -> list[str]:
    """Selectors with no matching target (caller turns these into a usage error)."""
    if not clients:
        return []
    return sorted({c for c in clients if c not in _TARGET_BY_CLIENT})


@dataclass(frozen=True)
class AgentRulesEntry:
    """One distilled live-decision pointer (identifier + title, optional category).

    A pointer, never a body: this is the "already decided / ruled out" digest the
    agent reads, with the decision itself reachable through the ``lore`` tools.
    """

    identifier: str
    title: str
    category: str | None = None

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "title": self.title,
            "category": self.category,
        }


@dataclass
class AgentRulesProjection:
    """The deterministic projection of the live corpus (entries + digest).

    ``digest`` is a sha256 over the *canonical* serialization of the ordered
    entries (formatting-independent), so the same corpus state yields the same
    digest regardless of how the block is rendered for a given client.
    """

    entries: list[AgentRulesEntry] = field(default_factory=list)
    digest: str = ""

    def to_dict(self) -> dict:
        return {
            "digest": self.digest,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _first_status_line(product: Product) -> str:
    """First non-empty line of ``## Status``, casefolded (empty when absent)."""
    body = product.sections.get("status")
    if not body:
        return ""
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return first.casefold()


def _category(product: Product) -> str | None:
    """First non-empty line of ``## Category`` (the decision's classification)."""
    body = product.sections.get("category")
    if not body:
        return None
    return next((line.strip() for line in body.splitlines() if line.strip()), None) or None


def _is_live_decision(entry_product: Product) -> bool:
    """True when a decision is Accepted and not retired (Superseded/Deprecated).

    Spec-driven retirement (ADR-051): retired states come from the decision
    spec, so the rule honours every retired status the type declares rather than
    a hard-coded pair. Structural only — no semantics.
    """
    status = _first_status_line(entry_product)
    if status != _LIVE_STATUS:
        return False
    spec = spec_for(_DECISION_TYPE)
    retired = {s.casefold() for s in (spec.retired_status if spec else ())}
    return status not in retired


def _canonical_payload(entries: list[AgentRulesEntry]) -> str:
    """Canonical, formatting-independent serialization the digest hashes.

    ``sort_keys`` + ``separators`` pin byte-for-byte stability; the entries are
    already ordered by identifier, so the digest depends only on corpus content.
    """
    return json.dumps(
        [entry.to_dict() for entry in entries],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def build_agent_rules_block(directory: str, recursive: bool = True) -> AgentRulesProjection:
    """Distil the live corpus under ``directory`` into the agent-rules projection.

    Walks the corpus once, keeps every live (Accepted, non-retired) decision as a
    one-line pointer, orders deterministically by canonical identifier, and
    computes the provenance digest. An empty corpus yields an empty projection
    with the digest of an empty entry list (a valid, stable state).
    """
    entries: list[AgentRulesEntry] = []
    for entry in walk_corpus(directory, recursive=recursive):
        if entry.artifact_type != _DECISION_TYPE:
            continue
        if not _is_live_decision(entry.product):
            continue
        spec = spec_for(_DECISION_TYPE)
        identifier = artifact_identifier(entry.product, spec, str(entry.path))
        entries.append(
            AgentRulesEntry(
                identifier=identifier,
                title=entry.product.title or identifier,
                category=_category(entry.product),
            )
        )

    # Deterministic order: by identifier (case-insensitive, then exact for ties).
    entries.sort(key=lambda e: (e.identifier.casefold(), e.identifier))
    digest = hashlib.sha256(_canonical_payload(entries).encode("utf-8")).hexdigest()
    return AgentRulesProjection(entries=entries, digest=digest)


def render_managed_block(projection: AgentRulesProjection) -> str:
    """The managed-block text (markers + distilled pointers), client-independent.

    Identical for every target: the block is plain Markdown that lives equally
    well inside a ``.md`` file or a Cursor rules file. The digest rides in the
    BEGIN marker so ``--check`` can read it without re-hashing the file.
    """
    lines = [
        f"{_BEGIN_PREFIX}{projection.digest}{_BEGIN_SUFFIX}",
        _GENERATED_HEADER,
        "## Settled decisions (RAC)",
        "",
        "These decisions are already accepted. Do not re-open or contradict them;"
        " ask the `lore` MCP tools (`get_artifact`, `search_artifacts`) for the"
        " full text before proposing a change that touches one.",
        "",
    ]
    if not projection.entries:
        lines.append("_No live decisions recorded yet._")
    else:
        for entry in projection.entries:
            suffix = f" _({entry.category})_" if entry.category else ""
            lines.append(f"- **{entry.identifier}** — {entry.title}{suffix}")
    lines.append(_END_MARKER)
    return "\n".join(lines)


def embedded_digest(file_text: str) -> str | None:
    """The digest carried in a file's BEGIN marker, or ``None`` when no block.

    Reads only the marker, never re-hashes the file — the cheap comparison the
    ``--check`` drift gate relies on.
    """
    start = file_text.find(_BEGIN_PREFIX)
    if start == -1:
        return None
    after = start + len(_BEGIN_PREFIX)
    end = file_text.find(_BEGIN_SUFFIX, after)
    if end == -1:
        return None
    return file_text[after:end].strip() or None


def merge_managed_block(existing: str | None, block: str) -> str:
    """Splice ``block`` into ``existing``, preserving everything outside the markers.

    When the file already has a managed block, only that span is replaced — the
    user's own prose before and after is kept byte-for-byte. When there is no
    block, the new one is appended after the existing content (or stands alone in
    a fresh file). The result always ends with a single trailing newline.
    """
    if existing is None or existing.strip() == "":
        return block + "\n"

    begin = existing.find(_BEGIN_PREFIX)
    end = existing.find(_END_MARKER)
    if begin != -1 and end != -1 and end > begin:
        end += len(_END_MARKER)
        before = existing[:begin]
        after = existing[end:]
        merged = f"{before}{block}{after}"
        if not merged.endswith("\n"):
            merged += "\n"
        return merged

    # No managed block yet: append one, separated by a blank line.
    body = existing.rstrip("\n")
    return f"{body}\n\n{block}\n"


# --- Generate / check results -------------------------------------------------

# Per-file outcome states (stable JSON contract, ADR-007).
STATE_WRITTEN = "written"  # the file did not exist; created with the block
STATE_UPDATED = "updated"  # the file existed; its managed block changed
STATE_IN_SYNC = "in-sync"  # the file's embedded digest already matches
STATE_STALE = "stale"  # (--check) embedded digest differs from the corpus
STATE_MISSING = "missing"  # (--check) the file or its managed block is absent


@dataclass(frozen=True)
class AgentRulesFileResult:
    """The outcome for one target file in a generate or check run."""

    client: str
    path: str
    state: str

    def to_dict(self) -> dict:
        return {"client": self.client, "path": self.path, "state": self.state}


@dataclass
class AgentRulesResult:
    """The outcome of a ``--agent-rules`` generate or check run.

    ``mode`` is ``"generate"`` or ``"check"``; ``digest`` is the live projection
    digest; ``files`` are the per-target outcomes in deterministic order.
    """

    mode: str
    digest: str
    root: str
    files: list[AgentRulesFileResult] = field(default_factory=list)

    @property
    def drifted(self) -> bool:
        """True when any checked file is stale or missing its block (gate fails)."""
        return any(f.state in (STATE_STALE, STATE_MISSING) for f in self.files)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "digest": self.digest,
            "root": self.root,
            "files": [f.to_dict() for f in self.files],
        }


def generate_agent_rules(
    directory: str,
    root: str,
    clients: list[str] | None = None,
    recursive: bool = True,
) -> AgentRulesResult:
    """Write/update the managed block in each target under ``root``.

    Derives the projection once, then for each target merges the rendered block
    into the file (preserving outside content), reporting whether each file was
    created, updated, or already in sync. Writes are skipped when the file's
    embedded digest already matches — generation is idempotent and byte-stable.
    """
    projection = build_agent_rules_block(directory, recursive=recursive)
    block = render_managed_block(projection)
    root_path = Path(root)

    results: list[AgentRulesFileResult] = []
    for target in targets_for(clients):
        dest = root_path / target.path
        existing = dest.read_text(encoding="utf-8") if dest.exists() else None

        if existing is not None and embedded_digest(existing) == projection.digest:
            results.append(AgentRulesFileResult(target.client, target.path, STATE_IN_SYNC))
            continue

        merged = merge_managed_block(existing, block)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(merged, encoding="utf-8")
        state = STATE_WRITTEN if existing is None else STATE_UPDATED
        results.append(AgentRulesFileResult(target.client, target.path, state))

    return AgentRulesResult("generate", projection.digest, str(root_path), results)


def check_agent_rules(
    directory: str,
    root: str,
    clients: list[str] | None = None,
    recursive: bool = True,
) -> AgentRulesResult:
    """Compare each committed target's embedded digest to the live projection.

    Never writes. A target is ``in-sync`` when its embedded digest matches the
    freshly derived projection digest, ``stale`` when it differs, and ``missing``
    when the file or its managed block is absent. ``result.drifted`` is the gate:
    true when any target is stale or missing (the caller exits non-zero).
    """
    projection = build_agent_rules_block(directory, recursive=recursive)
    root_path = Path(root)

    results: list[AgentRulesFileResult] = []
    for target in targets_for(clients):
        dest = root_path / target.path
        if not dest.exists():
            results.append(AgentRulesFileResult(target.client, target.path, STATE_MISSING))
            continue
        digest = embedded_digest(dest.read_text(encoding="utf-8"))
        if digest is None:
            results.append(AgentRulesFileResult(target.client, target.path, STATE_MISSING))
        elif digest == projection.digest:
            results.append(AgentRulesFileResult(target.client, target.path, STATE_IN_SYNC))
        else:
            results.append(AgentRulesFileResult(target.client, target.path, STATE_STALE))

    return AgentRulesResult("check", projection.digest, str(root_path), results)
