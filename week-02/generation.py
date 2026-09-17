"""
generation.py -- grounded answers and the four-outcome refusal gate.

NEVER imports streamlit.

WHERE THE DETERMINISM BOUNDARY SITS IN THIS FILE
------------------------------------------------

Week 1 put a deterministic gate in front of the narrative: numeric rules decided
whether evidence was sufficient, and the prose was generated from the verdict.
The obvious move here was the same shape -- a similarity threshold deciding
whether the corpus can answer.

**That was measured and it does not work.** Across the 24 golden questions the
top dense similarity for questions the corpus CAN answer runs 0.515 to 0.755,
and for questions it CANNOT answer runs 0.442 to 0.553. The ranges overlap:
Q16 ("how do i check gateway vs dns", nothing in the corpus) scores 0.553, above
Q1 (0.543) and Q12 (0.515), which are both answerable. A threshold placed
anywhere in that band misclassifies in both directions.

The reason is not a tuning failure. Cosine similarity measures topical
proximity, and an unanswerable question about this platform is topically very
close to the corpus -- it uses the same vocabulary, names the same services, and
concerns the same systems. "Where are the rate limits documented" looks exactly
like a corpus question. It just has no answer in it.

So the boundary is drawn differently here, and deliberately:

  DETERMINISTIC, decided by code before the model is called:
    * access-level refusal -- metadata says restricted, and a shadow retrieval
      proves the restricted document WOULD have ranked. This is policy, and
      policy lives outside the model.
    * superseded handling -- metadata, filtered and demoted by rules.
    * which passages the model may see -- retrieval, unchanged.
    * what counts as a valid citation -- every cited document_id is checked
      against the retrieved set after generation, and an answer citing anything
      it was not given is rejected by code, not trusted.

  MODEL-JUDGED, because it is reading comprehension and not policy:
    * whether the supplied passages actually answer the question.

That last one cannot be made deterministic without a second corpus of labels
that does not exist. Pretending otherwise -- shipping a threshold and calling it
a gate -- would be the Week 1 consumer sentence again: a number that looks
measured, chosen because it was available rather than because it was right.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

import embedding
import ingestion
import retrieval

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

GENERATION_MODEL = "openai/gpt-oss-120b"

# Low but not zero. Zero makes some servers deterministic and others merely
# greedy, and the honest claim is "low variance", not "reproducible".
TEMPERATURE = 0.1
# gpt-oss-120b spends output tokens on reasoning before it emits the JSON, and
# at 900 the object was being truncated mid-object -- the parse failure was a
# budget problem wearing the costume of a format problem. Raised to cover
# reasoning plus the answer; only tokens actually generated are billed.
MAX_OUTPUT_TOKENS = 2_500

# Rough per-million rates for the pre-run estimate only. Actual spend is always
# read back from the API usage block, never computed from these.
USD_PER_MILLION_INPUT = 0.10
USD_PER_MILLION_OUTPUT = 0.40


# ---------------------------------------------------------------------------
# The four outcomes
# ---------------------------------------------------------------------------

ANSWERED = "answered"
PARTIAL = "partial"
RESTRICTED = "restricted"
NOT_IN_CORPUS = "not_in_corpus"

# The three refusal types must stay distinguishable. Conflating the second with
# the third is a security problem rather than a usability one: telling someone
# "there is no guidance" when the truth is "there is guidance you may not read"
# hides the existence of a control from the person it is applied to.
REFUSAL_MEANINGS = {
    NOT_IN_CORPUS: "the corpus contains nothing on this",
    RESTRICTED: "relevant guidance exists but is above your access level",
    "referenced_absent": "a document is referenced by the corpus but is not present",
}


@dataclass
class Answer:
    """A generated answer plus everything needed to audit it."""

    outcome: str
    text: str
    citations: list = field(default_factory=list)
    not_covered: str = ""
    available_instead: list = field(default_factory=list)

    restricted_documents: tuple = ()
    referenced_absent: tuple = ()

    invalid_citations: tuple = ()
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    @property
    def is_refusal(self) -> bool:
        return self.outcome in (NOT_IN_CORPUS, RESTRICTED)

    @property
    def cited_documents(self) -> list:
        seen = []
        for citation in self.citations:
            doc = citation.get("document_id")
            if doc and doc not in seen:
                seen.append(doc)
        return seen


# ---------------------------------------------------------------------------
# The deterministic half
# ---------------------------------------------------------------------------


def restricted_would_have_ranked(retriever, request: retrieval.ContextRequest,
                                 query_vector) -> tuple:
    """Which restricted documents would have appeared had access allowed it.

    A shadow retrieval with the access filter lifted, reusing the SAME query
    vector -- so this costs no tokens and no extra round trip.

    This exists because "we excluded a restricted document" is not by itself
    interesting: POL-DEPLOY-001 is excluded on every single query, so reporting
    it every time is noise that trains the reader to ignore the line. What
    matters is whether the restricted document would actually have been
    RETURNED. That is the difference between "there is guidance you cannot read"
    and "there happens to be a restricted document in the corpus".
    """
    privileged = retrieval.ContextRequest(
        question=request.question,
        service=request.service,
        statuses=request.statuses,
        access_level="restricted",
        include_platform=request.include_platform,
        top_k=request.top_k,
        max_chunks_per_document=request.max_chunks_per_document,
    )
    shadow = retriever.retrieve(privileged, query_vector=query_vector)
    return tuple(sorted({
        scored.document_id for scored in shadow.results
        if scored.chunk.metadata["access_level"] == "restricted"
    }))


def referenced_but_absent(documents: Sequence) -> tuple:
    """Documents the corpus points at that are not on disk.

    The third refusal type. Currently empty for this corpus -- every one of the
    104 parsed references resolves -- but the check is wired because the refusal
    type has to be demonstrably distinguishable, not merely described.
    """
    on_disk = {d.document_id for d in documents}
    missing = set()
    for document in documents:
        for link in document.links:
            if link.target_id not in on_disk:
                missing.add(link.target_id)
    return tuple(sorted(missing))


def available_documents(documents: Sequence, service: Optional[str]) -> list:
    """What the corpus DOES hold for this scope, as document_id + title.

    Point 4 of the scoring rubric: naming what is available is the difference
    between a useful refusal and a dead end. This is computed from metadata, so
    the list is complete and correct regardless of what the model says.
    """
    rows = []
    for document in documents:
        if document.status != "current":
            continue
        # Restricted documents are deliberately NOT offered here. Listing one
        # under "what the corpus does hold" hands an operations-level caller a
        # document they cannot open, and it blurs the two refusal types back
        # together -- the whole point of separating them is that "exists but
        # you may not read it" is a different sentence from "here is what is
        # available to you". The restricted notice says it, once, precisely.
        if document.is_restricted:
            continue
        if service and document.service not in (service, "platform"):
            continue
        rows.append({
            "document_id": document.document_id,
            "title": document.title,
            "document_type": document.document_type,
            "service": document.service,
            "restricted": document.is_restricted,
        })
    return rows


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the retrieval layer of TriageLens, an incident-triage assistant for an API \
gateway platform. You answer an on-call engineer's question using ONLY the passages \
supplied to you.

ABSOLUTE RULES

1. Every factual claim must come from a supplied passage, and every claim must carry \
a citation naming the document_id it came from. If you cannot cite it, do not say it.
2. Never use knowledge from outside the supplied passages. You may not describe general \
incident-response practice, name tools, or suggest steps the passages do not contain. \
If the passages do not answer the question, say so.
3. Never claim a cause. Use "suspect", "correlates with", "worth investigating". The \
corpus is a triage layer: it classifies and escalates, it does not remediate or \
diagnose root cause.
4. Never invent a document_id. Cite only from the passages given.
5. If the passages partially answer the question, answer the part you can AND state \
plainly which part the corpus does not cover. A partial answer that hides its gap is \
worse than a refusal.
6. When you refuse, name what the corpus DOES hold for this area. "Not found" is not \
an answer; "the corpus has no rate-limit guidance; the payment-service runbook covers \
5xx and latency triage" is.

OUTCOME

Choose exactly one:
  "answered"      - the passages fully support an answer
  "partial"       - the passages support part of it; you must state what is missing
  "not_in_corpus" - the passages do not answer it at all

Note that the passages may be topically close to the question and still not answer it. \
Closeness is not coverage. Judge whether the passages actually contain the procedure, \
threshold or fact being asked for.

OUTPUT
Return ONLY a JSON object, no prose around it:

{
  "outcome": "answered" | "partial" | "not_in_corpus",
  "answer": "your answer to the engineer, in plain sentences, 2-6 sentences",
  "citations": [
    {"document_id": "RB-PAY-000", "section": "Discriminating checks",
     "supports": "the specific claim this passage backs"}
  ],
  "not_covered": "what the corpus does not address here, or empty string if nothing"
}"""


def build_user_prompt(question: str, result: retrieval.RetrievalResult) -> str:
    """The question plus the retrieved passages, verbatim and labelled."""
    blocks = []
    for position, scored in enumerate(result.results, start=1):
        chunk = scored.chunk
        metadata = chunk.metadata
        blocks.append(
            f"--- PASSAGE {position} ---\n"
            f"document_id: {chunk.document_id}\n"
            f"title: {metadata['title']}\n"
            f"section: {chunk.heading}\n"
            f"document_type: {metadata['document_type']} | service: {metadata['service']} "
            f"| status: {metadata['status']} | version: {metadata['version']}\n\n"
            f"{chunk.text}"
        )

    passages = "\n\n".join(blocks) if blocks else "(no passages were retrieved)"
    return (
        f"ENGINEER'S QUESTION:\n{question}\n\n"
        f"SUPPLIED PASSAGES ({len(result.results)}):\n\n{passages}"
    )


# ---------------------------------------------------------------------------
# Estimation
# ---------------------------------------------------------------------------


def estimate_generation(questions: Sequence, retriever, top_k: int = 6) -> dict:
    """Token volume and cost for a generation run, before any call is made.

    Uses the real tokenizer on the exact prompts that would be sent. Output is
    the one part that cannot be measured in advance, so it is stated as an
    assumption with its per-question figure visible rather than buried.
    """
    tokenizer = ingestion.get_tokenizer()
    if tokenizer is None:
        raise RuntimeError(
            "No tokenizer available, so no honest estimate can be made. "
            "Run `python ingestion.py --fetch-tokenizer` first."
        )

    prompts = []
    for question in questions:
        request = retrieval.ContextRequest(
            question=question["text"], service=question.get("service"), top_k=top_k
        )
        result = retriever.retrieve(request)
        prompts.append(SYSTEM_PROMPT + "\n\n" + build_user_prompt(question["text"], result))

    counts = ingestion.count_tokens(prompts, tokenizer)
    input_tokens = sum(counts)
    assumed_output = MAX_OUTPUT_TOKENS // 3      # ~300, the observed shape of these answers
    output_tokens = assumed_output * len(questions)

    return {
        "questions": len(questions),
        "input_tokens": input_tokens,
        "input_per_question": input_tokens // max(len(questions), 1),
        "assumed_output_per_question": assumed_output,
        "output_tokens": output_tokens,
        "usd": (input_tokens / 1_000_000 * USD_PER_MILLION_INPUT
                + output_tokens / 1_000_000 * USD_PER_MILLION_OUTPUT),
        "model": GENERATION_MODEL,
    }


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _parse_response(raw: str) -> dict:
    """Pull the JSON object out of the model's reply.

    Models wrap JSON in prose or fences no matter what the prompt says. This is
    tolerant about the wrapper and strict about the contents: a reply with no
    parseable object is an error, not something to paper over with a regex that
    guesses at fields.
    """
    raw = raw or ""
    match = JSON_BLOCK.search(raw)
    if not match:
        raise ValueError(
            f"no JSON object in model reply (len={len(raw)}). If the text ends "
            f"mid-object the cause is MAX_OUTPUT_TOKENS, not the model ignoring "
            f"the format instruction. Tail: {raw[-160:]!r}"
        )
    return json.loads(match.group(0))


def answer_question(retriever, documents: Sequence, request: retrieval.ContextRequest,
                    model: str = GENERATION_MODEL) -> tuple:
    """Retrieve, gate, generate, verify. Returns (Answer, RetrievalResult)."""
    query_vector = embedding.embed_query(request.question)
    result = retriever.retrieve(request, query_vector=query_vector)

    # --- deterministic, before the model sees anything ---------------------
    restricted = restricted_would_have_ranked(retriever, request, query_vector)
    absent = referenced_but_absent(documents)
    fallback = available_documents(documents, request.service)

    if not result.results:
        # Nothing survived the filter. No model call: there is nothing to
        # ground an answer in, and asking a model what to say about an empty
        # context is an invitation to invent.
        return Answer(
            outcome=RESTRICTED if restricted else NOT_IN_CORPUS,
            text=("Relevant guidance exists but is above your access level."
                  if restricted else
                  "No passages in the corpus match this question."),
            restricted_documents=restricted,
            referenced_absent=absent,
            available_instead=fallback,
            model="(no model call)",
        ), result

    # --- the model call ----------------------------------------------------
    client = embedding._client()
    response = client.chat.completions.create(
        model=model,
        temperature=TEMPERATURE,
        max_tokens=MAX_OUTPUT_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(request.question, result)},
        ],
    )

    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    embedding.record_spend("generate", model, input_tokens + output_tokens,
                           note=request.question[:60])

    parsed = _parse_response(response.choices[0].message.content)

    # --- deterministic, after the model ------------------------------------
    # Every cited document must be one that was actually supplied. A model that
    # cites something it was not given has left the evidence boundary, and that
    # is checked by code rather than trusted to the instruction that forbade it.
    supplied = {scored.document_id for scored in result.results}
    citations = [c for c in parsed.get("citations", []) if isinstance(c, dict)]
    invalid = tuple(sorted({
        c.get("document_id") for c in citations
        if c.get("document_id") not in supplied
    } - {None}))
    citations = [c for c in citations if c.get("document_id") in supplied]

    outcome = parsed.get("outcome", NOT_IN_CORPUS)
    if outcome not in (ANSWERED, PARTIAL, NOT_IN_CORPUS):
        outcome = NOT_IN_CORPUS

    # The access-level refusal OVERRIDES a not-in-corpus verdict, and augments
    # an answer. Saying "nothing covers this" when a restricted document would
    # have ranked is the exact conflation the three refusal types exist to
    # prevent, and the model cannot know it happened -- it never saw the
    # document. Only the filter knows, so only code can say it.
    if restricted and outcome == NOT_IN_CORPUS:
        outcome = RESTRICTED

    return Answer(
        outcome=outcome,
        text=parsed.get("answer", ""),
        citations=citations,
        not_covered=parsed.get("not_covered", "") or "",
        available_instead=fallback if outcome != ANSWERED else [],
        restricted_documents=restricted,
        referenced_absent=absent,
        invalid_citations=invalid,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    ), result


# ---------------------------------------------------------------------------
# Rendering -- deterministic, no model involved
# ---------------------------------------------------------------------------


def format_answer(answer: Answer, result: retrieval.RetrievalResult) -> str:
    """The answer as an on-call engineer would read it.

    Assembled by code from the Answer's fields. The model writes the prose in
    `answer.text`; everything around it -- the outcome label, the restricted
    notice, the availability list, the citation block -- is generated here from
    data the model never saw.
    """
    label = {
        ANSWERED: "ANSWERED",
        PARTIAL: "PARTIAL — the corpus covers part of this",
        RESTRICTED: "REFUSED — above your access level",
        NOT_IN_CORPUS: "REFUSED — not in the corpus",
    }[answer.outcome]

    lines = [f"[{label}]", "", answer.text or "(no answer text)"]

    if answer.not_covered:
        lines += ["", f"Not covered: {answer.not_covered}"]

    if answer.restricted_documents:
        lines += ["", (
            "Access: relevant guidance exists but is above your access level — "
            + ", ".join(answer.restricted_documents)
            + ". This is different from the corpus having nothing on the subject."
        )]

    if answer.referenced_absent:
        lines += ["", (
            "Referenced but absent: "
            + ", ".join(answer.referenced_absent)
            + " — cited by other documents but not present in the corpus."
        )]

    if answer.available_instead and answer.outcome != ANSWERED:
        rows = ", ".join(
            f"{d['document_id']} ({d['document_type']})"
            for d in answer.available_instead[:8]
        )
        lines += ["", f"What the corpus does hold for this scope: {rows}"]

    if answer.citations:
        lines += ["", "Citations:"]
        for position, citation in enumerate(answer.citations, start=1):
            lines.append(
                f"  [{position}] {citation.get('document_id')} · "
                f"{citation.get('section', '?')} — {citation.get('supports', '')}"
            )

    if answer.invalid_citations:
        lines += ["", (
            "REJECTED CITATIONS (cited but never supplied): "
            + ", ".join(answer.invalid_citations)
        )]

    return "\n".join(lines)
