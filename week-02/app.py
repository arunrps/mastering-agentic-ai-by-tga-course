"""
app.py -- TriageLens Week 2: incident-context retrieval over the runbook corpus.

This file renders. It computes nothing. Every number, verdict and citation below
was produced by ingestion.py, embedding.py, retrieval.py or generation.py, none
of which import Streamlit -- the same boundary Week 1 established, running the
same direction.

LAYOUT CONTRACT: the deterministic state sits ABOVE the chat, always. What the
filter did, what was withheld and why, which outcome the gate produced -- those
are facts, they are computed by rules, and they do not move or become less
prominent because a conversation is happening underneath them. The chat is the
bonus surface. A page that puts the model's prose on top and the evidence
underneath has inverted the thing this project is about.

Run with:  streamlit run app.py
"""

import os

import streamlit as st

# ---------------------------------------------------------------------------
# Credentials -- BEFORE importing anything that builds an API client.
#
# Streamlit Cloud cannot read ~/llm-class/.env, and embedding.py must not import
# streamlit to go looking. So the bridge is here and it goes one way: lift the
# key out of st.secrets into the environment, which is the one channel both
# deployment targets share. Locally st.secrets is absent or empty and
# embedding.load_api_key() falls back to the dotfile on its own.
# ---------------------------------------------------------------------------

def _bridge_secret_to_env() -> str:
    """Copy NEBIUS_API_KEY from st.secrets into os.environ. Returns the source."""
    if os.environ.get("NEBIUS_API_KEY"):
        return "environment"
    try:
        key = st.secrets.get("NEBIUS_API_KEY")
    except Exception:
        # No secrets.toml at all locally -- st.secrets raises rather than
        # returning empty, so this is the normal local path, not an error.
        key = None
    if key:
        os.environ["NEBIUS_API_KEY"] = str(key)
        return "st.secrets"
    return "dotfile fallback"


KEY_SOURCE = _bridge_secret_to_env()

import embedding        # noqa: E402  -- must follow the secret bridge
import generation       # noqa: E402
import ingestion        # noqa: E402
import retrieval        # noqa: E402

COLOR_ELEVATED = "#DC2626"   # reserved for genuinely elevated states

st.set_page_config(
    page_title="TriageLens — Runbook Retrieval",
    layout="wide",
)


@st.cache_resource
def load_stack():
    """The corpus, the index and the retriever. Built once per process."""
    documents = ingestion.load_corpus()
    index = embedding.load_index()
    return documents, index, retrieval.Retriever(index)


@st.cache_data
def corpus_report():
    return ingestion.build_report(tokenizer=None)


st.title("TriageLens")
st.caption(
    "Incident-context retrieval over the platform's runbooks, policies and "
    "postmortems. Retrieval and policy are deterministic; only the answer "
    "wording is generated."
)

try:
    documents, index, retriever = load_stack()
except (ingestion.IngestionError, embedding.EmbeddingError) as error:
    st.error(f"Could not start:\n\n{error}")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar -- the context request. In the finished system the Week 1 detector
# supplies these from its verdict; here they are explicit controls so retrieval
# can be exercised before that wiring exists.
# ---------------------------------------------------------------------------

st.sidebar.header("Context request")
st.sidebar.caption(
    "Week 1's evidence gate produces a verdict naming the elevated "
    "endpoint × backend slice. That verdict becomes this request. Until the two "
    "are wired together, set it here."
)

services = sorted({d.service for d in documents if d.service != "platform"})
service = st.sidebar.selectbox(
    "Backend service", ["(no scope)"] + services,
    help="Platform-wide documents (policies, catalog) are always included.",
)
service = None if service == "(no scope)" else service

privileged = st.sidebar.checkbox(
    "Caller may read restricted documents", value=False,
    help="Off is the default. With it off, restricted guidance is withheld and "
         "named — never silently omitted.",
)
include_superseded = st.sidebar.checkbox(
    "Let superseded documents compete", value=False,
    help="Off by default. On, they are demoted below current documents rather "
         "than excluded — the status-filter demonstration.",
)
top_k = st.sidebar.slider("Passages to retrieve", 3, 12, 6)

st.sidebar.divider()
spent = embedding.total_spend()
st.sidebar.caption(
    f"**Spend to date** — {spent['calls']} calls · {spent['tokens']:,} tokens · "
    f"${spent['usd']:.6f}\n\nKey source: `{KEY_SOURCE}`"
)

# ---------------------------------------------------------------------------
# DETERMINISTIC STATE -- above the chat, always
# ---------------------------------------------------------------------------

st.subheader("Corpus state")

report = corpus_report()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Documents", len(documents))
col2.metric("Chunks indexed", index.vectors.shape[0])
col3.metric("Embedding dims", index.vectors.shape[1])
col4.metric("Restricted", sum(1 for d in documents if d.is_restricted))

absent = generation.referenced_but_absent(documents)
state_left, state_right = st.columns(2)
with state_left:
    if report["topology"].has_mismatch:
        st.warning("Topology cross-check: mismatches present.")
    else:
        st.success(
            "Topology cross-check — every declared `runbook_id` exists and every "
            "current runbook is declared."
        )
with state_right:
    if absent:
        st.warning(
            "**Referenced but absent:** " + ", ".join(absent)
            + " — cited by other documents, not present in the corpus."
        )
    else:
        st.success(
            f"Document references — {sum(len(d.links) for d in documents)} parsed "
            "as structured links, none dangling."
        )

st.caption(
    f"Index `{index.model}` · fingerprint `{index.fingerprint[:12]}` · "
    f"query latency is bounded by the embedding round trip "
    f"(measured 3.6–8.7 s); all local retrieval runs under 50 ms."
)

st.divider()

# ---------------------------------------------------------------------------
# CHAT -- below the deterministic state, never above
# ---------------------------------------------------------------------------

st.subheader("Ask the corpus")
st.caption(
    "Answers are built only from retrieved passages. Three refusals are kept "
    "distinct: not in the corpus · exists but above your access level · "
    "referenced but absent."
)

if "history" not in st.session_state:
    st.session_state.history = []

for entry in st.session_state.history:
    with st.chat_message("user"):
        st.write(entry["question"])
    with st.chat_message("assistant"):
        st.markdown(entry["rendered"])

question = st.chat_input("checkout throwing 503s, where do i start?")

if question:
    with st.chat_message("user"):
        st.write(question)

    request = retrieval.ContextRequest(
        question=question,
        service=service,
        statuses=("current", "superseded") if include_superseded else ("current",),
        access_level="restricted" if privileged else "operations",
        top_k=top_k,
    )

    with st.chat_message("assistant"):
        with st.spinner("Retrieving and grounding…"):
            try:
                answer, result = generation.answer_question(retriever, documents, request)
            except Exception as error:            # noqa: BLE001 -- surface it, don't swallow
                st.error(f"Generation failed: {error}")
                st.stop()

        # --- the deterministic verdict, first ---------------------------
        badge = {
            generation.ANSWERED: ("✅", "Answered"),
            generation.PARTIAL: ("◐", "Partial — the corpus covers part of this"),
            generation.RESTRICTED: ("🔒", "Refused — above your access level"),
            generation.NOT_IN_CORPUS: ("∅", "Refused — not in the corpus"),
        }[answer.outcome]
        st.markdown(f"**{badge[0]} {badge[1]}**")

        if answer.text:
            st.write(answer.text)

        if answer.not_covered:
            st.info(f"**Not covered:** {answer.not_covered}")

        if answer.restricted_documents:
            st.warning(
                "**Access:** relevant guidance exists but is above your access "
                f"level — {', '.join(answer.restricted_documents)}. This is a "
                "different answer from the corpus having nothing on the subject."
            )

        if answer.referenced_absent:
            st.warning(
                "**Referenced but absent:** "
                + ", ".join(answer.referenced_absent)
            )

        if answer.available_instead and answer.outcome != generation.ANSWERED:
            rows = ", ".join(
                f"`{d['document_id']}`" for d in answer.available_instead[:10]
            )
            st.caption(f"What the corpus does hold for this scope: {rows}")

        if answer.invalid_citations:
            st.error(
                "**Citations rejected by the validator** — the answer cited "
                f"{', '.join(answer.invalid_citations)}, which were never "
                "supplied to it. Removed from the citation list below."
            )

        if answer.citations:
            st.markdown("**Citations**")
            for position, citation in enumerate(answer.citations, start=1):
                st.markdown(
                    f"{position}. `{citation.get('document_id')}` · "
                    f"*{citation.get('section', '?')}* — "
                    f"{citation.get('supports', '')}"
                )

        with st.expander(
            f"Retrieval trace — {result.candidates_considered} of "
            f"{result.corpus_size} chunks passed the pre-filter"
        ):
            st.code(retrieval.describe_filter(result), language=None)
            st.code(retrieval.format_citations(result), language=None)

        st.caption(
            f"{answer.model} · {answer.input_tokens:,} in + "
            f"{answer.output_tokens:,} out tokens"
        )

    # Re-render on the next run from the stored markdown, so history does not
    # re-call the API.
    st.session_state.history.append({
        "question": question,
        "rendered": f"**{badge[0]} {badge[1]}**\n\n{answer.text}",
    })
