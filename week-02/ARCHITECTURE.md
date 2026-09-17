# Week 2 Architecture — TriageLens Runbook Retrieval

**Written:** 12 Sep 2026 · Describes the system as built, not as planned.

Every stage below names the file and the function that implements it. The constants quoted are the
values in the code, not targets.

---

## The pipeline

```mermaid
flowchart TD
    subgraph CORPUS["Corpus — 19 internal documents"]
        C1["corpus/internal/*.md<br/>RB-* runbooks · POL-* policies<br/>CAT-* catalog · PM-* postmortems<br/>114,540 chars on disk"]
        C2["topology.json<br/>declared endpoint → backend → runbook_id"]
    end

    subgraph INGEST["Ingestion — ingestion.py · never imports streamlit"]
        I1["parse_frontmatter()<br/>11 required fields<br/>missing or malformed = IngestionError, not a warning"]
        I2["_validate_metadata()<br/>value sets, document_id pattern,<br/>status ↔ superseded_by consistency"]
        I3["split_sections()<br/>split on ## headings<br/>untitled preamble kept as (overview)"]
        I4["merge_short_sections()<br/>sections under 350 chars<br/>merged forward, never stranded"]
        I5["pack_blocks()<br/>whole paragraph blocks only<br/>target 1,200 · hard cap 2,000 chars"]
        I6["parse_links()<br/>## Related documents → DocumentLink[]<br/>NEVER embedded as prose"]
        I7["cross_check_topology()<br/>cross_check_links()<br/>reported, never raised"]
    end

    subgraph EMBED["Embedding — embedding.py"]
        E1["fingerprint()<br/>SHA-256 over exact texts + model name"]
        E2{"cache hit?"}
        E3["embed_texts()<br/>Nebius Qwen/Qwen3-Embedding-8B<br/>4,096 dims · L2-normalised<br/>batch 32"]
        E4[(".index/vectors.npy<br/>106 × 4,096<br/>.index/manifest.json")]
        E5["record_spend()<br/>.index/spend.jsonl<br/>actual usage, never estimated"]
    end

    subgraph QUERY["Query side"]
        Q1["embed_query()<br/>asymmetric: queries carry the<br/>instruction prefix, documents do not"]
        Q2[(".index/query_vectors.npz<br/>gitignored runtime cache")]
    end

    subgraph RETRIEVE["Hybrid retrieval — retrieval.py · Retriever"]
        R1["ContextRequest<br/>service · statuses · access_level · top_k"]
        R2["_filter()<br/>METADATA PRE-FILTER<br/>service + platform · status=current<br/>access_level=operations<br/>exclusions RETURNED, not silent"]
        R3["_bm25_ranking()<br/>BM25Okapi over tokenize()<br/>keeps RB-PAY-000, /checkout, 5xx, p95 whole"]
        R4["_dense_ranking()<br/>cosine over L2-normalised vectors"]
        R5["_fuse()<br/>RECIPROCAL RANK FUSION k=60<br/>ranks only — no score normalisation"]
        R6["_rerank()<br/>DETERMINISTIC<br/>cap 2 chunks per document<br/>superseded demoted below current"]
    end

    subgraph GEN["Generation — generation.py"]
        G1["restricted_would_have_ranked()<br/>shadow retrieval, access filter lifted<br/>same query vector = zero extra tokens"]
        G2["referenced_but_absent()<br/>link graph vs documents on disk"]
        G3["available_documents()<br/>what the corpus DOES hold<br/>restricted excluded from this list"]
        G4["answer_question()<br/>openai/gpt-oss-120b · temp 0.1<br/>passages only, JSON contract"]
        G5["CITATION VALIDATOR<br/>every cited document_id must be<br/>in the supplied set, else stripped<br/>and reported"]
    end

    subgraph OUT["Four outcomes — format_answer()"]
        O1["ANSWERED<br/>passages fully support it"]
        O2["PARTIAL<br/>answers what it can AND<br/>names what is not covered"]
        O3["REFUSED — not in corpus<br/>+ what the corpus does hold"]
        O4["REFUSED — above your access level<br/>names POL-DEPLOY-001 as existing,<br/>never its contents"]
        O5["REFERENCED BUT ABSENT<br/>wired; currently empty —<br/>all 104 references resolve"]
    end

    C1 --> I1 --> I2 --> I3 --> I4 --> I5
    C1 --> I6
    C2 --> I7
    I2 --> I7
    I6 --> I7
    I6 -.->|structured links, not vectors| G2

    I5 -->|"106 chunks<br/>min 358 · median 881 · max 1,855 chars<br/>23,309 tokens"| E1
    E1 --> E2
    E2 -->|miss: spends credit| E3 --> E4
    E3 --> E5
    E2 -->|hit: free| E4

    E4 --> R1
    Q1 --> Q2
    Q1 --> R4
    R1 --> R2
    R2 -->|"candidates only"| R3
    R2 --> R4
    R3 --> R5
    R4 --> R5
    R5 --> R6

    R2 -.->|withheld list| G1
    R6 -->|"top-k passages"| G4
    G1 --> G4
    G3 --> G4
    G4 --> G5

    G5 --> O1
    G5 --> O2
    G5 --> O3
    G1 ==>|"overrides a not-in-corpus verdict"| O4
    G2 --> O5

    classDef det fill:#E8F0FE,stroke:#2563EB,stroke-width:2px,color:#172033
    classDef prob fill:#FEF3E8,stroke:#EB6834,stroke-width:2px,color:#172033
    classDef store fill:#FFFFFF,stroke:#898781,stroke-dasharray:4 3,color:#172033
    classDef refuse fill:#FDECEC,stroke:#DC2626,stroke-width:2px,color:#172033
    classDef answer fill:#ECF7EE,stroke:#2F8F46,stroke-width:2px,color:#172033

    class I1,I2,I3,I4,I5,I6,I7,E1,E2,E5,R1,R2,R3,R4,R5,R6,G1,G2,G3,G5 det
    class G4,Q1,E3 prob
    class C1,C2,E4,Q2 store
    class O3,O4,O5 refuse
    class O1,O2 answer
```

**Blue = deterministic code.** **Orange = a model call.** **Dashed = storage.** **Green = an answered outcome.** **Red = a refusal path.**

The only probabilistic steps are the two embedding calls and the single generation call. Every
filter, every ranking, every fusion, every validation and every refusal type is decided by code.

---

## Stage by stage

| Stage | File | Entry point | What it produces |
|---|---|---|---|
| Corpus | `corpus/internal/*.md`, `topology.json` | — | 19 documents, 114,540 chars |
| Frontmatter parse + validate | `ingestion.py` | `parse_frontmatter()`, `_validate_metadata()` | validated metadata, or `IngestionError` |
| Section-aware chunking | `ingestion.py` | `split_sections()` → `merge_short_sections()` → `pack_blocks()` | 106 `Chunk` objects |
| Link extraction | `ingestion.py` | `parse_links()` | `DocumentLink[]`, never embedded |
| Cross-checks | `ingestion.py` | `cross_check_topology()`, `cross_check_links()` | reported, never raised |
| Embedding + cache | `embedding.py` | `build_index()` / `load_index()` | `.index/vectors.npy`, `.index/manifest.json` |
| Spend ledger | `embedding.py` | `record_spend()` | `.index/spend.jsonl` |
| Query embedding | `embedding.py` | `embed_query()` | one 4,096-dim vector, cached |
| Metadata pre-filter | `retrieval.py` | `Retriever._filter()` | candidate positions + exclusion lists |
| Lexical arm | `retrieval.py` | `Retriever._bm25_ranking()` | ranked positions |
| Dense arm | `retrieval.py` | `Retriever._dense_ranking()` | ranked positions |
| Fusion | `retrieval.py` | `Retriever._fuse()` | RRF scores, k=60 |
| Deterministic rerank | `retrieval.py` | `Retriever._rerank()` | top-k, per-document capped |
| Restricted detection | `generation.py` | `restricted_would_have_ranked()` | which restricted docs would have ranked |
| Generation | `generation.py` | `answer_question()` | JSON brief |
| Citation validation | `generation.py` | inside `answer_question()` | validated citations + rejected list |
| Rendering | `generation.py`, `app.py` | `format_answer()` | the four outcomes |

---

## The three boundaries the diagram is drawn to show

**1. `ingestion.py`, `embedding.py`, `retrieval.py` and `generation.py` never import Streamlit.**
`app.py` renders and computes nothing. The key crosses that boundary in one direction only —
`app.py` lifts `NEBIUS_API_KEY` from `st.secrets` into `os.environ` before importing
`embedding`, because the environment is the one channel both local and Streamlit Cloud share.

**2. `## Related documents` leaves the prose path entirely.** It is parsed to structured links and
is never embedded. It feeds the dangling-reference check, not the vector index.

**3. The restricted refusal is decided before the model is called and overrides its verdict.**
The model never sees a restricted passage, so it cannot know one was withheld. Only the filter
knows, so only code can say it — which is why `restricted_would_have_ranked()` sits outside the
generation call and why its edge into `REFUSED — above your access level` is the heavy one.

---

## Constants, as implemented

| Constant | Value | Where |
|---|---|---|
| `TARGET_CHUNK_CHARS` | 1,200 | `ingestion.py` |
| `MAX_CHUNK_CHARS` | 2,000 | `ingestion.py` |
| `MIN_SECTION_CHARS` | 350 | `ingestion.py` |
| `EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-8B` | `ingestion.py` |
| `EMBEDDING_DIMENSIONS` | 4,096 (measured, not documented) | `ingestion.py` |
| `EMBEDDING_CONTEXT_TOKENS` | 32,768 | `ingestion.py` |
| `BATCH_SIZE` | 32 | `embedding.py` |
| RRF `k` | 60 | `retrieval.py._fuse()` |
| `max_chunks_per_document` | 2 | `retrieval.ContextRequest` |
| default `top_k` | 6 | `retrieval.ContextRequest` |
| `GENERATION_MODEL` | `openai/gpt-oss-120b` | `generation.py` |
| `TEMPERATURE` | 0.1 | `generation.py` |
| `MAX_OUTPUT_TOKENS` | 2,500 | `generation.py` |
