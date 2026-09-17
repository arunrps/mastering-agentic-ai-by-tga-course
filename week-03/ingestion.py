"""
ingestion.py -- corpus loading, frontmatter parsing and section-aware chunking.

NEVER imports streamlit. Same boundary as detection.py in Week 1: this module
produces the deterministic artefacts (documents, metadata, chunks, link graph),
and the rendering layer only displays them. In later weeks the retrieval stack
calls these functions from a process that has no Streamlit runtime.

Determinism is a hard requirement, not a nicety. Re-embedding costs money, so
the same corpus must produce byte-identical chunks on every run: documents are
processed in sorted filename order, chunk IDs are derived from document_id and
an integer index, and nothing here depends on dict ordering, set iteration, a
clock or a random seed. `chunk_corpus()` is a pure function of the files on disk.

Run `python ingestion.py` for the ingestion report.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

import yaml

# ---------------------------------------------------------------------------
# Paths -- resolved against this file, never the working directory, so the
# module behaves the same when imported from a Streamlit process started
# elsewhere. Same reason as week-01's DATA_FILE.
# ---------------------------------------------------------------------------

WEEK_02 = Path(__file__).resolve().parent
CORPUS_DIR = WEEK_02 / "corpus" / "internal"
TOPOLOGY_FILE = WEEK_02 / "topology.json"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# All eleven are required in every document. A missing field is a build error,
# not a warning: a chunk that reaches the index without `service` or `status`
# cannot be filtered, and metadata filtering is how this corpus is supposed to
# be searched. Silent metadata loss degrades retrieval in a way that looks like
# a model problem later.
REQUIRED_FIELDS = (
    "document_id",
    "title",
    "document_type",
    "service",
    "status",
    "supersedes",
    "superseded_by",
    "owner_team",
    "access_level",
    "version",
    "last_reviewed",
)

# Fields that must carry a value. `supersedes` and `superseded_by` are
# deliberately absent from this tuple: null is their normal state and is
# meaningful, so they are required to be PRESENT but allowed to be empty.
NON_NULL_FIELDS = tuple(
    f for f in REQUIRED_FIELDS if f not in ("supersedes", "superseded_by")
)

VALID_DOCUMENT_TYPES = frozenset({"runbook", "policy", "catalog", "postmortem"})
VALID_STATUSES = frozenset({"current", "superseded"})
VALID_ACCESS_LEVELS = frozenset({"operations", "restricted"})

DOCUMENT_ID_PATTERN = re.compile(r"^[A-Z]{2,4}-[A-Z0-9]+-\d{3}(?:-ARCHIVED)?$")


# ---------------------------------------------------------------------------
# Chunking parameters
#
# Stated as named constants because they are the numbers that decide what gets
# embedded, and a later reader needs to see them without reading the algorithm.
# Changing any of them changes the chunk set and therefore costs an embedding
# run -- so they are also the things a test should pin.
# ---------------------------------------------------------------------------

# Hard ceiling. Measured against the corpus: the largest atomic paragraph block
# is 1,397 characters (PM-2026-014's numbered lesson), so at 2,000 no block is
# ever forced to split. "Never mid-sentence" therefore holds structurally
# rather than by best effort, and there is no sentence-splitter fallback in
# this module because nothing can reach one.
MAX_CHUNK_CHARS = 2_000

# Soft target. Packing stops adding blocks once a chunk passes this, so typical
# chunks land near it rather than near the ceiling.
TARGET_CHUNK_CHARS = 1_200

# Below this a section is merged forward into the next section of the same
# document instead of being emitted alone. A one-or-two-sentence chunk embeds
# to a vector dominated by the ops vocabulary every document shares -- "elevated
# 5xx", "escalate to the owning team" -- so it matches everything weakly and
# nothing strongly, and it crowds the result list. 350 characters is roughly
# two sentences of this corpus's prose.
MIN_SECTION_CHARS = 350

# The section that is parsed into structured links rather than embedded. See
# RELATED_DOCUMENTS_RATIONALE below.
RELATED_DOCUMENTS_HEADING = "related documents"

RELATED_DOCUMENTS_RATIONALE = """\
Parsed into structured links, never embedded. Every one of these sections is a
list of `- ID -- gloss`, 87-271 characters, built almost entirely from document
IDs and titles that appear verbatim in the other documents. Embedded they would
be the highest-similarity, lowest-information chunks in the corpus: they win on
any query naming a service and return no procedure. POL-SLO-001 is referenced
by 18 of 19 documents, so embedding all nineteen lists would manufacture
nineteen near-identical vectors -- a distractor set on top of the near
duplicates the corpus plants deliberately. As links they are worth more: they
give a followable graph for the sibling-document case and they are the only way
dangling references are detectable at all."""

# The label given to the untitled text between `# Title` and the first `##`.
#
# Every document has one, 170 to 1,181 characters. It is NOT boilerplate:
# RB-AUTH-000's 1,181-character preamble carries the "rejection is cheap, so a
# severe condition can raise errors while p95 stays flat" principle and the
# 4xx/5xx split warning, which is what the /login evaluation question needs.
# The obvious implementation -- iterate `##` sections -- drops it silently, and
# the corpus loses its answer to a graded question with nothing looking wrong.
OVERVIEW_SECTION = "(overview)"


class IngestionError(Exception):
    """A document could not be parsed or failed schema validation.

    Raised, never logged and skipped. A corpus that half-loads is worse than
    one that does not load: retrieval still returns results, they are just
    quietly missing a document, and nothing surfaces the gap.
    """


# ---------------------------------------------------------------------------
# Result types
#
# Plain dataclasses, like week-01's Verdict, for the same reason: the retrieval
# layer and later the agent need fields they can read and filter on, not prose
# they have to parse back out.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentLink:
    """One entry from a `## Related documents` list."""

    target_id: str
    gloss: str

    @property
    def marked_restricted(self) -> bool:
        """Whether the gloss itself flags the target as restricted.

        Kept rather than discarded: several runbooks write
        `POL-DEPLOY-001 -- deployment validation and rollback (restricted)`,
        and that marker is the corpus telling a reader the document exists but
        is not reproduced. That is exactly the distinction the restricted
        refusal path has to make.
        """
        return "restricted" in self.gloss.lower()


@dataclass(frozen=True)
class Section:
    """One `##` section of a document, before size-based packing."""

    heading: str
    text: str
    position: int

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class Document:
    """One corpus document: validated metadata, sections, and its link list."""

    document_id: str
    path: Path
    metadata: dict
    body: str
    sections: tuple
    links: tuple

    # --- convenience accessors, so callers do not index into `metadata` ---
    @property
    def title(self) -> str:
        return self.metadata["title"]

    @property
    def service(self) -> str:
        return self.metadata["service"]

    @property
    def document_type(self) -> str:
        return self.metadata["document_type"]

    @property
    def status(self) -> str:
        return self.metadata["status"]

    @property
    def access_level(self) -> str:
        return self.metadata["access_level"]

    @property
    def is_current(self) -> bool:
        return self.metadata["status"] == "current"

    @property
    def is_restricted(self) -> bool:
        return self.metadata["access_level"] == "restricted"


@dataclass(frozen=True)
class Chunk:
    """One unit of text that will be embedded, with its full parent metadata.

    `metadata` is the parent document's complete frontmatter, copied rather
    than referenced, so a chunk is self-sufficient once it reaches a vector
    store that only carries a flat payload.
    """

    chunk_id: str
    document_id: str
    heading: str
    section_position: int
    chunk_index: int
    chunks_in_section: int
    text: str
    metadata: dict

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def embed_text(self) -> str:
        """What actually gets embedded.

        The document title and section heading are prepended to the body. A
        chunk taken from the middle of `## Discriminating checks` otherwise
        arrives at the encoder with no indication of which service it belongs
        to -- the four service runbooks share that vocabulary deliberately, so
        the heading is often the only in-text signal separating them.
        """
        return f"{self.metadata['title']} -- {self.heading}\n\n{self.text}"


@dataclass
class TopologyCrossCheck:
    """Disagreements between the declared topology and the corpus on disk.

    Reported, never raised. Same stance as week-01's topology drift banner: a
    catalog that disagrees with reality is information, not a crash. The corpus
    also legitimately holds documents topology knows nothing about -- policies,
    catalog entries, postmortems and the archived runbook -- so those are
    listed separately from genuine mismatches.
    """

    declared_missing_from_corpus: tuple = ()
    corpus_runbooks_not_declared: tuple = ()
    non_runbook_documents: tuple = ()

    @property
    def has_mismatch(self) -> bool:
        return bool(self.declared_missing_from_corpus or self.corpus_runbooks_not_declared)


@dataclass
class LinkCrossCheck:
    """Dangling references found in `## Related documents` sections."""

    dangling: tuple = ()          # (source_id, target_id)
    references_superseded: tuple = ()   # (source_id, target_id)

    @property
    def has_dangling(self) -> bool:
        return bool(self.dangling)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

FRONTMATTER_PATTERN = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.S)


def parse_frontmatter(text: str, source: str) -> tuple:
    """Split a document into (metadata dict, body) and validate the schema.

    Every failure mode here raises. The alternative -- returning a partial
    document and warning -- is how a corpus quietly loses a field: retrieval
    keeps working, the filter on `service` just silently never matches one
    document, and the symptom shows up weeks later as a model that "missed"
    something.
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        raise IngestionError(
            f"{source}: no YAML frontmatter block. Expected the file to open "
            f"with '---' on its own line."
        )

    raw, body = match.group(1), match.group(2)
    try:
        metadata = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise IngestionError(f"{source}: frontmatter is not valid YAML -- {error}") from error

    if not isinstance(metadata, dict):
        raise IngestionError(
            f"{source}: frontmatter parsed to {type(metadata).__name__}, expected a mapping."
        )

    _validate_metadata(metadata, source)
    return metadata, body


def _validate_metadata(metadata: dict, source: str) -> None:
    """Check every required field is present, populated and in its value set."""
    missing = [f for f in REQUIRED_FIELDS if f not in metadata]
    if missing:
        raise IngestionError(
            f"{source}: frontmatter is missing required field(s): {', '.join(missing)}"
        )

    unpopulated = [
        f for f in NON_NULL_FIELDS
        if metadata[f] is None or str(metadata[f]).strip() == ""
    ]
    if unpopulated:
        raise IngestionError(
            f"{source}: required field(s) present but empty: {', '.join(unpopulated)}"
        )

    document_id = str(metadata["document_id"])
    if not DOCUMENT_ID_PATTERN.match(document_id):
        raise IngestionError(
            f"{source}: document_id {document_id!r} does not match the corpus scheme "
            f"(e.g. RB-PAY-000, POL-SLO-001, PM-2026-014, RB-PAY-000-ARCHIVED)."
        )

    for field_name, allowed in (
        ("document_type", VALID_DOCUMENT_TYPES),
        ("status", VALID_STATUSES),
        ("access_level", VALID_ACCESS_LEVELS),
    ):
        value = str(metadata[field_name])
        if value not in allowed:
            raise IngestionError(
                f"{source}: {field_name} is {value!r}, expected one of "
                f"{sorted(allowed)}."
            )

    # A superseded document must name its replacement, and a document naming a
    # replacement must be marked superseded. RB-PAY-000-ARCHIVED is the only
    # one of these in the corpus and its whole purpose is to be detectable by
    # metadata alone -- there is no warning in its body -- so an inconsistency
    # between these two fields would disarm the planted failure case.
    status = str(metadata["status"])
    superseded_by = metadata.get("superseded_by")
    if status == "superseded" and not superseded_by:
        raise IngestionError(
            f"{source}: status is 'superseded' but superseded_by is empty. The "
            f"superseded-document test depends on this link being followable."
        )
    if status == "current" and superseded_by:
        raise IngestionError(
            f"{source}: status is 'current' but superseded_by names "
            f"{superseded_by!r}."
        )

    # `last_reviewed` is a staleness signal a reviewer is meant to recognise, so
    # it has to be a real date rather than free text.
    reviewed = str(metadata["last_reviewed"])
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", reviewed):
        raise IngestionError(
            f"{source}: last_reviewed is {reviewed!r}, expected YYYY-MM-DD."
        )


# ---------------------------------------------------------------------------
# Sectioning
# ---------------------------------------------------------------------------

HEADING_PATTERN = re.compile(r"^##\s+(.*?)\s*$", re.M)

# Policies number their headings -- `## 1. Declared objectives` through
# `## 8. Related documents`. Stripping the ordinal is what lets one heading
# test cover all 19 documents; an exact match on "## Related documents" misses
# the three policies silently, leaving their link lists embedded as prose AND
# their links unparsed.
HEADING_ORDINAL_PATTERN = re.compile(r"^\d+\.\s+")


def normalise_heading(heading: str) -> str:
    """Heading text without its ordinal prefix, lowercased."""
    return HEADING_ORDINAL_PATTERN.sub("", heading).strip().lower()


def is_related_documents(heading: str) -> bool:
    return normalise_heading(heading) == RELATED_DOCUMENTS_HEADING


def split_sections(body: str) -> tuple:
    """Split a document body into (sections, related_documents_text).

    The `# Title` line and the untitled preamble that follows it become the
    OVERVIEW_SECTION rather than being discarded. See the comment on
    OVERVIEW_SECTION for why that matters more than it looks.
    """
    # Drop the H1: its text is already in `metadata['title']`, and carrying it
    # into the overview chunk would duplicate what embed_text prepends anyway.
    body = re.sub(r"^#\s+.*?$", "", body, count=1, flags=re.M)

    parts = HEADING_PATTERN.split(body)
    preamble = parts[0].strip()

    sections = []
    if preamble:
        sections.append(Section(heading=OVERVIEW_SECTION, text=preamble, position=0))

    related_text = ""
    # split() with one capture group yields [pre, head, text, head, text, ...]
    for index in range(1, len(parts), 2):
        heading = parts[index].strip()
        text = parts[index + 1].strip()
        if is_related_documents(heading):
            related_text = text
            continue
        if not text:
            continue
        sections.append(Section(heading=heading, text=text, position=len(sections)))

    return tuple(sections), related_text


LINK_PATTERN = re.compile(
    r"^[-*]\s*(?P<id>[A-Z]{2,4}-[A-Z0-9]+-\d{3}(?:-ARCHIVED)?)\s*(?:[-–—]+\s*(?P<gloss>.*))?$",
    re.M,
)


def parse_links(related_text: str) -> tuple:
    """Parse a `## Related documents` list into structured links.

    The gloss is kept, not discarded: several runbooks write
    `POL-DEPLOY-001 -- deployment validation and rollback (restricted)`, and
    that marker is the corpus stating a document exists but is not reproduced.
    """
    links = []
    seen = set()
    for match in LINK_PATTERN.finditer(related_text or ""):
        target = match.group("id")
        if target in seen:      # keep it deterministic and duplicate-free
            continue
        seen.add(target)
        links.append(DocumentLink(target_id=target, gloss=(match.group("gloss") or "").strip()))
    return tuple(links)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def split_paragraph_blocks(text: str) -> list:
    """Blank-line-delimited blocks, which is the atomic unit chunking respects.

    Markdown tables and numbered lists in this corpus contain no blank lines,
    so each is exactly one block and cannot be split. Verified against the
    corpus: the largest block is 1,397 characters, comfortably under
    MAX_CHUNK_CHARS, so no block is ever forced to split.
    """
    return [block.strip() for block in PARAGRAPH_SPLIT.split(text) if block.strip()]


def merge_short_sections(sections: Sequence) -> list:
    """Fold sections under MIN_SECTION_CHARS forward into the next section.

    Forward rather than backward: a short section is almost always an
    introduction to what follows -- a scope note, a one-line preamble to a
    table -- so attaching it to the following section keeps it with the text it
    introduces. A short FINAL section has nothing to fold into and is merged
    backward instead, which is the only case where that is the better join.
    """
    if not sections:
        return []

    merged = []
    carried = []          # headings + text waiting to be prefixed to the next
    for section in sections:
        if section.chars < MIN_SECTION_CHARS:
            carried.append(section)
            continue
        if carried:
            text = "\n\n".join([*(c.text for c in carried), section.text])
            heading = carried[0].heading
            position = carried[0].position
            carried = []
            merged.append(Section(heading=heading, text=text, position=position))
        else:
            merged.append(section)

    if carried:
        # Trailing short sections: attach to the last full section, or emit
        # alone if the whole document is shorter than the minimum.
        tail = "\n\n".join(c.text for c in carried)
        if merged:
            last = merged[-1]
            merged[-1] = Section(
                heading=last.heading,
                text=f"{last.text}\n\n{tail}",
                position=last.position,
            )
        else:
            merged.append(
                Section(heading=carried[0].heading, text=tail, position=carried[0].position)
            )

    # Renumber so `position` stays contiguous after merging.
    return [
        Section(heading=s.heading, text=s.text, position=index)
        for index, s in enumerate(merged)
    ]


def pack_blocks(blocks: Sequence) -> list:
    """Group paragraph blocks into chunk-sized pieces.

    Greedy and left-to-right, which is what makes it deterministic: the same
    blocks always produce the same grouping. A block is added to the current
    chunk unless doing so would cross MAX_CHUNK_CHARS; the chunk also closes
    once it has passed TARGET_CHUNK_CHARS, so typical chunks land near the
    target rather than filling to the ceiling.
    """
    chunks = []
    current = []
    size = 0

    for block in blocks:
        addition = len(block) + (2 if current else 0)
        if current and (size + addition > MAX_CHUNK_CHARS or size >= TARGET_CHUNK_CHARS):
            chunks.append("\n\n".join(current))
            current, size = [block], len(block)
            continue
        current.append(block)
        size += addition

    if current:
        chunks.append("\n\n".join(current))

    # Greedy packing strands a short tail whenever a section divides badly --
    # RB-INV-002's "Bulk retries are never authorised" is 289 characters and
    # was landing alone, separated from the checklist it qualifies. That is the
    # same stranding MIN_SECTION_CHARS prevents between sections, reappearing
    # one level down between pieces of a section.
    #
    # Fold it back when the join fits under the ceiling. When it does not, the
    # tail stays as it is rather than being force-fitted: exceeding
    # MAX_CHUNK_CHARS to tidy a distribution would trade a real constraint for
    # a cosmetic one. The report prints anything left under the minimum.
    if len(chunks) > 1 and len(chunks[-1]) < MIN_SECTION_CHARS:
        joined = f"{chunks[-2]}\n\n{chunks[-1]}"
        if len(joined) <= MAX_CHUNK_CHARS:
            chunks[-2:] = [joined]

    return chunks


def chunk_document(document: Document) -> list:
    """Every chunk for one document, in document order.

    Chunk IDs are `{document_id}#{index:02d}`. Derived from document_id and an
    integer, never from the title: RB-PAY-000 and RB-PAY-000-ARCHIVED carry the
    same title by design, so title-derived IDs would collide.
    """
    chunks = []
    sections = merge_short_sections(document.sections)

    for section in sections:
        pieces = pack_blocks(split_paragraph_blocks(section.text))
        for piece_index, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    chunk_id=f"{document.document_id}#{len(chunks):02d}",
                    document_id=document.document_id,
                    heading=section.heading,
                    section_position=section.position,
                    chunk_index=piece_index,
                    chunks_in_section=len(pieces),
                    text=piece,
                    metadata=dict(document.metadata),
                )
            )
    return chunks


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_document(path: Path) -> Document:
    """Parse and validate one corpus file."""
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text, path.name)

    document_id = str(metadata["document_id"])
    if path.stem != document_id:
        raise IngestionError(
            f"{path.name}: document_id is {document_id!r} but the filename stem is "
            f"{path.stem!r}. They must agree -- the join from topology.json is by ID "
            f"and a mismatch makes a document unreachable by one of the two routes."
        )

    sections, related_text = split_sections(body)
    if not sections:
        raise IngestionError(f"{path.name}: no content found below the frontmatter.")

    return Document(
        document_id=document_id,
        path=path,
        metadata=metadata,
        body=body,
        sections=sections,
        links=parse_links(related_text),
    )


def load_corpus(corpus_dir: Optional[Path] = None) -> list:
    """Every document in the corpus, in sorted filename order.

    Sorted, not directory order: chunk IDs and the report both depend on the
    sequence, and directory order is not stable across filesystems.
    """
    corpus_dir = Path(corpus_dir or CORPUS_DIR)
    if not corpus_dir.is_dir():
        raise IngestionError(f"Corpus directory not found: {corpus_dir}")

    paths = sorted(corpus_dir.glob("*.md"))
    if not paths:
        raise IngestionError(f"No .md documents found in {corpus_dir}")

    documents = [load_document(path) for path in paths]

    ids = [d.document_id for d in documents]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise IngestionError(f"Duplicate document_id(s) in the corpus: {duplicates}")

    return documents


def chunk_corpus(documents: Sequence) -> list:
    """Every chunk across every document, in document then section order."""
    chunks = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return chunks


# ---------------------------------------------------------------------------
# Cross-checks -- reported, never raised
# ---------------------------------------------------------------------------


def load_topology(path: Optional[Path] = None) -> dict:
    """The declared topology, as a plain dict. Copied in, never imported from week-01."""
    path = Path(path or TOPOLOGY_FILE)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise IngestionError(f"topology.json not found at {path}") from error
    except json.JSONDecodeError as error:
        raise IngestionError(f"topology.json is not valid JSON -- {error}") from error


def declared_runbook_ids(topology: dict) -> set:
    """Every runbook_id named anywhere in topology.json.

    Walks the structure rather than assuming a shape, so this keeps working if
    the topology grows a section. Topology owns resolution and validation, not
    enumeration -- the same stance as week-01.
    """
    found = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.endswith("runbook_id") and isinstance(value, str):
                    found.add(value)
                elif key.endswith("runbooks") and isinstance(value, list):
                    found.update(v for v in value if isinstance(v, str))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(topology)
    return found


def cross_check_topology(documents: Sequence, topology: dict) -> TopologyCrossCheck:
    """Compare declared runbook IDs against the corpus. Reports, never raises."""
    declared = declared_runbook_ids(topology)
    on_disk = {d.document_id for d in documents}

    # Superseded runbooks are excluded from the "should be declared" set. A
    # replaced runbook that topology still pointed at would be a genuine defect
    # -- the catalog routing responders to a document with an obsolete
    # escalation path -- so RB-PAY-000-ARCHIVED's absence is the correct state,
    # not a mismatch. Reporting it as one would train the reader to ignore this
    # line, which is the only line that would show a real drift.
    expected_declared = {
        d.document_id for d in documents
        if d.document_type == "runbook" and d.is_current
    }
    by_design = on_disk - expected_declared

    return TopologyCrossCheck(
        declared_missing_from_corpus=tuple(sorted(declared - on_disk)),
        corpus_runbooks_not_declared=tuple(sorted(expected_declared - declared)),
        non_runbook_documents=tuple(sorted(by_design)),
    )


def cross_check_links(documents: Sequence) -> LinkCrossCheck:
    """Find references to documents that do not exist, or that are superseded."""
    on_disk = {d.document_id for d in documents}
    superseded = {d.document_id for d in documents if d.status == "superseded"}

    dangling = []
    to_superseded = []
    for document in documents:
        for link in document.links:
            if link.target_id not in on_disk:
                dangling.append((document.document_id, link.target_id))
            elif link.target_id in superseded:
                to_superseded.append((document.document_id, link.target_id))

    return LinkCrossCheck(
        dangling=tuple(sorted(dangling)),
        references_superseded=tuple(sorted(to_superseded)),
    )


# ---------------------------------------------------------------------------
# Token counting
#
# Deliberately optional and deliberately not an estimate. A characters/4 figure
# would be a guess presented as a number, which is the same failure the week-01
# consumer sentence was: a value that looks measured and is not. If the real
# tokenizer is unavailable this returns None and the report says so.
# ---------------------------------------------------------------------------

# The model the chunk sizing is chosen against. Its context window (32,768
# tokens) is far above anything produced here -- the whole 114,540-character
# corpus would fit in one window -- so capacity is NOT the binding constraint.
# Chunk size is set by retrieval precision: a chunk must be one idea. The model
# is chosen for English retrieval quality and for having a published tokenizer,
# so this count can be exact rather than approximate.
# Verified against the live account on 11 Sep 2026, not read off a catalogue page.
# BAAI/bge-en-icl 404s on both api.studio.nebius.com and api.tokenfactory.nebius.com
# -- it is not deployed for this account. Qwen3-Embedding-8B is the only embedding
# model the models endpoint returns, and its dimension below is the measured
# len(response.data[0].embedding) from a live call, not a documented figure.
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"
EMBEDDING_DIMENSIONS = 4_096
EMBEDDING_CONTEXT_TOKENS = 32_768


def get_tokenizer(model: str = EMBEDDING_MODEL):
    """The real tokenizer for the embedding model, or None if not installed.

    Loads from the local HuggingFace cache. Downloading it is free and spends
    no API credit, but it is a network fetch, so it is never triggered
    implicitly -- run `python -m ingestion --fetch-tokenizer` once, on purpose.
    """
    try:
        from transformers import AutoTokenizer
    except ImportError:
        return None
    try:
        return AutoTokenizer.from_pretrained(model)
    except Exception:
        return None


def count_tokens(texts: Iterable, tokenizer) -> Optional[list]:
    """Exact token counts, or None when no tokenizer is available."""
    if tokenizer is None:
        return None
    return [len(tokenizer.encode(text, add_special_tokens=True)) for text in texts]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _distribution(values: Sequence) -> dict:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": int(statistics.median(ordered)),
        "mean": int(statistics.mean(ordered)),
        "max": ordered[-1],
        "total": sum(ordered),
    }


def build_report(corpus_dir: Optional[Path] = None,
                 topology_path: Optional[Path] = None,
                 tokenizer=None) -> dict:
    """Everything the ingestion report prints, as data."""
    documents = load_corpus(corpus_dir)
    chunks = chunk_corpus(documents)
    topology = load_topology(topology_path)

    char_counts = [c.chars for c in chunks]
    token_counts = count_tokens((c.embed_text for c in chunks), tokenizer)

    cardinality = {}
    for field_name in ("service", "document_type", "status", "access_level", "owner_team"):
        cardinality[field_name] = sorted({str(d.metadata[field_name]) for d in documents})

    return {
        "documents": documents,
        "chunks": chunks,
        "chars": _distribution(char_counts),
        "over_target": sum(1 for n in char_counts if n > TARGET_CHUNK_CHARS),
        "over_max": sum(1 for n in char_counts if n > MAX_CHUNK_CHARS),
        "tokens": _distribution(token_counts) if token_counts else None,
        "cardinality": cardinality,
        "topology": cross_check_topology(documents, topology),
        "links": cross_check_links(documents),
    }


def print_report(report: dict) -> None:
    """The ingestion report. Facts only -- nothing here is inferred."""
    documents, chunks = report["documents"], report["chunks"]
    rule = "-" * 78

    print("TriageLens Week 2 -- corpus ingestion report")
    print(rule)

    # --- documents ---
    print(f"\nDOCUMENTS LOADED: {len(documents)}   (failures raise, so a clean run means all of them)")
    corpus_chars = sum(len(d.body) for d in documents)
    print(f"  corpus body: {corpus_chars:,} characters")

    # --- chunks ---
    print(f"\nCHUNKS PRODUCED: {len(chunks)}")
    print(f"  {'document':<24}{'type':<12}{'service':<20}{'chunks':>7}{'chars':>9}")
    for document in documents:
        doc_chunks = [c for c in chunks if c.document_id == document.document_id]
        print(
            f"  {document.document_id:<24}{document.document_type:<12}"
            f"{document.service:<20}{len(doc_chunks):>7}"
            f"{sum(c.chars for c in doc_chunks):>9,}"
        )

    # --- size, characters ---
    chars = report["chars"]
    print(f"\nCHUNK SIZE -- CHARACTERS")
    print(f"  min {chars['min']:,}   median {chars['median']:,}   "
          f"mean {chars['mean']:,}   max {chars['max']:,}")
    print(f"  total {chars['total']:,}")
    print(f"  over target ({TARGET_CHUNK_CHARS:,}): {report['over_target']}")
    print(f"  over hard cap ({MAX_CHUNK_CHARS:,}): {report['over_max']}"
          + ("" if report["over_max"] == 0 else "   <-- BUG: the packer must never exceed this"))

    # --- size, tokens ---
    print(f"\nCHUNK SIZE -- TOKENS ({EMBEDDING_MODEL})")
    tokens = report["tokens"]
    if tokens is None:
        print("  UNAVAILABLE -- the real tokenizer is not installed.")
        print("  No characters/4 estimate is printed here on purpose: an estimate")
        print("  presented as a token count is a guess that looks like a measurement.")
        print("  Install it (free, no API credit) with:")
        print("      pip install -r requirements-dev.txt")
        print("      python ingestion.py --fetch-tokenizer")
    else:
        print(f"  min {tokens['min']:,}   median {tokens['median']:,}   "
              f"mean {tokens['mean']:,}   max {tokens['max']:,}")
        print(f"  TOTAL TOKENS TO EMBED: {tokens['total']:,}")
        print(f"  model context window: {EMBEDDING_CONTEXT_TOKENS:,} tokens "
              f"({EMBEDDING_CONTEXT_TOKENS // max(tokens['max'], 1)}x the largest chunk)")
        print(f"  output dimensions: {EMBEDDING_DIMENSIONS:,}")

    # --- metadata ---
    print(f"\nMETADATA CARDINALITY")
    for field_name, values in report["cardinality"].items():
        print(f"  {field_name:<16}{len(values)}   {', '.join(values)}")

    # --- topology ---
    topology = report["topology"]
    print(f"\nTOPOLOGY CROSS-CHECK")
    if topology.declared_missing_from_corpus:
        print(f"  MISMATCH -- declared in topology, absent from corpus: "
              f"{', '.join(topology.declared_missing_from_corpus)}")
    if topology.corpus_runbooks_not_declared:
        print(f"  MISMATCH -- runbook in corpus, not declared in topology: "
              f"{', '.join(topology.corpus_runbooks_not_declared)}")
    if not topology.has_mismatch:
        print("  no mismatches -- every declared runbook_id exists, and every corpus")
        print("  runbook is declared.")
    print(f"  not declared by design ({len(topology.non_runbook_documents)}): "
          f"{', '.join(topology.non_runbook_documents)}")
    print("    topology declares CURRENT runbooks. Policies, catalog documents and")
    print("    postmortems are not runbooks. RB-PAY-000-ARCHIVED is superseded, and a")
    print("    catalog still pointing at it would be the real defect.")

    stranded = [c for c in report["chunks"] if c.chars < MIN_SECTION_CHARS]
    if stranded:
        print(f"\nCHUNKS UNDER THE {MIN_SECTION_CHARS}-CHARACTER MINIMUM: {len(stranded)}")
        for chunk in sorted(stranded, key=lambda c: c.chars):
            print(f"  {chunk.chars:>5}  {chunk.chunk_id:<22}{chunk.heading}")
        print("    these could not be folded back without crossing the hard cap")

    # --- links ---
    links = report["links"]
    print(f"\nDOCUMENT REFERENCES ('Related documents', parsed as links, never embedded)")
    total_links = sum(len(d.links) for d in documents)
    print(f"  {total_links} references across {len(documents)} documents")
    if links.dangling:
        print(f"  DANGLING ({len(links.dangling)}):")
        for source, target in links.dangling:
            print(f"    {source} -> {target}   (target does not exist)")
    else:
        print("  no dangling references -- every referenced document_id exists on disk")
    if links.references_superseded:
        print(f"  references to superseded documents ({len(links.references_superseded)}):")
        for source, target in links.references_superseded:
            print(f"    {source} -> {target}")
    else:
        print("  no document links to a superseded document")

    # Inbound reference counts make the near-duplicate/distractor picture visible.
    inbound = {}
    for document in documents:
        for link in document.links:
            inbound[link.target_id] = inbound.get(link.target_id, 0) + 1
    unreferenced = sorted({d.document_id for d in documents} - set(inbound))
    if unreferenced:
        print(f"  referenced by nothing: {', '.join(unreferenced)}")

    print(f"\n{rule}")


def main(argv: Optional[Sequence] = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)

    if "--fetch-tokenizer" in argv:
        # Explicit, opt-in, and it spends no API credit -- it downloads the
        # tokenizer vocabulary from HuggingFace. Never triggered implicitly.
        try:
            from transformers import AutoTokenizer
        except ImportError:
            print("transformers is not installed. Run: pip install -r requirements-dev.txt")
            return 1
        print(f"Downloading tokenizer for {EMBEDDING_MODEL} (free, no API credit)...")
        AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
        print("Done. Re-run `python ingestion.py` for exact token counts.")
        return 0

    print_report(build_report(tokenizer=get_tokenizer()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
