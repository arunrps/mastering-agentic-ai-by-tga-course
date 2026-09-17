"""
retrieval.py -- hybrid retrieval: metadata pre-filter, BM25 + dense, fusion, rerank.

NEVER imports streamlit.

The architecture principle from Week 1 applies here directly: **retrieval is
deterministic.** Given the same index and the same context request, this module
returns the same passages in the same order, every time. Nothing in the path from
question to cited passage involves a model deciding anything -- the only model
call is the query embedding, which is a fixed function of the query text. The
probabilistic part is answer generation, and it is not in this file.

The pipeline, in order:

  1. METADATA PRE-FILTER -- narrow the candidate set by service, status and
     access level before any scoring. This is not an optimisation. The four
     service runbooks deliberately share their scope paragraph, class
     definitions and escalation shape (manifest 4.5), so pure similarity
     returns all four for any service-shaped query. The filter is what makes
     them separable, and it is load-bearing from the first call.

  2. BM25 -- lexical. The corpus is dense with exact-match tokens that dense
     retrieval blurs: document IDs (RB-PAY-000), endpoints (/checkout), status
     families (5xx), metrics (p95). A dense-only system answers "what does
     RB-PAY-002 say" with whatever is semantically near it.

  3. DENSE -- Qwen3-Embedding-8B, cosine over L2-normalised vectors. Handles
     the paraphrase half: "checkout is slow" against "elevated latency on the
     payment path".

  4. RECIPROCAL RANK FUSION -- combines the two rankings without needing their
     scores to be on a comparable scale. BM25 scores are unbounded and
     corpus-dependent; cosine sits in [-1, 1]. Any weighted sum of the two
     requires a normalisation constant that is really a tuning parameter in
     disguise, and it would have to be retuned whenever the corpus changed.
     RRF uses only the ranks, so it has one parameter and it is stable.

  5. RERANK -- deterministic, and narrower than a cross-encoder. See
     RERANK_NOTE: no cross-encoder is available on this Nebius account, and the
     two ways to get one both cost something the project is not ready to pay.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

import embedding
import ingestion

RERANK_NOTE = """\
There is no cross-encoder reranker on this Nebius account -- the /models
endpoint returns one embedding model and no rerank model. The two routes to a
true cross-encoder both have a cost:

  * A local cross-encoder (bge-reranker, ms-marco MiniLM) needs torch, which is
    a ~900MB dependency in a project whose deploy requirements.txt is two lines
    and which has to run on Streamlit Community Cloud.

  * An LLM-as-reranker makes RETRIEVAL probabilistic. That breaks the
    architecture principle the whole project rests on -- deterministic code
    produces the evidence, the model narrates from it -- and it adds a second
    round trip against a declared sub-3-second latency ceiling.

So stage 5 is a deterministic rerank over the fused list rather than a learned
one: it caps how many chunks any single document may contribute, and demotes
superseded documents below current ones. Both address concrete failure modes
this corpus plants on purpose. Whether a real cross-encoder is needed is a
question for measurement against the 24 evaluation questions, not for guessing
now -- and the deck's own advice is not to add machinery until vanilla
retrieval is measurably failing."""


# ---------------------------------------------------------------------------
# Tokenisation for BM25
# ---------------------------------------------------------------------------

# Keeps hyphenated and slashed compounds whole: `rb-pay-000`, `payment-service`,
# `5xx`, `p95`, `checkout`. A naive \w+ tokeniser shatters RB-PAY-000 into
# three meaningless pieces and destroys the exact-match behaviour BM25 is here
# to provide.
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)*")


def tokenize(text: str) -> list:
    """Lowercase tokens, with hyphenated compounds kept AND split.

    Both forms are emitted: `payment-service` yields `payment-service`,
    `payment` and `service`. The compound carries the precision -- a query for
    `payment-service` should not rank `catalog-service` highly just because
    both contain `service` -- and the parts carry the recall, so a question
    phrased as "the payment service" still matches.
    """
    tokens = []
    for match in TOKEN_PATTERN.findall(text.lower()):
        tokens.append(match)
        if "-" in match or "/" in match:
            tokens.extend(part for part in re.split(r"[-/]", match) if part)
    return tokens


# ---------------------------------------------------------------------------
# The context request
#
# Retrieval is driven by a STRUCTURED request, not by a free-text chat box.
# In the finished system the detector's verdict produces this object: it knows
# which endpoint x backend slice was elevated, so it knows which service to
# scope to. That is what makes this incident-context retrieval rather than
# "chat with your docs".
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextRequest:
    """What the caller is asking for, as fields rather than as a sentence."""

    question: str

    # Metadata pre-filter. `None` means no constraint on that dimension.
    service: Optional[str] = None
    document_types: Optional[tuple] = None

    # Defaults that encode policy rather than preference:
    #   - only `current` documents, so the superseded runbook is excluded
    #     unless a caller deliberately asks for it
    #   - `operations` access, so restricted documents are excluded and their
    #     exclusion is reportable rather than silent
    statuses: tuple = ("current",)
    access_level: str = "operations"

    # `platform` documents (the three policies, the two catalog files) apply to
    # every service. Excluding them when a service filter is set would drop the
    # severity matrix and the SLO policy from every service-scoped query.
    include_platform: bool = True

    top_k: int = 6
    candidates_per_arm: int = 20
    max_chunks_per_document: int = 2


@dataclass
class ScoredChunk:
    """One retrieved chunk with every score that produced its position.

    All four are carried, not just the final one. A citation that cannot be
    traced back to why the passage was selected is the retrieval equivalent of
    a number with no denominator -- and the Week 1 rule was that every figure
    on screen traces to something visible.
    """

    chunk: object
    bm25_rank: Optional[int] = None
    bm25_score: float = 0.0
    dense_rank: Optional[int] = None
    dense_score: float = 0.0
    fused_score: float = 0.0
    demoted: str = ""

    @property
    def document_id(self) -> str:
        return self.chunk.document_id

    @property
    def why(self) -> str:
        """One line explaining why this passage is in the result list."""
        parts = []
        if self.bm25_rank is not None:
            parts.append(f"lexical #{self.bm25_rank + 1} ({self.bm25_score:.2f})")
        if self.dense_rank is not None:
            parts.append(f"semantic #{self.dense_rank + 1} ({self.dense_score:.3f})")
        if not parts:
            parts.append("no arm")
        if self.demoted:
            parts.append(f"demoted: {self.demoted}")
        return " · ".join(parts)


@dataclass
class RetrievalResult:
    """The retrieved passages plus what the filter did on the way."""

    request: ContextRequest
    results: list
    candidates_considered: int
    corpus_size: int
    excluded_restricted: tuple = ()
    excluded_superseded: tuple = ()
    query_tokens: int = 0

    @property
    def cited_documents(self) -> list:
        seen = []
        for scored in self.results:
            if scored.document_id not in seen:
                seen.append(scored.document_id)
        return seen


# ---------------------------------------------------------------------------
# The retriever
# ---------------------------------------------------------------------------


class Retriever:
    """Hybrid retrieval over a built index.

    The BM25 index is built once per process from the chunk texts. It is cheap
    (no model, no API) and deterministic, so there is no cache to invalidate.
    """

    def __init__(self, index):
        from rank_bm25 import BM25Okapi

        self.index = index
        self.chunks = index.chunks
        self.vectors = index.vectors
        self._corpus_tokens = [tokenize(c.embed_text) for c in self.chunks]
        self._bm25 = BM25Okapi(self._corpus_tokens)

    # --- stage 1 -----------------------------------------------------------

    def _filter(self, request: ContextRequest) -> tuple:
        """Candidate positions after the metadata pre-filter, plus what it cut.

        Exclusions are RETURNED, not just applied. "The corpus contains nothing
        about this" and "relevant guidance exists but is above your access
        level" are different answers, and the second one is only available if
        the filter reports what it removed.
        """
        keep = []
        excluded_restricted = []
        excluded_superseded = []

        for position, chunk in enumerate(self.chunks):
            metadata = chunk.metadata

            if metadata["access_level"] == "restricted" and request.access_level != "restricted":
                excluded_restricted.append(chunk.document_id)
                continue

            if metadata["status"] not in request.statuses:
                excluded_superseded.append(chunk.document_id)
                continue

            if request.document_types and metadata["document_type"] not in request.document_types:
                continue

            if request.service is not None:
                service = metadata["service"]
                if service != request.service:
                    if not (request.include_platform and service == "platform"):
                        continue

            keep.append(position)

        return (
            keep,
            tuple(sorted(set(excluded_restricted))),
            tuple(sorted(set(excluded_superseded))),
        )

    # --- stages 2 and 3 ----------------------------------------------------

    def _bm25_ranking(self, question: str, candidates: Sequence) -> list:
        """(position, rank, score) for the top lexical matches among candidates."""
        scores = self._bm25.get_scores(tokenize(question))
        scored = [(position, float(scores[position])) for position in candidates]
        # Sort by score desc, then by position asc so ties are broken
        # deterministically rather than by whatever order the list happened to
        # be in. Reproducibility is a requirement, including in ties.
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [
            (position, rank, score)
            for rank, (position, score) in enumerate(scored)
            if score > 0.0
        ]

    def _dense_ranking(self, query_vector: np.ndarray, candidates: Sequence) -> list:
        """(position, rank, cosine) for the top semantic matches among candidates."""
        subset = self.vectors[list(candidates)]
        similarities = subset @ query_vector          # both L2-normalised
        scored = list(zip(candidates, (float(s) for s in similarities)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [(position, rank, score) for rank, (position, score) in enumerate(scored)]

    @staticmethod
    def _fuse(bm25: Sequence, dense: Sequence, k: int = 60) -> dict:
        """Reciprocal rank fusion.

        score = sum over arms of 1 / (k + rank). k=60 is the value from the
        original RRF paper and is left alone deliberately: it is the one knob
        here, and tuning it against 24 questions would be fitting noise.
        """
        fused = {}
        for position, rank, _ in bm25:
            fused[position] = fused.get(position, 0.0) + 1.0 / (k + rank + 1)
        for position, rank, _ in dense:
            fused[position] = fused.get(position, 0.0) + 1.0 / (k + rank + 1)
        return fused

    # --- stage 5 -----------------------------------------------------------

    @staticmethod
    def _rerank(scored: list, request: ContextRequest) -> list:
        """Deterministic rerank. See RERANK_NOTE for what this is not.

        Two rules, each aimed at a failure this corpus plants:

        1. **Cap chunks per document.** PM-2026-014 is 10,398 characters across
           9 chunks; RB-PAY-001 is 7 chunks. Without a cap a single verbose
           document fills the result list and crowds out the second document
           the answer needs -- which is exactly the planted partial-answer case
           (RB-PAY-001 covers single-endpoint degradation, RB-PAY-002 carries
           sibling corroboration). A system that returns six chunks of
           RB-PAY-001 has retrieved one document and called it six results.

        2. **Demote superseded documents.** They are normally filtered out
           entirely; when a caller deliberately includes them, they rank below
           equivalent current documents rather than competing on similarity
           alone. RB-PAY-000-ARCHIVED is near-identical to RB-PAY-000 by
           design, so on pure similarity it can outrank its own replacement.
        """
        per_document = {}
        kept = []
        for item in sorted(scored, key=lambda s: -s.fused_score):
            document_id = item.document_id
            if per_document.get(document_id, 0) >= request.max_chunks_per_document:
                continue
            per_document[document_id] = per_document.get(document_id, 0) + 1
            if item.chunk.metadata["status"] == "superseded":
                item.demoted = "superseded"
            kept.append(item)

        # Stable partition: current documents first, order otherwise preserved.
        current = [item for item in kept if not item.demoted]
        superseded = [item for item in kept if item.demoted]
        return current + superseded

    # --- public ------------------------------------------------------------

    def retrieve(self, request: ContextRequest,
                 query_vector: Optional[np.ndarray] = None) -> RetrievalResult:
        """Run the full pipeline for one context request."""
        candidates, restricted, superseded = self._filter(request)

        if not candidates:
            return RetrievalResult(
                request=request, results=[], candidates_considered=0,
                corpus_size=len(self.chunks),
                excluded_restricted=restricted, excluded_superseded=superseded,
            )

        query_tokens = 0
        if query_vector is None:
            before = embedding.total_spend()["tokens"]
            query_vector = embedding.embed_query(request.question)
            query_tokens = embedding.total_spend()["tokens"] - before

        bm25 = self._bm25_ranking(request.question, candidates)[:request.candidates_per_arm]
        dense = self._dense_ranking(query_vector, candidates)[:request.candidates_per_arm]
        fused = self._fuse(bm25, dense)

        bm25_by_position = {p: (r, s) for p, r, s in bm25}
        dense_by_position = {p: (r, s) for p, r, s in dense}

        scored = []
        for position, score in fused.items():
            bm25_entry = bm25_by_position.get(position)
            dense_entry = dense_by_position.get(position)
            scored.append(ScoredChunk(
                chunk=self.chunks[position],
                bm25_rank=bm25_entry[0] if bm25_entry else None,
                bm25_score=bm25_entry[1] if bm25_entry else 0.0,
                dense_rank=dense_entry[0] if dense_entry else None,
                dense_score=dense_entry[1] if dense_entry else 0.0,
                fused_score=score,
            ))

        results = self._rerank(scored, request)[:request.top_k]

        return RetrievalResult(
            request=request, results=results,
            candidates_considered=len(candidates), corpus_size=len(self.chunks),
            excluded_restricted=restricted, excluded_superseded=superseded,
            query_tokens=query_tokens,
        )


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


def format_citations(result: RetrievalResult, snippet_chars: int = 320) -> str:
    """The retrieved passages as a citation block.

    Every citation names the document, its section, its status and version, and
    WHY it was retrieved. The last part is the one usually missing: a reader who
    cannot see whether a passage arrived on an exact token match or on a
    paraphrase cannot judge whether to trust the ranking.
    """
    if not result.results:
        lines = ["No passages matched the context request."]
        if result.excluded_restricted:
            lines.append(
                "Relevant guidance may exist but is above the caller's access "
                f"level: {', '.join(result.excluded_restricted)}."
            )
        return "\n".join(lines)

    lines = []
    for position, scored in enumerate(result.results, start=1):
        chunk = scored.chunk
        metadata = chunk.metadata
        snippet = " ".join(chunk.text.split())
        if len(snippet) > snippet_chars:
            snippet = snippet[:snippet_chars].rsplit(" ", 1)[0] + " ..."
        lines.append(
            f"[{position}] {chunk.document_id} -- {metadata['title']}\n"
            f"    section: {chunk.heading}  "
            f"(piece {chunk.chunk_index + 1}/{chunk.chunks_in_section})\n"
            f"    {metadata['document_type']} · {metadata['service']} · "
            f"{metadata['status']} · v{metadata['version']} · "
            f"reviewed {metadata['last_reviewed']}\n"
            f"    why: {scored.why}\n"
            f"    \"{snippet}\""
        )
    return "\n\n".join(lines)


def describe_filter(result: RetrievalResult) -> str:
    """What the pre-filter did, in words. Exclusions are stated, never silent."""
    request = result.request
    scope = []
    if request.service:
        scope.append(f"service={request.service}"
                     + (" (+platform)" if request.include_platform else ""))
    if request.document_types:
        scope.append(f"type in {list(request.document_types)}")
    scope.append(f"status in {list(request.statuses)}")
    scope.append(f"access={request.access_level}")

    lines = [
        f"Pre-filter: {' · '.join(scope)}",
        f"  {result.candidates_considered} of {result.corpus_size} chunks passed",
    ]
    if result.excluded_restricted:
        lines.append(
            f"  excluded as restricted: {', '.join(result.excluded_restricted)} "
            "-- relevant guidance may exist here but is above this access level"
        )
    if result.excluded_superseded:
        lines.append(f"  excluded as superseded: {', '.join(result.excluded_superseded)}")
    return "\n".join(lines)
