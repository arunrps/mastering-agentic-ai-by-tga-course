"""
embedding.py -- Nebius embedding client and the on-disk vector cache.

NEVER imports streamlit. Same boundary as ingestion.py and week-01's detection.py.

Two things this module is careful about, both because they cost real money:

1. **Nothing is embedded twice.** The cache is keyed on a content hash of the
   exact texts sent to the API plus the model name. Re-running is free unless the
   chunks or the model actually changed, and when they have changed the manifest
   says which.

2. **Every call reports what it spent.** The API returns a usage block; it is
   recorded rather than estimated, because an estimate of spend is the same class
   of mistake as an estimate of token count presented as a measurement.

Run `python embedding.py --estimate` to see the cost of the next run without
making a call. Run `python embedding.py --embed` to actually spend.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import ingestion

# ---------------------------------------------------------------------------
# Endpoint and model
#
# Verified against the live account on 11 Sep 2026 rather than read off a
# catalogue page. BAAI/bge-en-icl returns 404 on BOTH api.studio.nebius.com and
# api.tokenfactory.nebius.com -- it is not deployed for this account, whatever
# the public model list shows. Qwen3-Embedding-8B is the only embedding model
# the /models endpoint returns, and EMBEDDING_DIMENSIONS in ingestion.py is the
# measured len(response.data[0].embedding), not a documented number.
# ---------------------------------------------------------------------------

NEBIUS_BASE_URL = "https://api.studio.nebius.com/v1/"

MODEL = ingestion.EMBEDDING_MODEL
DIMENSIONS = ingestion.EMBEDDING_DIMENSIONS

# Qwen3-Embedding is an instruction-tuned asymmetric encoder: queries carry a
# task instruction, documents do not. Skipping this costs real retrieval
# quality, and it is invisible when skipped -- results are merely worse, never
# wrong-looking. The task string is part of the index contract: change it and
# queries stop matching documents embedded under the old one.
QUERY_INSTRUCTION = (
    "Given an incident symptom or an on-call question, retrieve the runbook, "
    "policy or postmortem passage that says what to check"
)

# Nebius accepts batched input. 32 keeps each request well inside any payload
# limit while cutting round trips by an order of magnitude.
BATCH_SIZE = 32

# Published rate for the embedding tier, used ONLY for the pre-run estimate.
# Actual spend is always read back from the API's usage block.
USD_PER_MILLION_TOKENS = 0.01

CACHE_DIR = ingestion.WEEK_02 / ".index"
VECTORS_FILE = CACHE_DIR / "vectors.npy"
MANIFEST_FILE = CACHE_DIR / "manifest.json"
SPEND_LOG = CACHE_DIR / "spend.jsonl"


class EmbeddingError(Exception):
    """Raised when the index cannot be built or loaded safely."""


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def load_api_key() -> str:
    """The Nebius key, from the environment or from ~/llm-class/.env.

    Streamlit Cloud cannot read a local dotfile, so the deployed app sets the
    key as an environment variable via st.secrets before importing this module.
    The env var is therefore checked FIRST and the dotfile is the local
    convenience fallback, not the other way round.
    """
    key = os.environ.get("NEBIUS_API_KEY")
    if key:
        return key

    dotenv = Path.home() / "llm-class" / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("NEBIUS_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    raise EmbeddingError(
        "NEBIUS_API_KEY not found. Set it in the environment, or add it to "
        "~/llm-class/.env for local runs."
    )


def _client():
    from openai import OpenAI

    return OpenAI(base_url=NEBIUS_BASE_URL, api_key=load_api_key(), timeout=120)


# ---------------------------------------------------------------------------
# Cache identity
# ---------------------------------------------------------------------------


def fingerprint(texts: Sequence, model: str = MODEL) -> str:
    """Identity of an embedding run: the exact texts, in order, plus the model.

    Any change to chunking, to a corpus document, or to the model produces a
    different fingerprint and the cache misses. Nothing else does -- so a
    comment edit in this file, or a new field on the Chunk dataclass, does not
    silently trigger a paid re-run.
    """
    digest = hashlib.sha256()
    digest.update(model.encode("utf-8"))
    for text in texts:
        digest.update(b"\x00")
        digest.update(text.encode("utf-8"))
    return digest.hexdigest()


@dataclass
class Index:
    """Chunks plus their vectors, guaranteed to correspond by position."""

    chunks: list
    vectors: np.ndarray
    model: str
    fingerprint: str

    def __post_init__(self):
        if len(self.chunks) != self.vectors.shape[0]:
            raise EmbeddingError(
                f"index is inconsistent: {len(self.chunks)} chunks but "
                f"{self.vectors.shape[0]} vectors."
            )


# ---------------------------------------------------------------------------
# Spend
# ---------------------------------------------------------------------------


def record_spend(operation: str, model: str, tokens: int, note: str = "") -> dict:
    """Append one line to the spend log. Actual usage, never an estimate.

    Never raises. On Streamlit Community Cloud the container filesystem can be
    read-only, and an accounting write must not be able to fail a request that
    already succeeded. The spend log serves the local build loop; the API's own
    usage block is the record either way.
    """
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "operation": operation,
        "model": model,
        "tokens": tokens,
        "usd": round(tokens / 1_000_000 * USD_PER_MILLION_TOKENS, 8),
        "note": note,
    }
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with SPEND_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return entry


def total_spend() -> dict:
    """Everything spent so far, read back from the log."""
    if not SPEND_LOG.is_file():
        return {"calls": 0, "tokens": 0, "usd": 0.0}
    tokens = 0
    usd = 0.0
    calls = 0
    for line in SPEND_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        calls += 1
        tokens += entry["tokens"]
        usd += entry["usd"]
    return {"calls": calls, "tokens": tokens, "usd": round(usd, 8)}


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


def embed_texts(texts: Sequence, model: str = MODEL, operation: str = "embed") -> tuple:
    """Embed a list of texts. Returns (vectors, tokens_used).

    Vectors come back L2-normalised, so a dot product IS cosine similarity and
    the retrieval layer never has to remember to normalise.
    """
    client = _client()
    vectors = []
    tokens = 0

    for start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[start:start + BATCH_SIZE])
        response = client.embeddings.create(model=model, input=batch)
        # The API is documented to return data in input order, but the objects
        # carry an index and relying on documented ordering is how an index
        # silently misaligns with its chunks. Sort explicitly.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)
        if response.usage:
            tokens += response.usage.total_tokens

    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix /= norms

    record_spend(operation, model, tokens, note=f"{len(texts)} texts")
    return matrix, tokens


QUERY_CACHE_FILE = CACHE_DIR / "query_vectors.npz"


def embed_query(query: str, model: str = MODEL, use_cache: bool = True) -> np.ndarray:
    """Embed one query, with the instruction prefix documents do not get.

    Cached on disk, keyed by the exact instructed text. This is worth being
    honest about: the cache makes repeated questions and evaluation re-runs
    free and instant, and it does nothing at all for a first-time question --
    which is the case that matters for the latency ceiling. It is a demo and
    harness convenience, not a fix for the 3.6-8.7 second round trip.
    """
    text = f"Instruct: {QUERY_INSTRUCTION}\nQuery: {query}"
    key = hashlib.sha256(f"{model}\x00{text}".encode("utf-8")).hexdigest()

    if use_cache and QUERY_CACHE_FILE.is_file():
        with np.load(QUERY_CACHE_FILE) as cached:
            if key in cached:
                return cached[key]

    vectors, _ = embed_texts([text], model=model, operation="query")
    vector = vectors[0]

    if use_cache:
        # Same reasoning as record_spend: a cache write failing on a read-only
        # deploy filesystem must not fail a query that already has its answer.
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            existing = {}
            if QUERY_CACHE_FILE.is_file():
                with np.load(QUERY_CACHE_FILE) as cached:
                    existing = {k: cached[k] for k in cached.files}
            existing[key] = vector
            np.savez(QUERY_CACHE_FILE, **existing)
        except OSError:
            pass

    return vector


def estimate(chunks: Optional[Sequence] = None) -> dict:
    """What the next embedding run would cost, without making a call."""
    chunks = chunks if chunks is not None else ingestion.chunk_corpus(ingestion.load_corpus())
    texts = [c.embed_text for c in chunks]
    tokenizer = ingestion.get_tokenizer()
    counts = ingestion.count_tokens(texts, tokenizer)
    if counts is None:
        raise EmbeddingError(
            "No tokenizer available, so no honest estimate can be made. Run "
            "`python ingestion.py --fetch-tokenizer` first."
        )
    tokens = sum(counts)
    return {
        "chunks": len(chunks),
        "tokens": tokens,
        "usd": tokens / 1_000_000 * USD_PER_MILLION_TOKENS,
        "model": MODEL,
        "fingerprint": fingerprint(texts),
    }


def build_index(force: bool = False) -> Index:
    """Load the cached index, or build it -- which costs money.

    The cache hit is the normal path. A miss happens only when the chunks or
    the model changed, and the manifest records which fingerprint produced the
    vectors on disk so a mismatch can be explained rather than just obeyed.
    """
    documents = ingestion.load_corpus()
    chunks = ingestion.chunk_corpus(documents)
    texts = [c.embed_text for c in chunks]
    current = fingerprint(texts)

    if not force and VECTORS_FILE.is_file() and MANIFEST_FILE.is_file():
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        if manifest.get("fingerprint") == current and manifest.get("model") == MODEL:
            vectors = np.load(VECTORS_FILE)
            return Index(chunks=chunks, vectors=vectors, model=MODEL, fingerprint=current)

    vectors, tokens = embed_texts(texts, operation="embed_corpus")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(VECTORS_FILE, vectors)
    MANIFEST_FILE.write_text(json.dumps({
        "model": MODEL,
        "dimensions": int(vectors.shape[1]),
        "chunks": len(chunks),
        "fingerprint": current,
        "tokens_billed": tokens,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "query_instruction": QUERY_INSTRUCTION,
        "chunk_ids": [c.chunk_id for c in chunks],
    }, indent=2), encoding="utf-8")

    return Index(chunks=chunks, vectors=vectors, model=MODEL, fingerprint=current)


def load_index() -> Index:
    """The cached index. Raises rather than silently spending money."""
    if not (VECTORS_FILE.is_file() and MANIFEST_FILE.is_file()):
        raise EmbeddingError(
            "No index on disk. Run `python embedding.py --embed` to build one "
            "(this spends credit)."
        )
    documents = ingestion.load_corpus()
    chunks = ingestion.chunk_corpus(documents)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    current = fingerprint([c.embed_text for c in chunks])
    if manifest.get("fingerprint") != current:
        raise EmbeddingError(
            "The corpus or the chunking changed since the index was built, so "
            "the cached vectors no longer describe these chunks. Re-embed with "
            "`python embedding.py --embed` (this spends credit)."
        )
    return Index(chunks=chunks, vectors=np.load(VECTORS_FILE),
                 model=manifest["model"], fingerprint=current)


def main(argv: Optional[Sequence] = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    figures = estimate()

    print(f"model:       {figures['model']}")
    print(f"chunks:      {figures['chunks']}")
    print(f"tokens:      {figures['tokens']:,}")
    print(f"estimated:   ${figures['usd']:.6f}")
    print(f"fingerprint: {figures['fingerprint'][:16]}")

    spent = total_spend()
    print(f"\nspent to date: {spent['calls']} calls, {spent['tokens']:,} tokens, "
          f"${spent['usd']:.6f}")

    if "--embed" not in argv:
        print("\n(estimate only -- pass --embed to spend)")
        return 0

    print("\nembedding...")
    index = build_index(force="--force" in argv)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    print(f"index: {index.vectors.shape[0]} vectors x {index.vectors.shape[1]} dims")
    print(f"tokens billed: {manifest['tokens_billed']:,}")
    spent = total_spend()
    print(f"spent to date: {spent['calls']} calls, {spent['tokens']:,} tokens, "
          f"${spent['usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
